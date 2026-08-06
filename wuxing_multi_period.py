import argparse
import re
import sys
import time
import warnings
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning

import wuxing_crawler as crawler


@dataclass(frozen=True)
class MultiPeriodTiming:
    site_name: str
    url: str
    period: int
    elapsed_seconds: float
    ok: bool


def parse_periods(values: list[str] | str) -> list[int]:
    if isinstance(values, str):
        raw_values = re.split(r"[\s,，;；]+", values.strip())
    else:
        raw_values = []
        for value in values:
            raw_values.extend(re.split(r"[\s,，;；]+", str(value).strip()))

    periods: list[int] = []
    seen: set[int] = set()
    for raw in raw_values:
        if not raw:
            continue
        if not re.fullmatch(r"\d+", raw):
            raise ValueError(f"期数必须是数字：{raw}")
        period = int(raw)
        if period <= 0:
            raise ValueError(f"期数必须大于 0：{raw}")
        if period in seen:
            continue
        seen.add(period)
        periods.append(period)
    if not periods:
        raise ValueError("至少输入一个期数")
    return periods


def period_range_label(periods: list[int]) -> str:
    ordered = sorted(periods)
    if len(ordered) > 1 and ordered == list(range(ordered[0], ordered[-1] + 1)):
        return f"{ordered[0]}-{ordered[-1]}期"
    return "-".join(str(period) for period in periods) + "期"


def selected_positions(selected_sites: list[tuple[int, crawler.Site]]) -> dict[int, int]:
    return {index: position for position, (index, _) in enumerate(selected_sites, start=1)}


def retry_failed_sites(
    http_sites: list[tuple[int, crawler.Site]],
    browser_sites: list[tuple[int, crawler.Site]],
    outcomes: dict[int, tuple[crawler.Site, list[str], str | None, list[str], float]],
    period: int,
    retry_timeout: int,
    workers: int,
    browser_workers: int,
    show_browser: bool,
    total_sites: int,
    positions: dict[int, int],
    progress_started_at: float | None = None,
) -> dict[int, tuple[crawler.Site, list[str], str | None, list[str], float]]:
    progress_started_at = time.perf_counter() if progress_started_at is None else progress_started_at
    retry_groups = []
    has_retry = False
    for sites, max_workers in ((http_sites, workers), (browser_sites, browser_workers)):
        retry_sites = [
            (index, site, outcomes.get(index, (site, [], None, [], 0.0))[4])
            for index, site in sites
            if not outcomes.get(index, (site, [], None, [], 0.0))[1]
            and crawler.should_retry_failure(outcomes.get(index, (site, [], None, [], 0.0))[2])
        ]
        if retry_sites:
            has_retry = True
            retry_groups.append((retry_sites, ThreadPoolExecutor(max_workers=max(1, max_workers))))

    if has_retry:
        crawler.clear_runtime_caches()

    updated_outcomes = dict(outcomes)
    futures = {}
    try:
        for retry_sites, executor in retry_groups:
            for index, site, initial_elapsed in retry_sites:
                future = executor.submit(
                    crawler.scrape_indexed_site,
                    index,
                    site,
                    1,
                    retry_timeout,
                    show_browser,
                    period,
                )
                futures[future] = (initial_elapsed, site)
        for future in as_completed(futures):
            index, _, lines, error, documents, retry_elapsed = future.result()
            initial_elapsed, site = futures[future]
            total_elapsed = initial_elapsed + retry_elapsed
            updated_outcomes[index] = (site, lines, error, documents, total_elapsed)
            crawler.print_progress_status(updated_outcomes, site, total_sites, progress_started_at)
    finally:
        for _, executor in retry_groups:
            executor.shutdown(wait=True)
    return updated_outcomes


def scrape_period(
    selected_sites: list[tuple[int, crawler.Site]],
    period: int,
    timeout: int,
    workers: int,
    browser_workers: int,
    show_browser: bool,
) -> dict[int, tuple[crawler.Site, list[str], str | None, list[str], float]]:
    total_sites = len(selected_sites)
    http_sites = [(index, site) for index, site in selected_sites if not crawler.site_needs_browser(site)]
    browser_sites = [(index, site) for index, site in selected_sites if crawler.site_needs_browser(site)]
    browser_dependency_error = crawler.check_browser_dependencies() if browser_sites else None
    if browser_dependency_error:
        print(browser_dependency_error)

    progress_started_at = time.perf_counter()
    outcomes = crawler.run_initial_scrapes(
        http_sites=http_sites,
        browser_sites=browser_sites,
        count=1,
        timeout=timeout,
        show_browser=show_browser,
        period=period,
        workers=max(1, workers),
        browser_workers=max(1, browser_workers),
        browser_dependency_error=browser_dependency_error,
        total=total_sites,
        progress_positions=selected_positions(selected_sites),
        progress_started_at=progress_started_at,
    )

    outcomes = retry_failed_sites(
        http_sites=http_sites,
        browser_sites=[] if browser_dependency_error else browser_sites,
        outcomes=outcomes,
        period=period,
        retry_timeout=max(timeout * 3, crawler.DEFAULT_RETRY_TIMEOUT_MIN),
        workers=workers,
        browser_workers=browser_workers,
        show_browser=show_browser,
        total_sites=total_sites,
        positions=selected_positions(selected_sites),
        progress_started_at=progress_started_at,
    )
    print("")
    return outcomes


