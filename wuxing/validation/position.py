from __future__ import annotations

from dataclasses import dataclass

from wuxing.domain.enums import Region
from wuxing.domain.models import Candidate


@dataclass(frozen=True)
class PositionDecision:
    passed: bool
    target_orders: tuple[int, ...]
    window_orders: tuple[int, ...]
    reason: str


def evaluate_position_window(
    candidates: tuple[Candidate, ...] | list[Candidate],
    region: Region,
    period: int,
    window_size: int = 3,
) -> PositionDecision:
    ordered = tuple(sorted(candidates, key=lambda candidate: candidate.order))
    window = ordered[:window_size] if region is Region.TOP else ordered[-window_size:]
    target = tuple(candidate for candidate in ordered if candidate.period == period)
    target_orders = tuple(candidate.order for candidate in target)
    window_orders = tuple(candidate.order for candidate in window)
    passed = bool(target) and all(candidate.order in window_orders for candidate in target)
    if passed:
        reason = f"{region.label}方向目标期位于前/后{window_size}条候选内"
    elif not target:
        reason = f"候选中未找到{period}期"
    else:
        reason = f"{region.label}方向只允许前/后{window_size}条，{period}期不在范围内"
    return PositionDecision(
        passed=passed,
        target_orders=target_orders,
        window_orders=window_orders,
        reason=reason,
    )
