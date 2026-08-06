import unittest

from wuxing.domain.enums import Region, SourceKind
from wuxing.domain.errors import FetchError
from wuxing.domain.models import SiteConfig
from wuxing.sources.browser import BrowserCapture, BrowserPlan, BrowserSource


class FakeBrowserBackend:
    def __init__(self, capture: BrowserCapture):
        self._capture = capture

    def capture(self, site, period, timeout, show_browser, plan):
        return self._capture


class BrowserSourceTests(unittest.TestCase):
    def test_browser_source_preserves_rendered_document_identity(self):
        site = SiteConfig("site-a", "甲站", "https://example.com/topic/1", Region.TOP, "a.v1")
        capture = BrowserCapture(
            current_url=site.url,
            page_source="<html>209期【木行】</html>",
            body_text="209期【木行】",
            ocr_entries=(),
        )

        documents = BrowserSource(FakeBrowserBackend(capture)).fetch(site, 209, 20, False)

        self.assertEqual(len(documents), 2)
        self.assertTrue(all(document.source_kind is SourceKind.BROWSER for document in documents))
        self.assertEqual(
            {dict(document.metadata)["capture_part"] for document in documents},
            {"page_source", "body"},
        )
        self.assertTrue(all(document.rendered for document in documents))

    def test_article_browser_capture_rejects_changed_record_id(self):
        site = SiteConfig(
            "site-a",
            "甲站",
            "https://example.com/article/manager/6a0000000000000000000001",
            Region.BOTTOM,
            "article.a.v1",
        )
        capture = BrowserCapture(
            current_url="https://example.com/article/manager/6a0000000000000000000002",
            page_source="6a0000000000000000000001 甲站 209期绝杀一行【木行】",
            body_text="甲站 209期【木行】",
            record_id="6a0000000000000000000002",
            record_text="甲站 209期绝杀一行【木行】",
            ocr_entries=(),
        )

        with self.assertRaises(FetchError):
            BrowserSource(FakeBrowserBackend(capture)).fetch(site, 209, 20, False)

    def test_article_browser_capture_requires_target_anchor(self):
        site = SiteConfig(
            "site-a",
            "甲站",
            "https://example.com/article/manager/6a0000000000000000000001",
            Region.BOTTOM,
            "article.a.v1",
        )
        capture = BrowserCapture(
            current_url=site.url,
            page_source="6a0000000000000000000001 甲站 209期【木行】",
            body_text="甲站 209期【木行】",
            record_id="6a0000000000000000000001",
            record_text="甲站 209期【木行】",
            ocr_entries=(),
        )

        with self.assertRaises(FetchError):
            BrowserSource(FakeBrowserBackend(capture)).fetch(site, 209, 20, False)

    def test_dynamic_browser_source_only_exposes_exact_record_scope(self):
        site = SiteConfig(
            "site-a",
            "甲站",
            "https://example.com/article/manager/6a0000000000000000000001",
            Region.BOTTOM,
            "article.a.v1",
        )
        capture = BrowserCapture(
            current_url=site.url,
            page_source=(
                "6a0000000000000000000001 甲站 209期绝杀一行【木行】 "
                "6a0000000000000000000002 甲站 209期绝杀一行【火行】"
            ),
            body_text="甲站 209期绝杀一行【木行】 甲站 209期绝杀一行【火行】",
            record_id="6a0000000000000000000001",
            record_text="6a0000000000000000000001 甲站 209期绝杀一行【木行】",
            ocr_entries=(),
        )

        documents = BrowserSource(FakeBrowserBackend(capture)).fetch(site, 209, 20, False)

        self.assertEqual(len(documents), 1)
        self.assertEqual(dict(documents[0].metadata)["capture_part"], "record")
        self.assertIn("木行", documents[0].text)
        self.assertNotIn("火行", documents[0].text)

    def test_dynamic_browser_capture_without_exact_record_scope_is_rejected(self):
        site = SiteConfig(
            "site-a",
            "甲站",
            "https://example.com/article/manager/6a0000000000000000000001",
            Region.BOTTOM,
            "article.a.v1",
        )
        capture = BrowserCapture(
            current_url=site.url,
            page_source="6a0000000000000000000001 甲站 209期绝杀一行【木行】",
            body_text="甲站 209期绝杀一行【木行】",
            ocr_entries=(),
        )

        with self.assertRaisesRegex(FetchError, "唯一目标记录正文"):
            BrowserSource(FakeBrowserBackend(capture)).fetch(site, 209, 20, False)

    def test_dynamic_browser_capture_rejects_nested_other_record_id(self):
        site = SiteConfig(
            "site-a",
            "甲站",
            "https://example.com/article/manager/6a0000000000000000000001",
            Region.BOTTOM,
            "article.a.v1",
        )
        capture = BrowserCapture(
            current_url=site.url,
            page_source="6a0000000000000000000001 甲站 209期绝杀一行【木行】",
            body_text="甲站 209期绝杀一行【木行】",
            record_id="6a0000000000000000000001",
            record_text=(
                "6a0000000000000000000001 甲站 209期绝杀一行【木行】 "
                "6a0000000000000000000002 其他文章"
            ),
            ocr_entries=(),
        )

        with self.assertRaisesRegex(FetchError, "包含其他文章ID"):
            BrowserSource(FakeBrowserBackend(capture)).fetch(site, 209, 20, False)

    def test_browser_capture_rejects_wrong_clicked_article_by_required_anchor(self):
        site = SiteConfig("site-a", "八级心动", "https://example.com/#am", Region.TOP, "baji.v1")
        capture = BrowserCapture(
            current_url="https://example.com/topic/793011.html",
            page_source="来者不笑 211期绝杀一行【木行】",
            body_text="来者不笑 211期绝杀一行【木行】",
            ocr_entries=(),
        )

        with self.assertRaises(FetchError):
            BrowserSource(FakeBrowserBackend(capture)).fetch(
                site,
                211,
                20,
                False,
                BrowserPlan(required_text_pattern=r"八级心动.{0,40}?绝杀\s*一\s*行"),
            )


if __name__ == "__main__":
    unittest.main()
