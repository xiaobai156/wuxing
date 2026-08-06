from __future__ import annotations

from dataclasses import dataclass
import re

from wuxing.domain.enums import FailureCode
from wuxing.domain.models import Candidate, SiteConfig, SourceDocument, ValidationEvidence

from .authority import validate_authority_boundary
from .conflict import detect_period_conflict
from .position import evaluate_position_window


TARGET_ANCHOR_RE = re.compile(
    r"(?:绝杀|必杀|精杀|稳杀|死禁|殺|杀)\s*[（(]?\s*[一1①➀⑴㈠⒈]\s*[.。．、]?\s*[)）]?\s*行"
    r"|[一二三四五①②③④⑤\d]\s*行\s*中\s*特|五\s*[丢表]\s*主\s*四\s*行"
)


@dataclass(frozen=True)
class ValidationDecision:
    passed: bool
    candidate: Candidate | None
    failure_code: FailureCode | None
    reason: str
    evidence: ValidationEvidence


def _failure(
    code: FailureCode,
    reason: str,
    evidence: ValidationEvidence,
) -> ValidationDecision:
    return ValidationDecision(
        passed=False,
        candidate=None,
        failure_code=code,
        reason=reason,
        evidence=evidence,
    )


def validate_scrape_candidates(
    site: SiteConfig,
    period: int,
    candidates: tuple[Candidate, ...] | list[Candidate],
    authoritative_documents: tuple[SourceDocument, ...] | list[SourceDocument],
) -> ValidationDecision:
    candidates = tuple(candidates)
    documents = tuple(authoritative_documents)
    period_candidates = tuple(candidate for candidate in candidates if candidate.period == period)
    evidence = ValidationEvidence(
        period_pass=bool(period_candidates),
        authority_pass=False,
        keyword_pass=bool(period_candidates),
        wuxing_pass=all(candidate.wuxing in {"金行", "木行", "水行", "火行", "土行"} for candidate in period_candidates),
        conflict_pass=False,
    )
    if not period_candidates:
        return _failure(
            FailureCode.TARGET_NOT_FOUND,
            f"页面里未找到 {period}期的有效候选",
            evidence,
        )

    position = evaluate_position_window(candidates, site.region, period)
    if not position.passed:
        return _failure(
            FailureCode.POSITION_WINDOW,
            position.reason,
            ValidationEvidence(
                period_pass=True,
                position_pass=False,
                authority_pass=False,
                keyword_pass=False,
                wuxing_pass=True,
                conflict_pass=False,
                details=(position.reason,),
            ),
        )

    window_orders = set(position.window_orders)
    window_candidates = tuple(candidate for candidate in candidates if candidate.order in window_orders)
    window_period_candidates = tuple(
        candidate for candidate in window_candidates if candidate.period == period
    )
    keyword_pass = all(
        bool(candidate.anchor and candidate.keyword and TARGET_ANCHOR_RE.search(candidate.raw))
        for candidate in window_period_candidates
    )
    if not keyword_pass:
        return _failure(
            FailureCode.KEYWORD_MISMATCH,
            f"{period}期候选缺少同块栏目锚点或关键词",
            ValidationEvidence(
                period_pass=True,
                position_pass=True,
                authority_pass=False,
                keyword_pass=False,
                wuxing_pass=True,
                conflict_pass=False,
                details=(position.reason,),
            ),
        )

    authority_results = tuple(
        validate_authority_boundary(documents, candidate)
        for candidate in window_period_candidates
    )
    if not all(result.passed for result in authority_results):
        detail = next(result.reason for result in authority_results if not result.passed)
        return _failure(
            FailureCode.AUTHORITY_NOT_UNIQUE,
            detail,
            ValidationEvidence(
                period_pass=True,
                position_pass=True,
                authority_pass=False,
                keyword_pass=True,
                wuxing_pass=True,
                conflict_pass=False,
                details=(position.reason,),
            ),
        )

    conflict = detect_period_conflict(window_candidates, period)
    if conflict.conflict:
        return _failure(
            FailureCode.TARGET_CONFLICT,
            conflict.reason,
            ValidationEvidence(
                period_pass=True,
                position_pass=True,
                authority_pass=True,
                keyword_pass=True,
                wuxing_pass=True,
                conflict_pass=False,
                details=(position.reason,),
            ),
        )
    if conflict.duplicate:
        return _failure(
            FailureCode.DUPLICATE_WUXING,
            conflict.reason,
            ValidationEvidence(
                period_pass=True,
                position_pass=True,
                authority_pass=True,
                keyword_pass=True,
                wuxing_pass=True,
                conflict_pass=False,
                details=(position.reason,),
            ),
        )

    evidence = ValidationEvidence(
        period_pass=True,
        position_pass=position.passed,
        authority_pass=True,
        keyword_pass=True,
        wuxing_pass=True,
        conflict_pass=True,
        details=(position.reason,),
    )
    if not position.passed:
        return _failure(FailureCode.POSITION_WINDOW, position.reason, evidence)

    return ValidationDecision(
        passed=True,
        candidate=period_candidates[0],
        failure_code=None,
        reason="期号、权威边界、方向窗口、五行和同期唯一性均通过",
        evidence=evidence,
    )