def period_result_reason(site: crawler.Site, lines: list[str], error: str | None, documents: list[str], period: int) -> tuple[bool, str | None]:
    if lines:
        line_periods = [crawler.line_period_number(line) for line in lines]
        if all(line_period == period for line_period in line_periods):
            return True, None
        found_periods = "、".join(
            f"{line_period}期" if line_period is not None else "未知期号"
            for line_period in line_periods
        )
        return False, f"抓到 {found_periods}，不是指定 {period}期，已丢入失败"
    return False, crawler.clarify_error_message(error, documents, period)


def write_period_files(
    selected_sites: list[tuple[int, crawler.Site]],
    outcomes: dict[int, tuple[crawler.Site, list[str], str | None, list[str], float]],
    period: int,
) -> tuple[set[int], dict[int, str]]:
    success_indexes: set[int] = set()
    fail_reasons: dict[int, str] = {}
    success_lines: list[str] = []
    excluded_ranking_lines: list[str] = []
    fail_lines: list[str] = []
    fail_counts: Counter[str] = Counter()

    for index, site in selected_sites:
        _, lines, error, documents, _ = outcomes.get(index, (site, [], "未执行", [], 0.0))
        ok, reason = period_result_reason(site, lines, error, documents, period)
        if ok:
            success_indexes.add(index)
            formatted_lines = [crawler.format_success_output_line(line) for line in lines]
            if site.name in crawler.RANKING_EXCLUDED_SITE_NAMES:
                excluded_ranking_lines.extend(formatted_lines)
            else:
                success_lines.extend(formatted_lines)
        else:
            reason = reason or "未知失败"
            fail_reasons[index] = reason
            fail_counts[crawler.classify_failure_reason(reason)] += 1
            fail_lines.append(crawler.format_fail_line(site, reason))

    output_path = crawler.resolve_output_path(None, f"{period}期-五行.txt")
    fail_path = crawler.resolve_output_path(
        None,
        f"{period}期-五行-失败.txt",
        output_dir=crawler.DEFAULT_FAILURE_OUTPUT_DIR,
    )
    output_lines = crawler.build_success_output_lines(success_lines, excluded_ranking_lines)
    output_lines += [""] + crawler.build_slow_site_lines(outcomes, limit=max(1, len(outcomes)))
    output_path.write_text("\n".join(output_lines) + ("\n" if output_lines else ""), encoding="utf-8-sig")

    print(f"\n{period}期成功 {len(success_lines) + len(excluded_ranking_lines)} 行，保存到 {output_path}")
    if fail_lines:
        fail_path.write_text(crawler.format_failure_file_text(fail_lines), encoding="utf-8-sig")
        print(f"{period}期失败 {len(fail_lines)} 个网站，保存到 {fail_path}")
        print("失败分类：" + "，".join(f"{name} {count}个" for name, count in fail_counts.most_common()))
    else:
        if fail_path.exists():
            fail_path.unlink()
        print(f"{period}期失败 0 个网站，未生成失败文件")

    return success_indexes, fail_reasons


def collect_multi_timings(
    outcomes: dict[int, tuple[crawler.Site, list[str], str | None, list[str], float]],
    period: int,
) -> list[MultiPeriodTiming]:
    return [
        MultiPeriodTiming(site.name or "未命名", site.url, period, elapsed_seconds, bool(lines))
        for site, lines, _, _, elapsed_seconds in outcomes.values()
        if elapsed_seconds > 0
    ]


def build_multi_slow_site_lines(stats: list[MultiPeriodTiming], limit: int = 10) -> list[str]:
    rows = sorted(stats, key=lambda item: item.elapsed_seconds, reverse=True)
    if not rows:
        return ["多期慢站耗时统计：无可统计数据"]
    limit = max(1, limit)
    shown = rows[:limit]
    return [f"多期慢站耗时统计 Top {len(shown)}："] + [
        f"{rank}. {item.site_name} | {item.period}期 | {item.elapsed_seconds:.2f}s | {'成功' if item.ok else '失败'} | {item.url}"
        for rank, item in enumerate(shown, start=1)
    ]


def print_multi_slow_site_summary(stats: list[MultiPeriodTiming], limit: int = 10) -> None:
    print("")
    for line in build_multi_slow_site_lines(stats, limit=limit):
        print(line)


