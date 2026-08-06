from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
import json
from pathlib import Path
import re
import sys
import time
from typing import Callable, Iterable, Iterator, NamedTuple
import warnings

import wuxing_crawler as crawler


DEFAULT_CASES_PATH = "failed_site_validation_cases.json"
REGION_ALIASES = {
    "top": "top",
    "顶部": "top",
    "上": "top",
    "bottom": "bottom",
    "尾部": "bottom",
    "底部": "bottom",
    "下": "bottom",
}


class ValidationCase(NamedTuple):
    name: str
    url: str
    region: str
    period: int
    expected_wuxing: str | None


class ValidationResult(NamedTuple):
    name: str
    url: str
    region: str
    period: int
    passed: bool
    target_found: bool
    actual_wuxing: tuple[str, ...]
    direction_pass: bool
    anchor_pass: bool
    keyword_pass: bool
    wuxing_pass: bool
    has_conflict: bool
    has_duplicate_wuxing: bool
    failure_reason: str
    elapsed: float


class AuthorityCall(NamedTuple):
    url: str
    source_documents: tuple[str, ...]
    selected_documents: tuple[str, ...]


class ValidationTrace:
    def __init__(self) -> None:
        self.authority_calls: list[AuthorityCall] = []


ParserOverride = Callable[[str, crawler.Site], list[crawler.Candidate]]


class ValidationOnlyParserRule(NamedTuple):
    parser: ParserOverride
    anchor_pattern: re.Pattern[str]
    keyword_pattern: re.Pattern[str]


VALIDATION_ONLY_PARSERS: dict[str, ValidationOnlyParserRule] = {}


