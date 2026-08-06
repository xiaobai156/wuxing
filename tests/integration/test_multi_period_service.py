import unittest

from wuxing.config.site_loader import load_site_configs
from wuxing.domain.enums import SourceKind
from wuxing.domain.models import SourceDocument
from wuxing.registry import build_site_registry
from wuxing.services.multi_period import MultiPeriodService
from wuxing.services.scrape import ScrapeService


class PeriodGateway:
    def __init__(self):
        self.calls = []

    def fetch(self, rule, request):
        period = request.period
        self.calls.append(period)
        return (SourceDocument(
            document_id=f"doc-{period}",
            url=rule.site.url,
            source_kind=SourceKind.API,
            text=f"{period}期『典则俊雅』绝杀一行【木行】",
            order=0,
            record_id="6a20da1dca6da63e15d01fc8",
        ),)

    def fetch_fallback(self, rule, request):
        return self.fetch(rule, request)


class MultiPeriodServiceTests(unittest.TestCase):
    def test_any_success_stops_later_periods_and_does_not_need_cache(self):
        sites = load_site_configs("sites.json", allow_legacy=True)
        site = next(site for site in sites if site.name == "典则俊雅")
        registry = build_site_registry(sites)
        gateway = PeriodGateway()
        result = MultiPeriodService(ScrapeService(registry, gateway)).run(
            [site.site_id],
            (208, 209, 210),
            timeout_seconds=20,
        )
        self.assertEqual(gateway.calls, [208])
        self.assertEqual(result.successes[0].period, 208)
        self.assertEqual(result.all_failures, ())


if __name__ == "__main__":
    unittest.main()
