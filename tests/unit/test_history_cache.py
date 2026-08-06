import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from wuxing.domain.errors import CacheConflictError, CacheError
from wuxing.domain.enums import Region
from wuxing.storage.history_cache import HistoryCacheRepository, HistoryUpdate, validate_history_cache


class HistoryCacheTests(unittest.TestCase):
    def test_repository_keeps_only_latest_ten_periods(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "recent_10_cache.json"
            repository = HistoryCacheRepository(path)
            updates = [
                HistoryUpdate(
                    site_id="site-a",
                    name="甲站",
                    url="https://example.com/a",
                    region=Region.TOP,
                    period=period,
                    wuxing="木行",
                    source_digest=f"digest-{period}",
                    rule_version="a.v1",
                    captured_at="2026-07-31T00:00:00+08:00",
                )
                for period in range(190, 202)
            ]

            repository.apply_updates(updates)
            cache = repository.load()

        history = cache["sites"][0]["history"]
        self.assertEqual([item["period"] for item in history], list(range(201, 191, -1)))

    def test_same_site_period_conflict_never_overwrites_existing_value(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "recent_10_cache.json"
            repository = HistoryCacheRepository(path)
            original = HistoryUpdate("site-a", "甲站", "https://example.com/a", Region.TOP, 209, "木行", "one", "a.v1", "2026-07-31T00:00:00+08:00")
            conflict = HistoryUpdate("site-a", "甲站", "https://example.com/a", Region.TOP, 209, "火行", "two", "a.v2", "2026-07-31T00:01:00+08:00")
            repository.apply_updates([original])
            before = path.read_bytes()

            with self.assertRaises(CacheConflictError):
                repository.apply_updates([conflict])

            self.assertEqual(path.read_bytes(), before)

    def test_corrupt_cache_is_rejected_without_replacement(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "recent_10_cache.json"
            path.write_text("{broken", encoding="utf-8")
            before = path.read_bytes()

            with self.assertRaises(CacheError):
                HistoryCacheRepository(path).load()

            self.assertEqual(path.read_bytes(), before)

    def test_written_cache_is_valid_versioned_json(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "recent_10_cache.json"
            update = HistoryUpdate("site-a", "甲站", "https://example.com/a", Region.BOTTOM, 209, "金行", "digest", "a.v1", "2026-07-31T00:00:00+08:00")
            HistoryCacheRepository(path).apply_updates([update])

            payload = json.loads(path.read_text(encoding="utf-8-sig"))

        self.assertEqual(payload["schema_version"], 2)
        self.assertEqual(payload["updated_period"], 209)
        self.assertEqual(payload["sites"][0]["site_id"], "site-a")

    def test_cache_validation_rejects_more_than_ten_history_items(self):
        payload = {
            "schema_version": 2,
            "updated_period": 209,
            "sites": [{
                "site_id": "site-a",
                "name": "甲站",
                "url": "https://example.com/a",
                "region": "top",
                "history": [
                    {"period": period, "wuxing": "木行"}
                    for period in range(209, 198, -1)
                ],
            }],
        }

        with self.assertRaisesRegex(CacheError, "最多保留10期"):
            validate_history_cache(payload)

    def test_cache_update_rejects_requested_keep_above_ten(self):
        update = HistoryUpdate(
            "site-a", "甲站", "https://example.com/a", Region.TOP,
            209, "木行", "digest", "a.v1", "2026-07-31T00:00:00+08:00",
        )

        with self.assertRaisesRegex(CacheError, "最多只能保留10期"):
            from wuxing.storage.history_cache import apply_history_updates
            apply_history_updates({"schema_version": 2, "updated_period": 0, "sites": []}, [update], keep=11)


if __name__ == "__main__":
    unittest.main()
