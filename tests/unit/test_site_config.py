import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from wuxing.config.site_loader import build_versioned_site_payload, load_site_configs
from wuxing.domain.errors import ConfigError
from wuxing.domain.enums import Region


class SiteConfigTests(unittest.TestCase):
    def write_json(self, directory: str, payload: object) -> Path:
        path = Path(directory) / "sites.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def test_legacy_config_gets_deterministic_ids_for_migration(self):
        payload = [
            {"name": "甲站", "url": "https://example.com/a", "region": "top", "click_first": False},
            {"name": "乙站", "url": "https://example.com/b", "region": "bottom", "click_first": True},
        ]
        with TemporaryDirectory() as directory:
            path = self.write_json(directory, payload)

            first = load_site_configs(path, allow_legacy=True)
            second = load_site_configs(path, allow_legacy=True)

        self.assertEqual([site.site_id for site in first], [site.site_id for site in second])
        self.assertEqual(len({site.site_id for site in first}), 2)
        self.assertTrue(all(site.rule_id.endswith(".v1") for site in first))
        self.assertIs(first[0].region, Region.TOP)
        self.assertIs(first[1].region, Region.BOTTOM)

    def test_versioned_config_requires_unique_name_and_url(self):
        payload = {
            "schema_version": 2,
            "sites": [
                {"site_id": "site-a", "rule_id": "a.v1", "name": "同名", "url": "https://example.com/a", "region": "top"},
                {"site_id": "site-b", "rule_id": "b.v1", "name": "同名", "url": "https://example.com/b", "region": "bottom"},
            ],
        }
        with TemporaryDirectory() as directory:
            path = self.write_json(directory, payload)
            with self.assertRaises(ConfigError):
                load_site_configs(path)

    def test_duplicate_url_requires_same_explicit_shared_source_id(self):
        payload = {
            "schema_version": 2,
            "sites": [
                {
                    "site_id": "site-a",
                    "rule_id": "a.v1",
                    "name": "同页顶部",
                    "url": "https://example.com/shared",
                    "region": "top",
                    "shared_source_id": "shared-page-a",
                },
                {
                    "site_id": "site-b",
                    "rule_id": "b.v1",
                    "name": "同页底部",
                    "url": "https://example.com/shared",
                    "region": "bottom",
                    "shared_source_id": "shared-page-a",
                },
            ],
        }
        with TemporaryDirectory() as directory:
            path = self.write_json(directory, payload)
            sites = load_site_configs(path)

        self.assertEqual(len(sites), 2)
        self.assertEqual({site.shared_source_id for site in sites}, {"shared-page-a"})

    def test_versioned_payload_round_trips_without_losing_fetch_fields(self):
        legacy = [{
            "name": "动态站",
            "url": "https://example.com/article/admin/id",
            "api_url": "https://example.com/api/id",
            "region": "bottom",
            "click_first": True,
        }]
        with TemporaryDirectory() as directory:
            legacy_path = self.write_json(directory, legacy)
            sites = load_site_configs(legacy_path, allow_legacy=True)
            versioned = build_versioned_site_payload(sites)
            versioned_path = Path(directory) / "sites-v2.json"
            versioned_path.write_text(json.dumps(versioned, ensure_ascii=False), encoding="utf-8")

            loaded = load_site_configs(versioned_path)

        self.assertEqual(loaded, sites)
        self.assertEqual(loaded[0].api_url, "https://example.com/api/id")
        self.assertTrue(loaded[0].click_first)


if __name__ == "__main__":
    unittest.main()
