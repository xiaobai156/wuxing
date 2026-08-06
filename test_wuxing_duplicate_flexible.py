import importlib.util
from pathlib import Path
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).with_name("wuxing_duplicate_flexible.py")
SPEC = importlib.util.spec_from_file_location("wuxing_duplicate_flexible", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class WuxingDuplicateFlexibleTests(unittest.TestCase):
    def test_default_worker_count_is_eight_sites(self):
        self.assertEqual(MODULE.DEFAULT_WORKERS, 8)

    def test_compares_by_shared_period_numbers_not_positions(self):
        site_a = ((153, "金行"), (152, "木行"), (151, "水行"))
        site_b = ((155, "土行"), (153, "金行"), (152, "木行"), (151, "水行"))

        matches = MODULE.find_duplicate_matches({"A": site_a, "B": site_b})

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].status, "suspect")
        self.assertEqual(matches[0].periods, (153, 152, 151))

    def test_non_contiguous_matching_periods_do_not_form_one_run(self):
        site_a = ((153, "金行"), (151, "水行"), (150, "火行"))
        site_b = ((153, "金行"), (151, "水行"), (150, "火行"))

        matches = MODULE.find_duplicate_matches({"A": site_a, "B": site_b})

        self.assertEqual(len(matches), 0)

    def test_one_or_two_continuous_matches_are_ignored(self):
        site_a = ((153, "金行"), (152, "木行"))
        site_b = ((153, "金行"), (152, "木行"))

        matches = MODULE.find_duplicate_matches({"A": site_a, "B": site_b})

        self.assertEqual(len(matches), 0)

    def test_three_to_five_continuous_matches_are_suspect(self):
        site_a = ((153, "金行"), (152, "木行"), (151, "水行"), (150, "火行"), (149, "土行"))
        site_b = ((153, "金行"), (152, "木行"), (151, "水行"), (150, "火行"), (149, "土行"))

        matches = MODULE.find_duplicate_matches({"A": site_a, "B": site_b})

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].status, "suspect")
        self.assertEqual(matches[0].length, 5)

    def test_six_or_more_continuous_matches_are_rejected(self):
        site_a = (
            (153, "金行"),
            (152, "木行"),
            (151, "水行"),
            (150, "火行"),
            (149, "土行"),
            (148, "金行"),
        )
        site_b = (
            (153, "金行"),
            (152, "木行"),
            (151, "水行"),
            (150, "火行"),
            (149, "土行"),
            (148, "金行"),
        )

        matches = MODULE.find_duplicate_matches({"A": site_a, "B": site_b})

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].status, "reject")
        self.assertEqual(matches[0].length, 6)

    def test_duplicate_exception_is_bound_to_the_full_url(self):
        signature = tuple((period, "火行") for period in range(208, 202, -1))
        signatures = {"典则俊雅": signature, "普通站": signature}
        special_url = "https://wigrzse.3acpt-tc9xa-kzxasm.xyz:29444/article/manager/6a20da1dca6da63e15d01fc8?url=pg"

        self.assertEqual(
            MODULE.find_duplicate_matches(
                signatures,
                {"典则俊雅": special_url, "普通站": "https://example.com/ordinary"},
            ),
            [],
        )
        matches = MODULE.find_duplicate_matches(
            signatures,
            {"典则俊雅": "https://example.com/ordinary", "普通站": "https://example.com/other"},
        )
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].status, "reject")

    def test_history_cache_skips_sites_that_already_have_signature(self):
        cached = MODULE.Site("https://example.com/cached", "top", False, "缓存站")
        pending = MODULE.Site("https://example.com/pending", "bottom", False, "待抓站")
        cache = {
            "sites": [
                {
                    "name": "缓存站",
                    "url": "https://example.com/cached",
                    "region": "top",
                    "history": [{"period": 158, "wuxing": "金行"}],
                }
            ]
        }

        signatures, pending_sites = MODULE.split_cached_and_pending_sites([cached, pending], cache, 158, 10, 60)

        self.assertEqual(signatures, {"缓存站": ((158, "金行"),)})
        self.assertEqual(pending_sites, [pending])

    def test_cache_policy_message_marks_cache_as_new_site_baseline(self):
        lines = MODULE.cache_policy_lines(False, "recent_10_cache.json")

        self.assertIn("recent_10_cache.json", lines[0])
        self.assertIn("新增判重依据", lines[0])
        self.assertTrue(any("旧实时指纹" in line for line in lines))

    def test_no_history_cache_message_is_debug_only(self):
        lines = MODULE.cache_policy_lines(True, "recent_10_cache.json")

        self.assertTrue(any("仅限调试" in line for line in lines))
        self.assertTrue(any("不能作为新增判重依据" in line for line in lines))

    def test_click_through_site_uses_its_detail_source_for_duplicate_history(self):
        site = MODULE.Site(
            "https://mxiscni.nkh6s-vfni4-lwgfvw.xyz:16677/topic/257907.html",
            "top",
            False,
            "男儿本色",
        )
        document = "\n".join([
            "190期:绝杀(1)行【水行】开:0000准",
            "189期:绝杀(1)行【火行】开:龙15准",
        ])

        with mock.patch.object(MODULE, "collect_click_through_detail_documents", return_value=[document]) as collect_detail:
            result_site, signature, error = MODULE.check_site(site, 190, 2, 60, 20, False)

        self.assertEqual(result_site, site)
        self.assertEqual(signature, ((190, "水行"), (189, "火行")))
        self.assertIsNone(error)
        collect_detail.assert_called_once_with(site, 20, 190)

    def test_conflicting_same_period_values_reject_the_entire_signature(self):
        site = MODULE.Site("https://example.com/conflict", "top", False, "冲突站")
        document = "\n".join([
            "190期:【绝杀一行】【金行】开:0000准",
            "190期:【绝杀一行】【木行】开:0000准",
            "189期:【绝杀一行】【水行】开:0000准",
        ])

        signature = MODULE.build_flexible_signature([document], site, 190, 2, 60)

        self.assertIsNone(signature)

    def test_generic_same_value_candidates_require_unique_source(self):
        site = MODULE.Site("https://example.com/ambiguous", "top", False, "普通站")
        document = "\n".join([
            "190期:【绝杀一行】【金行】开:0000准",
            "190期:【绝杀一行】【金行】开:龙15准",
        ])

        signature = MODULE.build_flexible_signature([document], site, 190, 1, 60)

        self.assertIsNone(signature)

    def test_site_specific_parser_may_accept_repeated_same_value_candidates(self):
        site = MODULE.Site(
            "https://fhktrabu.zbfrm-uzct1-pmycbu.xyz:16677/topic/469065.html",
            "bottom",
            False,
            "异口同声",
        )
        document = "\n".join([
            "190期:【绝杀一行】【金行】开:0000准",
            "190期:【绝杀一行】【金行】开:龙15准",
        ])

        signature = MODULE.build_flexible_signature([document], site, 190, 1, 60)

        self.assertEqual(signature, ((190, "金行"),))

    def test_api_first_live_fetch_uses_api_documents(self):
        site = MODULE.Site(
            "https://example.com/article/admin/123",
            "top",
            False,
            "API站",
            "https://example.com/api/article/123",
        )
        document = "190期:【绝杀一行】【水行】开:0000准"

        with (
            mock.patch.object(MODULE, "collect_article_admin_api_documents", return_value=([document], None)) as collect_api,
            mock.patch.object(MODULE, "collect_documents") as collect_http,
            mock.patch.object(MODULE, "fetch_browser_text") as fetch_browser,
        ):
            _, signature, error = MODULE.check_site(site, 190, 1, 60, 12, False)

        self.assertEqual(signature, ((190, "水行"),))
        self.assertIsNone(error)
        collect_api.assert_called_once_with(site, 12)
        collect_http.assert_not_called()
        fetch_browser.assert_not_called()

    def test_browser_first_live_fetch_uses_public_browser_routing_helpers(self):
        site = MODULE.Site("https://example.com/browser", "top", True, "浏览器站")
        document = "190期:【绝杀一行】【火行】开:0000准"

        with (
            mock.patch.object(MODULE, "site_uses_browser_first", return_value=True),
            mock.patch.object(MODULE, "site_browser_click_first", return_value=False) as click_rule,
            mock.patch.object(MODULE, "fetch_browser_text", return_value=document) as fetch_browser,
            mock.patch.object(MODULE, "collect_documents") as collect_http,
        ):
            _, signature, error = MODULE.check_site(site, 190, 1, 60, 12, False)

        self.assertEqual(signature, ((190, "火行"),))
        self.assertIsNone(error)
        click_rule.assert_called_once_with(site)
        fetch_browser.assert_called_once_with(site.url, 20, False, False, 190, site=site)
        collect_http.assert_not_called()

    def test_pending_sites_are_partitioned_with_site_needs_browser(self):
        http_site = MODULE.Site("https://example.com/http", "top", False, "HTTP站")
        browser_site = MODULE.Site("https://example.com/browser", "bottom", False, "浏览器站")

        with mock.patch.object(MODULE, "site_needs_browser", side_effect=lambda site: site is browser_site):
            http_sites, browser_sites = MODULE.partition_pending_sites([http_site, browser_site])

        self.assertEqual(http_sites, [http_site])
        self.assertEqual(browser_sites, [browser_site])

    def test_strict_position_window_is_applied_to_the_requested_period(self):
        document = "\n".join(
            f"{100 + index}期:【绝杀一行】【金行】开:0000准" for index in range(31)
        )
        top_site = MODULE.Site("https://example.com/top", "top", False, "顶部站")
        bottom_site = MODULE.Site("https://example.com/bottom", "bottom", False, "尾部站")

        top_signature = MODULE.build_flexible_signature([document], top_site, 130, 1, 1)
        bottom_signature = MODULE.build_flexible_signature([document], bottom_site, 130, 1, 1)

        self.assertIsNone(top_signature)
        self.assertEqual(bottom_signature, ((130, "金行"),))

    def test_top_fourth_candidate_cannot_pass_duplicate_signature_window(self):
        document = "\n".join([
            "193期:【绝杀一行】【木行】开:0000准",
            "192期:【绝杀一行】【水行】开:0000准",
            "191期:【绝杀一行】【火行】开:0000准",
            "190期:【绝杀一行】【金行】开:0000准",
        ])
        site = MODULE.Site("https://example.com/top-fourth", "top", False, "顶部第四条")

        self.assertIsNone(MODULE.build_flexible_signature([document], site, 190, 1, 60))

    def test_bottom_child_document_cannot_pass_duplicate_signature_window(self):
        root = "\n".join([
            "191期:【绝杀一行】【木行】开:0000准",
            "192期:【绝杀一行】【水行】开:0000准",
            "193期:【绝杀一行】【火行】开:0000准",
            "194期:【绝杀一行】【土行】开:0000准",
        ])
        child = "190期:【绝杀一行】【金行】开:0000准"
        site = MODULE.Site("https://example.com/bottom-child", "bottom", False, "尾部子文档")

        self.assertIsNone(MODULE.build_flexible_signature([root, child], site, 190, 1, 60))

    def test_child_document_cannot_supply_the_only_duplicate_candidates(self):
        root = "页面导航，无绝杀数据"
        child = "190期:【绝杀一行】【金行】开:0000准"
        site = MODULE.Site("https://example.com/child-only", "bottom", False, "仅子文档")

        self.assertIsNone(MODULE.build_flexible_signature([root, child], site, 190, 1, 60))

    def test_conflict_outside_selected_window_still_rejects_signature(self):
        lines = [f"{100 + index}期:【绝杀一行】【金行】开:0000准" for index in range(31)]
        lines.append("100期:【绝杀一行】【木行】开:龙15准")
        site = MODULE.Site("https://example.com/top-conflict", "top", False, "顶部冲突站")

        signature = MODULE.build_flexible_signature(["\n".join(lines)], site, 100, 1, 1)

        self.assertIsNone(signature)

    def test_api_document_without_target_signal_falls_back_to_browser(self):
        site = MODULE.Site(
            "https://example.com/article/admin/123",
            "top",
            False,
            "API回退站",
            "https://example.com/api/article/123",
        )
        browser_document = "190期:【绝杀一行】【土行】开:0000准"

        with (
            mock.patch.object(MODULE, "collect_article_admin_api_documents", return_value=(["无目标数据"], None)),
            mock.patch.object(MODULE, "site_browser_click_first", return_value=False),
            mock.patch.object(MODULE, "fetch_browser_text", return_value=browser_document) as fetch_browser,
        ):
            _, signature, error = MODULE.check_site(site, 190, 1, 60, 12, False)

        self.assertEqual(signature, ((190, "土行"),))
        self.assertIsNone(error)
        fetch_browser.assert_called_once_with(site.url, 20, False, False, 190, site=site)


if __name__ == "__main__":
    unittest.main()
