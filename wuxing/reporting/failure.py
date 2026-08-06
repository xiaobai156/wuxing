from collections import Counter
from collections.abc import Iterable

from wuxing.domain.enums import FailureCode, ResultStatus
from wuxing.domain.models import ScrapeResult


_STAGE_BY_CODE = {
    FailureCode.CONFIG_ERROR: "配置校验",
    FailureCode.FETCH_TIMEOUT: "网络抓取",
    FailureCode.TLS_ERROR: "网络抓取",
    FailureCode.HTTP_ERROR: "网络抓取",
    FailureCode.EMPTY_DOCUMENT: "页面内容校验",
    FailureCode.ENTRY_NOT_FOUND: "专属入口校验",
    FailureCode.RECORD_ID_MISMATCH: "文章记录校验",
    FailureCode.INVALID_RECORD_ID: "文章记录校验",
    FailureCode.API_RECORD_INVALID: "文章记录校验",
    FailureCode.AUTHORITY_NOT_UNIQUE: "栏目边界校验",
    FailureCode.TARGET_NOT_FOUND: "指定期数校验",
    FailureCode.POSITION_WINDOW: "指定期数校验",
    FailureCode.KEYWORD_MISMATCH: "指定期数校验",
    FailureCode.NON_STANDARD_WUXING: "指定期数校验",
    FailureCode.TARGET_CONFLICT: "同期唯一性校验",
    FailureCode.DUPLICATE_WUXING: "同期唯一性校验",
    FailureCode.OCR_UNVERIFIED: "OCR校验",
    FailureCode.CACHE_ERROR: "缓存更新",
    FailureCode.INTERNAL_ERROR: "内部处理",
}

_CATEGORY_BY_CODE = {
    FailureCode.CONFIG_ERROR: "配置错误",
    FailureCode.FETCH_TIMEOUT: "请求超时",
    FailureCode.TLS_ERROR: "TLS错误",
    FailureCode.HTTP_ERROR: "HTTP错误",
    FailureCode.EMPTY_DOCUMENT: "页面为空",
    FailureCode.ENTRY_NOT_FOUND: "专属入口缺失",
    FailureCode.RECORD_ID_MISMATCH: "文章ID不一致",
    FailureCode.INVALID_RECORD_ID: "记录ID无效",
    FailureCode.API_RECORD_INVALID: "API记录无效",
    FailureCode.AUTHORITY_NOT_UNIQUE: "栏目边界冲突",
    FailureCode.TARGET_NOT_FOUND: "指定期数缺失",
    FailureCode.POSITION_WINDOW: "方向范围外",
    FailureCode.KEYWORD_MISMATCH: "栏目字段错误",
    FailureCode.NON_STANDARD_WUXING: "五行值无效",
    FailureCode.TARGET_CONFLICT: "同期结果冲突",
    FailureCode.DUPLICATE_WUXING: "同期结果重复",
    FailureCode.OCR_UNVERIFIED: "OCR未验证",
    FailureCode.CACHE_ERROR: "缓存更新失败",
    FailureCode.INTERNAL_ERROR: "内部错误",
}


def _validated_failure(result: ScrapeResult) -> ScrapeResult:
    if result.status is not ResultStatus.FAILURE or result.failure_code is None:
        raise ValueError("只能格式化失败结果")
    return result


def _single_line(value: object) -> str:
    return " ".join(str(value).replace("\r", "\n").splitlines())


def format_failure_stage(result: ScrapeResult) -> str:
    result = _validated_failure(result)
    return _STAGE_BY_CODE.get(result.failure_code, "内部处理")


def format_failure_category(result: ScrapeResult) -> str:
    result = _validated_failure(result)
    return _CATEGORY_BY_CODE.get(result.failure_code, result.failure_code.value)


def format_failure_line(result: ScrapeResult) -> str:
    result = _validated_failure(result)
    return (
        f"失败 {_single_line(result.site.name)} {_single_line(result.site.url)} "
        f"方向: {result.site.region.value} 期数: {result.period}\n"
        f"阶段: {format_failure_stage(result)} 原因: {_single_line(result.reason)}"
    )


def format_failure_file_text(items: Iterable[str | ScrapeResult]) -> str:
    items = tuple(items)
    if not items:
        return ""
    if all(isinstance(item, ScrapeResult) for item in items):
        results = tuple(item for item in items if isinstance(item, ScrapeResult))
        entries = [format_failure_line(result) for result in results]
        category_counts = Counter(format_failure_category(result) for result in results)
        summary = "\n".join(
            ["失败分类统计"]
            + [f"{category} {count}条" for category, count in category_counts.items()]
        )
        return "\n\n".join(entries) + "\n\n" + summary + "\n"

    if any(isinstance(item, ScrapeResult) for item in items):
        raise TypeError("失败报告不能混用 ScrapeResult 和文本行")
    normalized = [str(item).strip() for item in items if str(item).strip()]
    return "\n\n".join(normalized) + ("\n" if normalized else "")


__all__ = [
    "format_failure_category",
    "format_failure_file_text",
    "format_failure_line",
    "format_failure_stage",
]
