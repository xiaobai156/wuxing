from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from wuxing.storage.history_cache import HistoryCacheRepository


@dataclass(frozen=True)
class DuplicateReport:
    candidate_name: str
    compared_site: str | None
    common_periods: tuple[int, ...]
    matching_periods: tuple[int, ...]
    longest_run: int
    status: str


def _longest_contiguous(periods: set[int]) -> int:
    if not periods:
        return 0
    longest = current = 1
    ordered = sorted(periods)
    for previous, current_period in zip(ordered, ordered[1:]):
        if current_period == previous + 1:
            current += 1
            longest = max(longest, current)
        else:
            current = 1
    return longest


class DuplicateService:
    def __init__(self, repository: HistoryCacheRepository):
        self.repository = repository

    def compare_history(
        self,
        candidate_name: str,
        candidate_history: Mapping[int, str],
    ) -> DuplicateReport:
        cache = self.repository.load()
        best = DuplicateReport(candidate_name, None, (), (), 0, "none")
        for site in cache["sites"]:
            if not isinstance(site, dict):
                continue
            history = site.get("history", [])
            if not isinstance(history, list):
                continue
            existing = {
                int(item["period"]): str(item["wuxing"])
                for item in history
                if isinstance(item, dict) and isinstance(item.get("period"), int)
            }
            common = set(candidate_history).intersection(existing)
            matching = {period for period in common if candidate_history[period] == existing[period]}
            longest = _longest_contiguous(matching)
            if longest > best.longest_run:
                status = "duplicate" if longest >= 6 else "suspect" if longest >= 3 else "none"
                best = DuplicateReport(
                    candidate_name=candidate_name,
                    compared_site=str(site.get("name", "")) or None,
                    common_periods=tuple(sorted(common)),
                    matching_periods=tuple(sorted(matching)),
                    longest_run=longest,
                    status=status,
                )
        return best


__all__ = ["DuplicateReport", "DuplicateService"]
