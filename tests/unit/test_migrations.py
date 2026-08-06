import unittest

from wuxing.domain.enums import Region
from wuxing.domain.models import SiteConfig
from wuxing.storage.migrations import build_legacy_cache_migration_preview


class CacheMigrationTests(unittest.TestCase):
    def setUp(self):
        self.site = SiteConfig(
            site_id="site-a",
            name="甲站",
            url="https://example.com/a",
            region=Region.TOP,
            rule_id="a.v1",
        )

    def test_preview_reports_orphans_without_silently_dropping_them(self):
        legacy = {
            "version": 1,
            "updated_period": 209,
            "sites": [
                {"name": "甲站", "url": "https://example.com/a", "region": "top", "history": [{"period": 209, "wuxing": "木行"}]},
                {"name": "已删除站", "url": "https://example.com/deleted", "region": "top", "history": [{"period": 209, "wuxing": "火行"}]},
            ],
        }

        preview = build_legacy_cache_migration_preview(legacy, [self.site])

        self.assertEqual(preview.matched_site_ids, ("site-a",))
        self.assertEqual(preview.orphan_labels, ("已删除站 | https://example.com/deleted",))
        self.assertEqual(preview.conflicts, ())
        self.assertEqual(preview.cache["sites"][0]["history"][0]["period"], 209)

    def test_preview_reports_missing_config_site(self):
        preview = build_legacy_cache_migration_preview({"version": 1, "sites": []}, [self.site])

        self.assertEqual(preview.missing_site_ids, ("site-a",))

    def test_preview_stops_on_duplicate_legacy_matches(self):
        legacy_entry = {"name": "甲站", "url": "https://example.com/a", "region": "top", "history": [{"period": 209, "wuxing": "木行"}]}
        legacy = {"version": 1, "sites": [legacy_entry, dict(legacy_entry)]}

        preview = build_legacy_cache_migration_preview(legacy, [self.site])

        self.assertEqual(len(preview.conflicts), 1)
        self.assertEqual(preview.cache["sites"], [])


if __name__ == "__main__":
    unittest.main()
