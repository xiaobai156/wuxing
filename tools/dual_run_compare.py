from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import wuxing_crawler as legacy  # noqa: E402

from cli.common import build_runtime  # noqa: E402
from wuxing.domain.enums import WritePolicy  # noqa: E402
from wuxing.domain.models import ScrapeRequest  # noqa: E402


def run_one(runtime, name: str, period: int, timeout: int) -> dict[str, object]:
    site = next(site for site in runtime.sites if site.name == name)
    new_result = runtime.scrape_service.scrape(
        site.site_id,
        ScrapeRequest(periods=(period,), timeout_seconds=timeout, write_policy=WritePolicy.READ_ONLY),
    )
    legacy_site = legacy.Site(site.url, site.region.value, site.click_first, site.name, site.api_url)
    started = time.monotonic()
    try:
        lines, error, _documents = legacy.scrape_site_detailed(
            legacy_site,
            1,
            timeout,
            False,
            period,
        )
        old_wuxing = legacy.line_wuxing_value(lines[0]) if lines else None
        old_status = bool(lines)
        old_reason = error or ""
    except Exception as exc:
        old_wuxing = None
        old_status = False
        old_reason = f"{type(exc).__name__}: {exc}"
    row = {
        "name": name,
        "url": site.url,
        "period": period,
        "new_status": new_result.status.value,
        "new_wuxing": new_result.candidate.wuxing if new_result.candidate else None,
        "new_reason": new_result.reason or (new_result.failure_code.value if new_result.failure_code else ""),
        "new_elapsed_seconds": round(new_result.elapsed_seconds, 3),
        "old_status": "success" if old_status else "failure",
        "old_wuxing": old_wuxing,
        "old_reason": old_reason,
        "old_elapsed_seconds": round(time.monotonic() - started, 3),
    }
    row["same_result"] = (
        row["new_status"] == row["old_status"]
        and row["new_wuxing"] == row["old_wuxing"]
    )
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description="修复版2与冻结旧版只读逐站对照")
    parser.add_argument("--period", type=int, default=211)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--name", action="append", dest="names")
    parser.add_argument("--all", action="store_true", help="逐站对照全部正式目录")
    parser.add_argument("--offset", type=int, default=0, help="全量清单的起始位置，配合 --all 分批执行")
    parser.add_argument("--limit", type=int, help="全量清单本批数量，配合 --all 分批执行")
    parser.add_argument("--workers", type=int, default=1, help="只读对照并发数，默认1，浏览器站点建议不超过2")
    parser.add_argument("--output", type=Path, help="本批 JSON 报告路径")
    args = parser.parse_args()
    if args.offset < 0:
        parser.error("--offset 不能小于0")
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit 必须大于0")
    if args.workers <= 0:
        parser.error("--workers 必须大于0")
    runtime = build_runtime()
    if args.all and args.names:
        parser.error("--all 不能与 --name 同时使用")
    all_names = (
        tuple(site.name for site in runtime.sites)
        if args.all
        else tuple(args.names or ("典则俊雅", "齐天大胜", "财富沟通", "后继有人", "轰动大陆"))
    )
    if not args.all and (args.offset or args.limit is not None):
        parser.error("--offset/--limit 只能与 --all 一起使用")
    names = all_names[args.offset:args.offset + args.limit if args.limit is not None else None]
    if not names:
        parser.error("本批没有可执行的目录")

    def compare(name: str) -> dict[str, object]:
        try:
            return run_one(runtime, name, args.period, args.timeout)
        except Exception as exc:
            return {"name": name, "error": f"{type(exc).__name__}: {exc}", "same_result": False}

    rows_by_name: dict[str, dict[str, object]] = {}
    started = time.monotonic()
    worker_count = min(args.workers, len(names))
    if worker_count == 1:
        for index, name in enumerate(names, 1):
            rows_by_name[name] = compare(name)
            print(f"[双跑 {index}/{len(names)}] {name}", flush=True)
    else:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {executor.submit(compare, name): name for name in names}
            for index, future in enumerate(as_completed(futures), 1):
                name = futures[future]
                rows_by_name[name] = future.result()
                print(f"[双跑 {index}/{len(names)}] {name}", flush=True)
    rows = [rows_by_name[name] for name in names]
    report = {
        "period": args.period,
        "cache_written": False,
        "formal_txt_written": False,
        "offset": args.offset,
        "limit": args.limit,
        "workers": worker_count,
        "complete": len(rows) == len(names),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "names": list(names),
        "rows": rows,
        "same_count": sum(1 for row in rows if row.get("same_result")),
        "difference_count": sum(1 for row in rows if not row.get("same_result")),
    }
    output = args.output or (ROOT / "migration" / "dual-run-report.json")
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8-sig")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["difference_count"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
