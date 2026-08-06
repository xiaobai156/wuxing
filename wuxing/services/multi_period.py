from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from wuxing.domain.enums import RunMode, WritePolicy
from wuxing.domain.models import ScrapeRequest, ScrapeResult

from .scrape import ScrapeService


@dataclass(frozen=True)
class MultiPeriodResult:
    attempts: tuple[ScrapeResult, ...]

    @property
    def successes(self) -> tuple[ScrapeResult, ...]:
        return tuple(result for result in self.attempts if result.candidate is not None)

    @property
    def failures(self) -> tuple[ScrapeResult, ...]:
        return tuple(result for result in self.attempts if result.candidate is None)

    @property
    def all_failures(self) -> tuple[tuple[ScrapeResult, ...], ...]:
        grouped: dict[str, list[ScrapeResult]] = {}
        for result in self.failures:
            grouped.setdefault(result.site.site_id, []).append(result)
        successful_sites = {result.site.site_id for result in self.successes}
        return tuple(
            tuple(results)
            for site_id, results in grouped.items()
            if site_id not in successful_sites
        )


class MultiPeriodService:
    def __init__(self, scrape_service: ScrapeService):
        self.scrape_service = scrape_service

    def run(
        self,
        site_ids: Iterable[str],
        periods: Iterable[int],
        timeout_seconds: int = 20,
        show_browser: bool = False,
    ) -> MultiPeriodResult:
        periods = tuple(periods)
        attempts: list[ScrapeResult] = []
        for site_id in site_ids:
            for period in periods:
                result = self.scrape_service.scrape(
                    site_id,
                    ScrapeRequest(
                        periods=(period,),
                        mode=RunMode.MULTI,
                        timeout_seconds=timeout_seconds,
                        show_browser=show_browser,
                        write_policy=WritePolicy.READ_ONLY,
                    ),
                )
                attempts.append(result)
                if result.candidate is not None:
                    break
        return MultiPeriodResult(tuple(attempts))


__all__ = ["MultiPeriodResult", "MultiPeriodService"]