def build_multi_fail_lines(
    sites: list[crawler.Site],
    all_failed_indexes: list[int],
    period_failures: dict[int, dict[int, str]],
    periods: list[int],
) -> list[str]:
    lines = [
        f"{period_range_label(periods)} 五行多期汇总失败报告",
        "规则：只列所有指定期都失败的目录；已任意一期成功的目录不列入。",
        f"指定期数：{' '.join(str(period) for period in periods)}",
        f"多期全部失败：{len(all_failed_indexes)} 个目录",
        "",
    ]
    for index in all_failed_indexes:
        site = sites[index]
        lines.append(crawler.format_fail_line(site, "多期全部失败"))
        for period in periods:
            reason = period_failures.get(index, {}).get(period, "该期未执行")
            lines.append(f"  {period}期: {reason}")
        lines.append("")
    if not all_failed_indexes:
        lines.append("全部目录至少有一个指定期抓取成功。")
    return lines


def write_multi_fail_report(
    sites: list[crawler.Site],
    all_failed_indexes: list[int],
    period_failures: dict[int, dict[int, str]],
    periods: list[int],
) -> Path:
    path = crawler.resolve_output_path(
        None,
        f"{period_range_label(periods)}-五行-多期汇总失败.txt",
        output_dir=crawler.DEFAULT_FAILURE_OUTPUT_DIR,
    )
    path.write_text("\n".join(build_multi_fail_lines(sites, all_failed_indexes, period_failures, periods)) + "\n", encoding="utf-8-sig")
    return path


def run_multi_period(args: argparse.Namespace) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    warnings.simplefilter("ignore", InsecureRequestWarning)
    requests.packages.urllib3.disable_warnings()

    period_input = args.period_text or " ".join(args.period_args)
    if not period_input.strip():
        period_input = input("Periods: ")
    periods = parse_periods(period_input)

    sites = crawler.load_sites(args.sites_config)
    if not sites:
        print("站点配置为空")
        return 2

    if hasattr(crawler, "clear_runtime_caches"):
        crawler.clear_runtime_caches()

    pending_indexes = set(range(len(sites)))
    period_failures: dict[int, dict[int, str]] = {index: {} for index in pending_indexes}
    all_timings: list[MultiPeriodTiming] = []

    print(f"多期模式：{' '.join(str(period) for period in periods)}")
    print("说明：多期模式不更新 recent_10_cache.json；目录任意一期成功后，后续期数不再抓该目录。")

    for period in periods:
        if not pending_indexes:
            print("\n全部目录已至少命中一期，后续期数跳过。")
            break

        selected_sites = [(index, sites[index]) for index in sorted(pending_indexes)]
        print(f"\n开始 {period}期：待验证 {len(selected_sites)} 个目录")
        outcomes = scrape_period(
            selected_sites=selected_sites,
            period=period,
            timeout=args.timeout,
            workers=args.workers,
            browser_workers=args.browser_workers,
            show_browser=args.show_browser,
        )
        all_timings.extend(collect_multi_timings(outcomes, period))
        success_indexes, fail_reasons = write_period_files(selected_sites, outcomes, period)
        crawler.print_slow_site_summary(outcomes)

        for index, reason in fail_reasons.items():
            period_failures.setdefault(index, {})[period] = reason
        pending_indexes.difference_update(success_indexes)
        print(f"{period}期后仍未命中：{len(pending_indexes)} 个目录")

    all_failed_indexes = sorted(pending_indexes)
    summary_path = write_multi_fail_report(sites, all_failed_indexes, period_failures, periods)
    print(f"\n多期汇总失败报告保存到 {summary_path}")
    print(f"多期全部失败 {len(all_failed_indexes)} 个目录")
    print_multi_slow_site_summary(all_timings)
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="多期抓取绝杀一行五行；目录任意一期成功即通过")
    parser.add_argument("period_args", nargs="*", help="期数，例如 187 188 189 190")
    parser.add_argument("--periods", dest="period_text", default="", help="期数字符串，例如 \"187 188 189 190\"")
    parser.add_argument("--sites-config", default=crawler.DEFAULT_SITES_CONFIG, help="站点配置 JSON，默认 sites.json")
    parser.add_argument("--timeout", type=int, default=20, help="单站超时秒数")
    parser.add_argument("--workers", type=int, default=8, help="普通站并发数")
    parser.add_argument("--browser-workers", type=int, default=2, help="浏览器站并发数")
    parser.add_argument("--show-browser", action="store_true", help="显示浏览器窗口")
    return parser


def main() -> None:
    if __name__ == "__main__":
        print("旧版多期入口已封闭：请使用 杀五行_修复版2-多期.bat，避免绕过统一校验")
        raise SystemExit(2)

    raise SystemExit(run_multi_period(build_arg_parser().parse_args()))


if __name__ == "__main__":
    main()
