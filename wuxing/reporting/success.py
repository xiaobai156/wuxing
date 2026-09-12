from collections import Counter
from collections.abc import Iterable

from wuxing.domain.enums import ResultStatus
from wuxing.domain.models import ScrapeResult


WUXING_ORDER = ("金行", "木行", "水行", "火行", "土行")
RANKING_HEADER = "内容\t次数\t排名"


def format_success_line(result: ScrapeResult) -> str:
    if result.status is not ResultStatus.SUCCESS or result.candidate is None:
        raise ValueError("只能格式化成功结果")
    return f"{result.candidate.wuxing} {result.site.name}"


def format_slow_site_lines(results: Iterable[ScrapeResult], limit: int = 10) -> list[str]:
    rows = sorted(
        (result for result in results if result.elapsed_seconds > 0),
        key=lambda result: result.elapsed_seconds,
        reverse=True,
    )[: max(1, limit)]
    if not rows:
        return ["慢站耗时统计：无可统计数据"]
    return [f"慢站耗时统计 Top {len(rows)}："] + [
        f"{index}. {result.site.name} | {result.elapsed_seconds:.2f}s | "
        f"{'成功' if result.status is ResultStatus.SUCCESS else '失败'} | {result.site.url}"
        for index, result in enumerate(rows, start=1)
    ]


def format_success_file_lines(
    results: Iterable[ScrapeResult],
    excluded_names: frozenset[str] = frozenset(),
) -> list[str]:
    results = tuple(results)
    lines = [
        format_success_line(result)
        for result in results
        if result.status is ResultStatus.SUCCESS
        and result.candidate is not None
        and result.site.name not in excluded_names
    ]
    excluded = [
        format_success_line(result)
        for result in results
        if result.status is ResultStatus.SUCCESS
        and result.candidate is not None
        and result.site.name in excluded_names
    ]
    if excluded:
        lines.extend(["", "重复目录-不参与排行", *excluded])
    return lines


def format_ranking_lines(success_lines: Iterable[str]) -> list[str]:
    counts = Counter(
        line.split(maxsplit=1)[0]
        for line in success_lines
        if line.strip() and line.split(maxsplit=1)[0] in WUXING_ORDER
    )
    ordered = sorted(
        counts.items(),
        key=lambda item: (-item[1], WUXING_ORDER.index(item[0])),
    )
    lines = ["", RANKING_HEADER]
    rank = 0
    previous_count = None
    for index, (content, count) in enumerate(ordered, start=1):
        if count != previous_count:
            rank = index
            previous_count = count
        lines.append(f"{content}\t{count}\t{rank}")
    return lines if ordered else []


def format_success_output_lines(success_lines: Iterable[str]) -> list[str]:
    lines = list(success_lines)
    try:
        excluded_index = lines.index("重复目录-不参与排行")
    except ValueError:
        excluded_index = len(lines)
    return lines + format_ranking_lines(lines[:excluded_index])
