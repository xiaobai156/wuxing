from __future__ import annotations

from dataclasses import dataclass

from wuxing.domain.models import Candidate


@dataclass(frozen=True)
class ConflictDecision:
    conflict: bool
    duplicate: bool
    wuxing_values: tuple[str, ...]
    candidate_count: int
    reason: str


def detect_period_conflict(
    candidates: tuple[Candidate, ...] | list[Candidate],
    period: int,
) -> ConflictDecision:
    target = tuple(candidate for candidate in candidates if candidate.period == period)
    values = tuple(dict.fromkeys(candidate.wuxing for candidate in target))
    conflict = len(values) > 1
    duplicate = len(target) > 1 and not conflict
    if conflict:
        reason = f"{period}期同站出现多个高可信候选且五行冲突：{'、'.join(values)}"
    elif duplicate:
        reason = f"{period}期同站出现{len(target)}个相同五行候选，来源边界不唯一"
    else:
        reason = f"{period}期候选唯一"
    return ConflictDecision(
        conflict=conflict,
        duplicate=duplicate,
        wuxing_values=values,
        candidate_count=len(target),
        reason=reason,
    )
