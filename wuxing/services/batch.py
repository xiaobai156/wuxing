from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from typing import Callable, Iterable

from wuxing.config.settings import DEFAULT_HTTP_WORKERS
from wuxing.domain.models import BatchResult, ScrapeRequest, ScrapeResult

from .scrape import ScrapeService


ProgressCallback = Callable[[int, int, BatchResult, float, str], None]


class BatchService:
    def __init__(self, scrape_service: ScrapeService):
        self.scrape_service = scrape_service

    def run(
        self,
        site_ids: Iterable[str],
        request: ScrapeRequest,
        max_workers: int = DEFAULT_HTTP_WORKERS,
        progress_callback: ProgressCallback | None = None,
    ) -> BatchResult:
        site_ids = tuple(site_ids)
        if not site_ids:
            return BatchResult(())
        started = time.monotonic()
        indexed: dict[object, int] = {}
        results: list[ScrapeResult | None] = [None] * len(site_ids)
        with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(site_ids)))) as executor:
            futures = {
                executor.submit(self.scrape_service.scrape, site_id, request): index
                for index, site_id in enumerate(site_ids)
            }
            for future in as_completed(futures):
                index = futures[future]
                result = future.result()
                results[index] = result
                indexed[future] = index
                if progress_callback is not None:
                    complete = tuple(item for item in results if item is not None)
                    progress_callback(
                        len(complete),
                        len(site_ids),
                        BatchResult(complete),
                        time.monotonic() - started,
                        result.site.name,
                    )
        return BatchResult(tuple(result for result in results if result is not None))


__all__ = ["BatchService", "ProgressCallback"]
