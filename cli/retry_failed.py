from __future__ import annotations

import argparse
import os
import re
import tempfile
from pathlib import Path

from wuxing.domain.enums import ResultStatus, WritePolicy
from wuxing.domain.models import ScrapeRequest
from wuxing.reporting.failure import format_failure_file_text, format_failure_line
from wuxing.reporting.success import format_success_file_lines
from wuxing.services.batch import BatchService

from .common import (
    DEFAULT_FAILURE_DIR,
    DEFAULT_SUCCESS_DIR,
    RANKING_EXCLUDED_NAMES,
    append_success_lines,
    build_runtime,
)


_FAILURE_RE = re.compile(
    r"失败\s+(?P<name>[^\[]+?)\s+\[(?P<url>https?://[^\]]+)\]\([^)]*\)"
    r"\s+方向:\s*(?P<region>top|bottom)\s+期数:\s*(?P<period>\d+)"
)
_PLAIN_FAILURE_RE = re.compile(
    r"失败\s+(?P<name>\S+)\s+(?P<url>https?://\S+)\s+方向:\s*"
    r"(?P<region>top|bottom)\s+期数:\s*(?P<period>\d+)"
)


def load_failure_records(path: str | Path) -> tuple[dict[str, object], ...]:
    text = Path(path).read_text(encoding="utf-8-sig")
    records: list[dict[str, object]] = []
    seen: set[tuple[str, str, str, int]] = set()
    for pattern in (_FAILURE_RE, _PLAIN_FAILURE_RE):
        for match in pattern.finditer(text):
            item = match.groupdict()
            record = (item["name"].strip(), item["url"], item["region"], int(item["period"]))
            if record not in seen:
                seen.add(record)
                records.append({"name": record[0], "url": record[1], "region": record[2], "period": record[3]})
    if not records:
        raise ValueError(f"失败 TXT 没有可处理记录：{path}")
    periods = {int(item["period"]) for item in records}
    if len(periods) != 1:
        raise ValueError(f"失败 TXT 包含多个期数，拒绝混跑：{sorted(periods)}")
    return tuple(records)


def resolve_sites(records: tuple[dict[str, object], ...], runtime):
    selected = []
    for item in records:
        matches = [
            site for site in runtime.sites
            if site.name == item["name"] and site.url == item["url"]
            and site.region.value == item["region"]
        ]
        if len(matches) != 1:
            raise ValueError(f"失败记录无法唯一匹配正式站点：{item['name']}")
        selected.append((item, matches[0]))
    return tuple(selected)


def _rewrite_failures(path: Path, remaining: list, original: str) -> None:
    if not remaining:
        path.write_text("", encoding="utf-8-sig")
        return
    keep = []
    for block in original.replace("\r\n", "\n").split("\n\n"):
        if any(
            block.startswith(f"失败 {item['name']} ")
            and f"期数: {item['period']}" in block
            for item in remaining
        ):
            keep.append(block)
    payload = "\n\n".join(keep) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8-sig", newline="", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, path)


def retry_failed(
    failure_path: str | Path,
    output_dir: str | Path = DEFAULT_SUCCESS_DIR,
    timeout_seconds: int = 20,
    config_path: str | Path | None = None,
    cache_path: str | Path | None = None,
) -> int:
    failure_path = Path(failure_path)
    original = failure_path.read_text(encoding="utf-8-sig")
    records = load_failure_records(failure_path)
    runtime = build_runtime(config_path, cache_path)
    selected = resolve_sites(records, runtime)
    period = int(records[0]["period"])
    remaining = list(records)
    request = ScrapeRequest(periods=(period,), timeout_seconds=timeout_seconds, write_policy=WritePolicy.UPDATE_CACHE)
    for index, (record, site) in enumerate(selected, start=1):
        print(f"[验证 {index}/{len(selected)}] {site.name} | {period}期", flush=True)
        validation = BatchService(runtime.scrape_service).run((site.site_id,), request, max_workers=1)
        validated = validation.results[0]
        if validated.status is not ResultStatus.SUCCESS:
            print(f"{site.name} 验证失败：{validated.reason}")
            continue
        rerun = BatchService(runtime.scrape_service).run((site.site_id,), request, max_workers=1)
        result = rerun.results[0]
        if result.status is not ResultStatus.SUCCESS:
            print(f"{site.name} 正式重跑失败：{result.reason}")
            continue
        report = runtime.scrape_service.update_cache((result,), request)
        if report.errors or report.skipped_reason or report.updated_sites != 1:
            print(f"{site.name} 缓存更新未完成：{report.errors or report.skipped_reason}")
            continue
        append_success_lines(Path(output_dir) / f"{period}期-五行.txt", format_success_file_lines((result,), RANKING_EXCLUDED_NAMES))
        remaining = [item for item in remaining if item != record]
        print(f"{site.name} 通过并已更新：{result.candidate.wuxing}", flush=True)
    _rewrite_failures(failure_path, remaining, original)
    print(f"处理完成：成功 {len(records) - len(remaining)}，保留失败 {len(remaining)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="只读取失败 TXT 并定向重抓失败站点")
    parser.add_argument("failure_txt")
    parser.add_argument("--output", default=str(DEFAULT_SUCCESS_DIR))
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--config")
    parser.add_argument("--cache")
    args = parser.parse_args(argv)
    return retry_failed(args.failure_txt, args.output, args.timeout, args.config, args.cache)


if __name__ == "__main__":
    raise SystemExit(main())
