import unittest

import wuxing_crawler as legacy
from wuxing.parsers import kernel


class ParserKernelParityTests(unittest.TestCase):
    def assert_parser_parity(self, url: str, name: str, region: str, document: str):
        old_site = legacy.Site(url, region, False, name)
        new_site = kernel.Site(url, region, False, name)

        old = legacy.parse_candidates_for_site(document, old_site)
        new = kernel.parse_candidates_for_site(document, new_site)

        self.assertEqual(
            [(item.period, item.wuxing, item.order, item.raw) for item in new],
            [(item.period, item.wuxing, item.order, item.raw) for item in old],
        )

    def test_generic_topic_parser_matches_legacy(self):
        self.assert_parser_parity(
            "https://example.com/topic/1",
            "普通站",
            "top",
            "209期绝杀一行【木行】开：0000准\n208期绝杀一行【火行】开：鼠19准",
        )

    def test_yirujiwang_contiguous_boundary_matches_legacy(self):
        self.assert_parser_parity(
            "https://eebysckd.2go6k-y0pfv-fqbdsm.xyz:16677/topic/626030.html",
            "一如既往",
            "top",
            "一如既往 发表于\n209期精杀一行【木行】\n208期精杀一行【火行】\n"
            "1期精杀一行【土行】\n365期精杀一行【金行】\n209期精杀一行【水行】",
        )

    def test_manager_article_parser_matches_legacy(self):
        self.assert_parser_parity(
            "https://wigrzse.3acpt-tc9xa-kzxasm.xyz:29444/article/manager/6a20da1dca6da63e15d01fc8?url=pg",
            "典则俊雅",
            "bottom",
            "209期『典则俊雅』绝杀一行【木行】开：0000准\n208期『典则俊雅』绝杀一行【火行】开：鼠19准",
        )

    def test_authoritative_document_selection_matches_legacy(self):
        url = "https://eebysckd.2go6k-y0pfv-fqbdsm.xyz:16677/topic/626030.html"
        old_site = legacy.Site(url, "top", False, "一如既往")
        new_site = kernel.Site(url, "top", False, "一如既往")
        documents = [
            "document.writeln('aggregate') 一如既往 发表于\n209期精杀一行【水行】",
            "一如既往 发表于\n209期精杀一行【木行】\n208期精杀一行【火行】",
        ]

        old = legacy.site_authoritative_documents(documents, old_site, period=209)
        new = kernel.site_authoritative_documents(documents, new_site, period=209)

        self.assertEqual(new, old)


if __name__ == "__main__":
    unittest.main()
