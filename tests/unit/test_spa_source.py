import json
import unittest

from wuxing.domain.enums import Region, SourceKind
from wuxing.domain.errors import FetchError
from wuxing.domain.models import SiteConfig
from wuxing.sources.spa import decode_spa_forum_documents, validate_spa_profile


class SpaSourceTests(unittest.TestCase):
    def setUp(self):
        self.site = SiteConfig(
            "site-spa",
            "笨鸟先飞",
            "https://example.com/#/users/116157",
            Region.TOP,
            "spa.user.v1",
        )

    def test_spa_records_are_limited_to_url_user_id(self):
        payload = {
            "data": [
                {"id": 1, "user_id": 999, "topic": "诱饵", "content": "209期【火行】"},
                {"id": 2, "user_id": 116157, "topic": "笨鸟先飞绝杀一行", "content": "209期【木行】"},
            ]
        }

        documents = decode_spa_forum_documents(json.dumps(payload), self.site)

        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].record_id, "2")
        self.assertEqual(documents[0].source_kind, SourceKind.SPA)
        self.assertNotIn("火行", documents[0].text)

    def test_spa_profile_requires_exact_user_id_and_expected_name(self):
        validate_spa_profile({"id": 116157, "nickname": "笨鸟先飞"}, self.site)
        with self.assertRaises(FetchError):
            validate_spa_profile({"id": 999, "nickname": "笨鸟先飞"}, self.site)


if __name__ == "__main__":
    unittest.main()
