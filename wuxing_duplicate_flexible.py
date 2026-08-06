import argparse
import sys
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from itertools import combinations

import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning

from wuxing_crawler import (
    DEFAULT_HISTORY_CACHE,
    Site,
    ambiguous_target_candidates_reason,
    article_admin_should_render_fallback,
    collect_article_admin_api_documents,
    collect_click_through_detail_documents,
    collect_documents,
    create_session,
    fetch_browser_text,
    has_conflicting_target_candidates,
    is_valid_wuxing,
    load_history_cache,
    load_sites,
    parse_candidates_for_site,
    pick_candidates,
    region_three_window_failure_reason,
    resolve_output_path,
    site_browser_click_first,
    site_needs_browser,
    site_uses_api_first,
    site_uses_browser_first,
    site_uses_click_through_detail,
    signature_from_history_cache,
)


DEFAULT_PERIODS = 10
DEFAULT_LOOKBACK = 60
DEFAULT_WORKERS = 8
SUSPECT_MIN_MATCH = 3
REJECT_MIN_MATCH = 6

# 用户已明确授权的单站判重特例，必须按完整 URL 精确生效。
DUPLICATE_EXCEPTION_URLS = frozenset({
    "https://wigrzse.3acpt-tc9xa-kzxasm.xyz:29444/article/manager/6a20da1dca6da63e15d01fc8?url=pg",
})


@dataclass(frozen=True)
class DuplicateMatch:
    status: str
    site_a: str
    site_b: str
    periods: tuple[int, ...]
    wuxing: tuple[str, ...]

    @property
    def length(self) -> int:
        return len(self.periods)


def cache_policy_lines(no_history_cache: bool, history_cache: str) -> list[str]:
    if no_history_cache:
        return [
            "判重基准：已禁用 recent_10_cache.json，仅限调试/排障使用",
            "警告：--no-history-cache 的实时抓取结果不能作为新增判重依据，新增判重必须使用正式重复检测器 + recent_10_cache.json 基准结果",
        ]
    return [
        f"判重基准：正式重复检测器 + {history_cache}，可作为新增判重依据",
        "禁止：旧实时指纹脚本、临时指纹脚本、人工临时拼出的实时指纹不能作为新增判重依据",
    ]


def pick_wuxing(candidates, pick: str) -> str | None:
    valid_candidates = [candidate for candidate in candidates if is_valid_wuxing(candidate.wuxing)]
    if not valid_candidates:
        return None
    candidate = pick_candidates(valid_candidates, pick, 1)[0]
    return candidate.wuxing


def signature_label(site: Site) -> str:
    return site.name or site.url


def is_duplicate_exception(site_label: str, site_urls: dict[str, str] | None) -> bool:
    return bool(site_urls and site_urls.get(site_label) in DUPLICATE_EXCEPTION_URLS)


def split_cached_and_pending_sites(
    sites: list[Site],
    cache: dict,
    period: int,
    periods: int,
    lookback: int,
) -> tuple[dict[str, tuple[tuple[int, str], ...]], list[Site]]:
    signatures: dict[str, tuple[tuple[int, str], ...]] = {}
    pending: list[Site] = []
    for site in sites:
        signature = signature_from_history_cache(cache, site, period, periods, lookback)
        if signature:
            signatures[signature_label(site)] = signature
        else:
            pending.append(site)
    return signatures, pending


def partition_pending_sites(sites: list[Site]) -> tuple[list[Site], list[Site]]:
    http_sites = [site for site in sites if not site_needs_browser(site)]
    browser_sites = [site for site in sites if site_needs_browser(site)]
    return http_sites, browser_sites


def build_flexible_signature(
    documents: list[str],
    site: Site,
    period: int,
    periods: int,
    lookback: int,
) -> tuple[tuple[int, str], ...] | None:
    candidates = []
    for document_index, document in enumerate(documents):
        for candidate in parse_candidates_for_site(document, site):
            if not candidate.period.endswith("期"):
                continue
            if not is_valid_wuxing(candidate.wuxing):
                continue
            candidates.append(
                type(candidate)(
                    period=candidate.period,
                    wuxing=candidate.wuxing,
                    order=document_index * 100000 + candidate.order,
                    raw=candidate.raw,
                )
            )

    def parser_fn(document: str):
        return parse_candidates_for_site(document, site)

    if not documents:
        return None
    primary_candidates = [
        candidate for candidate in parser_fn(documents[0])
        if is_valid_wuxing(candidate.wuxing)
    ]
    if not primary_candidates:
        return None
    if region_three_window_failure_reason(documents, site.pick, period, parser_fn=parser_fn):
        return None
    scoped_candidates = primary_candidates

    values: list[tuple[int, str]] = []
    for target_period in range(period, max(period - lookback, 0), -1):
        if has_conflicting_target_candidates(candidates, target_period):
            return None
        if ambiguous_target_candidates_reason(site, candidates, target_period):
            return None
        period_label = f"{target_period}期"
        period_candidates = [candidate for candidate in scoped_candidates if candidate.period == period_label]
        wuxing = pick_wuxing(period_candidates, site.pick)
        if not wuxing:
            continue
        values.append((target_period, wuxing))
        if len(values) >= periods:
            return tuple(values)
    return tuple(values) if values else None


