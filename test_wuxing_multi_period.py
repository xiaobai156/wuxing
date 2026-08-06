import importlib.util
from concurrent.futures import Future
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

MODULE_PATH = Path(__file__).with_name("wuxing_multi_period.py")
SPEC = importlib.util.spec_from_file_location("wuxing_multi_period", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class WuxingMultiPeriodTests(unittest.TestCase):
    def test_parse_periods_accepts_space_and_comma_text(self):
        self.assertEqual(MODULE.parse_periods("187 188,189，190"), [187, 188, 189, 190])

    def test_parse_periods_removes_duplicates_but_keeps_order(self):
        self.assertEqual(MODULE.parse_periods(["189", "188", "189", "187"]), [189, 188, 187])

    def test_parse_periods_rejects_non_numeric_value(self):
        with self.assertRaises(ValueError):
            MODULE.parse_periods("187 abc")

    def test_period_range_label_compacts_consecutive_periods(self):
        self.assertEqual(MODULE.period_range_label([187, 188, 189, 190]), "187-190期")
        self.assertEqual(MODULE.period_range_label([190, 188]), "190-188期")

    def test_multi_period_retry_clears_runtime_cache_before_resubmitting(self):
        site = MODULE.crawler.Site("https://example.com/a", "top", False, "测试站")
        outcomes = {0: (site, [], "页面里未找到 191期", ["旧正文"], 1.0)}

        with mock.patch.object(MODULE.crawler, "clear_runtime_caches") as clear_caches, mock.patch.object(
            MODULE.crawler,
            "scrape_indexed_site",
            return_value=(0, site, ["金行 191期 测试站"], None, ["新正文"], 0.5),
        ):
            MODULE.retry_failed_sites(
                [(0, site)], [], outcomes, 191, 45, 1, 1, False, 1, {0: 1}
            )

        clear_caches.assert_called_once_with()

    def test_multi_fail_summary_lists_only_all_failed_sites_and_period_reasons(self):
        sites = [
            MODULE.crawler.Site("https://example.com/a", "top", False, "已成功"),
            MODULE.crawler.Site("https://example.com/b", "bottom", False, "全失败"),
        ]

        lines = MODULE.build_multi_fail_lines(
            sites=sites,
            all_failed_indexes=[1],
            period_failures={1: {187: "页面里未找到 187期", 188: "页面里未找到 188期"}},
            periods=[187, 188],
        )
        text = "\n".join(lines)

        self.assertIn("多期全部失败：1 个目录", text)
        self.assertIn("名称: 全失败", text)
        self.assertIn("187期: 页面里未找到 187期", text)
        self.assertIn("188期: 页面里未找到 188期", text)
        self.assertNotIn("名称: 已成功", text)

    def test_build_multi_slow_site_lines_sorts_by_elapsed_time(self):
        stats = [
            MODULE.MultiPeriodTiming("快站", "https://example.com/a", 187, 1.1, True),
            MODULE.MultiPeriodTiming("慢站", "https://example.com/b", 188, 9.4, False),
        ]

        lines = MODULE.build_multi_slow_site_lines(stats, limit=2)

        self.assertEqual(lines[0], "多期慢站耗时统计 Top 2：")
        self.assertIn("慢站", lines[1])
        self.assertIn("188期", lines[1])
        self.assertIn("9.40s", lines[1])
        self.assertIn("失败", lines[1])

    def test_retries_keep_http_8_browser_2_pools_and_accumulate_elapsed_time(self):
        http_site = MODULE.crawler.Site("https://example.com/http", "top", False, "HTTP站")
        browser_site = MODULE.crawler.Site("https://example.com/#/browser", "top", False, "浏览器站")
        initial = {
            0: (http_site, [], "timeout", [], 1.25),
            1: (browser_site, [], "timeout", [], 2.5),
        }
        executor_workers = []

        class ImmediateExecutor:
            def __init__(self, max_workers):
                executor_workers.append(max_workers)

            def submit(self, function, *args):
                future = Future()
                future.set_result(function(*args))
                return future

            def shutdown(self, wait=True):
                return None

        def retry(index, site, count, timeout, show_browser, period):
            elapsed = 3.0 if index == 0 else 4.0
            return index, site, [f"金行 {period}期 {site.name}"], None, [], elapsed

        with (
            mock.patch.object(MODULE.crawler, "run_initial_scrapes", return_value=initial),
            mock.patch.object(MODULE.crawler, "check_browser_dependencies", return_value=None),
            mock.patch.object(MODULE.crawler, "scrape_indexed_site", side_effect=retry),
            mock.patch.object(MODULE, "ThreadPoolExecutor", ImmediateExecutor),
        ):
            outcomes = MODULE.scrape_period(
                [(0, http_site), (1, browser_site)],
                period=187,
                timeout=20,
                workers=8,
                browser_workers=2,
                show_browser=False,
            )

        self.assertEqual(executor_workers, [8, 2])
        self.assertEqual(outcomes[0][4], 4.25)
        self.assertEqual(outcomes[1][4], 6.5)

    def test_period_success_file_keeps_ranking_and_lists_every_site_timing(self):
        sites = [
            MODULE.crawler.Site(f"https://example.com/{index}", "top", False, f"站点{index}")
            for index in range(11)
        ]
        selected_sites = list(enumerate(sites))
        outcomes = {
            index: (
                site,
                [f"金行 187期 {site.name}"] if index == 0 else [],
                None if index == 0 else "页面里未找到 187期",
                [],
                float(index + 1),
            )
            for index, site in selected_sites
        }

        with TemporaryDirectory() as directory:
            success_path = Path(directory) / "187期-五行.txt"
            fail_path = Path(directory) / "187期-五行-失败.txt"
            with mock.patch.object(
                MODULE.crawler,
                "resolve_output_path",
                side_effect=[success_path, fail_path],
            ):
                MODULE.write_period_files(selected_sites, outcomes, 187)
            text = success_path.read_text(encoding="utf-8-sig")

        self.assertIn("排行表", text)
        self.assertIn("慢站耗时统计 Top 11：", text)
        for site in sites:
            self.assertIn(site.url, text)

    def test_multi_period_stops_successful_site_and_never_updates_recent_cache(self):
        first = MODULE.crawler.Site("https://example.com/a", "top", False, "先成功")
        second = MODULE.crawler.Site("https://example.com/b", "top", False, "后成功")
        args = MODULE.argparse.Namespace(
            period_text="187 188",
            period_args=[],
            sites_config="sites.json",
            timeout=20,
            workers=8,
            browser_workers=2,
            show_browser=False,
        )
        selected_by_period = []

        def scrape(selected_sites, period, **kwargs):
            selected_by_period.append((period, [index for index, _ in selected_sites]))
            return {}

        with TemporaryDirectory() as directory:
            report_path = Path(directory) / "report.txt"
            with (
                mock.patch.object(MODULE.crawler, "load_sites", return_value=[first, second]),
                mock.patch.object(MODULE.crawler, "clear_runtime_caches"),
                mock.patch.object(MODULE.crawler, "update_history_cache_from_outcomes") as update_cache,
                mock.patch.object(MODULE.crawler, "save_history_cache") as save_cache,
                mock.patch.object(MODULE, "scrape_period", side_effect=scrape),
                mock.patch.object(
                    MODULE,
                    "write_period_files",
                    side_effect=[({0}, {1: "失败"}), ({1}, {})],
                ),
                mock.patch.object(MODULE.crawler, "print_slow_site_summary"),
                mock.patch.object(MODULE, "write_multi_fail_report", return_value=report_path),
                mock.patch.object(MODULE, "print_multi_slow_site_summary"),
            ):
                result = MODULE.run_multi_period(args)

        self.assertEqual(result, 0)
        self.assertEqual(selected_by_period, [(187, [0, 1]), (188, [1])])
        update_cache.assert_not_called()
        save_cache.assert_not_called()


if __name__ == "__main__":
    unittest.main()