def resolve_local_path(value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent / path
    return path.resolve()


def normalize_region(value: object, index: int) -> str:
    normalized = REGION_ALIASES.get(crawler.clean_line(str(value)).lower())
    if normalized is None:
        raise ValueError(f"测试清单第{index}项 region 必须是 top 或 bottom")
    return normalized


def load_validation_cases(path: str | Path = DEFAULT_CASES_PATH) -> list[ValidationCase]:
    cases_path = resolve_local_path(path)
    raw_cases = json.loads(cases_path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw_cases, list):
        raise ValueError("失败站点测试清单根节点必须是数组")

    cases: list[ValidationCase] = []
    seen: set[tuple[str, str, int]] = set()
    for index, item in enumerate(raw_cases, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"测试清单第{index}项必须是对象")
        if item.get("enabled", True) is False:
            continue
        name = crawler.clean_line(str(item.get("name", "")))
        url = crawler.clean_line(str(item.get("url", "")))
        if not name and not url:
            raise ValueError(f"测试清单第{index}项必须填写 name 或 url")
        period = item.get("period")
        if isinstance(period, bool) or not isinstance(period, int) or period <= 0:
            raise ValueError(f"测试清单第{index}项 period 必须是正整数")
        region = normalize_region(item.get("region", ""), index)
        expected = crawler.clean_line(str(item.get("expected_wuxing", ""))) or None
        if expected is not None and not crawler.is_valid_wuxing(expected):
            raise ValueError(f"测试清单第{index}项 expected_wuxing 不是标准五行")
        identity = (name, url, period)
        if identity in seen:
            raise ValueError(f"测试清单第{index}项与前面重复")
        seen.add(identity)
        cases.append(ValidationCase(name, url, region, period, expected))
    if not cases:
        raise ValueError("失败站点测试清单没有启用的站点")
    return cases


def resolve_validation_site(case: ValidationCase, sites: Iterable[crawler.Site]) -> crawler.Site:
    matches = [
        site
        for site in sites
        if (not case.name or site.name == case.name) and (not case.url or site.url == case.url)
    ]
    if not matches:
        raise ValueError("正式 sites.json 中找不到名称/网址完全匹配的站点")
    if len(matches) > 1:
        raise ValueError("正式 sites.json 中匹配到多个站点，拒绝验证")
    site = matches[0]
    if site.pick != case.region:
        raise ValueError(f"方向不一致：清单是 {case.region}，正式配置是 {site.pick}")
    return site


@contextmanager
def validation_only_overrides(site: crawler.Site) -> Iterator[None]:
    rule = VALIDATION_ONLY_PARSERS.get(site.url)
    if rule is None:
        yield
        return

    original = crawler.parse_candidates_for_site

    def patched(document: str, current_site: crawler.Site) -> list[crawler.Candidate]:
        if current_site.url == site.url:
            return rule.parser(document, current_site)
        return original(document, current_site)

    crawler.parse_candidates_for_site = patched
    try:
        yield
    finally:
        crawler.parse_candidates_for_site = original


@contextmanager
def capture_authority_calls(trace: ValidationTrace) -> Iterator[None]:
    original = crawler.site_authoritative_documents

    def traced(
        documents: Iterable[str],
        site: crawler.Site,
        parser_fn=crawler.parse_candidates,
        period: int | None = None,
    ) -> list[str]:
        source_documents = list(documents)
        selected_documents = original(source_documents, site, parser_fn=parser_fn, period=period)
        trace.authority_calls.append(
            AuthorityCall(site.url, tuple(source_documents), tuple(selected_documents))
        )
        return selected_documents

    crawler.site_authoritative_documents = traced
    try:
        yield
    finally:
        crawler.site_authoritative_documents = original


def collect_target_candidates(
    documents: Iterable[str],
    site: crawler.Site,
    period: int,
) -> list[crawler.Candidate]:
    target = f"{period}期"
    return [
        candidate
        for document in documents
        for candidate in crawler.parse_candidates_for_site(document, site)
        if candidate.period == target
    ]


def validation_only_rule_checks(
    documents: Iterable[str],
    site: crawler.Site,
    period: int,
    rule: ValidationOnlyParserRule,
) -> tuple[bool, bool]:
    target = f"{period}期"
    anchor_with_target = False
    for document in documents:
        text = crawler.clean_line(crawler.html_to_text(document))
        if not rule.anchor_pattern.search(text):
            continue
        target_candidates = [
            candidate
            for candidate in crawler.parse_candidates_for_site(document, site)
            if candidate.period == target
        ]
        if not target_candidates:
            continue
        anchor_with_target = True
        if any(rule.keyword_pattern.search(crawler.clean_line(candidate.raw)) for candidate in target_candidates):
            return True, True
    return anchor_with_target, False


def anchor_check(
    documents: list[str],
    site: crawler.Site,
    target_candidates: list[crawler.Candidate],
    period: int,
    trace: ValidationTrace | None,
) -> bool:
    validation_rule = VALIDATION_ONLY_PARSERS.get(site.url)
    if validation_rule is not None:
        return validation_only_rule_checks(documents, site, period, validation_rule)[0]

    dedicated = site.url in crawler.SITE_SPECIFIC_ONLY_URLS
    if not dedicated:
        return False
    anchor = crawler.SITE_CURRENT_BLOCK_ANCHORS.get(site.url)
    if anchor is not None:
        target = f"{period}期"
        for document in documents:
            text = crawler.clean_line(crawler.html_to_text(document))
            candidates = crawler.parse_candidates_for_site(document, site)
            if anchor.search(text) and any(candidate.period == target for candidate in candidates):
                return True
        if trace is None:
            return False
        for call in trace.authority_calls:
            if call.url != site.url or not call.selected_documents:
                continue
            selected_has_target = any(
                candidate.period == target
                for document in call.selected_documents
                for candidate in crawler.parse_candidates_for_site(document, site)
            )
            if selected_has_target and call.selected_documents != call.source_documents:
                return True
        return False
    if dedicated:
        return bool(target_candidates)
    return False


def sorted_wuxing(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted(set(values), key=lambda value: crawler.VALID_WUXING_ORDER.get(value, 99)))


def build_validation_result(
    case: ValidationCase,
    site: crawler.Site,
    lines: list[str],
    error: str | None,
    documents: list[str],
    elapsed: float,
    trace: ValidationTrace | None = None,
) -> ValidationResult:
    parser_fn = lambda document: crawler.parse_candidates_for_site(document, site)
    target_candidates = collect_target_candidates(documents, site, case.period)
    line_values = [
        crawler.line_wuxing_value(line)
        for line in lines
        if crawler.line_period_number(line) == case.period
    ]
    line_values = [value for value in line_values if value]
    parsed_values = [candidate.wuxing for candidate in target_candidates if crawler.is_valid_wuxing(candidate.wuxing)]
    conflict_values = crawler.period_wuxing_values(
        documents,
        case.period,
        parser_fn=parser_fn,
        include_raw=site.url not in crawler.SITE_SPECIFIC_ONLY_URLS,
    )
    actual_wuxing = sorted_wuxing([*line_values, *conflict_values, *parsed_values])
    target_found = bool(line_values or target_candidates or conflict_values)
    line_success = any(crawler.line_period_number(line) == case.period for line in lines)
    region_reason = crawler.region_three_window_failure_reason(
        documents,
        site.pick,
        case.period,
        parser_fn=parser_fn,
    )
    strict_reason = crawler.strict_position_window_failure_reason(
        documents,
        site.pick,
        case.period,
        parser_fn=parser_fn,
    )
    window_candidates = crawler.region_target_window_candidates(
        crawler.authoritative_window_candidates(documents, parser_fn=parser_fn),
        site.pick,
    )
    direction_pass = any(
        candidate.period == f"{case.period}期" and crawler.is_valid_wuxing(candidate.wuxing)
        for candidate in window_candidates
    ) and region_reason is None and strict_reason is None
    anchor_pass = anchor_check(documents, site, target_candidates, case.period, trace)
    validation_rule = VALIDATION_ONLY_PARSERS.get(site.url)
    if validation_rule is not None:
        anchor_pass, keyword_pass = validation_only_rule_checks(
            documents,
            site,
            case.period,
            validation_rule,
        )
    else:
        keyword_pass = site.url in crawler.SITE_SPECIFIC_ONLY_URLS and any(
            crawler.TARGET_SECTION_RE.search(crawler.clean_line(candidate.raw))
            for candidate in target_candidates
        )
    has_conflict = len(conflict_values) > 1
    unique_sources = {
        (candidate.wuxing, crawler.clean_line(candidate.raw))
        for candidate in target_candidates
        if crawler.is_valid_wuxing(candidate.wuxing)
    }
    duplicate_counts = Counter(wuxing for wuxing, _ in unique_sources)
    has_duplicate_wuxing = any(count > 1 for count in duplicate_counts.values())
    expected_pass = case.expected_wuxing is None or actual_wuxing == (case.expected_wuxing,)
    wuxing_pass = len(actual_wuxing) == 1 and crawler.is_valid_wuxing(actual_wuxing[0]) and expected_pass
    passed = all(
        (
            line_success,
            target_found,
            direction_pass,
            anchor_pass,
            keyword_pass,
            wuxing_pass,
            not has_conflict,
        )
    )

    reasons: list[str] = []
    if not target_found:
        reasons.append(f"未抓到 {case.period}期")
    if region_reason:
        reasons.append(region_reason)
    if strict_reason:
        reasons.append(strict_reason)
    if not anchor_pass:
        reasons.append("站点/栏目锚点未通过")
    if not keyword_pass:
        reasons.append("目标关键词未通过")
    if has_conflict:
        reasons.append(f"同期五行冲突：{' / '.join(sorted_wuxing(conflict_values))}")
    if not wuxing_pass:
        if case.expected_wuxing and actual_wuxing and actual_wuxing != (case.expected_wuxing,):
            reasons.append(f"实际五行与预期不符：预期 {case.expected_wuxing}")
        else:
            reasons.append("未得到唯一标准五行")
    if error:
        reasons.append(crawler.clarify_error_message(error, documents, case.period))
    failure_reason = "无" if passed else "；".join(dict.fromkeys(reasons)) or "正式抓取未返回成功结果"

    return ValidationResult(
        site.name or case.name or "未命名",
        site.url or case.url,
        site.pick,
        case.period,
        passed,
        target_found,
        actual_wuxing,
        direction_pass,
        anchor_pass,
        keyword_pass,
        wuxing_pass,
        has_conflict,
        has_duplicate_wuxing,
        failure_reason,
        elapsed,
    )


def configuration_failure(case: ValidationCase, reason: str) -> ValidationResult:
    return ValidationResult(
        case.name or "未命名",
        case.url,
        case.region,
        case.period,
        False,
        False,
        (),
        False,
        False,
        False,
        False,
        False,
        False,
        reason,
        0.0,
    )


def run_validation_case(
    case: ValidationCase,
    sites: Iterable[crawler.Site],
    timeout: int,
    show_browser: bool,
) -> ValidationResult:
    try:
        site = resolve_validation_site(case, sites)
    except ValueError as exc:
        return configuration_failure(case, str(exc))

    started_at = time.perf_counter()
    trace = ValidationTrace()
    with validation_only_overrides(site), capture_authority_calls(trace):
        crawler.clear_runtime_caches()
        lines, error, documents = crawler.scrape_site_detailed(site, 1, timeout, show_browser, case.period)
        if not lines and crawler.should_retry_failure(error or ""):
            retry_timeout = max(timeout * 3, crawler.DEFAULT_RETRY_TIMEOUT_MIN)
            crawler.clear_runtime_caches()
            lines, error, documents = crawler.scrape_site_detailed(
                site,
                1,
                retry_timeout,
                show_browser,
                case.period,
            )
        result = build_validation_result(
            case,
            site,
            lines,
            error,
            documents,
            time.perf_counter() - started_at,
            trace,
        )
    return result


def yes_no(value: bool) -> str:
    return "是" if value else "否"


def pass_fail(value: bool) -> str:
    return "通过" if value else "失败"


def format_validation_result(result: ValidationResult, index: int, total: int) -> list[str]:
    region_label = "top / 顶部" if result.region == "top" else "bottom / 尾部"
    wuxing = " / ".join(result.actual_wuxing) if result.actual_wuxing else "未抓到"
    return [
        f"[{index}/{total}] {result.name}",
        f"网址：{result.url}",
        f"指定期数：{result.period}期",
        f"配置方向：{region_label}",
        f"是否抓到指定期数：{yes_no(result.target_found)}",
        f"实际五行：{wuxing}",
        f"top/bottom 是否正确：{pass_fail(result.direction_pass)}",
        f"锚点是否通过：{pass_fail(result.anchor_pass)}",
        f"关键词是否通过：{pass_fail(result.keyword_pass)}",
        f"五行是否通过：{pass_fail(result.wuxing_pass)}",
        f"同期冲突：{yes_no(result.has_conflict)}",
        f"重复五行：{yes_no(result.has_duplicate_wuxing)}",
        f"验证结果：{pass_fail(result.passed)}",
        f"失败原因：{result.failure_reason}",
        f"耗时：{result.elapsed:.2f}s",
    ]


def filter_cases(cases: Iterable[ValidationCase], query: str) -> list[ValidationCase]:
    normalized = crawler.clean_line(query).lower()
    if not normalized:
        return list(cases)
    return [case for case in cases if normalized in case.name.lower() or normalized in case.url.lower()]


def main(argv: list[str] | None = None) -> int:
    if __name__ == "__main__":
        print("旧版失败验证入口已封闭：请使用 杀五行_修复版2-失败验证.bat，避免绕过统一校验")
        return 2

    parser = argparse.ArgumentParser(description="独立验证失败站点，不更新缓存，不生成正式 TXT")
    parser.add_argument("--cases", default=DEFAULT_CASES_PATH, help="失败站点测试清单 JSON")
    parser.add_argument("--sites-config", default=crawler.DEFAULT_SITES_CONFIG, help="正式站点配置 JSON")
    parser.add_argument("--site", default="", help="只验证名称或网址包含该关键词的清单项")
    parser.add_argument("--timeout", type=int, default=20, help="单站首次抓取超时秒数")
    parser.add_argument("--show-browser", action="store_true", help="显示浏览器窗口")
    args = parser.parse_args(argv)

    warnings.simplefilter("ignore", crawler.InsecureRequestWarning)
    crawler.requests.packages.urllib3.disable_warnings()

    if args.timeout <= 0:
        print("timeout 必须大于 0")
        return 2
    try:
        cases = filter_cases(load_validation_cases(args.cases), args.site)
        sites = crawler.load_sites(args.sites_config)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"验证配置读取失败：{type(exc).__name__}: {exc}")
        return 2
    if not cases:
        print(f"测试清单中没有匹配项：{args.site}")
        return 2

    print("独立失败站点验证模式：不更新 recent_10_cache.json，不生成或覆盖正式成功/失败 TXT。")
    print(f"本次只验证 {len(cases)} 个清单站点。\n")
    results: list[ValidationResult] = []
    for index, case in enumerate(cases, start=1):
        result = run_validation_case(case, sites, args.timeout, args.show_browser)
        results.append(result)
        print("\n".join(format_validation_result(result, index, len(cases))))
        print()

    passed_count = sum(result.passed for result in results)
    print(f"验证汇总：通过 {passed_count} 个，失败 {len(results) - passed_count} 个。")
    if passed_count != len(results):
        print("存在未通过站点：禁止同步到正式 py/json，禁止运行正式 BAT。")
        return 1
    print("全部通过：可以同步已经验证好的最小修改，再运行正式 BAT 验收。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