def matching_runs(
    signature_a: tuple[tuple[int, str], ...],
    signature_b: tuple[tuple[int, str], ...],
) -> list[tuple[tuple[int, ...], tuple[str, ...]]]:
    values_a = dict(signature_a)
    values_b = dict(signature_b)
    shared_periods = sorted(set(values_a) & set(values_b), reverse=True)
    runs: list[tuple[list[int], list[str]]] = []
    current_periods: list[int] = []
    current_wuxing: list[str] = []
    previous_period: int | None = None

    for period in shared_periods:
        is_match = values_a[period] == values_b[period]
        is_continuous = previous_period is None or previous_period - period == 1
        if not is_match or not is_continuous:
            if current_periods:
                runs.append((current_periods, current_wuxing))
            current_periods = []
            current_wuxing = []
        if is_match:
            current_periods.append(period)
            current_wuxing.append(values_a[period])
        previous_period = period

    if current_periods:
        runs.append((current_periods, current_wuxing))

    return [(tuple(periods), tuple(wuxing)) for periods, wuxing in runs]


def best_duplicate_match(
    site_a: str,
    signature_a: tuple[tuple[int, str], ...],
    site_b: str,
    signature_b: tuple[tuple[int, str], ...],
) -> DuplicateMatch | None:
    runs = matching_runs(signature_a, signature_b)
    if not runs:
        return None
    periods, wuxing = max(runs, key=lambda run: len(run[0]))
    if len(periods) >= REJECT_MIN_MATCH:
        status = "reject"
    elif len(periods) >= SUSPECT_MIN_MATCH:
        status = "suspect"
    else:
        return None
    return DuplicateMatch(status, site_a, site_b, periods, wuxing)


def find_duplicate_matches(
    signatures: dict[str, tuple[tuple[int, str], ...]],
    site_urls: dict[str, str] | None = None,
) -> list[DuplicateMatch]:
    matches: list[DuplicateMatch] = []
    for (site_a, signature_a), (site_b, signature_b) in combinations(signatures.items(), 2):
        if is_duplicate_exception(site_a, site_urls) or is_duplicate_exception(site_b, site_urls):
            continue
        match = best_duplicate_match(site_a, signature_a, site_b, signature_b)
        if match:
            matches.append(match)
    return sorted(matches, key=lambda match: (match.status != "reject", -match.length, match.site_a, match.site_b))


def check_site(
    site: Site,
    period: int,
    periods: int,
    lookback: int,
    timeout: int,
    show_browser: bool,
) -> tuple[Site, tuple[tuple[int, str], ...] | None, str | None]:
    try:
        documents: list[str] = []
        browser_timeout = max(timeout, 20)
        uses_api_first = site_uses_api_first(site)
        api_error: Exception | None = None
        if uses_api_first:
            documents, api_error = collect_article_admin_api_documents(site, timeout)

        uses_browser_first = site_uses_browser_first(site)
        if not documents and uses_browser_first:
            document = fetch_browser_text(
                site.url,
                browser_timeout,
                site_browser_click_first(site),
                show_browser,
                period,
                site=site,
            )
            documents = [document]
        elif not documents and not uses_api_first and site_uses_click_through_detail(site):
            documents = collect_click_through_detail_documents(site, timeout, period)
        elif not documents and not uses_api_first:
            with create_session() as session:
                documents = collect_documents(session, site.url, timeout)

        if article_admin_should_render_fallback(site, documents, api_error, period):
            document = fetch_browser_text(
                site.url,
                browser_timeout,
                site_browser_click_first(site),
                show_browser,
                period,
                site=site,
            )
            documents = [document]

        signature = build_flexible_signature(documents, site, period, periods, lookback)
        if signature is None and not uses_browser_first and not uses_api_first:
            try:
                browser_document = fetch_browser_text(
                    site.url, browser_timeout, False, show_browser, period, site=site
                )
                signature = build_flexible_signature(
                    documents + [browser_document], site, period, periods, lookback
                )
            except Exception as exc:
                if not documents:
                    return site, None, f"{type(exc).__name__}: {exc}"
        if signature is None:
            return site, None, f"向前{lookback}期内未找到可用数据"
        return site, signature, None
    except Exception as exc:
        return site, None, f"{type(exc).__name__}: {exc}"


