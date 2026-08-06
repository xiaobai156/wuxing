from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import threading
import time
from typing import Iterable, Protocol

from wuxing.domain.enums import FailureCode, FetchStrategy, ResultStatus, RunMode, WritePolicy
from wuxing.domain.errors import CacheError, ConfigError, FetchError
from wuxing.domain.models import ScrapeRequest, ScrapeResult, SiteConfig, SourceDocument
from wuxing.config.settings import DEFAULT_BROWSER_WORKERS
from wuxing.registry import SiteRegistry, SiteRule
from wuxing.sources.browser import BrowserSource, SeleniumBrowserBackend
from wuxing.sources.click_through import ClickThroughSource
from wuxing.sources.documents import DocumentCollector
from wuxing.sources.http import RequestsHttpClient
from wuxing.sources.spa import spa_api_urls, validate_spa_profile
from wuxing.storage.history_cache import HistoryCacheRepository, HistoryUpdate
from wuxing.validation.result import ValidationDecision, validate_scrape_candidates


class SourceGateway(Protocol):
    def fetch(self, rule: SiteRule, request: ScrapeRequest) -> tuple[SourceDocument, ...]: ...

    def fetch_fallback(self, rule: SiteRule, request: ScrapeRequest) -> tuple[SourceDocument, ...]: ...


class LiveSourceGateway:
    """Real HTTP/browser transport; it never decides the final 五行 result."""

    def __init__(
        self,
        http_client: RequestsHttpClient | None = None,
        browser_source: BrowserSource | None = None,
    ):
        self.http_client = http_client or RequestsHttpClient()
        self.browser_source = browser_source or BrowserSource(SeleniumBrowserBackend())
        self.documents = DocumentCollector(self.http_client.fetch_text)
        self.click_through = ClickThroughSource(self.http_client.fetch_text)
        self._browser_slots = threading.BoundedSemaphore(DEFAULT_BROWSER_WORKERS)

    def fetch(self, rule: SiteRule, request: ScrapeRequest) -> tuple[SourceDocument, ...]:
        period = request.period
        site = rule.site
        if rule.fetch_strategy is FetchStrategy.ARTICLE_API:
            if rule.api_decoder is None or not site.api_url:
                raise ConfigError(f"站点缺少 article API 解码器：{site.name}")
            return rule.api_decoder(self.http_client.fetch_text(site.api_url, request.timeout_seconds))
        if rule.fetch_strategy is FetchStrategy.SPA_API:
            profile_url, forums_url = spa_api_urls(site)
            import json

            profile = json.loads(self.http_client.fetch_text(profile_url, request.timeout_seconds))
            validate_spa_profile(profile, site)
            payload = self.http_client.fetch_text(forums_url, request.timeout_seconds)
            if rule.api_decoder is None:
                raise ConfigError(f"站点缺少 SPA API 解码器：{site.name}")
            return rule.api_decoder(payload)
        if rule.fetch_strategy is FetchStrategy.BROWSER_FIRST:
            return self._fetch_browser(rule, request)
        if rule.fetch_strategy is FetchStrategy.CLICK_THROUGH:
            return self.click_through.fetch(site, period, request.timeout_seconds)
        return self.documents.collect(site.url, request.timeout_seconds)

    def fetch_fallback(self, rule: SiteRule, request: ScrapeRequest) -> tuple[SourceDocument, ...]:
        if not self._browser_fallback_allowed(rule):
            raise FetchError(f"站点不允许浏览器兜底：{rule.site.name}")
        return self._fetch_browser(rule, request, fallback=True)

    def _fetch_browser(
        self,
        rule: SiteRule,
        request: ScrapeRequest,
        fallback: bool = False,
    ) -> tuple[SourceDocument, ...]:
        with self._browser_slots:
            return self.browser_source.fetch(
                rule.site,
                request.period,
                max(request.timeout_seconds, 20) if fallback else request.timeout_seconds,
                request.show_browser,
                rule.browser_plan,
            )

    @staticmethod
    def _browser_fallback_allowed(rule: SiteRule) -> bool:
        return (
            rule.fetch_strategy in {
                FetchStrategy.ARTICLE_API,
                FetchStrategy.SPA_API,
                FetchStrategy.HTTP_THEN_BROWSER,
            }
            and "/article/" in rule.site.url
        )


