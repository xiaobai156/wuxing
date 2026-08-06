import unittest

from wuxing.domain.enums import Region, SourceKind
from wuxing.domain.errors import FetchError
from wuxing.domain.models import SiteConfig
from wuxing.sources.click_through import ClickThroughSource


class FakeFetcher:
    def __init__(self, pages):
        self.pages = pages

    def __call__(self, url, timeout):
        return self.pages[url]


class ClickThroughSourceTests(unittest.TestCase):
    def setUp(self):
        self.site = SiteConfig(
            "site-male",
            "男儿本色",
            "https://example.com/list",
            Region.TOP,
            "male.v1",
        )

    def test_requires_one_exact_period_and_keyword_entry(self):
        fetcher = FakeFetcher({
            self.site.url: '<a href="/detail/209">209期：【男儿本色】★绝杀一行★实力见证</a>',
            "https://example.com/detail/209": "209期 男儿本色 绝杀一行【木行】",
        })
        documents = ClickThroughSource(fetcher).fetch(self.site, 209, 20)
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].source_kind, SourceKind.PAGE)
        self.assertIn("木行", documents[0].text)

    def test_duplicate_entries_are_rejected(self):
        fetcher = FakeFetcher({
            self.site.url: (
                '<a href="/a">209期：【男儿本色】★绝杀一行★实力见证</a>'
                '<a href="/b">209期：【男儿本色】★绝杀一行★实力见证</a>'
            ),
        })
        with self.assertRaises(FetchError):
            ClickThroughSource(fetcher).fetch(self.site, 209, 20)

    def test_accepts_site_generated_metadata_after_exact_entry_title(self):
        fetcher = FakeFetcher({
            self.site.url: (
                '<a href="/detail/209">209期：【男儿本色】☆绝杀一行☆实力见证！ '
                '百万资料库 1785542842</a>'
            ),
            "https://example.com/detail/209": "209期 男儿本色 绝杀一行【木行】",
        })

        documents = ClickThroughSource(fetcher).fetch(self.site, 209, 20)

        self.assertEqual(len(documents), 1)
        self.assertIn("木行", documents[0].text)


if __name__ == "__main__":
    unittest.main()
