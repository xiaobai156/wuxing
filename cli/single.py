from __future__ import annotations

import argparse
from pathlib import Path

from wuxing.domain.enums import WritePolicy
from wuxing.domain.models import ScrapeRequest
from wuxing.reporting.failure import format_failure_file_text
from wuxing.reporting.progress import format_progress
from wuxing.reporting.success import format_success_file_lines
from wuxing.services.batch import BatchService

from .common import (
    DEFAULT_FAILURE_DIR,
    DEFAULT_SUCCESS_DIR,
    RANKING_EXCLUDED_NAMES,
    build_runtime,
    write_text,
)


def run_single(
    period: int,
    runtime=None,
    output_dir: str | Path = DEFAULT_SUCCESS_DIR,
    failure_dir: str | Path = DEFAULT_FAILURE_DIR,
    timeout_seconds: int = 20,
    show_browser: bool = False,
    workers: int = 8,
    read_only: bool = False,
):
    runtime = runtime or build_runtime()
    request = ScrapeRequest(
        periods=(period,),
        timeout_seconds=timeout_seconds,
        show_browser=show_browser,
        write_policy=WritePolicy.READ_ONLY if read_only else WritePolicy.UPDATE_CACHE,
    )
    def progress(current, total, batch, elapsed, site_name):
        print(format_progress(current, total, batch, elapsed, site_name), flush=True)

    batch = BatchService(runtime.scrape_service).run(
        (site.site_id for site in runtime.sites),
        request,
        max_workers=workers,
        progress_callback=progress,
    )
    success_lines = format_success_file_lines(batch.results, RANKING_EXCLUDED_NAMES)
    success_path = write_text(Path(output_dir) / f"{period}期-五行.txt", "\n".join(success_lines) + ("\n" if success_lines else ""))
    failure_path = write_text(
        Path(failure_dir) / f"{period}期-五行-失败.txt",
        format_failure_file_text(batch.failures),
    )
    cache_report = runtime.scrape_service.update_cache(batch.results, request)
    if cache_report.errors:
        print("缓存更新未完成：")
        for error in cache_report.errors:
            print(f"- {error}")
    print(f"成功 {len(batch.successes)} 个，保存到 {success_path}")
    print(f"失败 {len(batch.failures)} 个，保存到 {failure_path}")
    return batch, success_path, failure_path


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="解耦版单期绝杀一行五行抓取")
    parser.add_argument("period", type=int)
    parser.add_argument("--config")
    parser.add_argument("--cache")
    parser.add_argument("--output", default=str(DEFAULT_SUCCESS_DIR))
    parser.add_argument("--fail", default=str(DEFAULT_FAILURE_DIR))
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--show-browser", action="store_true")
    parser.add_argument("--read-only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    runtime = build_runtime(args.config, args.cache)
    run_single(
        args.period,
        runtime,
        args.output,
        args.fail,
        args.timeout,
        args.show_browser,
        args.workers,
        args.read_only,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
