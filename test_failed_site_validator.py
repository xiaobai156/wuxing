import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).with_name("failed_site_validator.py")
SPEC = importlib.util.spec_from_file_location("failed_site_validator", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class FailedSiteValidatorTests(unittest.TestCase):
    def test_load_cases_requires_name_or_url_and_positive_period(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "cases.json"
            path.write_text(
                json.dumps(
                    [
                        {
                            "name": "损人利己",
                            "url": "https://example.com/topic/1",
                            "region": "top",
                            "period": 195,
                            "expected_wuxing": "木行",
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            cases = MODULE.load_validation_cases(path)

        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0].period, 195)
        self.assertEqual(cases[0].region, "top")
        self.assertEqual(cases[0].expected_wuxing, "木行")

    def test_success_diagnostics_include_all_required_checks(self):
        site = MODULE.crawler.Site(
            "https://ekhivjcg.llnnt-l11x5-bywtoe.xyz:16677/topic/469882.html",
            "top",
            False,
            "损人利己",
        )
        case = MODULE.ValidationCase("损人利己", site.url, "top", 195, "木行")
        document = "195期【绝杀一行】【杀木行】开0000对\n194期【绝杀一行】【杀水行】开蛇26对"

        trace = MODULE.ValidationTrace()
        trace.authority_calls.append(
            MODULE.AuthorityCall(site.url, ("特码料 195期：【绝杀一行】损人利己", document), (document,))
        )
        result = MODULE.build_validation_result(
            case,
            site,
            ["木行 195期 损人利己"],
            None,
            [document],
            1.25,
            trace,
        )

        self.assertTrue(result.passed)
        self.assertTrue(result.target_found)
        self.assertEqual(result.actual_wuxing, ("木行",))
        self.assertTrue(result.direction_pass)
        self.assertTrue(result.anchor_pass)
        self.assertTrue(result.keyword_pass)
        self.assertTrue(result.wuxing_pass)
        self.assertFalse(result.has_conflict)
        self.assertFalse(result.has_duplicate_wuxing)
        rendered = "\n".join(MODULE.format_validation_result(result, 1, 1))
        for label in (
            "是否抓到指定期数",
            "实际五行",
            "top/bottom 是否正确",
            "锚点是否通过",
            "关键词是否通过",
            "五行是否通过",
            "同期冲突",
            "重复五行",
            "失败原因",
        ):
            self.assertIn(label, rendered)

    def test_generic_parser_without_dedicated_anchor_cannot_pass(self):
        site = MODULE.crawler.Site("https://example.com/topic/1", "top", False, "通用站")
        case = MODULE.ValidationCase("通用站", site.url, "top", 195, "木行")
        document = "195期：【绝杀一行】【木行】开0000对"

        result = MODULE.build_validation_result(
            case,
            site,
            ["木行 195期 通用站"],
            None,
            [document],
            1.0,
        )

        self.assertFalse(result.anchor_pass)
        self.assertFalse(result.passed)
        self.assertIn("锚点未通过", result.failure_reason)

    def test_anchor_and_candidate_in_separate_documents_need_authoritative_binding_trace(self):
        site = MODULE.crawler.Site(
            "https://ekhivjcg.llnnt-l11x5-bywtoe.xyz:16677/topic/469882.html",
            "top",
            False,
            "损人利己",
        )
        case = MODULE.ValidationCase("损人利己", site.url, "top", 195, "木行")
        anchor_only = "特码料 195期：【绝杀一行】损人利己"
        candidate_only = "195期【绝杀一行】【杀木行】开0000对"

        result = MODULE.build_validation_result(
            case,
            site,
            ["木行 195期 损人利己"],
            None,
            [anchor_only, candidate_only],
            1.0,
        )

        self.assertFalse(result.anchor_pass)
        self.assertFalse(result.passed)

    def test_conflict_and_out_of_region_are_reported_as_failure(self):
        site = MODULE.crawler.Site("https://example.com/topic/1", "top", False, "冲突站")
        case = MODULE.ValidationCase("冲突站", site.url, "top", 195, None)
        documents = [
            "198期：【绝杀一行】【金行】开0000对\n"
            "197期：【绝杀一行】【木行】开0000对\n"
            "196期：【绝杀一行】【土行】开0000对\n"
            "195期：【绝杀一行】【水行】开0000对",
            "195期：【绝杀一行】【火行】开0000对",
        ]

        result = MODULE.build_validation_result(
            case,
            site,
            [],
            "195期同站出现多个高可信候选且五行冲突，已丢入失败",
            documents,
            2.0,
        )

        self.assertFalse(result.passed)
        self.assertTrue(result.target_found)
        self.assertFalse(result.direction_pass)
        self.assertTrue(result.has_conflict)
        self.assertIn("五行冲突", result.failure_reason)

    def test_successful_dedicated_parser_keeps_anchor_pass_after_body_is_scoped(self):
        site = MODULE.crawler.Site(
            "https://ekhivjcg.llnnt-l11x5-bywtoe.xyz:16677/topic/469882.html",
            "top",
            False,
            "损人利己",
        )
        case = MODULE.ValidationCase("损人利己", site.url, "top", 195, "木行")
        scoped_body = "195期【绝杀一行】【杀木行】开0000对\n194期【绝杀一行】【杀水行】开蛇26对"

        trace = MODULE.ValidationTrace()
        trace.authority_calls.append(
            MODULE.AuthorityCall(site.url, ("特码料 195期：【绝杀一行】损人利己", scoped_body), (scoped_body,))
        )
        result = MODULE.build_validation_result(
            case,
            site,
            ["木行 195期 损人利己"],
            None,
            [scoped_body],
            1.0,
            trace,
        )

        self.assertTrue(result.anchor_pass)
        self.assertTrue(result.passed)

    def test_run_case_does_not_update_cache_or_resolve_output_files(self):
        site = MODULE.crawler.Site(
            "https://ekhivjcg.llnnt-l11x5-bywtoe.xyz:16677/topic/469882.html",
            "top",
            False,
            "损人利己",
        )
        case = MODULE.ValidationCase("损人利己", site.url, "top", 195, "木行")
        document = "损人利己发文 195期【绝杀一行】【杀木行】开0000对"

        with (
            mock.patch.object(
                MODULE.crawler,
                "scrape_site_detailed",
                return_value=(["木行 195期 损人利己"], None, [document]),
            ) as scrape,
            mock.patch.object(MODULE.crawler, "update_history_cache_from_outcomes") as update_cache,
            mock.patch.object(MODULE.crawler, "save_history_cache") as save_cache,
            mock.patch.object(MODULE.crawler, "mutate_history_cache") as mutate_cache,
            mock.patch.object(MODULE.crawler, "resolve_output_path") as resolve_output,
            mock.patch.object(MODULE.crawler, "clear_runtime_caches") as clear_caches,
        ):
            result = MODULE.run_validation_case(case, [site], timeout=20, show_browser=False)

        self.assertTrue(result.passed)
        scrape.assert_called_once_with(site, 1, 20, False, 195)
        clear_caches.assert_called_once_with()
        update_cache.assert_not_called()
        save_cache.assert_not_called()
        mutate_cache.assert_not_called()
        resolve_output.assert_not_called()

    def test_duplicate_wuxing_ignores_same_source_collected_twice(self):
        site = MODULE.crawler.Site(
            "https://ekhivjcg.llnnt-l11x5-bywtoe.xyz:16677/topic/469882.html",
            "top",
            False,
            "损人利己",
        )
        case = MODULE.ValidationCase("损人利己", site.url, "top", 195, "木行")
        document = "195期【绝杀一行】【杀木行】开0000对"
        trace = MODULE.ValidationTrace()
        trace.authority_calls.append(
            MODULE.AuthorityCall(site.url, ("特码料 195期：【绝杀一行】损人利己", document), (document,))
        )

        result = MODULE.build_validation_result(
            case,
            site,
            ["木行 195期 损人利己"],
            None,
            [document, document],
            1.0,
            trace,
        )

        self.assertFalse(result.has_duplicate_wuxing)

    def test_nonstandard_target_candidate_cannot_pass_direction_check(self):
        site = MODULE.crawler.Site("https://example.com/special", "top", False, "专属站")
        case = MODULE.ValidationCase("专属站", site.url, "top", 195, None)
        candidate = MODULE.crawler.Candidate("195期", "风行", 0, "195期【绝杀一行】【风行】")

        with mock.patch.object(MODULE.crawler, "parse_candidates_for_site", return_value=[candidate]):
            result = MODULE.build_validation_result(case, site, [], "非标准五行", [candidate.raw], 1.0)

        self.assertTrue(result.target_found)
        self.assertFalse(result.direction_pass)
        self.assertFalse(result.wuxing_pass)

    def test_validation_only_parser_without_target_keyword_cannot_pass(self):
        site = MODULE.crawler.Site("https://example.com/special", "top", False, "专属站")
        case = MODULE.ValidationCase("专属站", site.url, "top", 195, "木行")

        def override(document, current_site):
            return [MODULE.crawler.Candidate("195期", "木行", 0, "195期 木行")]

        MODULE.VALIDATION_ONLY_PARSERS[site.url] = MODULE.ValidationOnlyParserRule(
            override,
            re.compile(r"专属站"),
            re.compile(r"绝杀一行"),
        )
        try:
            with MODULE.validation_only_overrides(site):
                result = MODULE.build_validation_result(
                    case,
                    site,
                    ["木行 195期 专属站"],
                    None,
                    ["195期 木行"],
                    1.0,
                )
        finally:
            MODULE.VALIDATION_ONLY_PARSERS.pop(site.url, None)

        self.assertFalse(result.keyword_pass)
        self.assertFalse(result.passed)

    def test_validation_only_parser_with_generic_keyword_but_no_site_anchor_cannot_pass(self):
        site = MODULE.crawler.Site("https://example.com/special", "top", False, "专属站")
        case = MODULE.ValidationCase("专属站", site.url, "top", 195, "木行")

        def override(document, current_site):
            return [MODULE.crawler.Candidate("195期", "木行", 0, "195期 绝杀一行 木行")]

        MODULE.VALIDATION_ONLY_PARSERS[site.url] = MODULE.ValidationOnlyParserRule(
            override,
            re.compile(r"专属站"),
            re.compile(r"绝杀一行"),
        )
        try:
            with MODULE.validation_only_overrides(site):
                result = MODULE.build_validation_result(
                    case,
                    site,
                    ["木行 195期 专属站"],
                    None,
                    ["195期 绝杀一行 木行"],
                    1.0,
                )
        finally:
            MODULE.VALIDATION_ONLY_PARSERS.pop(site.url, None)

        self.assertFalse(result.anchor_pass)
        self.assertFalse(result.passed)

    def test_validation_only_anchor_and_keyword_cannot_be_combined_across_documents(self):
        site = MODULE.crawler.Site("https://example.com/special", "top", False, "专属站")
        case = MODULE.ValidationCase("专属站", site.url, "top", 195, "木行")

        def override(document, current_site):
            return [MODULE.crawler.Candidate("195期", "木行", 0, document)]

        MODULE.VALIDATION_ONLY_PARSERS[site.url] = MODULE.ValidationOnlyParserRule(
            override,
            re.compile(r"专属站"),
            re.compile(r"绝杀一行"),
        )
        try:
            with MODULE.validation_only_overrides(site):
                result = MODULE.build_validation_result(
                    case,
                    site,
                    ["木行 195期 专属站"],
                    None,
                    ["专属站 195期 木行", "195期 绝杀一行 木行"],
                    1.0,
                )
        finally:
            MODULE.VALIDATION_ONLY_PARSERS.pop(site.url, None)

        self.assertFalse(result.keyword_pass)
        self.assertFalse(result.passed)

    def test_retry_clears_runtime_cache_before_each_real_attempt(self):
        site = MODULE.crawler.Site(
            "https://ekhivjcg.llnnt-l11x5-bywtoe.xyz:16677/topic/469882.html",
            "top",
            False,
            "损人利己",
        )
        case = MODULE.ValidationCase("损人利己", site.url, "top", 195, "木行")
        document = "损人利己发文 195期【绝杀一行】【杀木行】开0000对"

        with (
            mock.patch.object(
                MODULE.crawler,
                "scrape_site_detailed",
                side_effect=[
                    ([], "请求超时", []),
                    (["木行 195期 损人利己"], None, [document]),
                ],
            ) as scrape,
            mock.patch.object(MODULE.crawler, "clear_runtime_caches") as clear_caches,
        ):
            result = MODULE.run_validation_case(case, [site], timeout=20, show_browser=False)

        self.assertTrue(result.passed)
        self.assertEqual(scrape.call_count, 2)
        self.assertEqual(clear_caches.call_count, 2)

    def test_validation_override_is_scoped_and_restores_formal_parser(self):
        site = MODULE.crawler.Site("https://example.com/special", "top", False, "专属站")
        original = MODULE.crawler.parse_candidates_for_site

        def override(document, current_site):
            return [MODULE.crawler.Candidate("195期", "木行", 0, document)]

        MODULE.VALIDATION_ONLY_PARSERS[site.url] = MODULE.ValidationOnlyParserRule(
            override,
            re.compile(r"专属内容"),
            re.compile(r"专属内容"),
        )
        try:
            with MODULE.validation_only_overrides(site):
                candidates = MODULE.crawler.parse_candidates_for_site("专属内容", site)
                self.assertEqual([(item.period, item.wuxing) for item in candidates], [("195期", "木行")])
            self.assertIs(MODULE.crawler.parse_candidates_for_site, original)
        finally:
            MODULE.VALIDATION_ONLY_PARSERS.pop(site.url, None)


if __name__ == "__main__":
    unittest.main()
