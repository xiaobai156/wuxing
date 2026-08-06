from collections.abc import Iterable

from wuxing.domain.enums import ResultStatus
from wuxing.domain.models import ScrapeResult


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
    lines.extend(["", *format_slow_site_lines(results)])
    return lines