@dataclass(frozen=True)
class _Attempt:
    documents: tuple[SourceDocument, ...]
    validation: ValidationDecision


@dataclass(frozen=True)
class CacheUpdateReport:
    updated_sites: int = 0
    errors: tuple[str, ...] = ()


class ScrapeService:
    def __init__(
        self,
        registry: SiteRegistry,
        source_gateway: SourceGateway,
        cache_repository: HistoryCacheRepository | None = None,
    ):
        self.registry = registry
        self.source_gateway = source_gateway
        self.cache_repository = cache_repository

    def scrape(self, site_id: str, request: ScrapeRequest) -> ScrapeResult:
        if len(request.periods) != 1:
            raise ConfigError("ScrapeService 单次只接受一个期数，多期由批量服务逐期调用")
        rule = self.registry.require(site_id)
        started = time.monotonic()
        attempts = 0
        documents: tuple[SourceDocument, ...] = ()
        try:
            attempts += 1
            documents = self.source_gateway.fetch(rule, request)
            attempt = self._validate(rule, request.period, documents)
            if self._needs_browser_fallback(rule, attempt.validation):
                attempts += 1
                documents = self.source_gateway.fetch_fallback(rule, request)
                attempt = self._validate(rule, request.period, documents)
            result = self._result(rule.site, request.period, attempt, documents, started, attempts)
            return result
        except Exception as exc:
            if attempts == 1 and self._can_fallback_exception(rule, exc):
                try:
                    attempts += 1
                    documents = self.source_gateway.fetch_fallback(rule, request)
                    attempt = self._validate(rule, request.period, documents)
                    result = self._result(rule.site, request.period, attempt, documents, started, attempts)
                    return result
                except Exception as fallback_exc:
                    exc = fallback_exc
            return ScrapeResult.failure(
                site=rule.site,
                period=request.period,
                code=self._failure_code(exc),
                reason=self._reason(exc),
                elapsed_seconds=time.monotonic() - started,
                documents=documents,
                attempts=max(attempts, 1),
            )

    def update_cache(
        self,
        results: Iterable[ScrapeResult],
        request: ScrapeRequest,
    ) -> CacheUpdateReport:
        """Persist finalized single-period results without changing their status."""
        results = tuple(results)
        if request.write_policy is not WritePolicy.UPDATE_CACHE:
            return CacheUpdateReport()
        successful_results = tuple(
            result
            for result in results
            if result.status is ResultStatus.SUCCESS and result.candidate is not None
        )
        if not successful_results:
            return CacheUpdateReport()
        if request.mode is not RunMode.SINGLE:
            return CacheUpdateReport(
                errors=tuple(
                    self._cache_error(result, "只有单期正式成功允许更新 recent_10_cache.json")
                    for result in successful_results
                ),
            )
        if self.cache_repository is None:
            return CacheUpdateReport(
                errors=tuple(
                    self._cache_error(result, "未配置缓存仓库")
                    for result in successful_results
                ),
            )

        updated_sites = 0
        errors: list[str] = []
        for result in successful_results:
            try:
                self._apply_cache_update(result)
            except Exception as exc:
                errors.append(self._cache_error(result, str(exc)))
            else:
                updated_sites += 1
        return CacheUpdateReport(updated_sites=updated_sites, errors=tuple(errors))

    def _apply_cache_update(self, result: ScrapeResult) -> None:
        if not result.evidence.all_pass:
            raise CacheError("成功结果缺少完整验证回执")
        if result.candidate is None:
            raise CacheError("成功结果缺少候选")
        source_documents = [
            document
            for document in result.documents
            if document.document_id == result.candidate.source_document_id
        ]
        if len(source_documents) != 1:
            raise CacheError("成功候选没有唯一来源文档")
        source_document = source_documents[0]
        source_digest = (
            source_document.content_sha256
            if source_document is not None
            else hashlib.sha256(result.candidate.raw.encode("utf-8")).hexdigest()
        )
        self.cache_repository.apply_updates([HistoryUpdate(
            site_id=result.site.site_id,
            name=result.site.name,
            url=result.site.url,
            region=result.site.region,
            period=result.period,
            wuxing=result.candidate.wuxing,
            source_digest=source_digest,
            rule_version=result.candidate.rule_version,
            captured_at=datetime.now(timezone.utc).isoformat(),
        )])

    @staticmethod
    def _cache_error(result: ScrapeResult, reason: str) -> str:
        return f"{result.site.name} {result.period}期缓存更新未完成：{reason}"

    @staticmethod
    def _validate(rule: SiteRule, period: int, documents: tuple[SourceDocument, ...]) -> _Attempt:
        authoritative = rule.select_authority(documents, period)
        candidates = rule.parse(authoritative)
        validation = validate_scrape_candidates(rule.site, period, candidates, authoritative)
        return _Attempt(authoritative, validation)

    @staticmethod
    def _result(
        site: SiteConfig,
        period: int,
        attempt: _Attempt,
        original_documents: tuple[SourceDocument, ...],
        started: float,
        attempts: int,
    ) -> ScrapeResult:
        elapsed = time.monotonic() - started
        if attempt.validation.passed:
            return ScrapeResult.success(
                site=site,
                period=period,
                candidate=attempt.validation.candidate,
                elapsed_seconds=elapsed,
                evidence=attempt.validation.evidence,
                documents=original_documents,
                attempts=attempts,
            )
        return ScrapeResult.failure(
            site=site,
            period=period,
            code=attempt.validation.failure_code or FailureCode.INTERNAL_ERROR,
            reason=attempt.validation.reason,
            elapsed_seconds=elapsed,
            evidence=attempt.validation.evidence,
            documents=original_documents,
            attempts=attempts,
        )

    @staticmethod
    def _needs_browser_fallback(rule: SiteRule, validation: ValidationDecision) -> bool:
        return (
            validation.failure_code is FailureCode.EMPTY_DOCUMENT
            and rule.fetch_strategy in {
                FetchStrategy.ARTICLE_API,
                FetchStrategy.SPA_API,
                FetchStrategy.HTTP_THEN_BROWSER,
            }
            and "/article/" in rule.site.url
        )

    @classmethod
    def _can_fallback_exception(cls, rule: SiteRule, exc: Exception) -> bool:
        if not cls._dynamic_browser_rule(rule):
            return False
        message = f"{type(exc).__name__}: {exc}".lower()
        return "404" in message or "空壳" in message

    @staticmethod
    def _dynamic_browser_rule(rule: SiteRule) -> bool:
        return (
            rule.fetch_strategy in {
                FetchStrategy.ARTICLE_API,
                FetchStrategy.SPA_API,
                FetchStrategy.HTTP_THEN_BROWSER,
            }
            and "/article/" in rule.site.url
        )

    @staticmethod
    def _failure_code(exc: Exception) -> FailureCode:
        message = f"{type(exc).__name__}: {exc}".lower()
        if isinstance(exc, ConfigError):
            return FailureCode.CONFIG_ERROR
        if "ocr" in message or "图像识别" in message or "图片识别" in message:
            return FailureCode.OCR_UNVERIFIED
        if "记录id格式无效" in message:
            return FailureCode.INVALID_RECORD_ID
        if "article api" in message and ("字段" in message or "拒绝解析" in message):
            return FailureCode.API_RECORD_INVALID
        if "timeout" in message or "timed out" in message:
            return FailureCode.FETCH_TIMEOUT
        if any(marker in message for marker in ("ssl", "tls", "handshake", "certificate")):
            return FailureCode.TLS_ERROR
        if "404" in message or "http" in message:
            return FailureCode.HTTP_ERROR
        if "empty" in message or "空内容" in message or "空壳" in message:
            return FailureCode.EMPTY_DOCUMENT
        if "锚点" in message or "入口" in message or "专属" in message:
            return FailureCode.ENTRY_NOT_FOUND
        if "id" in message and ("record" in message or "文章" in message):
            return FailureCode.RECORD_ID_MISMATCH
        return FailureCode.INTERNAL_ERROR

    @staticmethod
    def _reason(exc: Exception) -> str:
        return f"{type(exc).__name__}: {exc}"


__all__ = ["CacheUpdateReport", "LiveSourceGateway", "ScrapeService", "SourceGateway"]
