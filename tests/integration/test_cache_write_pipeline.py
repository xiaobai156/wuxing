import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock

from wuxing.config.site_loader import load_site_configs
from wuxing.domain.enums import ResultStatus, RunMode, SourceKind, WritePolicy
from wuxing.domain.errors import CacheError
from wuxing.domain.models import Candidate, ScrapeRequest, SourceDocument, ValidationEvidence
from wuxing.registry import build_site_registry
from wuxing.services.scrape import ScrapeService
from wuxing.storage.history_cache import HistoryCacheRepository, HistoryUpdate


class CacheGateway:
    def fetch(self, rule, request):
        return (SourceDocument(
            document_id="cache-doc",
            url=rule.site.url,
            source_kind=SourceKind.API,
            text="209期『典则俊雅』绝杀一行【木行】",
            order=0,
            record_id="6a20da1dca6da63e15d01fc8",
        ),)

    def fetch_fallback(self, rule, request):
        return self.fetch(rule, request)


class CacheWritePipelineTests(unittest.TestCase):
    def setUp(self):
        self.sites = load_site_configs("sites.json", allow_legacy=True)
        self.site = next(site for site in self.sites if site.name == "典则俊雅")
        self.registry = build_site_registry(self.sites)

    def test_realtime_judgment_does_not_read_or_write_cache(self):
        repository = Mock()
        service = ScrapeService(self.registry, CacheGateway(), repository)
        request = ScrapeRequest(
            periods=(209,),
            write_policy=WritePolicy.UPDATE_CACHE,
        )

        result = service.scrape(self.site.site_id, request)

        self.assertEqual(result.status, ResultStatus.SUCCESS)
        repository.load.assert_not_called()
        repository.apply_updates.assert_not_called()

    def test_successful_single_result_updates_cache_only_after_explicit_commit(self):
        with TemporaryDirectory() as directory:
            repository = HistoryCacheRepository(Path(directory) / "recent_10_cache.json")
            service = ScrapeService(self.registry, CacheGateway(), repository)
            request = ScrapeRequest(
                periods=(209,),
                write_policy=WritePolicy.UPDATE_CACHE,
            )

            result = service.scrape(self.site.site_id, request)

            self.assertEqual(result.status, ResultStatus.SUCCESS)
            self.assertEqual(repository.load()["sites"], [])
            report = service.update_cache((result,), request)
            self.assertEqual(report.updated_sites, 1)
            self.assertEqual(report.errors, ())
            history = repository.load()["sites"][0]["history"]
            self.assertEqual(history[0]["period"], 209)

    def test_cache_conflict_does_not_change_realtime_result_and_reports_update_failure(self):
        with TemporaryDirectory() as directory:
            repository = HistoryCacheRepository(Path(directory) / "recent_10_cache.json")
            repository.apply_updates([HistoryUpdate(
                self.site.site_id,
                self.site.name,
                self.site.url,
                self.site.region,
                209,
                "火行",
                "old",
                "old.v1",
                "now",
            )])
            service = ScrapeService(self.registry, CacheGateway(), repository)
            request = ScrapeRequest(
                periods=(209,),
                write_policy=WritePolicy.UPDATE_CACHE,
            )

            result = service.scrape(self.site.site_id, request)

            self.assertEqual(result.status, ResultStatus.SUCCESS)
            self.assertEqual(result.candidate.wuxing, "木行")
            report = service.update_cache((result,), request)
            self.assertEqual(report.updated_sites, 0)
            self.assertEqual(len(report.errors), 1)
            self.assertIn("缓存更新未完成", report.errors[0])
            self.assertEqual(repository.load()["sites"][0]["history"][0]["wuxing"], "火行")

    def test_cache_update_skips_read_only_and_empty_result_batches(self):
        repository = Mock()
        service = ScrapeService(self.registry, CacheGateway(), repository)
        request = ScrapeRequest(periods=(209,), write_policy=WritePolicy.UPDATE_CACHE)
        result = service.scrape(self.site.site_id, request)

        read_only = ScrapeRequest(periods=(209,), write_policy=WritePolicy.READ_ONLY)
        self.assertEqual(service.update_cache((result,), read_only).errors, ())
        self.assertEqual(service.update_cache((), request).errors, ())
        repository.apply_updates.assert_not_called()

    def test_cache_update_reports_invalid_mode_and_missing_repository(self):
        service = ScrapeService(self.registry, CacheGateway())
        request = ScrapeRequest(periods=(209,), write_policy=WritePolicy.UPDATE_CACHE)
        result = service.scrape(self.site.site_id, request)

        multi = ScrapeRequest(
            periods=(209,),
            mode=RunMode.MULTI,
            write_policy=WritePolicy.UPDATE_CACHE,
        )
        report = service.update_cache((result,), multi)
        self.assertEqual(report.updated_sites, 0)
        self.assertIn("只有单期正式成功", report.errors[0])

        report = service.update_cache((result,), request)
        self.assertEqual(report.updated_sites, 0)
        self.assertIn("未配置缓存仓库", report.errors[0])

    def test_cache_update_rejects_incomplete_or_ambiguous_success_evidence(self):
        repository = Mock()
        service = ScrapeService(self.registry, CacheGateway(), repository)
        with self.assertRaisesRegex(CacheError, "完整验证回执"):
            service._apply_cache_update(SimpleNamespace(
                evidence=ValidationEvidence(),
                candidate=None,
            ))

        all_pass = ValidationEvidence(True, True, True, True, True, True)
        with self.assertRaisesRegex(CacheError, "缺少候选"):
            service._apply_cache_update(SimpleNamespace(
                evidence=all_pass,
                candidate=None,
            ))

        candidate = Candidate(
            period=209,
            wuxing="木行",
            source_document_id="duplicate-doc",
            order=0,
            raw="209期绝杀一行【木行】",
            rule_version="test.v1",
        )
        document = SourceDocument(
            document_id="duplicate-doc",
            url=self.site.url,
            source_kind=SourceKind.API,
            text=candidate.raw,
            order=0,
        )
        with self.assertRaisesRegex(CacheError, "唯一来源文档"):
            service._apply_cache_update(SimpleNamespace(
                evidence=all_pass,
                candidate=candidate,
                documents=(document, document),
            ))


if __name__ == "__main__":
    unittest.main()
