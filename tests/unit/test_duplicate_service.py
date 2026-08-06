import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from wuxing.domain.enums import Region
from wuxing.services.duplicate import DuplicateService
from wuxing.storage.history_cache import HistoryCacheRepository, HistoryUpdate


class DuplicateServiceTests(unittest.TestCase):
    def test_compares_common_periods_and_reports_longest_contiguous_run(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "recent_10_cache.json"
            repository = HistoryCacheRepository(path)
            repository.apply_updates([
                HistoryUpdate("site-old", "旧站", "https://old", Region.TOP, period, "木行", str(period), "old.v1", "now")
                for period in range(200, 210)
            ])
            candidate = {period: "木行" for period in range(202, 210)}
            report = DuplicateService(repository).compare_history("新站", candidate)

        self.assertEqual(report.longest_run, 8)
        self.assertEqual(report.status, "duplicate")
        self.assertEqual(report.compared_site, "旧站")

    def test_does_not_compare_by_list_position(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "recent_10_cache.json"
            repository = HistoryCacheRepository(path)
            repository.apply_updates([
                HistoryUpdate("site-old", "旧站", "https://old", Region.TOP, 209, "木行", "209", "old.v1", "now"),
                HistoryUpdate("site-old", "旧站", "https://old", Region.TOP, 207, "木行", "207", "old.v1", "now"),
            ])
            report = DuplicateService(repository).compare_history("新站", {208: "木行", 207: "火行"})

        self.assertEqual(report.longest_run, 0)
        self.assertEqual(report.status, "none")


if __name__ == "__main__":
    unittest.main()