def duplicate_lines(matches: list[DuplicateMatch]) -> list[str]:
    lines: list[str] = []
    for index, match in enumerate(matches, start=1):
        if lines:
            lines.append("")
        label = "重复拒收" if match.status == "reject" else "疑似重复"
        period_text = "、".join(f"{period}期:{wuxing}" for period, wuxing in zip(match.periods, match.wuxing))
        lines.append(f"{label}{index}：连续{match.length}期一致")
        lines.append(f"{match.site_a}")
        lines.append(f"{match.site_b}")
        lines.append(period_text)
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description="按期号对齐检测不同 URL 的历史数据重复")
    parser.add_argument("--period", type=int, required=True, help="必须手动指定基准期号，例如：--period 148")
    parser.add_argument("--periods", type=int, default=DEFAULT_PERIODS, help="每个网站优先取最近多少期可用数据，默认 10")
    parser.add_argument("--lookback", type=int, default=DEFAULT_LOOKBACK, help="最多向前找多少期，默认 60")
    parser.add_argument("--timeout", type=int, default=12, help="单站超时秒数")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="普通网页并发数，默认 8")
    parser.add_argument("--browser-workers", type=int, default=2, help="图片/二次点击网站并发数，默认 2")
    parser.add_argument("--show-browser", action="store_true", help="显示图片/二次点击网站浏览器窗口")
    parser.add_argument("--output", default=None, help="重复网站 txt，默认：统一归纳目录/N期宽松重复网站.txt")
    parser.add_argument("--fail", default=None, help="失败 txt，默认：统一归纳目录/N期宽松重复检测失败.txt")
    parser.add_argument("--history-cache", default=DEFAULT_HISTORY_CACHE, help="最近10期历史缓存 JSON")
    parser.add_argument("--no-history-cache", action="store_true", help="已禁用：判重不得脱离 recent_10_cache.json")
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")
    warnings.simplefilter("ignore", InsecureRequestWarning)
    requests.packages.urllib3.disable_warnings()

    if args.period <= 0:
        print("必须手动指定大于 0 的期号，例如：--period 148")
        sys.exit(2)
    if args.no_history_cache:
        print("已拒绝：正式判重不允许关闭 recent_10_cache.json 或独立联网解析")
        sys.exit(2)

    for line in cache_policy_lines(args.no_history_cache, args.history_cache):
        print(line)

    signatures: dict[str, tuple[tuple[int, str], ...]] = {}
    failures: list[str] = []
    sites = load_sites()
    signature_urls = {signature_label(site): site.url for site in sites}
    pending_sites = sites
    if not args.no_history_cache:
        cache = load_history_cache(args.history_cache)
        cached_signatures, pending_sites = split_cached_and_pending_sites(sites, cache, args.period, args.periods, args.lookback)
        signatures.update(cached_signatures)
        for label in cached_signatures:
            print(f"[CACHE] {label}")

    if pending_sites:
        failures.extend(
            f"{site.url} {site.pick} 缓存缺少近{args.periods}期完整数据，拒绝实时补抓判重"
            for site in pending_sites
        )
    http_sites, browser_sites = [], []

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = [
            executor.submit(check_site, site, args.period, args.periods, args.lookback, args.timeout, args.show_browser)
            for site in http_sites
        ]
        for future in as_completed(futures):
            site, signature, error = future.result()
            if signature:
                signatures[signature_label(site)] = signature
                print(f"[OK] {site.url}")
            else:
                failures.append(f"{site.url} {site.pick} {error or '未找到结果'}")
                print(f"[FAIL] {site.url} -> {error}")

    with ThreadPoolExecutor(max_workers=max(1, args.browser_workers)) as executor:
        futures = [
            executor.submit(check_site, site, args.period, args.periods, args.lookback, args.timeout, args.show_browser)
            for site in browser_sites
        ]
        for future in as_completed(futures):
            site, signature, error = future.result()
            if signature:
                signatures[signature_label(site)] = signature
                print(f"[OK] {site.url}")
            else:
                failures.append(f"{site.url} {site.pick} {error or '未找到结果'}")
                print(f"[FAIL] {site.url} -> {error}")

    output_path = resolve_output_path(args.output, f"{args.period}期历史重复检测.txt")
    fail_path = resolve_output_path(args.fail, f"{args.period}期历史重复检测失败.txt")
    matches = find_duplicate_matches(signatures, signature_urls)
    output = duplicate_lines(matches)
    output_path.write_text("\n".join(output) + ("\n" if output else ""), encoding="utf-8-sig")
    fail_path.write_text("\n".join(failures) + ("\n" if failures else ""), encoding="utf-8-sig")

    reject_count = sum(1 for match in matches if match.status == "reject")
    suspect_count = sum(1 for match in matches if match.status == "suspect")
    print(f"\n重复拒收 {reject_count} 组，疑似重复 {suspect_count} 组，保存到 {output_path}")
    print(f"失败 {len(failures)} 个网站，保存到 {fail_path}")


if __name__ == "__main__":
    print("旧版入口已封闭：请使用 杀五行_修复版2-判重.bat，避免绕过统一判重服务")
    raise SystemExit(2)
