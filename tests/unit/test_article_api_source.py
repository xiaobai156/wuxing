import base64
import json
import unittest

from wuxing.domain.enums import Region, SourceKind
from wuxing.domain.errors import FetchError
from wuxing.domain.models import SiteConfig
from wuxing.sources.article_api import decode_article_api_document


def b64(value: str) -> str:
    return base64.b64encode(value.encode()).decode()


class ArticleApiSourceTests(unittest.TestCase):
    def setUp(self):
        self.site = SiteConfig(
            site_id="site-a",
            name="目标作者",
            url="https://example.com/article/manager/6a0000000000000000000001?url=x",
            region=Region.BOTTOM,
            rule_id="article.a.v1",
            api_url="https://example.com/api/proxy/manager-articles/6a0000000000000000000001",
        )

    def record(self, record_id: str, author: str, body: str, direction: str | None = "bottom") -> dict:
        record = {
            "id": record_id,
            "authorNickname": author,
            "title": b64(f"{author}标题"),
            "html": b64(body),
            "formSections": [{"type": "mainArticle", "name": "主文章"}],
        }
        if direction is not None:
            record["direction"] = direction
        return record

    def test_nested_payload_uses_exact_url_record_id_not_decoy(self):
        payload = {
            "items": [
                self.record("6a0000000000000000000002", "其他作者", "209期精杀一行【火行】"),
                {"nested": self.record("6a0000000000000000000001", "目标作者", "209期精杀一行【木行】")},
            ]
        }

        document = decode_article_api_document(json.dumps(payload), self.site)

        self.assertEqual(document.record_id, "6a0000000000000000000001")
        self.assertEqual(document.source_kind, SourceKind.API)
        self.assertIn("【木行】", document.text)
        self.assertNotIn("【火行】", document.text)

    def test_duplicate_target_id_is_rejected(self):
        target = self.record("6a0000000000000000000001", "目标作者", "209期精杀一行【木行】")
        payload = {"first": target, "second": dict(target)}

        with self.assertRaises(FetchError):
            decode_article_api_document(json.dumps(payload), self.site)

    def test_author_mismatch_is_rejected_after_id_match(self):
        payload = {"data": self.record("6a0000000000000000000001", "错误作者", "209期精杀一行【木行】")}

        with self.assertRaises(FetchError):
            decode_article_api_document(json.dumps(payload), self.site)

    def test_direction_field_is_checked_when_api_provides_it(self):
        target = self.record("6a0000000000000000000001", "目标作者", "209期精杀一行【木行】")
        target["direction"] = "top"

        with self.assertRaises(FetchError):
            decode_article_api_document(json.dumps({"data": target}), self.site)

    def test_missing_direction_field_is_rejected(self):
        target = self.record(
            "6a0000000000000000000001",
            "目标作者",
            "209期精杀一行【木行】",
            direction=None,
        )

        with self.assertRaisesRegex(FetchError, "方向字段缺失"):
            decode_article_api_document(json.dumps({"data": target}), self.site)

    def test_section_direction_is_used_when_top_level_direction_is_missing(self):
        target = self.record(
            "6a0000000000000000000001",
            "目标作者",
            "209期精杀一行【木行】",
            direction=None,
        )
        target["formSections"].append({"type": "htmlcode", "name": "底部"})

        document = decode_article_api_document(json.dumps({"data": target}), self.site)

        self.assertEqual(document.metadata_map["direction"], "bottom")

    def test_multiple_section_directions_are_rejected(self):
        target = self.record(
            "6a0000000000000000000001",
            "目标作者",
            "209期精杀一行【木行】",
            direction=None,
        )
        target["formSections"].extend([
            {"type": "htmlcode", "name": "顶部"},
            {"type": "htmlcode", "name": "底部"},
        ])

        with self.assertRaisesRegex(FetchError, "方向栏目不唯一"):
            decode_article_api_document(json.dumps({"data": target}), self.site)

    def test_dynamic_article_id_must_have_expected_format(self):
        invalid_site = SiteConfig(
            site_id="site-invalid",
            name="目标作者",
            url="https://example.com/article/manager/not-an-article-id",
            region=Region.BOTTOM,
            rule_id="article.invalid.v1",
            api_url="https://example.com/api/proxy/manager-articles/not-an-article-id",
        )

        with self.assertRaisesRegex(FetchError, "记录ID格式无效"):
            decode_article_api_document("{}", invalid_site)


if __name__ == "__main__":
    unittest.main()
