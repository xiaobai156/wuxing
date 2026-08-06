import unittest

from wuxing.config.site_loader import load_site_configs
from wuxing.domain.enums import FailureCode, ResultStatus, SourceKind, WritePolicy
from wuxing.domain.errors import ConfigError, FetchError
from wuxing.domain.models import ScrapeRequest, SourceDocument
from wuxing.registry import build_site_registry
from wuxing.services.scrape import LiveSourceGateway, ScrapeService
from types import SimpleNamespace


class FakeSourceGateway:
    def __init__(self, documents):
        self.documents = tuple(documents)
        self.calls = []

    def fetch(self, rule, request):
        self.calls.append((rule.site_id, request.periods))
        return self.documents

    def fetch_fallback(self, rule, request):
        self.calls.append(("fallback", rule.site_id, request.periods))
        return self.documents


class Api404Gateway(FakeSourceGateway):
    def fetch(self, rule, request):
        self.calls.append((rule.site_id, request.periods))
        raise FetchError("HTTP抓取失败：HTTP 404")


class InvalidApiGateway(FakeSourceGateway):
    def fetch(self, rule, request):
        raise FetchError("article API方向字段缺失，拒绝解析")


class ScrapeServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sites = load_site_configs("sites.json", allow_legacy=True)
        cls.registry = build_site_registry(cls.sites)

    def request(self, period=209):
        return ScrapeRequest(
            periods=(period,),
            write_policy=WritePolicy.READ_ONLY,
        )

    def source(self, text):
        return SourceDocument(
            document_id="fixture-doc",
            url="https://example.com/topic/1",
            source_kind=SourceKind.API,
            text=text,
            order=0,
            record_id="6a20da1dca6da63e15d01fc8",
        )

    def test_service_returns_success_from_one_authoritative_candidate(self):
        site = next(site for site in self.sites if site.name == "典则俊雅")
        gateway = FakeSourceGateway((self.source("209期『典则俊雅』绝杀一行【木行】"),))
        result = ScrapeService(self.registry, gateway).scrape(site.site_id, self.request())
        self.assertEqual(result.status, ResultStatus.SUCCESS)
        self.assertEqual(result.candidate.wuxing, "木行")
        self.assertEqual(gateway.calls, [(site.site_id, (209,))])

    def test_service_rejects_conflicting_candidates_without_success(self):
        site = next(site for site in self.sites if site.name == "典则俊雅")
        gateway = FakeSourceGateway((self.source(
            "209期『典则俊雅』绝杀一行【木行】\n"
            "209期『典则俊雅』绝杀一行【火行】"
        ),))
        result = ScrapeService(self.registry, gateway).scrape(site.site_id, self.request())
        self.assertEqual(result.status, ResultStatus.FAILURE)
        self.assertEqual(result.failure_code.value, "TARGET_CONFLICT")
        self.assertIsNone(result.candidate)

    def test_api_404_uses_browser_fallback_once(self):
        site = next(site for site in self.sites if site.name == "典则俊雅")
        gateway = Api404Gateway((self.source("209期『典则俊雅』绝杀一行【木行】"),))
        result = ScrapeService(self.registry, gateway).scrape(site.site_id, self.request())
        self.assertEqual(result.status, ResultStatus.SUCCESS)
        self.assertEqual(result.attempts, 2)
        self.assertEqual(gateway.calls, [(site.site_id, (209,)), ("fallback", site.site_id, (209,))])

    def test_valid_api_record_missing_target_does_not_use_browser_fallback(self):
        site = next(site for site in self.sites if site.name == "典则俊雅")
        gateway = FakeSourceGateway((self.source("208期『典则俊雅』绝杀一行【木行】"),))

        result = ScrapeService(self.registry, gateway).scrape(site.site_id, self.request(209))

        self.assertEqual(result.failure_code.value, "TARGET_NOT_FOUND")
        self.assertEqual(result.attempts, 1)
        self.assertEqual(gateway.calls, [(site.site_id, (209,))])

    def test_invalid_article_api_record_has_specific_failure_code(self):
        site = next(site for site in self.sites if site.name == "典则俊雅")
        result = ScrapeService(self.registry, InvalidApiGateway(())).scrape(site.site_id, self.request())
        self.assertEqual(result.failure_code.value, "API_RECORD_INVALID")

    def test_scrape_service_rejects_multi_period_direct_call(self):
        site = next(site for site in self.sites if site.name == "典则俊雅")
        request = ScrapeRequest(periods=(208, 209), write_policy=WritePolicy.READ_ONLY)
        with self.assertRaisesRegex(ConfigError, "单次只接受一个期数"):
            ScrapeService(self.registry, FakeSourceGateway(())).scrape(site.site_id, request)

    def test_live_gateway_initializes_with_injected_transports(self):
        http = SimpleNamespace(fetch_text=lambda *_args: "")
        browser = SimpleNamespace(fetch=lambda *_args: ())
        gateway = LiveSourceGateway(http_client=http, browser_source=browser)
        self.assertIs(gateway.http_client, http)
        self.assertIs(gateway.browser_source, browser)

    def test_browser_fallback_helpers_respect_dynamic_article_identity(self):
        dynamic_site = next(site for site in self.sites if "/article/" in site.url)
        static_site = next(site for site in self.sites if "/article/" not in site.url)
        dynamic_rule = self.registry.require(dynamic_site.site_id)
        static_rule = self.registry.require(static_site.site_id)

        self.assertTrue(LiveSourceGateway._browser_fallback_allowed(dynamic_rule))
        self.assertFalse(LiveSourceGateway._browser_fallback_allowed(static_rule))
        self.assertFalse(ScrapeService._can_fallback_exception(static_rule, FetchError("HTTP 404")))

    def test_failure_code_mapping_keeps_transport_diagnostics_specific(self):
        cases = (
            (ConfigError("bad config"), FailureCode.CONFIG_ERROR),
            (FetchError("OCR脚本执行失败"), FailureCode.OCR_UNVERIFIED),
            (FetchError("记录ID格式无效"), FailureCode.INVALID_RECORD_ID),
            (FetchError("article API字段缺失，拒绝解析"), FailureCode.API_RECORD_INVALID),
            (FetchError("timeout"), FailureCode.FETCH_TIMEOUT),
            (FetchError("TLS handshake failed"), FailureCode.TLS_ERROR),
            (FetchError("HTTP 500"), FailureCode.HTTP_ERROR),
            (FetchError("页面是空壳"), FailureCode.EMPTY_DOCUMENT),
            (FetchError("专属锚点缺失"), FailureCode.ENTRY_NOT_FOUND),
            (FetchError("record id mismatch"), FailureCode.RECORD_ID_MISMATCH),
            (RuntimeError("unexpected"), FailureCode.INTERNAL_ERROR),
        )
        for exception, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(ScrapeService._failure_code(exception), expected)


if __name__ == "__main__":
    unittest.main()
