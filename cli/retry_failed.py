from __future__ import annotations

import argparse
import hashlib
import os
import re
import tempfile
from pathlib import Path

from wuxing.domain.enums import ResultStatus, WritePolicy
from wuxing.domain.models import ScrapeRequest
from wuxing.reporting.success import format_success_line
from wuxing.services.batch import BatchService
from wuxing.storage.file_lock import exclusive_file_lock

from .common import DEFAULT_SUCCESS_DIR, append_success_lines, build_runtime


_RECORD_START = re.compile(r"^\s*失败(?:\s|$)")
_MARKDOWN_HEADER = re.compile(
    r"^\s*失败\s+(?P<name>[^\[]+?)\s+\[(?P<url>https?://[^\]]+)\]"
    r"\([^)]*\)\s+方向:\s*(?P<region>top|bottom)\s+期数:\s*0*(?P<period>\d+)\s*$"
)
_PLAIN_HEADER = re.compile(
    r"^\s*失败\s+(?P<name>.+?)\s+(?P<url>https?://\S+)\s+方向:\s*"
    r"(?P<region>top|bottom)\s+期数:\s*0*(?P<period>\d+)\s*$"
)


def _identity(record: dict[str, object]) -> tuple[str, str, str, int]:
    return (
        str(record["name"]),
        str(record["url"]),
        str(record["region"]),
        int(record["period"]),
    )


def _parse_text(text: str, path: Path) -> list[dict[str, object]]:
    lines = text.splitlines(keepends=True)
    summary = next(
        (index for index, line in enumerate(lines) if line.lstrip().startswith("失败分类")),
        len(lines),
    )
    starts = [
        index
        for index, line in enumerate(lines[:summary])
        if _RECORD_START.match(line)
    ]
    records: list[dict[str, object]] = []
    for ordinal, start in enumerate(starts):
        header = lines[start].rstrip("\r\n")
        match = _MARKDOWN_HEADER.match(header) or _PLAIN_HEADER.match(header)
        if match is None:
            raise ValueError(f"失败记录格式无法识别：第 {start + 1} 行")
        data = match.groupdict()
        records.append(
            {
                "ordinal": ordinal,
                "start": start,
                "end": starts[ordinal + 1] if ordinal + 1 < len(starts) else summary,
                "name": data["name"].strip(),
                "url": data["url"],
                "region": data["region"],
                "period": int(data["period"]),
            }
        )
    if not records:
        raise ValueError(f"失败 TXT 没有可处理记录：{path}")
    periods = {int(record["period"]) for record in records}
    if len(periods) != 1:
        raise ValueError(f"失败 TXT 包含多个期数，拒绝混跑：{sorted(periods)}")
    return records


def _read_snapshot(path: Path) -> tuple[bytes, list[dict[str, object]]]:
    raw = path.read_bytes()
    return raw, _parse_text(raw.decode("utf-8-sig"), path)


def load_failure_records(path: str | Path) -> tuple[dict[str, object], ...]:
    _, records = _read_snapshot(Path(path))
    unique: list[dict[str, object]] = []
    seen: set[tuple[str, str, str, int]] = set()
    for record in records:
        key = _identity(record)
        if key in seen:
            continue
        seen.add(key)
        unique.append({key: record[key] for key in ("name", "url", "region", "period")})
    return tuple(unique)


def resolve_sites(records, runtime):
    selected = []
    for record in records:
        matches = [
            site
            for site in runtime.sites
            if site.name == record["name"]
            and site.url == record["url"]
            and site.region.value == record["region"]
        ]
        if len(matches) != 1:
            raise ValueError(f"失败记录无法唯一匹配正式站点：{record['name']}")
        selected.append((record, matches[0]))
    return tuple(selected)


def _hash_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _atomic_write(path: Path, payload: str) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8-sig",
            newline="",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _remove_records(
    path: Path,
    identity: tuple[str, str, str, int],
    expected: str,
) -> str:
    with exclusive_file_lock(path):
        raw, records = _read_snapshot(path)
        if _hash_bytes(raw) != expected:
            raise RuntimeError("失败 TXT 在处理期间发生变化，已停止写入以保护新增记录")
        matched = [record for record in records if _identity(record) == identity]
        if not matched:
            raise RuntimeError("失败记录已被外部修改，已停止写入")

        lines = raw.decode("utf-8-sig").splitlines(keepends=True)
        removed = {_identity(record) for record in matched}
        remaining = [
            record for record in records if _identity(record) not in removed
        ]
        payload = "" if not remaining else "".join(
            "".join(lines[record["start"] : record["end"]])
            for record in remaining
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(path, payload)
    return _hash_bytes(path.read_bytes())


def retry_failed(
    failure_path,
    output_dir=DEFAULT_SUCCESS_DIR,
    timeout_seconds=20,
    config_path=None,
    cache_path=None,
) -> int:
    path = Path(failure_path)
    raw, records = _read_snapshot(path)
    expected = _hash_bytes(raw)
    runtime = build_runtime(config_path, cache_path)
    selected = resolve_sites(records, runtime)
    period = int(records[0]["period"])
    service = BatchService(runtime.scrape_service)
    validation_request = ScrapeRequest(
        periods=(period,),
        timeout_seconds=timeout_seconds,
        write_policy=WritePolicy.READ_ONLY,
    )
    submit_request = ScrapeRequest(
        periods=(period,),
        timeout_seconds=timeout_seconds,
        write_policy=WritePolicy.UPDATE_CACHE,
    )
    successful_records = 0
    seen: set[tuple[str, str, str, int]] = set()

    for record, site in selected:
        identity = _identity(record)
        if identity in seen:
            continue
        seen.add(identity)
        print(f"[验证] {site.name} | {period}期", flush=True)
        validation_results = service.run(
            (site.site_id,), validation_request, max_workers=1
        ).results
        if len(validation_results) != 1:
            raise RuntimeError(f"{site.name} 验证未返回唯一结果")
        validation = validation_results[0]
        if validation.status is not ResultStatus.SUCCESS:
            print(f"{site.name} 验证失败：{validation.reason}")
            continue

        rerun_results = service.run(
            (site.site_id,), validation_request, max_workers=1
        ).results
        if len(rerun_results) != 1:
            raise RuntimeError(f"{site.name} 重抓未返回唯一结果")
        result = rerun_results[0]
        if result.status is not ResultStatus.SUCCESS:
            print(f"{site.name} 重抓失败：{result.reason}")
            continue

        report = runtime.scrape_service.update_cache((result,), submit_request)
        reason = report.errors or getattr(report, "skipped_reason", None)
        if reason or report.updated_sites != 1:
            print(f"{site.name} 缓存更新未完成：{reason or '未更新任何站点'}")
            continue

        append_success_lines(
            Path(output_dir) / f"{period}期-五行.txt",
            [format_success_line(result)],
        )
        expected = _remove_records(path, identity, expected)
        successful_records += sum(1 for item in records if _identity(item) == identity)
        print(f"{site.name} 已更新：{result.candidate.wuxing}", flush=True)

    remaining = len(records) - successful_records
    print(f"处理完成：成功 {successful_records}，保留失败 {remaining}")
    return 0 if remaining == 0 else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description="只读取失败 TXT 并定向重抓失败站点")
    parser.add_argument("failure_txt")
    parser.add_argument("--output", default=str(DEFAULT_SUCCESS_DIR))
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--config")
    parser.add_argument("--cache")
    args = parser.parse_args(argv)
    try:
        return retry_failed(
            args.failure_txt,
            args.output,
            args.timeout,
            args.config,
            args.cache,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
