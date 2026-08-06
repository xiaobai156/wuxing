from __future__ import annotations

import argparse
from pathlib import Path
import time

from wuxing.domain.models import BatchResult
from wuxing.reporting.failure import format_failure_file_text
from wuxing.reporting.progress import format_progress
from wuxing.reporting.success import format_success_file_lines
from wuxing.services.multi_period import MultiPeriodService

from .common import DEFAULT_FAILURE_DIR, DEFAULT_SUCCESS_DIR, RANKING_EXCLUDED_NAMES, build_runtime, write_text


def run_multi(
    periods: tuple[int, ...],
    runtime=None,
    output_dir: str | Path = DEFAULT_SUCCESS_DIR,
    failure_dir: str | Path = DEFAULT_FAILURE_DIR,
    timeout_seconds: int = 20,
    show_browser: bool = False,
):
    runtime = runtime or build_runtime()
    started = time.monotonic()
    result = MultiPeriodService(runtime.scrape_service).run(
        (site.site_id for site in runtime.sites),
        periods,
        timeout_seconds,
        show_browser,
    )
    for index, period in enumerate(periods, start=1):
        period_results = tuple(item for item in result.attempts if item.period == period)
        batch = BatchResult(period_results)
        if period_results:
            print(format_progress(index, len(periods), batch, time.monotonic() - started, f"{period}期"), flush=True)
        success_lines = format_success_file_lines(period_results, RANKING_EXCLUDED_NAMES)
        failure_results = tuple(item for item in period_results if item.candidate is None)
        write_text(Path(output_dir) / f"{period}期-五行.txt", "\n".join(success_lines) + ("\n" if success_lines else ""))
        write_text(Path(failure_dir) / f"{period}期-五行-失败.txt", format_failure_file_text(failure_results))

    summary_results = tuple(item for attempts in result.all_failures for item in attempts)
    summary_path = write_text(
        Path(failure_dir) / "多期-全部失败汇总.txt",
        format_failure_file_text(summary_results),
    )
    print(f"多期全部失败汇总保存到 {summary_path}")
    return result


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="解耦版多期抓取，目录任一期成功即通过")
    parser.add_argument("periods", nargs="+", type=int)
    parser.add_argument("--config")
    parser.add_argument("--cache")
    parser.add_argument("--output", default=str(DEFAULT_SUCCESS_DIR))
    parser.add_argument("--fail", default=str(DEFAULT_FAILURE_DIR))
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--show-browser", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    run_multi(
        tuple(args.periods),
        build_runtime(args.config, args.cache),
        args.output,
        args.fail,
        args.timeout,
        args.show_browser,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
