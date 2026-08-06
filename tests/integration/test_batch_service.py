import unittest

from wuxing.config.site_loader import load_site_configs
from wuxing.domain.enums import ResultStatus, SourceKind, WritePolicy
from wuxing.domain.models import ScrapeRequest, SourceDocument
from wuxing.registry import build_site_registry
from wuxing.services.batch import BatchService
from wuxing.services.scrape import ScrapeService
from wuxing.sources.article_api import article_id_from_url


class MappingGateway:
    def __init__(self, texts):
        self.texts = texts

    def fetch(self, rule, request):
        return (SourceDocument(
            document_id=f"doc-{rule.site_id}",
            url=rule.site.url,
            source_kind=SourceKind.API,
            text=self.texts[rule.site.name],
            order=0,
            record_id=article_id_from_url(rule.site.url),
        ),)

    def fetch_fallback(self, rule, request):
        return self.fetch(rule, request)


class BatchServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sites = load_site_configs("sites.json", allow_legacy=True)
        cls.registry = build_site_registry(sites)
        cls.sites = [next(site for site in sites if site.name == name) for name in ("典则俊雅", "齐天大胜")]

    def test_batch_calls_single_service_and_preserves_site_results(self):
        gateway = MappingGateway({
            "典则俊雅": "209期『典则俊雅』绝杀一行【木行】",
            "齐天大胜": "209期『齐天大胜』四行中特【金、木、水、土】",
        })
        service = ScrapeService(self.registry, gateway)
        batch = BatchService(service).run(
            [site.site_id for site in self.sites],
            ScrapeRequest(periods=(209,), write_policy=WritePolicy.READ_ONLY),
            max_workers=2,
        )
        self.assertEqual([result.site.name for result in batch.results], ["典则俊雅", "齐天大胜"])
        self.assertTrue(all(result.status is ResultStatus.SUCCESS for result in batch.results))


if __name__ == "__main__":
    unittest.main()
