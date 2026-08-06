import base64
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest import mock

import requests

MODULE_PATH = Path(__file__).with_name("wuxing_crawler.py")
SPEC = importlib.util.spec_from_file_location("wuxing_crawler", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class WuxingCrawlerTests(unittest.TestCase):
    def test_tianxiawushuang_parser_joins_split_html_result_rows(self):
        document = (
            '<h1>天下无双【必杀一行】资料已公开</h1>'
            '205期:<font>必杀一行</font>【火行】开:？00准<br/>'
            '204期:<font>必杀一行</font>【土行】开:虎05准'
        )

        candidates = MODULE.parse_tianxiawushuang_candidates(document)

        self.assertEqual([(item.period, item.wuxing) for item in candidates], [
            ("204期", "土行"),
            ("205期", "火行"),
        ])

    def test_yirujiwang_authority_ignores_aggregated_conflicting_article(self):
        site = MODULE.Site(
            "https://eebysckd.2go6k-y0pfv-fqbdsm.xyz:16677/topic/626030.html",
            "top",
            False,
            "一如既往",
        )
        header = "杀肖区\n205期: 一如既往\n「精杀一行」"
        target_article = (
            "一如既往 发表于\n205期精杀一行【金行】开：0000准\n"
            "204期精杀一行【水行】开：虎05准"
        )
        conflicting_aggregate = (
            "一如既往 发表于\n207期精杀一行【土行】开：马24准\n"
            "206期精杀一行【木行】开：猴10准\n205期精杀一行【火行】开：蛇01错"
        )

        selected = MODULE.site_authoritative_documents(
            [header, target_article, conflicting_aggregate], site
        )

        self.assertEqual(selected, [target_article])

    def test_yirujiwang_authority_is_order_independent_for_aggregated_conflict(self):
        site = MODULE.Site(
            "https://eebysckd.2go6k-y0pfv-fqbdsm.xyz:16677/topic/626030.html",
            "top",
            False,
            "一如既往",
        )
        aggregate = (
            "document.writeln('聚合脚本') 一如既往 发表于\n209期精杀一行【水行】开：0000准\n"
            "208期精杀一行【火行】开：鼠19准\n207期精杀一行【土行】开：鼠31准"
        )
        target_article = (
            "一如既往 发表于\n209期精杀一行【木行】开：0000准\n"
            "208期精杀一行【火行】开：鼠19准"
        )

        selected = MODULE.site_authoritative_documents(
            [aggregate, target_article], site, period=209
        )

        self.assertEqual(selected, [target_article])

    def test_yirujiwang_authority_rejects_aggregate_without_target_article(self):
        site = MODULE.Site(
            "https://eebysckd.2go6k-y0pfv-fqbdsm.xyz:16677/topic/626030.html",
            "top",
            False,
            "一如既往",
        )
        aggregate = (
            "document.writeln('聚合脚本') 一如既往 发表于\n209期精杀一行【水行】开：0000准\n"
            "208期精杀一行【火行】开：鼠19准"
        )

        selected = MODULE.site_authoritative_documents([aggregate], site, period=209)

        self.assertEqual(selected, [])

    def test_yirujiwang_authority_accepts_rendered_dom_with_script_marker(self):
        site = MODULE.Site(
            "https://eebysckd.2go6k-y0pfv-fqbdsm.xyz:16677/topic/626030.html",
            "top",
            False,
            "一如既往",
        )
        rendered_dom = (
            "<html><head><script>document.writeln(utf8to16(strdecode('encoded')))</script></head>"
            "<body>一如既往 发表于<br>"
            "209期精杀一行【木行】开：0000准<br>"
            "208期精杀一行【火行】开：鼠19准</body></html>"
        )

        selected = MODULE.site_authoritative_documents([rendered_dom], site, period=209)

        self.assertEqual(selected, [rendered_dom])

    def test_yirujiwang_parser_stops_at_non_contiguous_aggregated_record(self):
        aggregate = (
            "一如既往 发表于\n"
            "209期精杀一行【木行】开：0000准\n"
            "208期精杀一行【火行】开：鼠19准\n"
            "207期精杀一行【土行】开：鼠31准\n"
            "206期精杀一行【金行】开：牛12准\n"
            "1期精杀一行【水行】开：龙03准\n"
            "365期精杀一行【火行】开：蛇01准\n"
            "364期精杀一行【金行】开：马02准\n"
            "209期精杀一行【水行】开：猴04准"
        )

        candidates = MODULE.parse_yirujiwang_candidates(aggregate)

        self.assertEqual(
            [(item.period, item.wuxing) for item in candidates if item.period == "209期"],
            [("209期", "木行")],
        )
        self.assertNotIn(("365期", "火行"), [(item.period, item.wuxing) for item in candidates])

    def test_chetoutouwei_four_rows_parse_missing_wuxing(self):
        site = MODULE.Site(
            "https://cahgjib.5blx9-z8506-ekiwxc.work:29488/article/admin/6a1449c2597e16d57eacb67a?url=lqz",
            "bottom",
            True,
            "彻头彻尾",
            "https://cahgjib.5blx9-z8506-ekiwxc.work:29488/api/proxy/manager-articles/6a1449c2597e16d57eacb67a",
        )
        document = (
            "205期:《彻头彻尾》四行中特【金.木.水.土】开：火40准\n"
            "204期:《彻头彻尾》四行中特【火.金.木.土】开：水05准"
        )

        candidates = MODULE.parse_candidates_for_site(document, site)

        self.assertEqual([(item.period, item.wuxing) for item in candidates], [
            ("205期", "火行"),
            ("204期", "水行"),
        ])

    def test_chetoutouwei_does_not_browser_fallback_when_api_document_is_valid(self):
        site = MODULE.Site(
            "https://cahgjib.5blx9-z8506-ekiwxc.work:29488/article/admin/6a1449c2597e16d57eacb67a?url=lqz",
            "bottom",
            True,
            "彻头彻尾",
            "https://cahgjib.5blx9-z8506-ekiwxc.work:29488/api/proxy/manager-articles/6a1449c2597e16d57eacb67a",
        )
        document = "204期:《彻头彻尾》四行中特【火.金.木.土】开：水05准"

        self.assertFalse(MODULE.article_admin_should_render_fallback(site, [document], None, 205))

    def test_chetoutouwei_reports_missing_period_from_authoritative_api(self):
        site = MODULE.Site(
            "https://cahgjib.5blx9-z8506-ekiwxc.work:29488/article/admin/6a1449c2597e16d57eacb67a?url=lqz",
            "bottom",
            True,
            "彻头彻尾",
            "https://cahgjib.5blx9-z8506-ekiwxc.work:29488/api/proxy/manager-articles/6a1449c2597e16d57eacb67a",
        )
        document = "204期:《彻头彻尾》四行中特【火.金.木.土】开：水05准"

        with mock.patch.object(MODULE, "collect_article_admin_api_documents", return_value=([document], None)):
            lines, error, _ = MODULE.scrape_site_detailed(site, 1, 20, False, 205)

        self.assertEqual(lines, [])
        self.assertEqual(error, "页面里未找到 205期")

    def test_retry_timeout_minimum_is_forty_five_seconds(self):
        self.assertEqual(MODULE.DEFAULT_RETRY_TIMEOUT_MIN, 45)

    def test_connection_aborted_filenotfound_uses_retry_and_curl_fallback(self):
        error = ConnectionError("('Connection aborted.', FileNotFoundError(2, 'No such file or directory'))")

        self.assertTrue(MODULE.should_try_curl_fallback(error))
        self.assertTrue(MODULE.should_retry_failure(str(error)))

    def test_collect_documents_reuses_successful_url_cache(self):
        MODULE.clear_runtime_caches()
        session = object()
        with mock.patch.object(MODULE, "fetch_text", return_value="<html>ok</html>") as fetch_text:
            first = MODULE.collect_documents(session, "https://example.com/page", 20)
            second = MODULE.collect_documents(session, "https://example.com/page", 20)

        self.assertEqual(first, ["<html>ok</html>"])
        self.assertEqual(second, ["<html>ok</html>"])
        fetch_text.assert_called_once_with(session, "https://example.com/page", 20)

    def test_collect_documents_dedupes_repeated_iframe_documents(self):
        MODULE.clear_runtime_caches()
        session = object()
        html = "<html><body>190期 稳杀一行【金行】<iframe src='/same'></iframe></body></html>"

        with mock.patch.object(MODULE, "fetch_text", return_value=html):
            documents = MODULE.collect_documents(session, "https://example.com/page", 20)

        self.assertEqual(documents, [html])

    def test_collect_documents_ignores_cross_origin_iframe_by_default(self):
        MODULE.clear_runtime_caches()
        session = object()
        root = "<html><iframe src='https://ads.example.net/injected'></iframe></html>"

        with mock.patch.object(MODULE, "fetch_text", return_value=root) as fetch_text:
            documents = MODULE.collect_documents(session, "https://example.com/page", 20)

        self.assertEqual(documents, [root])
        fetch_text.assert_called_once_with(session, "https://example.com/page", 20)

    def test_scrape_site_detailed_reuses_parsed_candidates_per_document(self):
        MODULE.clear_runtime_caches()
        site = MODULE.Site("https://example.com/page", "top", False, "测试站")
        document = "<html><body>190期 稳杀一行【金行】</body></html>"

        with (
            mock.patch.object(MODULE, "collect_documents", return_value=[document]),
            mock.patch.object(MODULE, "parse_candidates_for_site", wraps=MODULE.parse_candidates_for_site) as parser,
        ):
            lines, error, _ = MODULE.scrape_site_detailed(site, 1, 20, False, 190)

        self.assertEqual(lines, ["金行 190期 测试站"])
        self.assertIsNone(error)
        parser.assert_called_once_with(document, site)

    def test_collect_documents_fetches_same_depth_links_concurrently(self):
        MODULE.clear_runtime_caches()
        session = object()
        pages = {
            "https://example.com/page": "<html><iframe src='/one'></iframe><iframe src='/two'></iframe></html>",
            "https://example.com/one": "<html>one</html>",
            "https://example.com/two": "<html>two</html>",
        }

        def fake_fetch(_session, url, _timeout):
            if url != "https://example.com/page":
                time.sleep(0.2)
            return pages[url]

        started = time.perf_counter()
        with mock.patch.object(MODULE, "fetch_text", side_effect=fake_fetch):
            documents = MODULE.collect_documents(session, "https://example.com/page", 20)
        elapsed = time.perf_counter() - started

        self.assertEqual(
            documents,
            [
                pages["https://example.com/page"],
                pages["https://example.com/one"],
                pages["https://example.com/two"],
                pages["https://example.com/one"] + "\n" + pages["https://example.com/two"],
            ],
        )
        self.assertLess(elapsed, 0.35)

    def test_browser_first_url_skips_document_collection(self):
        MODULE.clear_runtime_caches()
        site = MODULE.Site(
            "https://pwqviw.1tcpi-45qgo-qddfnk.work:16677/topic/291140.html",
            "top",
            False,
            "浏览器站",
        )
        document = "190期:绝杀(1)行【金行】开:？00对"

        with (
            mock.patch.object(MODULE, "fetch_browser_text", return_value=document) as browser_fetch,
            mock.patch.object(MODULE, "collect_documents") as collect_documents,
        ):
            lines, error, _ = MODULE.scrape_site_detailed(site, 1, 20, False, 190)

        self.assertEqual(lines, ["金行 190期 浏览器站"])
        self.assertIsNone(error)
        browser_fetch.assert_called_once_with(site.url, 20, False, False, 190, site=site)
        collect_documents.assert_not_called()

    def test_nanerbense_opens_only_the_matching_period_detail_page(self):
        MODULE.clear_runtime_caches()
        site = MODULE.Site(
            "https://mxiscni.nkh6s-vfni4-lwgfvw.xyz:16677/topic/257907.html",
            "top",
            False,
            "男儿本色",
        )
        listing = """
        <a href="/topic/other.html"><div class="title"><p>190期：【其他站】☆绝杀一行☆实力见证！</p></div></a>
        <a href="/topic/naner-190.html"><div class="title"><p>190期：【男儿本色】☆绝杀一行☆实力见证！</p></div></a>
        """
        detail = "190期:绝杀(1)行【水行】开:0000准\n189期:绝杀(1)行【火行】开:龙15准"

        with (
            mock.patch.object(MODULE, "fetch_text", return_value=listing),
            mock.patch.object(MODULE, "collect_documents", return_value=[detail]) as collect_documents,
        ):
            lines, error, _ = MODULE.scrape_site_detailed(site, 1, 20, False, 190)

        self.assertEqual(lines, ["水行 190期 男儿本色"])
        self.assertIsNone(error)
        self.assertIn(site.url, MODULE.SITE_SPECIFIC_ONLY_URLS)
        self.assertEqual(
            collect_documents.call_args.args[1],
            "https://mxiscni.nkh6s-vfni4-lwgfvw.xyz:16677/topic/naner-190.html",
        )

    def test_nanerbense_rejects_non_unique_matching_period_entry(self):
        MODULE.clear_runtime_caches()
        site = MODULE.Site(
            "https://mxiscni.nkh6s-vfni4-lwgfvw.xyz:16677/topic/257907.html",
            "top",
            False,
            "男儿本色",
        )
        listing = """
        <a href="/topic/naner-a.html"><div class="title"><p>190期：【男儿本色】☆绝杀一行☆实力见证！</p></div></a>
        <a href="/topic/naner-b.html"><div class="title"><p>190期：【男儿本色】☆绝杀一行☆实力见证！</p></div></a>
        """

        with (
            mock.patch.object(MODULE, "fetch_text", return_value=listing),
            mock.patch.object(MODULE, "collect_documents") as collect_documents,
        ):
            lines, error, _ = MODULE.scrape_site_detailed(site, 1, 20, False, 190)

        self.assertEqual(lines, [])
        self.assertIn("专属入口不唯一", error)
        collect_documents.assert_not_called()

    def test_browser_first_urls_are_routed_to_browser_worker_pool(self):
        site = MODULE.Site(
            "https://pwqviw.1tcpi-45qgo-qddfnk.work:16677/topic/291140.html",
            "top",
            False,
            "浏览器站",
        )

        self.assertTrue(MODULE.site_uses_browser_first(site))
        self.assertTrue(MODULE.site_needs_browser(site))

    def test_article_admin_api_url_is_loaded_and_routed_to_http_pool(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sites.json"
            path.write_text(
                json.dumps(
                    [
                        {
                            "name": "接口站",
                            "url": "https://example.com/article/admin/abc",
                            "api_url": "https://example.com/api/article/abc",
                            "region": "bottom",
                            "click_first": True,
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            site = MODULE.load_sites(path)[0]

        self.assertEqual(site.api_url, "https://example.com/api/article/abc")
        self.assertTrue(MODULE.site_uses_api_first(site))
        self.assertFalse(MODULE.site_needs_browser(site))

    def test_article_admin_uses_api_url_before_browser(self):
        MODULE.clear_runtime_caches()
        article_id = "6a143f7ebf0a6cb1dd38fb8f"
        site = MODULE.Site(
            f"https://example.com/article/admin/{article_id}?url=test",
            "bottom",
            True,
            "接口站",
            f"https://example.com/api/proxy/manager-articles/{article_id}",
        )
        api_document = "190期:绝杀一行【水行】开:0000准"
        payload = json.dumps({
            "id": article_id,
            "authorNickname": "接口站",
            "title": base64.b64encode("190期：【绝杀一行】".encode()).decode(),
            "html": base64.b64encode(api_document.encode()).decode(),
            "formSections": [{"id": "section", "name": "主条目", "type": "mainarticle"}],
        }, ensure_ascii=False)

        with (
            mock.patch.object(MODULE, "fetch_text", return_value=payload) as fetch_text,
            mock.patch.object(MODULE, "fetch_browser_text") as browser_fetch,
        ):
            lines, error, documents = MODULE.scrape_site_detailed(site, 1, 20, False, 190)

        self.assertEqual(lines, ["水行 190期 接口站"])
        self.assertIsNone(error)
        self.assertEqual(documents, [api_document])
        fetch_text.assert_called_once()
        self.assertEqual(fetch_text.call_args.args[1], site.api_url)
        browser_fetch.assert_not_called()

    def test_article_admin_api_404_falls_back_to_browser_page(self):
        MODULE.clear_runtime_caches()
        article_id = "6a143f7ebf0a6cb1dd38fb8f"
        site = MODULE.Site(
            f"https://example.com/article/admin/{article_id}",
            "bottom",
            True,
            "接口站",
            f"https://example.com/api/proxy/manager-articles/{article_id}",
        )

        browser_document = "190期:绝杀一行【土行】开:0000准"
        with (
            mock.patch.object(MODULE, "fetch_text", side_effect=MODULE.DocumentFetchError("HTTPError: 404 Client Error")),
            mock.patch.object(MODULE, "fetch_browser_text", return_value=browser_document) as browser_fetch,
        ):
            lines, error, _ = MODULE.scrape_site_detailed(site, 1, 20, False, 190)

        self.assertEqual(lines, ["土行 190期 接口站"])
        self.assertIsNone(error)
        browser_fetch.assert_called_once_with(
            site.url, 20, MODULE.site_browser_click_first(site), False, 190, site=site
        )

    def test_article_admin_decoded_empty_shell_falls_back_to_browser_page(self):
        MODULE.clear_runtime_caches()
        article_id = "6a143f7ebf0a6cb1dd38fb8f"
        site = MODULE.Site(
            f"https://example.com/article/admin/{article_id}",
            "bottom",
            True,
            "接口站",
            f"https://example.com/api/proxy/manager-articles/{article_id}",
        )
        api_document = "190期 页面加载中"
        browser_document = "190期:绝杀一行【木行】开:0000准"

        with (
            mock.patch.object(MODULE, "collect_article_admin_api_documents", return_value=([api_document], None)),
            mock.patch.object(MODULE, "fetch_browser_text", return_value=browser_document) as browser_fetch,
        ):
            lines, error, _ = MODULE.scrape_site_detailed(site, 1, 20, False, 190)

        self.assertEqual(lines, ["木行 190期 接口站"])
        self.assertIsNone(error)
        browser_fetch.assert_called_once_with(
            site.url, 20, MODULE.site_browser_click_first(site), False, 190, site=site
        )

    def test_article_admin_empty_base64_shell_falls_back_to_browser_page(self):
        MODULE.clear_runtime_caches()
        article_id = "6a143f7ebf0a6cb1dd38fb8f"
        site = MODULE.Site(
            f"https://example.com/article/admin/{article_id}",
            "bottom",
            True,
            "接口站",
            f"https://example.com/api/proxy/manager-articles/{article_id}",
        )
        payload = json.dumps({"id": article_id, "html": ""})
        browser_document = "190期:绝杀一行【木行】开:0000准"

        with (
            mock.patch.object(MODULE, "fetch_text", return_value=payload),
            mock.patch.object(MODULE, "fetch_browser_text", return_value=browser_document) as browser_fetch,
        ):
            lines, error, _ = MODULE.scrape_site_detailed(site, 1, 20, False, 190)

        self.assertEqual(lines, ["木行 190期 接口站"])
        self.assertIsNone(error)
        browser_fetch.assert_called_once_with(
            site.url, 20, MODULE.site_browser_click_first(site), False, 190, site=site
        )

    def test_article_admin_rejects_invalid_base64_without_browser_fallback(self):
        MODULE.clear_runtime_caches()
        article_id = "6a143f7ebf0a6cb1dd38fb8f"
        site = MODULE.Site(
            f"https://example.com/article/admin/{article_id}",
            "bottom",
            True,
            "接口站",
            f"https://example.com/api/proxy/manager-articles/{article_id}",
        )
        payload = json.dumps({
            "id": article_id,
            "authorNickname": "接口站",
            "title": base64.b64encode("190期：【绝杀一行】".encode()).decode(),
            "html": "%%%not-base64%%%",
            "formSections": [{"id": "section", "name": "主条目", "type": "mainarticle"}],
        })

        with (
            mock.patch.object(MODULE, "fetch_text", return_value=payload),
            mock.patch.object(MODULE, "fetch_browser_text") as browser_fetch,
        ):
            lines, error, _ = MODULE.scrape_site_detailed(site, 1, 20, False, 190)

        self.assertEqual(lines, [])
        self.assertIn("Base64", error)
        browser_fetch.assert_not_called()

    def test_article_admin_rejects_json_id_mismatch_without_browser_fallback(self):
        MODULE.clear_runtime_caches()
        article_id = "6a143f7ebf0a6cb1dd38fb8f"
        site = MODULE.Site(
            f"https://example.com/article/admin/{article_id}",
            "bottom",
            True,
            "接口站",
            f"https://example.com/api/proxy/manager-articles/{article_id}",
        )
        body = base64.b64encode("190期:绝杀一行【火行】开:0000准".encode()).decode()
        payload = json.dumps({"id": "6a144657597e16d57eacb65e", "html": body})

        with (
            mock.patch.object(MODULE, "fetch_text", return_value=payload),
            mock.patch.object(MODULE, "fetch_browser_text") as browser_fetch,
        ):
            lines, error, _ = MODULE.scrape_site_detailed(site, 1, 20, False, 190)

        self.assertEqual(lines, [])
        self.assertIn("ID不一致", error)
        browser_fetch.assert_not_called()

    def test_article_admin_decoded_body_still_requires_unique_target_wuxing(self):
        MODULE.clear_runtime_caches()
        article_id = "6a143f7ebf0a6cb1dd38fb8f"
        site = MODULE.Site(
            f"https://example.com/article/admin/{article_id}",
            "bottom",
            True,
            "接口站",
            f"https://example.com/api/proxy/manager-articles/{article_id}",
        )
        decoded = "\n".join([
            "190期:绝杀一行【火行】开:0000准",
            "190期:绝杀一行【金行】开:0000准",
        ])
        payload = json.dumps({
            "id": article_id,
            "authorNickname": "接口站",
            "title": base64.b64encode("190期：【绝杀一行】".encode()).decode(),
            "html": base64.b64encode(decoded.encode()).decode(),
            "formSections": [{"id": "section", "name": "主条目", "type": "mainarticle"}],
        })

        with (
            mock.patch.object(MODULE, "fetch_text", return_value=payload),
            mock.patch.object(MODULE, "fetch_browser_text") as browser_fetch,
        ):
            lines, error, _ = MODULE.scrape_site_detailed(site, 1, 20, False, 190)

        self.assertEqual(lines, [])
        self.assertIn("五行冲突", error)
        browser_fetch.assert_not_called()

    def test_article_admin_decoded_body_keeps_advertisement_boundary_strict(self):
        MODULE.clear_runtime_caches()
        article_id = "6a143f7ebf0a6cb1dd38fb8f"
        site = MODULE.Site(
            f"https://example.com/article/admin/{article_id}",
            "bottom",
            True,
            "接口站",
            f"https://example.com/api/proxy/manager-articles/{article_id}",
        )
        decoded = "\n".join(["190期 普通资料", "广告栏目", "绝杀一行【金行】开:0000准"])
        payload = json.dumps({
            "id": article_id,
            "authorNickname": "接口站",
            "title": base64.b64encode("190期：【绝杀一行】".encode()).decode(),
            "html": base64.b64encode(decoded.encode()).decode(),
            "formSections": [{"id": "section", "name": "主条目", "type": "mainarticle"}],
        })

        with (
            mock.patch.object(MODULE, "fetch_text", return_value=payload),
            mock.patch.object(MODULE, "fetch_browser_text") as browser_fetch,
        ):
            lines, error, _ = MODULE.scrape_site_detailed(site, 1, 20, False, 190)

        self.assertEqual(lines, [])
        self.assertIn("未找到", error)
        browser_fetch.assert_not_called()

    def test_article_admin_api_with_target_signal_does_not_fallback_to_browser_on_strict_failure(self):
        MODULE.clear_runtime_caches()
        article_id = "6a143f7ebf0a6cb1dd38fb8f"
        site = MODULE.Site(
            f"https://example.com/article/admin/{article_id}",
            "top",
            True,
            "接口站",
            f"https://example.com/api/proxy/manager-articles/{article_id}",
        )
        api_document = "\n".join(
            [
                "191期:绝杀一行【金行】开:0000准",
                "190期:绝杀一行【木行】开:0000准",
                "189期:绝杀一行【水行】开:0000准",
                "188期:绝杀一行【土行】开:0000准",
            ]
        )

        payload = json.dumps({
            "id": article_id,
            "authorNickname": "接口站",
            "title": base64.b64encode("191期：【绝杀一行】".encode()).decode(),
            "html": base64.b64encode(api_document.encode()).decode(),
            "formSections": [{"id": "section", "name": "主条目", "type": "mainarticle"}],
        })
        with (
            mock.patch.object(MODULE, "fetch_text", return_value=payload),
            mock.patch.object(MODULE, "fetch_browser_text") as browser_fetch,
        ):
            lines, error, _ = MODULE.scrape_site_detailed(site, 1, 20, False, 188)

        self.assertEqual(lines, [])
        self.assertIn("顶部只允许前3条", error)
        browser_fetch.assert_not_called()

    def test_article_api_selects_only_the_unique_nested_record_by_url_id(self):
        article_id = "6a143f7ebf0a6cb1dd38fb8f"
        site = MODULE.Site(
            f"https://example.com/article/admin/{article_id}",
            "bottom",
            True,
            "接口站",
            f"https://example.com/api/proxy/manager-articles/{article_id}",
        )
        target_html = "190期:绝杀一行【金行】开:0000准"
        decoy_html = "190期:绝杀一行【木行】开:0000准"
        record = lambda body, record_id: {
            "id": record_id,
            "authorNickname": "接口站",
            "title": base64.b64encode("190期：【绝杀一行】".encode()).decode(),
            "html": base64.b64encode(body.encode()).decode(),
            "formSections": [{"id": "section", "name": "主条目", "type": "mainarticle"}],
        }
        payload = json.dumps({"data": [record(decoy_html, "other-id"), record(target_html, article_id)]})

        self.assertEqual(MODULE.decode_article_admin_api_document(payload, site), target_html)

    def test_article_api_rejects_duplicate_nested_target_ids(self):
        article_id = "6a143f7ebf0a6cb1dd38fb8f"
        site = MODULE.Site(
            f"https://example.com/article/admin/{article_id}",
            "bottom",
            False,
            "接口站",
            f"https://example.com/api/proxy/manager-articles/{article_id}",
        )
        record = {
            "id": article_id,
            "authorNickname": "接口站",
            "title": base64.b64encode("190期：【绝杀一行】".encode()).decode(),
            "html": base64.b64encode("190期:绝杀一行【金行】".encode()).decode(),
            "formSections": [{"id": "section", "name": "主条目", "type": "mainarticle"}],
        }

        with self.assertRaisesRegex(MODULE.DocumentFetchError, "多个"):
            MODULE.decode_article_admin_api_document(json.dumps({"items": [record, dict(record)]}), site)

    def test_article_api_rejects_missing_author_title_or_main_column(self):
        article_id = "6a143f7ebf0a6cb1dd38fb8f"
        site = MODULE.Site(
            f"https://example.com/article/admin/{article_id}",
            "bottom",
            False,
            "接口站",
            f"https://example.com/api/proxy/manager-articles/{article_id}",
        )
        base = {
            "id": article_id,
            "authorNickname": "接口站",
            "title": base64.b64encode("190期：【绝杀一行】".encode()).decode(),
            "html": base64.b64encode("190期:绝杀一行【金行】".encode()).decode(),
            "formSections": [{"id": "section", "name": "主条目", "type": "mainarticle"}],
        }
        for field in ("authorNickname", "title", "formSections"):
            with self.subTest(field=field):
                invalid = dict(base)
                invalid.pop(field)
                with self.assertRaises(MODULE.DocumentFetchError):
                    MODULE.decode_article_admin_api_document(json.dumps(invalid), site)

    def test_spa_forums_keep_only_the_exact_user_article_records(self):
        site = MODULE.Site(
            "https://example.com:12277/#/users/116157",
            "top",
            True,
            "笨鸟先飞",
        )
        payload = json.dumps([
            {"id": 1, "user_id": 999, "topic": "诱饵", "content": "190期绝杀一行【木行】"},
            {"id": 2, "user_id": 116157, "topic": "目标", "content": "190期绝杀一行【金行】"},
        ])
        documents = MODULE.decode_spa_forums_documents(payload, site)

        self.assertEqual(
            documents,
            [f"{MODULE.SPA_STRUCTURED_RECORD_MARKER}\n目标\n190期绝杀一行【金行】"],
        )

    def test_spa_forums_reject_duplicate_article_id_and_profile_mismatch(self):
        site = MODULE.Site(
            "https://example.com:12277/#/users/116157",
            "top",
            True,
            "笨鸟先飞",
        )
        duplicate = json.dumps([
            {"id": 2, "user_id": 116157, "topic": "一", "content": "190期绝杀一行【金行】"},
            {"id": 2, "user_id": 116157, "topic": "二", "content": "190期绝杀一行【木行】"},
        ])
        with self.assertRaisesRegex(MODULE.DocumentFetchError, "文章ID重复"):
            MODULE.decode_spa_forums_documents(duplicate, site)

        with self.assertRaisesRegex(MODULE.DocumentFetchError, "用户"):
            MODULE.validate_spa_profile({"id": 116157, "nickname": "其他用户"}, site)

    def test_browser_dynamic_document_requires_the_page_record_boundary(self):
        article_id = "6a143f7ebf0a6cb1dd38fb8f"
        site = MODULE.Site(
            f"https://example.com/article/admin/{article_id}",
            "bottom",
            False,
            "接口站",
        )
        source = f"<script>recordId='{article_id}'; author='接口站'</script>"
        body = "190期:绝杀一行【金行】"
        self.assertEqual(
            MODULE.validate_browser_record_boundary(site, site.url, source, body),
            None,
        )

        with self.assertRaisesRegex(MODULE.DocumentFetchError, "文章ID"):
            MODULE.validate_browser_record_boundary(site, site.url, "<main>接口站</main>", body)

        with self.assertRaisesRegex(MODULE.DocumentFetchError, "作者"):
            MODULE.validate_browser_record_boundary(site, site.url, source.replace("接口站", "其他"), body)

    def test_target_signal_never_combines_period_and_wuxing_across_documents(self):
        self.assertFalse(
            MODULE.documents_have_target_signal(
                ["190期", "绝杀一行【金行】"],
                190,
            )
        )

    def test_spa_sites_use_structured_api_before_browser(self):
        site = MODULE.Site(
            "https://example.com:12277/#/users/116157",
            "top",
            True,
            "笨鸟先飞",
        )
        self.assertTrue(MODULE.site_uses_spa_api_first(site))
        self.assertFalse(MODULE.site_uses_browser_first(site))

    def test_spa_structured_record_stops_before_old_footer_rows(self):
        site = MODULE.Site(
            "https://example.com:12277/#/users/116157",
            "top",
            True,
            "笨鸟先飞",
        )
        document = "\n".join([
            MODULE.SPA_STRUCTURED_RECORD_MARKER,
            "200期:绝杀一行【金行】开:0000准",
            "199期:绝杀一行【木行】开:0000准",
            "旧帖子",
            "200期:绝杀一行【水行】开:0000准",
        ])

        candidates = MODULE.parse_candidates_for_site(document, site)

        self.assertEqual([(item.period, item.wuxing) for item in candidates], [("200期", "金行"), ("199期", "木行")])

    def test_article_manager_api_requires_same_origin_exact_path_and_author(self):
        article_id = "6a33e71adfa16552b923d2b7"
        page_url = f"https://example.com:29400/article/manager/{article_id}?url=jyb"
        valid_api = f"https://example.com:29400/api/proxy/manager-articles/{article_id}"
        body = base64.b64encode(
            "<p>193期:〖齐天大胜〗④行中特【土.金.水.火】开:00准</p>".encode()
        ).decode()

        invalid_cases = [
            ("https://other.example:29400" + f"/api/proxy/manager-articles/{article_id}", "齐天大胜"),
            (f"https://example.com:29400/api/other/{article_id}", "齐天大胜"),
            (valid_api, "新齐天大胜"),
        ]
        for api_url, author in invalid_cases:
            with self.subTest(api_url=api_url, author=author):
                site = MODULE.Site(page_url, "bottom", False, "齐天大胜", api_url)
                payload = json.dumps({
                    "id": article_id,
                    "authorNickname": author,
                    "title": base64.b64encode("193期：【绝杀一行】".encode()).decode(),
                    "html": body,
                    "formSections": [{"id": "section", "name": "主条目", "type": "mainarticle"}],
                })
                with mock.patch.object(MODULE, "fetch_text", return_value=payload):
                    lines, error, _ = MODULE.scrape_site_detailed(site, 1, 20, False, 193)
                self.assertEqual(lines, [])
                self.assertTrue(any(word in error for word in ("同源", "路径", "作者")), error)

    def test_manager_site_parser_requires_one_real_record_and_exact_anchors(self):
        url = "https://drxgkjt.uu1oc-eyjpt-uxyccu.xyz:29400/article/manager/6a33e71adfa16552b923d2b7?url=jyb"
        site = MODULE.Site(url, "bottom", False, "齐天大胜")
        valid = "<p><span>193期:</span><span>〖齐天大胜〗</span><span>④行中特【土.金.水.火】</span></p>"
        candidates = MODULE.parse_candidates_for_site(valid, site)
        self.assertEqual([(item.period, item.wuxing) for item in candidates], [("193期", "木行")])

        invalid_documents = [
            "<p>193期:〖新齐天大胜资料〗④行中特【土.金.水.火】</p>",
            "<p>193期:齐天大胜A ④行中特【土.金.水.火】</p>",
            "<p>193期:〖齐天大胜〗非④行中特【土.金.水.火】</p>",
            "<p>193期:〖齐天大胜〗非 ④行中特【土.金.水.火】</p>",
            "<p>193期:〖齐天大胜〗不是④行中特【土.金.水.火】</p>",
            "<p>193期:〖齐天大胜〗取消④行中特【土.金.水.火】</p>",
            "<p>193期:今日标题</p><p>〖齐天大胜〗④行中特【土.金.水.火】</p>",
            "<div>193期:〖齐天大胜〗<div>④行中特【土.金.水.火】</div></div>",
            "<p>193期:〖齐天大胜〗④行中特【土.金.水.水】</p>",
        ]
        for document in invalid_documents:
            with self.subTest(document=document):
                self.assertEqual(MODULE.parse_candidates_for_site(document, site), [])

        single_url = "https://hquomm.20t3f-0yztv-jiozun.xyz:29444/article/manager/6a4c273b57dc857ae1c07d6d?url=dgd"
        single_site = MODULE.Site(single_url, "bottom", False, "金馬快报")
        self.assertEqual(
            MODULE.parse_candidates_for_site(
                "<p>193期:《金馬快报》不推荐绝杀一行【火】</p>", single_site
            ),
            [],
        )

    def test_manager_site_conflict_and_bottom_three_window_are_enforced(self):
        url = "https://drxgkjt.uu1oc-eyjpt-uxyccu.xyz:29400/article/manager/6a33e71adfa16552b923d2b7?url=jyb"
        site = MODULE.Site(url, "bottom", False, "齐天大胜")
        rows = "".join(
            f"<p>{period}期:〖齐天大胜〗④行中特【{values}】</p>"
            for period, values in [
                (190, "金.木.水.火"),
                (191, "金.木.水.土"),
                (192, "金.木.火.土"),
                (193, "金.水.火.土"),
                (194, "木.水.火.土"),
            ]
        )
        parser_fn = lambda document: MODULE.parse_candidates_for_site(document, site)
        self.assertIn("后3条", MODULE.region_three_window_failure_reason([rows], "bottom", 191, parser_fn))
        self.assertIsNone(MODULE.region_three_window_failure_reason([rows], "bottom", 192, parser_fn))
        self.assertIsNone(MODULE.region_three_window_failure_reason([rows], "bottom", 194, parser_fn))

        conflict = rows + "<p>193期:〖齐天大胜〗④行中特【金.木.水.火】</p>"
        candidates = MODULE.parse_candidates_for_site(conflict, site)
        self.assertTrue(MODULE.has_conflicting_target_candidates(candidates, 193))

    def test_verified_direct_browser_sites_skip_click_first(self):
        MODULE.clear_runtime_caches()
        site = MODULE.Site(
            "https://flrmed.u3l95-7ktwf-clwwtq.work:29455/article/admin/6a13fd7b741e3e91a04e59d1?url=sgnn",
            "bottom",
            True,
            "爆发钱庄",
        )
        document = "190期:绝杀一行【土行】开:0000准"

        with mock.patch.object(MODULE, "fetch_browser_text", return_value=document) as browser_fetch:
            lines, error, _ = MODULE.scrape_site_detailed(site, 1, 20, False, 190)

        self.assertEqual(lines, ["土行 190期 爆发钱庄"])
        self.assertIsNone(error)
        browser_fetch.assert_called_once_with(site.url, 20, False, False, 190, site=site)

    def test_191_site_specific_current_blocks_ignore_old_conflicts(self):
        samples = [
            ("澳门创富网", "https://nyekjhvz.kr4ar-cgeaj-aekfox.xyz:16677/", "top", "澳门创富 『绝杀一行』 191期:【绝杀一行】【水行】开:0000准 190期:【绝杀一行】【木行】开:兔16错 旧附加脚本 191期:精打细算 万花巷杀一行:【土行】", "水行"),
            ("桃李不言", "https://e7rzi6.t5ti5-at6k5-fugxpa.work/topic/469841.html", "top", "特料帖 191期:【绝杀一行】 作者:桃李不言 191期【绝杀一行】【杀火行】开0000对 190期【绝杀一行】【杀木行】开兔16错 旧附加脚本 191期【绝杀一行】【杀水行】开牛29错", "火行"),
            ("随便项链", "https://zcphjs.ce83x-ms2rz-orwude.work:12277/#/users/3475", "top", "用户主页 随便项链 随便项链 2026-07-10 12:44:46 191 绝杀一行 澳彩 191期【绝杀一行】【杀火行】开:？00对 190期【绝杀一行】【杀金行】开:兔16对 旧帖子 随便项链 191期【绝杀一行】【杀水行】开:牛29错", "火行"),
            ("可爱孤儿", "https://zcphjs.ce83x-ms2rz-orwude.work:12277/#/users/3031", "top", "用户主页 可怕孤儿 可怕孤儿 2026-07-10 22:09:58 192 绝杀一行 澳彩 192期【绝杀一行】【杀土行】开？00对 191期【绝杀一行】【杀水行】开虎29对 190期【绝杀一行】【杀金行】开兔16对 旧帖子 可怕孤儿 191期【绝杀一行】【杀火行】开？00对", "水行"),
            ("笨鸟先飞", "https://zcphjs.ce83x-ms2rz-orwude.work:12277/#/users/116157", "top", "用户主页 笨鸟先飞a 2026-07-10 22:40:32 192 192期:金龙【绝杀一行】已公开 澳彩 192期:绝杀(1)行【土行】开0000准 191期:绝杀(1)行【金行】开虎29准 190期:绝杀(1)行【火行】开兔16准 笨鸟先飞a 2026-07-09 22:34:20 191 191期:金龙【绝杀一行】已公开 澳彩 191期:绝杀(1)行【水行】开0000准", "金行"),
            ("广西仔", "https://jldzuea.0xkqd-q7ng5-boerfb.xyz:16677/topic/677608.html", "bottom", "191期:精品推荐【绝杀一行】 877750a.com 发表于 07月10日 189期:绝杀(一)行【金行】开:龙15准 190期:绝杀(一)行【火行】开:兔16准 191期:绝杀(一)行【木行】开:0000准 旧附加脚本 191期:绝杀(一)行【水行】开:牛29准", "木行"),
            ("信口雌黄", "https://fzzmqscl.bdppk-lyf4y-teyajr.xyz:16677/topic/439186.html", "bottom", "href=/topic/439186.html 高手贴 191期【绝杀一行】已更新 作者:信口雌黄 189期【绝杀一行】《水行》开:龙15准 190期【绝杀一行】《土行》开:兔16准 191期【绝杀一行】《金行》开:0000准 旧附加脚本 191期【绝杀一行】《木行》开:牛29准", "金行"),
            ("百万资料", "https://swnrapsd.74wyl-mm601-cbpzhn.xyz:16677/", "top", "百万资料库 191期稳杀(1)行【木】开0000准 190期稳杀(1)行【水】开兔16准 旧栏目 191期绝杀一行【金行】开牛29准", "木行"),
            ("猪狗不如", "https://cwaskgxv.hzpd5-2r09a-wieopn.xyz:16677/topic/282016.html", "top", "191期【绝杀一行】已公开 猪狗不如 发表于 07月10日 191期:〓【绝杀一行】〓【金行】开:0000赢 190期:〓【绝杀一行】〓【土行】开:兔16赢 旧附加脚本 191期:〓【绝杀一行】〓【水行】开:牛29错", "金行"),
            ("而立之年", "https://dzuojaf.rua12-mwvo8-oriqfc.xyz:16677/topic/461725.html", "top", "精华料 191期:【必杀一行】而立之年 发表于 07月09日 191期：必杀一行【土行】特0000准 190期：必杀一行【金行】特兔16准 旧附加脚本 191期：必杀一行【火行】特牛29准", "土行"),
            ("歧路亡羊", "https://ykeejph.z9koz-18xjn-pvglgy.xyz:16677/topic/677751.html", "top", "191期歧路亡羊【绝杀一行】←内幕猛料! 歧路亡羊 发表于 07月09日 191期【绝杀一行】【金行】开0000准 190期【绝杀一行】【土行】开兔16准 旧附加脚本 191期【绝杀一行】【木行】开牛29准", "金行"),
            ("浮生未歇", "https://evvuoswc.2n3pw-mjk5d-wndmjh.xyz:16677/topic/287366.html", "top", "191期〖浮生未歇〗【绝杀一行】浮生未歇 发表于 07月09日 191期【绝杀一行】【水】开:？00准 190期【绝杀一行】【木】开:兔16错 旧附加脚本 191期【绝杀一行】【木】开:牛29准", "水行"),
            ("八级心动", "https://cwdcaqzn.7mj0h-75k3q-cbuvqb.work:16677/#am", "top", "href=/topic/793011.html 191期:精选来者不笑(绝杀一行) 作者:来者不笑 191期；绝杀一行：（火）开；000中 190期；绝杀一行：（土）开；兔16中 旧附加脚本 191期；绝杀一行：（水）开；牛29中", "火行"),
            ("异口同声", "https://fhktrabu.zbfrm-uzct1-pmycbu.xyz:16677/topic/469065.html", "bottom", "191期【绝杀一行】已更新 异口同声 发表于 07月10日 189期:【绝杀一行】〖金行〗开:龙15准 190期:【绝杀一行】〖水行〗开:兔16准 191期:【绝杀一行】〖土行〗开:0000准 上一篇:191期澳彩【20码中特】 旧附加脚本 191期:【绝杀一行】〖水行〗开:牛29错", "土行"),
            ("提心吊胆", "https://eebysckd.2go6k-y0pfv-fqbdsm.xyz:16677/topic/626101.html", "top", "191期:提心吊胆「精杀一行」提心吊胆 发表于 07月09日 191期：▼精杀一行▼【木】开0000对 190期：▼精杀一行▼【金】开兔16对 旧附加脚本 191期：▼精杀一行▼【水】开牛29错", "木行"),
            ("迷迷糊糊", "https://hhsmgw.rcl5b-akta2-ylzzwv.xyz:16677/topic/282006.html", "top", "191期【绝杀一行】已公开 迷迷糊糊 发表于 07月10日 191期:【绝杀1行】【土行】开:000赢 190期:【绝杀1行】【火行】开:兔16赢 旧附加脚本 191期:【绝杀1行】【木行】开:牛29赢", "土行"),
        ]

        for name, url, pick, document, expected in samples:
            with self.subTest(site=name):
                site = MODULE.Site(url, pick, True, name)
                candidates = MODULE.parse_candidates_for_site(document, site)
                values = [candidate.wuxing for candidate in candidates if candidate.period == "191期"]
                self.assertEqual(values, [expected])
                self.assertIn(url, MODULE.SITE_SPECIFIC_ONLY_URLS)

    def test_site_current_block_uses_first_authoritative_document_only(self):
        site = MODULE.Site(
            "https://e7rzi6.t5ti5-at6k5-fugxpa.work/topic/469841.html",
            "top",
            False,
            "桃李不言",
        )
        shell = "页面壳"
        current = "特料帖 191期【绝杀一行】 作者:桃李不言 191期【绝杀一行】【杀火行】开0000对"
        stale = "特料帖 191期【绝杀一行】 作者:桃李不言 191期【绝杀一行】【杀水行】开牛29错"

        documents = MODULE.site_authoritative_documents(
            [shell, current, stale],
            site,
            parser_fn=lambda document: MODULE.parse_candidates_for_site(document, site),
        )

        self.assertEqual(documents, [current])

    def test_current_block_ignores_conflict_from_old_noise_outside_block(self):
        site = MODULE.Site(
            "https://cwaskgxv.hzpd5-2r09a-wieopn.xyz:16677/topic/282016.html",
            "top",
            False,
            "猪狗不如",
        )
        document = (
            "191期【绝杀一行】已公开 猪狗不如 发表于 07月10日 "
            "191期: 〓 【绝杀一行】 〓 【金行】开:0000赢 "
            "190期: 〓 【绝杀一行】 〓 【土行】开:兔16赢 "
            "旧附加脚本 191期: 〓 【绝杀一行】 〓 【水行】开:牛29错"
        )

        old_noise = MODULE.Candidate("191期", "水行", 99, "旧附加脚本")
        with mock.patch.object(MODULE, "collect_documents", return_value=[document]), mock.patch.object(
            MODULE, "parse_raw_candidates", return_value=[old_noise]
        ):
            lines, error, _ = MODULE.scrape_site_detailed(site, 1, 20, False, 191)

        self.assertEqual(lines, ["金行 191期 猪狗不如"])
        self.assertIsNone(error)

    def test_current_block_rejects_conflict_inside_authoritative_block(self):
        site = MODULE.Site(
            "https://cwaskgxv.hzpd5-2r09a-wieopn.xyz:16677/topic/282016.html",
            "top",
            False,
            "猪狗不如",
        )
        rows = [
            (
                "191期:【绝杀一行】【金行】开0000赢 "
                "191期:【绝杀一行】【水行】开0000赢 "
                "190期:【绝杀一行】【土行】开兔16赢"
            ),
            (
                "190期:【绝杀一行】【土行】开兔16赢 "
                "191期:【绝杀一行】【金行】开0000赢 "
                "191期:【绝杀一行】【水行】开0000赢"
            ),
            (
                "192期:【绝杀一行】【木行】开0000赢 "
                "191期:【绝杀一行】【金行】开0000赢 "
                "191期:【绝杀一行】【水行】开0000赢 "
                "190期:【绝杀一行】【土行】开兔16赢"
            ),
            (
                "190期:【绝杀一行】【土行】开兔16赢 "
                "191期:【绝杀一行】【金行】开0000赢 "
                "正文备注：上一篇预测有误，现更正如下 "
                "191期:【绝杀一行】【水行】开0000赢"
            ),
        ]

        for row_text in rows:
            with self.subTest(rows=row_text), mock.patch.object(
                MODULE,
                "collect_documents",
                return_value=[f"191期【绝杀一行】已公开 猪狗不如 发表于 07月10日 {row_text}"],
            ):
                lines, error, _ = MODULE.scrape_site_detailed(site, 1, 20, False, 191)

            self.assertEqual(lines, [])
            self.assertIn("五行冲突", error)

    def test_191_browser_routes_skip_known_pages_and_click_exact_bajixindong_topic(self):
        skip_urls = {
            "https://zcphjs.ce83x-ms2rz-orwude.work:12277/#/users/3475",
            "https://zcphjs.ce83x-ms2rz-orwude.work:12277/#/users/3031",
            "https://swnrapsd.74wyl-mm601-cbpzhn.xyz:16677/",
            "https://fzzmqscl.bdppk-lyf4y-teyajr.xyz:16677/topic/439186.html",
            "https://evvuoswc.2n3pw-mjk5d-wndmjh.xyz:16677/topic/287366.html",
            "https://2.www39169b.com:888/#62111",
        }
        for url in skip_urls:
            self.assertFalse(MODULE.site_browser_click_first(MODULE.Site(url, "top", True, "站点")))

        class Element:
            def __init__(self, text, href):
                self.text = text
                self.href = href

            def get_attribute(self, name):
                return self.href if name == "href" else None

        site_url = "https://cwdcaqzn.7mj0h-75k3q-cbuvqb.work:16677/#am"
        exact = Element("191期 精选来者不笑 绝杀一行", "https://cwdcaqzn.7mj0h-75k3q-cbuvqb.work:16677/topic/793011.html")
        noise = Element("191期 其他绝杀一行", "https://cwdcaqzn.7mj0h-75k3q-cbuvqb.work:16677/topic/999999.html")
        self.assertIs(MODULE.select_site_click_target([noise, exact], site_url, 191), exact)

    def test_browser_text_cache_keeps_same_request_in_memory(self):
        MODULE.clear_runtime_caches()

        def fake_fetch(url, timeout, click_first, show_browser, period=None):
            return f"{url} {timeout} {click_first} {period}"

        with mock.patch.object(MODULE, "fetch_browser_text_uncached", side_effect=fake_fetch) as fetch_browser:
            first = MODULE.fetch_browser_text("https://example.com/page", 20, True, False, 159)
            second = MODULE.fetch_browser_text("https://example.com/page", 20, True, False, 159)

        self.assertEqual(first, second)
        fetch_browser.assert_called_once()

    def test_browser_text_cache_separates_same_url_site_sections(self):
        MODULE.clear_runtime_caches()
        url = "https://zxliojf.83gjk-dnne7-kuyach.xyz:16677/"
        spring = MODULE.Site(url, "top", False, "春满乡村")
        shanshui = MODULE.Site(url, "bottom", False, "山水诗意")

        def fake_fetch(_url, _timeout, _click_first, _show_browser, _period, site=None):
            return site.name

        with mock.patch.object(MODULE, "fetch_browser_text_uncached", side_effect=fake_fetch) as fetch_browser:
            spring_text = MODULE.fetch_browser_text(url, 20, False, False, 193, site=spring)
            shanshui_text = MODULE.fetch_browser_text(url, 20, False, False, 193, site=shanshui)

        self.assertEqual(spring_text, "春满乡村")
        self.assertEqual(shanshui_text, "山水诗意")
        self.assertEqual(fetch_browser.call_count, 2)

    def test_single_period_retry_clears_runtime_cache_before_resubmitting(self):
        site = MODULE.Site("https://example.com/a", "top", False, "测试站")
        outcomes = {0: (site, [], "页面里未找到 191期", ["旧正文"], 1.0)}

        with mock.patch.object(MODULE, "clear_runtime_caches") as clear_caches, mock.patch.object(
            MODULE,
            "scrape_indexed_site",
            return_value=(0, site, ["金行 191期 测试站"], None, ["新正文"], 0.5),
        ):
            MODULE.run_retry_scrapes(outcomes, [(0, site)], [], 1, 45, False, 191)

        clear_caches.assert_called_once_with()

    def test_regular_http_scrape_closes_created_session(self):
        class FakeSession:
            def __init__(self):
                self.closed = False

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                self.close()

            def close(self):
                self.closed = True

        session = FakeSession()
        site = MODULE.Site("https://example.com/a", "top", False, "测试站")
        document = "191期绝杀一行【金行】开0000准"

        with mock.patch.object(MODULE, "create_session", return_value=session), mock.patch.object(
            MODULE, "collect_documents", return_value=[document]
        ):
            lines, error, _ = MODULE.scrape_site_detailed(site, 1, 20, False, 191)

        self.assertEqual(lines, ["金行 191期 测试站"])
        self.assertIsNone(error)
        self.assertTrue(session.closed)

    def test_api_fetch_closes_created_session_on_error(self):
        class FakeSession:
            def __init__(self):
                self.closed = False

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                self.close()

            def close(self):
                self.closed = True

        session = FakeSession()
        site = MODULE.Site(
            "https://example.com/article/admin/abc?url=x",
            "bottom",
            False,
            "接口站",
            "https://example.com/api/abc",
        )

        with mock.patch.object(MODULE, "create_session", return_value=session), mock.patch.object(
            MODULE, "fetch_text", side_effect=RuntimeError("boom")
        ):
            documents, error = MODULE.collect_article_admin_api_documents(site, 20)

        self.assertEqual(documents, [])
        self.assertIsInstance(error, RuntimeError)
        self.assertTrue(session.closed)

    def test_history_cache_transaction_serializes_concurrent_updates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "recent_10_cache.json"
            MODULE.save_history_cache({"version": 1, "sites": []}, cache_path)
            sites = [
                MODULE.Site("https://example.com/a", "top", False, "A"),
                MODULE.Site("https://example.com/b", "bottom", False, "B"),
            ]

            def write(site, wuxing):
                def mutate(cache):
                    time.sleep(0.05)
                    MODULE.update_history_cache_entries(cache, [(site, 191, wuxing)])
                    return cache

                MODULE.mutate_history_cache(cache_path, mutate)

            threads = [
                threading.Thread(target=write, args=(sites[0], "金行")),
                threading.Thread(target=write, args=(sites[1], "木行")),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            cache = MODULE.load_history_cache(cache_path)
            self.assertEqual({item["name"] for item in cache["sites"]}, {"A", "B"})

    def test_history_cache_keeps_latest_ten_periods(self):
        site = MODULE.Site("https://example.com/a", "bottom", False, "测试站")
        cache = {}

        for period in range(149, 160):
            MODULE.update_history_cache_entries(cache, [(site, period, "金行")], keep=10)

        entry = cache["sites"][0]
        self.assertEqual([item["period"] for item in entry["history"]], [159, 158, 157, 156, 155, 154, 153, 152, 151, 150])

    def test_history_cache_signature_uses_region_site_identity(self):
        site = MODULE.Site("https://example.com/a", "top", False, "同网址顶部")
        other = MODULE.Site("https://example.com/a", "bottom", False, "同网址尾部")
        cache = {}
        MODULE.update_history_cache_entries(cache, [(site, 158, "金行"), (other, 158, "水行")], keep=10)

        self.assertEqual(MODULE.signature_from_history_cache(cache, site, 158, 10, 60), ((158, "金行"),))
        self.assertEqual(MODULE.signature_from_history_cache(cache, other, 158, 10, 60), ((158, "水行"),))

    def test_pick_candidates_uses_region_order(self):
        candidates = [
            MODULE.Candidate(period="144期", wuxing="金行", order=10, raw="top"),
            MODULE.Candidate(period="144期", wuxing="木行", order=90, raw="bottom"),
        ]
        self.assertEqual(MODULE.pick_candidates(candidates, "top", 1)[0].wuxing, "金行")
        self.assertEqual(MODULE.pick_candidates(candidates, "bottom", 1)[0].wuxing, "木行")

    def test_filter_valid_wuxing_candidates_keeps_only_standard_five(self):
        candidates = [
            MODULE.Candidate(period="144期", wuxing="金行", order=1, raw="ok"),
            MODULE.Candidate(period="144期", wuxing="红波", order=2, raw="bad"),
            MODULE.Candidate(period="144期", wuxing="金行/木行", order=3, raw="bad"),
        ]
        self.assertEqual(MODULE.filter_valid_wuxing_candidates(candidates), [candidates[0]])

    def test_four_wuxing_zhongte_uses_missing_wuxing(self):
        document = "151期:《彻头彻尾》 四行中特 【金.木.水.土】 开:00准"
        candidates = MODULE.parse_candidates(document)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].period, "151期")
        self.assertEqual(candidates[0].wuxing, "火行")

    def test_four_wuxing_zhongte_accepts_circle_wrapped_chars(self):
        document = "154期四行中特⊙金土火◎开虎41准"
        candidates = MODULE.parse_candidates(document)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].period, "154期")
        self.assertEqual(candidates[0].wuxing, "火行")

    def test_wudiuzhu_sihang_uses_missing_wuxing(self):
        document = "154期 【火.土.木.金】 五丢主四行 √"
        candidates = MODULE.parse_candidates(document)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].period, "154期")
        self.assertEqual(candidates[0].wuxing, "水行")

    def test_wubiaozhu_sihang_uses_highlighted_wuxing(self):
        document = """
        <p>【五表主四行】√</p>
        <p>155期【土.木.金.水】</p>
        <p>154期【<span style="background-color: #ffff00;">火</span>.土.木.金】</p>
        <p>151期【<span style="background-color: #ffff00;">水</span>.火.土.木】</p>
        """
        candidates = MODULE.parse_candidates(document)
        self.assertEqual([(candidate.period, candidate.wuxing) for candidate in candidates], [
            ("154期", "火行"),
            ("151期", "水行"),
        ])

    def test_white_swan_site_specific_uses_section_and_current_first_wuxing(self):
        site = MODULE.Site("https://buvwlreg.drr11-soh5x-jcaafg.xyz:16677/", "top", False, "白天鹅")
        document = """
        <p>154期：【别的资料】【金行】开虎41准</p>
        <p>山水诗意（四行中特）</p>
        <p>155期四行中特</p><p>⊙</p><p>水</p><p>金木土</p><p>⊙</p><p>开？00准</p>
        <p>154期四行中特</p><p>⊙</p><p>金土</p><p>火</p><p>⊙</p><p>开虎41准</p>
        """
        candidates = MODULE.parse_candidates_for_site(document, site)
        self.assertEqual([(candidate.period, candidate.wuxing) for candidate in candidates], [
            ("155期", "水行"),
            ("154期", "火行"),
        ])

    def test_white_swan_site_specific_orders_latest_period_first(self):
        site = MODULE.Site("https://buvwlreg.drr11-soh5x-jcaafg.xyz:16677/", "top", False, "白天鹅")
        document = """
        <p>154期四行中特</p><p>⊙</p><p>金土</p><p>火</p><p>⊙</p><p>开虎41准</p>
        <p>155期四行中特</p><p>⊙</p><p>水</p><p>金木土</p><p>⊙</p><p>开？00准</p>
        """

        _, candidates = MODULE.best_document_with_period_candidates(
            [document],
            155,
            "top",
            parser_fn=lambda value: MODULE.parse_candidates_for_site(value, site),
        )

        self.assertEqual([(candidate.period, candidate.wuxing) for candidate in candidates], [
            ("155期", "水行"),
        ])

    def test_dadizhu_site_specific_uses_wubiao_section_and_current_first_wuxing(self):
        site = MODULE.Site("https://jdjzpkce.osyaf-gxlte-otlblr.xyz:16677/", "top", False, "大地主")
        document = """
        <p>【大表主十肖】√</p>
        <p>155期【龙虎鸡狗猴牛蛇马鼠兔】</p>
        <p>【五表主四行】√</p>
        <p>155期【土.木.金.水】</p>
        <p>154期【<span style="background-color: #ffff00;">火</span>.土.木.金】</p>
        """
        candidates = MODULE.parse_candidates_for_site(document, site)
        self.assertEqual([(candidate.period, candidate.wuxing) for candidate in candidates], [
            ("155期", "土行"),
            ("154期", "火行"),
        ])

    def test_zxliojf_site_specific_separates_two_sections(self):
        document = """
        <p>春满乡村（绝杀1.行）</p>
        <p>156期绝杀1.行【火火火】 开？00√</p>
        <p>155期绝杀1.行【金金金】 开鼠07√</p>
        <p>山水诗意（四行中特）</p>
        <p>155期四行中特⊙水金木土⊙开鼠07准</p>
        <p>156期四行中特⊙金木土水⊙开？00准</p>
        """
        chunman = MODULE.Site("https://zxliojf.83gjk-dnne7-kuyach.xyz:16677/", "top", False, "春满乡村")
        shanshui = MODULE.Site("https://zxliojf.83gjk-dnne7-kuyach.xyz:16677/", "bottom", False, "山水诗意")

        self.assertEqual(
            [(candidate.period, candidate.wuxing) for candidate in MODULE.parse_candidates_for_site(document, chunman)],
            [("156期", "火行"), ("155期", "金行")],
        )
        self.assertEqual(
            [(candidate.period, candidate.wuxing) for candidate in MODULE.parse_candidates_for_site(document, shanshui)],
            [("155期", "火行"), ("156期", "火行")],
        )

    def test_shanshuishiyi_bottom_window_ignores_following_sections(self):
        site = MODULE.Site("https://zxliojf.83gjk-dnne7-kuyach.xyz:16677/", "bottom", False, "山水诗意")
        document = """
        <p>春满乡村（绝杀1.行）</p>
        <p>182期绝杀1.行【火火火】 开？00√</p>
        <p>山水诗意（四行中特）</p>
        <p>178期四行中特◎水金火木◎开牛18准</p>
        <p>181期四行中特◎金土火木◎开鼠19错</p>
        <p>182期四行中特◎土火木金◎开？00准</p>
        <p>别的资料（绝杀一行）</p>
        <p>183期:【绝杀一行】【金行】开:0000准</p>
        <p>184期:【绝杀一行】【木行】开:0000准</p>
        <p>185期:【绝杀一行】【水行】开:0000准</p>
        """

        candidates = MODULE.parse_candidates_for_site(document, site)

        self.assertEqual(
            [(candidate.period, candidate.wuxing) for candidate in MODULE.region_target_window_candidates(candidates, "bottom")],
            [("178期", "土行"), ("181期", "水行"), ("182期", "水行")],
        )
        self.assertIsNone(
            MODULE.region_three_window_failure_reason(
                [document],
                "bottom",
                182,
                parser_fn=lambda value: MODULE.parse_candidates_for_site(value, site),
            )
        )

    def test_zxliojf_mirror_url_uses_same_site_specific_sections(self):
        document = """
        <p>春满乡村（绝杀1.行）</p>
        <p>160期绝杀1.行【木木木】 开？00√</p>
        <p>159期绝杀1.行【金金金】 开龙39√</p>
        <p>山水诗意（四行中特）</p>
        <p>160期四行中特⊙金木土水⊙开？00准</p>
        """
        site = MODULE.Site("https://akqasqa.drr11-soh5x-jcaafg.xyz:16677/", "top", False, "春满乡村")

        self.assertEqual(
            [(candidate.period, candidate.wuxing) for candidate in MODULE.parse_candidates_for_site(document, site)],
            [("160期", "木行"), ("159期", "金行")],
        )

    def test_xinkoucuhuang_page_order_puts_current_section_in_bottom_window(self):
        site = MODULE.Site("https://fzzmqscl.bdppk-lyf4y-teyajr.xyz:16677/topic/439186.html", "bottom", False, "信口雌黄")
        document = "\n".join([
            "363期【绝杀一行】《木行》开:龙26准",
            "364期【绝杀一行】《水行》开:马12准",
            "365期【绝杀一行】《土行》开:龙26准",
            "160期【绝杀一行】《木行》开:羊11准",
            "157期【绝杀一行】《金行》开:兔40准",
            "158期【绝杀一行】《水行》开:兔16准",
            "159期【绝杀一行】《火行》开:龙39准",
            "160期【绝杀一行】《木行》开:0000准",
        ])

        candidates = MODULE.parse_candidates_for_site(document, site)

        self.assertEqual(
            [candidate.period for candidate in MODULE.region_target_window_candidates(candidates, "bottom")],
            ["158期", "159期", "160期"],
        )

    def test_pingtewangxin_bottom_window_uses_period_order_for_latest_rows(self):
        site = MODULE.Site("https://tulprhfc.wghcb-bnmgm-hyymaz.work:16655/topic/453352.html", "bottom", False, "平特网心")
        document = "\n".join([
            "190期:绝杀(1)行【水行】开:0000准",
            "189期:绝杀(1)行【金行】开:龙15准",
            "188期:绝杀(1)行【火行】开:兔16准",
            "187期:绝杀(1)行【木行】开:马01准",
            "190期:澳彩【平特一肖】免费发表",
        ])

        candidates = MODULE.parse_candidates_for_site(document, site)

        self.assertIn(site.url, MODULE.SITE_SPECIFIC_ONLY_URLS)
        self.assertEqual(
            [(candidate.period, candidate.wuxing) for candidate in MODULE.region_target_window_candidates(candidates, "bottom")],
            [("188期", "火行"), ("189期", "金行"), ("190期", "水行")],
        )
        self.assertIsNone(
            MODULE.region_three_window_failure_reason(
                [document],
                "bottom",
                190,
                parser_fn=lambda value: MODULE.parse_candidates_for_site(value, site),
            )
        )

    def test_tianqingrunsou_top_window_uses_visible_latest_rows(self):
        site = MODULE.Site("https://ykeejph.z9koz-18xjn-pvglgy.xyz:16677/topic/682107.html", "top", False, "天青润薮")
        document = "\n".join([
            "绝杀一行",
            "179期: 绝杀一行 【火行】 開:0000准",
            "178期: 绝杀一行 【金行】 開:鸡10准",
            "177期: 绝杀一行 【土行】 開:蛇14准",
            "2026年五行号码：金行：04 05 12 13 26 27 34 35 42 43",
        ])

        candidates = MODULE.parse_candidates_for_site(document, site)

        self.assertIn(site.url, MODULE.SITE_SPECIFIC_ONLY_URLS)
        self.assertEqual(
            [(candidate.period, candidate.wuxing) for candidate in MODULE.region_target_window_candidates(candidates, "top")],
            [("179期", "火行"), ("178期", "金行"), ("177期", "土行")],
        )
        self.assertIsNone(
            MODULE.region_three_window_failure_reason(
                [document],
                "top",
                179,
                parser_fn=lambda value: MODULE.parse_candidates_for_site(value, site),
            )
        )
    def test_yishenxianqi_bottom_window_uses_visible_latest_rows(self):
        site = MODULE.Site("https://myvvqq.30dok-2s9fd-bibfmg.work/", "bottom", False, "一身仙气")
        document = "\n".join([
            "一身仙气（绝杀一行）",
            "150期:绝杀(1)行【水行】开:狗09对",
            "169期:绝杀(1)行【火行】开:羊24对",
            "170期:绝杀(1)行【土行】开:龙03对",
            "171期:绝杀(1)行【金行】开:兔28对",
            "176期:绝杀(1)行【金行】开:鸡10对",
            "177期:绝杀(1)行【土行】开:蛇14对",
            "178期:绝杀(1)行【水行】开:？00对",
            "2026年五行号码：金行：04 05 12 13 26 27 34 35 42 43",
        ])

        candidates = MODULE.parse_candidates_for_site(document, site)

        self.assertIn(site.url, MODULE.SITE_SPECIFIC_ONLY_URLS)
        self.assertEqual(
            [(candidate.period, candidate.wuxing) for candidate in MODULE.region_target_window_candidates(candidates, "bottom")],
            [("176期", "金行"), ("177期", "土行"), ("178期", "水行")],
        )
        self.assertIsNone(
            MODULE.region_three_window_failure_reason(
                [document],
                "bottom",
                178,
                parser_fn=lambda value: MODULE.parse_candidates_for_site(value, site),
            )
        )
    def test_yikoutongsheng_site_specific_ignores_bottom_navigation(self):
        site = MODULE.Site("https://fhktrabu.zbfrm-uzct1-pmycbu.xyz:16677/topic/469065.html", "bottom", False, "异口同声")
        document = "\n".join([
            "178期:【绝杀一行】【金行】开:牛18准",
            "179期:【绝杀一行】【火行】开:龙15准",
            "180期:【绝杀一行】【木行】开:狗21准",
            "181期:【绝杀一行】【金行】开:0000准",
            "金 04.05.12.13.26.27.34.35.42.43",
            "上一篇: 181期澳彩【20码中特】免费发表",
            "下一篇: 181期澳彩【六肖中特】免费发表",
        ])

        candidates = MODULE.parse_candidates_for_site(document, site)

        self.assertIn(site.url, MODULE.SITE_SPECIFIC_ONLY_URLS)
        self.assertEqual(
            [(candidate.period, candidate.wuxing) for candidate in MODULE.region_target_window_candidates(candidates, "bottom")],
            [("179期", "火行"), ("180期", "木行"), ("181期", "金行")],
        )
        self.assertIsNone(
            MODULE.region_three_window_failure_reason(
                [document],
                "bottom",
                181,
                parser_fn=lambda value: MODULE.parse_candidates_for_site(value, site),
            )
        )

    def test_yikoutongsheng_accepts_corner_wuxing_brackets(self):
        site = MODULE.Site("https://fhktrabu.zbfrm-uzct1-pmycbu.xyz:16677/topic/469065.html", "bottom", False, "异口同声")
        document = "\n".join([
            "179期:【绝杀一行】〖火行〗开:龙15准",
            "180期:【绝杀一行】〖木行〗开:狗21准",
            "181期:【绝杀一行】〖金行〗开:鼠19准",
            "182期:【绝杀一行】〖水行〗开:0000准",
            "上一篇： 182期:澳彩【20码中特】免费发表",
            "下一篇： 182期:澳彩【六尾中特】免费发表",
        ])

        candidates = MODULE.parse_candidates_for_site(document, site)

        self.assertEqual(
            [(candidate.period, candidate.wuxing) for candidate in MODULE.region_target_window_candidates(candidates, "bottom")],
            [("180期", "木行"), ("181期", "金行"), ("182期", "水行")],
        )
        self.assertIsNone(
            MODULE.region_three_window_failure_reason(
                [document],
                "bottom",
                182,
                parser_fn=lambda value: MODULE.parse_candidates_for_site(value, site),
            )
        )

    def test_region_three_window_cannot_be_bypassed_by_single_child_document(self):
        root = "\n".join([
            "191期:【绝杀一行】【木行】开:00准",
            "192期:【绝杀一行】【水行】开:00准",
            "193期:【绝杀一行】【火行】开:00准",
            "194期:【绝杀一行】【土行】开:00准",
        ])
        child = "190期:【绝杀一行】【金行】开:00准"

        reason = MODULE.region_three_window_failure_reason([root, child], "bottom", 190)
        _, candidates = MODULE.best_document_with_period_candidates([root, child], 190, "bottom")

        self.assertIsNotNone(reason)
        self.assertIn("底部只允许后3条", reason)
        self.assertEqual(candidates, [])

    def test_yibenwanli_site_specific_parses_split_sijin_rows(self):
        site = MODULE.Site("https://mflmcobome.26222hi.app:2569/htm/bbs/top040.html", "bottom", False, "一本万利")
        document = "\n".join([
            "176期:", "💧死禁一行💧", "开:", "鸡10", "中", "【水】",
            "177期:", "💧死禁一行💧", "开:", "蛇14", "错", "【水】",
            "178期:", "💧死禁一行💧", "开:", "牛18", "中", "【金】",
            "179期:", "💧死禁一行💧", "开:", "00", "中", "【金】",
            "金行：[03.04.11.12.25]",
        ])

        candidates = MODULE.parse_candidates_for_site(document, site)

        self.assertIn(site.url, MODULE.SITE_SPECIFIC_ONLY_URLS)
        self.assertEqual(
            [(candidate.period, candidate.wuxing) for candidate in MODULE.region_target_window_candidates(candidates, "bottom")],
            [("177期", "水行"), ("178期", "金行"), ("179期", "金行")],
        )
    def test_zhuangyuanhong_top_window_uses_visible_latest_rows(self):
        site = MODULE.Site("https://3.www112291a.com:2053/gengxin/16.html", "top", False, "狀元紅")
        document = "\n".join([
            "176期:绝杀①行【木行】开:0000准",
            "175期:绝杀①行【土行】开:蛇26准",
            "174期:绝杀①行【木行】开:虎41准",
            "173期:绝杀①行【火行】开:蛇26准",
            "172期:绝杀①行【水行】开:猪44错",
            "171期:绝杀①行【土行】开:兔28错",
            "170期:绝杀①行【水行】开:龙03准",
            "169期:绝杀①行【金行】开:羊24准",
            "2026年五行号码：",
            "金行：04 05 12 13 26 27 34 35 42 43",
        ])

        candidates = MODULE.parse_candidates_for_site(document, site)

        self.assertEqual(
            [(candidate.period, candidate.wuxing) for candidate in MODULE.region_target_window_candidates(candidates, "top")],
            [("176期", "木行"), ("175期", "土行"), ("174期", "木行")],
        )
        self.assertIsNone(
            MODULE.region_three_window_failure_reason(
                [document],
                "top",
                176,
                parser_fn=lambda value: MODULE.parse_candidates_for_site(value, site),
            )
        )

    def test_zhugeshentong_site_specific_parses_real_four_wuxing_rows(self):
        site = MODULE.Site("https://hl.www25195a.com/read.php?tid=607", "bottom", False, "诸葛神通")
        document = "\n".join([
            "182期: 『诸葛神通』 🚲 四行中特 🚲【 火 .金.木.水】开: 火41",
            "183期: 『诸葛神通』 🚲 四行中特 🚲【火. 木 .水.土】开: 木24",
            "184期: 『诸葛神通』 🚲 四行中特 🚲【火.金.水.土】开:00准",
            "184期:澳彩【六肖中特】免费发表",
            "184期:澳彩【三行中特】免费发表",
        ])

        candidates = MODULE.parse_candidates_for_site(document, site)

        self.assertIn(site.url, MODULE.SITE_SPECIFIC_ONLY_URLS)
        self.assertEqual(
            [(candidate.period, candidate.wuxing) for candidate in MODULE.region_target_window_candidates(candidates, "bottom")],
            [("182期", "土行"), ("183期", "金行"), ("184期", "木行")],
        )
        self.assertIsNone(
            MODULE.region_three_window_failure_reason(
                [document],
                "bottom",
                184,
                parser_fn=lambda value: MODULE.parse_candidates_for_site(value, site),
            )
        )

    def test_shenji_uses_http_specific_absolute_kill_one_line_block(self):
        site = MODULE.Site("https://wxaxdfc.523mo-z7mla-owjdon.xyz:16677/", "top", False, "神机")
        document = (
            "<div>其他栏目 191期稳杀半单双【大单】开0000√</div>"
            "<div>（绝杀一行）</div>"
            "<div>191期稳杀(1)行【木木木】开0000√</div>"
            "<div>190期稳杀(1)行【水水水】开兔16√</div>"
        )

        candidates = MODULE.parse_candidates_for_site(document, site)

        self.assertFalse(MODULE.site_uses_browser_first(site))
        self.assertIn(site.url, MODULE.SITE_SPECIFIC_ONLY_URLS)
        self.assertEqual(
            [(candidate.period, candidate.wuxing) for candidate in candidates],
            [("191期", "木行")],
        )

    def test_baiwanziliao_uses_http_specific_split_script_row(self):
        site = next(item for item in MODULE.load_sites("sites.json") if item.name == "百万资料")
        document = "<div>191期稳杀(1)行 【木】 开 0000准</div>"

        candidates = MODULE.parse_candidates_for_site(document, site)

        self.assertFalse(site.click_first)
        self.assertFalse(MODULE.site_uses_browser_first(site))
        self.assertEqual(
            [(candidate.period, candidate.wuxing) for candidate in candidates],
            [("191期", "木行")],
        )

    def test_cangbaoge_uses_http_specific_treasure_kill_block(self):
        site = MODULE.Site("https://huqtzej.vvlq2-j4i8n-lisghq.xyz:16677/", "top", False, "藏宝阁")
        document = (
            "<h3>藏宝图稳杀一行</h3>"
            "<div>192期稳杀一行【金行】开0000准</div>"
            "<div>191期稳杀一行【木行】开虎29准</div>"
            "<div>190期稳杀一行【土行】开兔16准</div>"
            "<h3>其他栏目</h3><div>191期稳杀一行【水行】开牛29错</div>"
        )

        candidates = MODULE.parse_candidates_for_site(document, site)

        self.assertFalse(MODULE.site_uses_browser_first(site))
        self.assertIn(site.url, MODULE.SITE_SPECIFIC_ONLY_URLS)
        self.assertEqual(
            [(candidate.period, candidate.wuxing) for candidate in candidates],
            [("192期", "金行"), ("191期", "木行"), ("190期", "土行")],
        )

    def test_three_screenshot_sites_use_strict_dedicated_rows(self):
        samples = [
            (
                "损人利己",
                "https://ekhivjcg.llnnt-l11x5-bywtoe.xyz:16677/topic/469882.html",
                "损人利己 发表 于 07月12日 10:39:32\n"
                "193期：【绝杀一行】【杀金行】开0000对\n"
                "192期：【绝杀一行】【杀火行】开马25对",
                "金行",
            ),
            (
                "飞瀑流泉",
                "https://buzfwpox.pwp8o-vfhi5-xmrytn.xyz:16677/topic/464877.html",
                "193期 飞瀑流泉【绝杀一行】已上料\n"
                "193期：【稳杀一行】【金】开？00准\n"
                "192期：【稳杀一行】【水】开马25准",
                "金行",
            ),
            (
                "暴风骤雨",
                "https://pxgaayml.2wyk5-dwn70-cljflt.xyz:16677/topic/458324.html",
                "高等帖 193期【绝杀一行】已公开\n"
                "193期：【绝杀一行】【火】开0000准\n"
                "192期：【绝杀一行】【金】开马25准",
                "火行",
            ),
        ]

        for name, url, document, expected_wuxing in samples:
            with self.subTest(site=name):
                site = MODULE.Site(url, "top", name == "飞瀑流泉", name)
                candidates = MODULE.parse_candidates_for_site(document, site)
                self.assertEqual(
                    [(candidate.period, candidate.wuxing) for candidate in candidates],
                    [("193期", expected_wuxing), ("192期", "火行" if name == "损人利己" else "水行" if name == "飞瀑流泉" else "金行")],
                )
                self.assertIn(url, MODULE.SITE_SPECIFIC_ONLY_URLS)

        fly_site = MODULE.Site(
            "https://buzfwpox.pwp8o-vfhi5-xmrytn.xyz:16677/topic/464877.html",
            "top",
            True,
            "飞瀑流泉",
        )
        self.assertFalse(MODULE.site_browser_click_first(fly_site))

    def test_screenshot_parser_joins_split_rows_and_rejects_other_markers(self):
        site = MODULE.Site(
            "https://pxgaayml.2wyk5-dwn70-cljflt.xyz:16677/topic/458324.html",
            "top",
            False,
            "暴风骤雨",
        )
        document = "暴风骤雨\n193期：\n【绝杀一行】\n【火】开：0000准\n192期：\n【其他一行】\n【金】开：马25准"

        candidates = MODULE.parse_candidates_for_site(document, site)

        self.assertEqual([(candidate.period, candidate.wuxing) for candidate in candidates], [("193期", "火行")])

    def test_sunrenliji_binds_body_to_header_period_and_ignores_stale_block(self):
        site = MODULE.Site(
            "https://ekhivjcg.llnnt-l11x5-bywtoe.xyz:16677/topic/469882.html",
            "top",
            False,
            "损人利己",
        )
        header = "特码料 193期：【绝杀一行】损人利己"
        current = "193期【绝杀一行】【杀金行】开0000对\n192期【绝杀一行】【杀火行】开马25对"
        stale = "194期【绝杀一行】【杀火行】开牛29对\n193期【绝杀一行】【杀木行】开马24错"

        documents = [header, current, stale]
        selected = MODULE.site_authoritative_documents(
            documents,
            site,
            parser_fn=lambda value: MODULE.parse_candidates_for_site(value, site),
        )

        self.assertEqual(selected, [current])

    def test_sunrenliji_scrape_ignores_conflict_from_unrelated_document(self):
        site = MODULE.Site(
            "https://ekhivjcg.llnnt-l11x5-bywtoe.xyz:16677/topic/469882.html",
            "top",
            False,
            "损人利己",
        )
        header = "特码料 195期：【绝杀一行】损人利己"
        current = "195期【绝杀一行】【杀木行】开0000对\n194期【绝杀一行】【杀水行】开蛇25对"
        unrelated = "196期【绝杀一行】【杀金行】开0000对\n195期【绝杀一行】【杀水行】开蛇25对"

        with mock.patch.object(MODULE, "collect_documents", return_value=[header, current, unrelated]):
            lines, error, _ = MODULE.scrape_site_detailed(site, 1, 20, False, 195)

        self.assertEqual(lines, ["木行 195期 损人利己"])
        self.assertIsNone(error)

    def test_sunrenliji_scrape_rejects_conflict_inside_authoritative_document(self):
        site = MODULE.Site(
            "https://ekhivjcg.llnnt-l11x5-bywtoe.xyz:16677/topic/469882.html",
            "top",
            False,
            "损人利己",
        )
        header = "特码料 195期：【绝杀一行】损人利己"
        current = "195期【绝杀一行】【杀木行】开0000对\n195期【绝杀一行】【杀水行】开蛇25对"

        with mock.patch.object(MODULE, "collect_documents", return_value=[header, current]):
            lines, error, _ = MODULE.scrape_site_detailed(site, 1, 20, False, 195)

        self.assertEqual(lines, [])
        self.assertIn("五行冲突", error or "")

    def test_sunrenliji_ignores_matching_unrelated_document_before_header(self):
        site = MODULE.Site(
            "https://ekhivjcg.llnnt-l11x5-bywtoe.xyz:16677/topic/469882.html",
            "top",
            False,
            "损人利己",
        )
        unrelated = "195期【绝杀一行】【杀水行】开蛇25对"
        header = "特码料 195期：【绝杀一行】损人利己"
        current = "195期【绝杀一行】【杀木行】开0000对\n194期【绝杀一行】【杀水行】开蛇25对"

        selected = MODULE.site_authoritative_documents(
            [unrelated, header, "页面样式", current],
            site,
            parser_fn=lambda value: MODULE.parse_candidates_for_site(value, site),
        )

        self.assertEqual(selected, [current])

    def test_sunrenliji_missing_bound_http_body_uses_browser_document(self):
        site = MODULE.Site(
            "https://ekhivjcg.llnnt-l11x5-bywtoe.xyz:16677/topic/469882.html",
            "top",
            False,
            "损人利己",
        )
        header = "特码料 195期：【绝杀一行】损人利己"
        unrelated = "195期【绝杀一行】【杀水行】开蛇25对"
        browser_document = (
            "特码料 195期：【绝杀一行】损人利己\n"
            "195期【绝杀一行】【杀木行】开0000对\n"
            "194期【绝杀一行】【杀水行】开蛇25对"
        )

        with (
            mock.patch.object(
                MODULE,
                "collect_documents",
                return_value=[header, "样式一", "样式二", "样式三", unrelated],
            ),
            mock.patch.object(MODULE, "fetch_browser_text", return_value=browser_document) as browser_fetch,
        ):
            lines, error, _ = MODULE.scrape_site_detailed(site, 1, 20, False, 195)

        self.assertEqual(lines, ["木行 195期 损人利己"])
        self.assertIsNone(error)
        browser_fetch.assert_called_once()

    def test_yishenxianqi_uses_longest_http_authoritative_block(self):
        site = MODULE.Site("https://myvvqq.30dok-2s9fd-bibfmg.work/", "bottom", False, "一身仙气")
        partial = "一身仙气（绝杀一行） 170期:绝杀(1)行【土行】开龙03对 171期:绝杀(1)行【金行】开兔28对"
        complete = (
            "一身仙气（绝杀一行） "
            "188期:绝杀(1)行【土行】开兔16对 "
            "190期:绝杀(1)行【金行】开兔16对 "
            "191期:绝杀(1)行【水行】开0000对"
        )
        def parser(document):
            return MODULE.parse_candidates_for_site(document, site)

        authoritative = MODULE.site_authoritative_documents([partial, complete], site, parser_fn=parser)
        candidates = MODULE.authoritative_window_candidates(authoritative, parser_fn=parser)

        self.assertFalse(MODULE.site_uses_browser_first(site))
        self.assertEqual(authoritative, [complete])
        self.assertEqual(
            [(candidate.period, candidate.wuxing) for candidate in candidates],
            [("188期", "土行"), ("190期", "金行"), ("191期", "水行")],
        )

    def test_three_bottom_sites_parse_visible_browser_text_only(self):
        samples = [
            (
                MODULE.Site("https://jldzuea.0xkqd-q7ng5-boerfb.xyz:16677/topic/677608.html", "bottom", False, "广西仔"),
                "191期:精品推荐【绝杀一行】 877750a.com 发表于 07月10日 "
                "192期:绝杀(一)行【水行】开鸡45准 365期:绝杀(一)行【金行】开牛29准 "
                "189期:绝杀(一)行【金行】开龙15准 190期:绝杀(一)行【火行】开兔16准 "
                "191期:绝杀(一)行【木行】开0000准",
                "木行",
            ),
            (
                MODULE.Site("https://fzzmqscl.bdppk-lyf4y-teyajr.xyz:16677/topic/439186.html", "bottom", True, "信口雌黄"),
                "高手贴 191期【绝杀一行】已更新 作者:信口雌黄 "
                "192期【绝杀一行】《火行》开鸡45准 365期【绝杀一行】《土行》开牛29准 "
                "189期【绝杀一行】《水行》开龙15准 190期【绝杀一行】《土行》开兔16准 "
                "191期【绝杀一行】《金行》开0000准",
                "金行",
            ),
            (
                MODULE.Site("https://fhktrabu.zbfrm-uzct1-pmycbu.xyz:16677/topic/469065.html", "bottom", False, "异口同声"),
                "191期【绝杀一行】已更新 异口同声 发表于 07月10日 "
                "192期:【绝杀一行】〖火行〗开鸡45准 365期:【绝杀一行】〖木行〗开牛29准 "
                "189期:【绝杀一行】〖金行〗开龙15准 190期:【绝杀一行】〖水行〗开兔16准 "
                "191期:【绝杀一行】〖土行〗开0000准 五行号码表 上一篇:其他资料",
                "土行",
            ),
        ]
        hidden_source = "999期:绝杀一行【水行】"

        for site, visible_text, expected in samples:
            with self.subTest(site=site.name):
                document = MODULE.compose_browser_document(site.url, hidden_source, visible_text, [])
                candidates = MODULE.parse_candidates_for_site(document, site)
                window = MODULE.region_target_window_candidates(candidates, site.pick)

                self.assertTrue(MODULE.site_uses_browser_first(site))
                self.assertNotIn("999期", document)
                self.assertEqual(window[-1].period, "191期")
                self.assertEqual(window[-1].wuxing, expected)

    def test_xing_zhongte_rejects_non_four_unique_wuxing(self):
        invalid_documents = [
            "151期:《测试》 四行中特 【金】 开:00准",
            "151期:《测试》 四行中特 【金.木.水】 开:00准",
            "151期:《测试》 四行中特 【金.木.水.水】 开:00准",
        ]
        for document in invalid_documents:
            with self.subTest(document=document):
                self.assertEqual(MODULE.parse_candidates(document), [])

    def test_tou_zhongte_is_not_wuxing_candidate(self):
        document = "151期:《奋起直追》 ④头中特 【1.2.3.4】 开:40准"
        self.assertEqual(MODULE.parse_candidates(document), [])

    def test_period_wuxing_without_target_keyword_is_rejected(self):
        document = "168期:【普通资料】【火行】开:00准"
        self.assertEqual(MODULE.parse_candidates(document), [])

    def test_target_keyword_required_before_wuxing_candidate(self):
        document = "168期:【绝杀一行】【火行】开:00准"
        candidates = MODULE.parse_candidates(document)
        self.assertEqual([(candidate.period, candidate.wuxing) for candidate in candidates], [("168期", "火行")])

    def test_period_selection_accepts_target_inside_region_three_window(self):
        documents = [
            "\n".join([
                "152期:【绝杀一行】【水行】开:0000准",
                "151期:【绝杀一行】【火行】开:鼠31准",
            ]),
        ]

        _, top_candidates = MODULE.best_document_with_period_candidates(documents, 151, "top")
        _, bottom_candidates = MODULE.best_document_with_period_candidates(documents, 151, "bottom")

        self.assertEqual(len(top_candidates), 1)
        self.assertEqual(top_candidates[0].period, "151期")
        self.assertEqual(len(bottom_candidates), 1)
        self.assertEqual(bottom_candidates[0].period, "151期")

    def test_period_selection_rejects_target_outside_region_three_window(self):
        documents = [
            "\n".join([
                "152期:【绝杀一行】【水行】开:0000准",
                "151期:【绝杀一行】【火行】开:鼠31准",
                "150期:【绝杀一行】【木行】开:虎41准",
                "149期:【绝杀一行】【土行】开:兔16准",
            ]),
        ]

        _, top_candidates = MODULE.best_document_with_period_candidates(documents, 149, "top")
        _, bottom_candidates = MODULE.best_document_with_period_candidates(documents, 152, "bottom")

        self.assertEqual(top_candidates, [])
        self.assertEqual(bottom_candidates, [])

    def test_top_selection_uses_position_not_largest_period_across_documents(self):
        documents = [
            "152期:【绝杀一行】【土行】开:0000准",
            "364期:【绝杀一行】【水行】开:马12对",
        ]

        _, candidates = MODULE.best_document_with_period_candidates(documents, 152, "top")

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].period, "152期")
        self.assertEqual(candidates[0].wuxing, "土行")

    def test_large_candidate_set_uses_only_position_window(self):
        candidates = [
            MODULE.Candidate(period=f"{100 + index}期", wuxing="金行", order=index, raw=str(index))
            for index in range(31)
        ]

        self.assertEqual(
            [candidate.period for candidate in MODULE.position_window_candidates(candidates, "top")],
            ["100期", "101期", "102期", "103期", "104期"],
        )
        self.assertEqual(
            [candidate.period for candidate in MODULE.position_window_candidates(candidates, "bottom")],
            ["126期", "127期", "128期", "129期", "130期"],
        )

    def test_combined_document_candidates_collapses_same_period_same_wuxing(self):
        documents = [
            "155期:【绝杀一行】【水行】开:0000准",
            "155期:【绝杀一行】【水行】开:0000准",
            "154期:【绝杀一行】【金行】开:虎41准",
        ]

        candidates = MODULE.combined_document_candidates(documents)

        self.assertEqual(
            [(candidate.period, candidate.wuxing) for candidate in candidates],
            [("155期", "水行"), ("154期", "金行")],
        )

    def test_conflicting_target_candidates_are_detected(self):
        candidates = [
            MODULE.Candidate(period="158期", wuxing="金行", order=1, raw="a"),
            MODULE.Candidate(period="158期", wuxing="木行", order=2, raw="b"),
            MODULE.Candidate(period="157期", wuxing="水行", order=3, raw="c"),
        ]
        self.assertTrue(MODULE.has_conflicting_target_candidates(candidates, 158))
        self.assertFalse(MODULE.has_conflicting_target_candidates([candidates[0], candidates[2]], 158))

    def test_scrape_rejects_target_conflict_before_candidate_compression(self):
        site = MODULE.Site("https://example.com/page", "top", False, "冲突站")
        documents = [
            "190期:【绝杀一行】【金行】开:00准",
            "190期:【绝杀一行】【木行】开:00准",
        ]

        with mock.patch.object(MODULE, "collect_documents", return_value=documents):
            lines, error, _ = MODULE.scrape_site_detailed(site, 1, 20, False, 190)

        self.assertEqual(lines, [])
        self.assertIn("五行冲突", error)

    def test_click_first_requires_one_exact_period_and_target_match(self):
        class Element:
            def __init__(self, text):
                self.text = text

        exact = Element("190期 绝杀一行")
        elements = [Element("189期 绝杀一行"), Element("190期 普通栏目"), exact]
        self.assertIs(MODULE.select_unique_click_target(elements, 190), exact)

        with self.assertRaises(MODULE.DocumentFetchError):
            MODULE.select_unique_click_target([Element("189期 绝杀一行")], 190)
        with self.assertRaises(MODULE.DocumentFetchError):
            MODULE.select_unique_click_target([exact, Element("190期 必杀一行")], 190)

    def test_generic_parser_does_not_attach_adjacent_ad_wuxing_to_period(self):
        document = "\n".join([
            "190期 普通资料",
            "广告栏目",
            "绝杀一行【金行】开:00准",
        ])

        self.assertEqual(MODULE.parse_candidates(document), [])

    def test_generic_parser_does_not_cross_recommendation_navigation_boundary(self):
        document = "\n".join([
            "190期 普通资料",
            "推荐栏目",
            "绝杀一行【金行】开:00准",
        ])

        self.assertEqual(MODULE.parse_candidates(document), [])

    def test_multiple_target_candidates_require_site_specific_parser(self):
        site = MODULE.Site("https://example.com/generic", "top", False, "普通站")
        candidates = [
            MODULE.Candidate(period="158期", wuxing="金行", order=1, raw="目标栏目 158期 金行"),
            MODULE.Candidate(period="158期", wuxing="金行", order=2, raw="其他栏目 158期 金行"),
        ]

        reason = MODULE.ambiguous_target_candidates_reason(site, candidates, 158)

        self.assertIsNotNone(reason)
        self.assertIn("158期同站出现多个高可信候选", reason)
        self.assertIn("未配置专属解析", reason)

    def test_site_specific_parser_allows_multiple_same_target_candidates(self):
        site = MODULE.Site("https://fhktrabu.zbfrm-uzct1-pmycbu.xyz:16677/topic/469065.html", "bottom", False, "异口同声")
        candidates = [
            MODULE.Candidate(period="184期", wuxing="水行", order=1, raw="正文 184期 水行"),
            MODULE.Candidate(period="184期", wuxing="水行", order=2, raw="正文重复 184期 水行"),
        ]

        self.assertIsNone(MODULE.ambiguous_target_candidates_reason(site, candidates, 184))

    def test_dianzejunya_site_rule_parses_its_single_wuxing_record(self):
        site = MODULE.Site(
            "https://wigrzse.3acpt-tc9xa-kzxasm.xyz:29444/article/manager/6a20da1dca6da63e15d01fc8?url=pg",
            "bottom",
            False,
            "典则俊雅",
            "https://wigrzse.3acpt-tc9xa-kzxasm.xyz:29444/api/proxy/manager-articles/6a20da1dca6da63e15d01fc8",
        )
        document = "\n".join([
            "207期:『典则俊雅』绝杀一行【木】开:31准",
            "208期:『典则俊雅』绝杀一行【火】开:19错",
        ])

        candidates = MODULE.parse_site_specific_candidates(document, site)

        self.assertEqual(
            [(candidate.period, candidate.wuxing) for candidate in candidates],
            [("207期", "木行"), ("208期", "火行")],
        )

    def test_failed_validation_sites_have_site_specific_target_rows(self):
        samples = [
            (
                MODULE.Site("https://g63.52619c.com:8443/tie1/1614.html", "bottom", False, "产生共鸣"),
                "189期稳杀一行 【金】 开龙15准",
                [("189期", "金行")],
            ),
            (
                MODULE.Site("https://useaul.z3rj5-9jlwg-dynocd.xyz:16677/topic/384879.html", "top", False, "满汉全席"),
                "189期: 绝杀一行 【土行】 開:龙15准",
                [("189期", "土行")],
            ),
            (
                MODULE.Site("https://huqtzej.vvlq2-j4i8n-lisghq.xyz:16677/", "top", False, "藏宝阁"),
                "189期稳杀一行 【水行】 开龙15错",
                [("189期", "水行")],
            ),
            (
                MODULE.Site("https://993345.com/gsb1.aspx?id=1482", "bottom", False, "天下无双"),
                "天下无双【必杀一行】资料已公开 189期: 必杀一行 【金行】开:龙15准",
                [("189期", "金行")],
            ),
            (
                MODULE.Site("https://2.www39169b.com:888/#62111", "top", True, "八步毛哥"),
                "八步毛哥【必杀一行】\n188期： 必杀一行 【 土行 】开 兔16 中",
                [("188期", "土行")],
            ),
        ]

        for site, document, expected in samples:
            with self.subTest(site=site.name):
                candidates = MODULE.parse_candidates_for_site(document, site)
                self.assertIn(site.url, MODULE.SITE_SPECIFIC_ONLY_URLS)
                self.assertEqual(
                    [(candidate.period, candidate.wuxing) for candidate in candidates],
                    expected,
                )

    def test_babumaoge_joins_split_row_inside_exact_section(self):
        site = MODULE.Site("https://2.www39169b.com:888/#62111", "top", True, "八步毛哥")
        document = "\n".join(
            [
                "其他资料 193期绝杀一行【水行】",
                "八步毛哥【必杀一行】",
                "193期：",
                "必杀一行",
                "【金行】开？00中",
            ]
        )

        candidates = MODULE.parse_candidates_for_site(document, site)

        self.assertEqual(
            [(candidate.period, candidate.wuxing) for candidate in candidates],
            [("193期", "金行")],
        )

    def test_special_named_parsers_reject_target_rows_without_exact_title(self):
        samples = [
            (
                MODULE.Site("https://2.www39169b.com:888/#62111", "top", True, "八步毛哥"),
                "其他栏目\n193期：必杀一行【水行】开？00中",
            ),
            (
                MODULE.Site(
                    "https://pxgaayml.2wyk5-dwn70-cljflt.xyz:16677/topic/458324.html",
                    "top",
                    False,
                    "暴风骤雨",
                ),
                "其他栏目\n193期：【绝杀一行】【水】开：0000准",
            ),
            (
                MODULE.Site("https://myvvqq.30dok-2s9fd-bibfmg.work/", "bottom", False, "一身仙气"),
                "其他栏目\n193期:绝杀(1)行【水行】开:0000对",
            ),
        ]

        for site, document in samples:
            with self.subTest(site=site.name):
                self.assertEqual(MODULE.parse_candidates_for_site(document, site), [])

    def test_manhquanxi_parses_split_html_text_nodes(self):
        site = MODULE.Site(
            "https://useaul.z3rj5-9jlwg-dynocd.xyz:16677/topic/384879.html",
            "top",
            False,
            "满汉全席",
        )
        document = "\n".join(
            [
                "193期【绝杀一行】",
                "满汉全席 发表于",
                "193期:",
                "绝杀一行",
                "【金行】",
                "開:0000准",
                "192期:",
                "绝杀一行",
                "【木行】",
                "開:马25错",
                "下一篇:193期【绝杀三尾】",
            ]
        )

        self.assertEqual(
            [(candidate.period, candidate.wuxing) for candidate in MODULE.parse_candidates_for_site(document, site)],
            [("193期", "金行"), ("192期", "木行")],
        )

    def test_xinfengluntan_uses_http_before_browser_fallback(self):
        site = MODULE.Site(
            "https://zqliou.kify1-fbyi6-lmeykn.xyz:16677/",
            "top",
            False,
            "信封论坛",
        )

        self.assertFalse(MODULE.site_uses_browser_first(site))

    def test_xinfengluntan_rejects_body_document_without_exact_title(self):
        site = MODULE.Site(
            "https://zqliou.kify1-fbyi6-lmeykn.xyz:16677/",
            "top",
            False,
            "信封论坛",
        )
        document = "193期:【绝杀一行】【金行】开:0000准\n192期:【绝杀一行】【木行】开:马25错"

        candidates = MODULE.parse_candidates_for_site(document, site)

        self.assertEqual(candidates, [])

    def test_xinfengluntan_binds_split_title_to_its_following_section(self):
        site = MODULE.Site(
            "https://zqliou.kify1-fbyi6-lmeykn.xyz:16677/",
            "top",
            False,
            "信封论坛",
        )
        documents = [
            "澳门信封论坛 『绝杀一波』\n201期绝杀一波【红波】",
            "澳门信封论坛\n『绝杀一行』",
            "201期:\n【绝杀一行】\n【土行】\n开:0000准",
            "澳门信封论坛\n『绝杀一头』\n201期绝杀一头【0头】",
        ]

        selected = MODULE.site_authoritative_documents(documents, site)
        candidates = MODULE.combined_document_candidates(
            selected,
            parser_fn=lambda document: MODULE.parse_candidates_for_site(document, site),
        )

        self.assertEqual(len(selected), 1)
        self.assertEqual(
            [(item.period, item.wuxing) for item in candidates if item.period == "201期"],
            [("201期", "土行")],
        )

    def test_xinfengluntan_ignores_generic_name_before_exact_target_section(self):
        site = MODULE.Site(
            "https://zqliou.kify1-fbyi6-lmeykn.xyz:16677/",
            "top",
            False,
            "信封论坛",
        )
        document = "\n".join(
            ["澳门信封论坛升级公告"]
            + [f"普通栏目第{index}行" for index in range(30)]
            + [
                "澳门信封论坛 『绝杀一行』",
                "193期:【绝杀一行】【金行】开:0000准",
                "192期:【绝杀一行】【木行】开:马25错",
            ]
        )

        candidates = MODULE.parse_candidates_for_site(document, site)

        self.assertEqual(
            [(candidate.period, candidate.wuxing) for candidate in candidates],
            [("193期", "金行"), ("192期", "木行")],
        )

    def test_yishenxianqi_parses_current_193_row(self):
        site = MODULE.Site("https://myvvqq.30dok-2s9fd-bibfmg.work/", "bottom", False, "一身仙气")
        document = "\n".join(
            [
                "一身仙气（绝杀一行）",
                "193期:绝杀(1)行 【木行】开:0000对",
                "192期:绝杀(1)行 【火行】开:马25对",
            ]
        )

        candidates = MODULE.parse_candidates_for_site(document, site)

        self.assertEqual(
            [(candidate.period, candidate.wuxing) for candidate in candidates],
            [("193期", "木行"), ("192期", "火行")],
        )

    def test_screenshot_defined_site_parsers_isolate_their_target_sections(self):
        samples = [
            (
                MODULE.Site("https://993345.com/gsb1.aspx?id=1482", "bottom", False, "天下无双"),
                "天下无双【必杀一行】资料已公开\n192期:必杀一行【木行】开:00准\n191期:必杀一行【土行】开:虎29错\n2026年五行:\n192期:必杀一行【火行】",
                ("192期", "木行"),
            ),
            (
                MODULE.Site("https://yylxuru.en4hs-c1zt6-qzcdin.xyz:16677/", "top", False, "澳门精吊桶"),
                "澳门金吊桶『绝杀一行』\n192期: ▼绝杀一行▼ 【木】开00对\n191期: ▼绝杀一行▼ 【土】开虎29错\n点击投注8808彩票\n192期:绝杀一行【火】",
                ("192期", "木行"),
            ),
            (
                MODULE.Site("https://ekhivjcg.llnnt-l11x5-bywtoe.xyz:16677/topic/469882.html", "top", False, "损人利己"),
                "特码解析192期【绝杀一行】损人利己\n192期【绝杀一行】【杀火行】开0000对\n191期【绝杀一行】【杀水行】开虎29对\n上一篇 192期【绝杀一行】【杀金行】",
                ("192期", "火行"),
            ),
            (
                MODULE.Site("https://swnrapsd.74wyl-mm601-cbpzhn.xyz:16677/", "top", False, "百万资料"),
                "杀一行\n192期稳杀(1)行【土】开0000准\n191期稳杀(1)行【木】开虎29准",
                ("192期", "土行"),
            ),
            (
                MODULE.Site("https://useaul.z3rj5-9jlwg-dynocd.xyz:16677/topic/384879.html", "top", False, "满汉全席"),
                "192期【绝杀一行】\n192期:绝杀一行【木行】开:0000准\n191期:绝杀一行【水行】开:虎29准\n下一篇:192期【绝杀三尾】【火行】",
                ("192期", "木行"),
            ),
            (
                MODULE.Site("https://zqliou.kify1-fbyi6-lmeykn.xyz:16677/", "top", False, "信封论坛"),
                "澳门信封论坛『绝杀一行』\n192期:【绝杀一行】【木行】开:0000准\n191期:【绝杀一行】【水行】开:虎29准\n点击投注8808彩票\n192期:【绝杀一行】【火行】",
                ("192期", "木行"),
            ),
            (
                MODULE.Site("https://zxliojf.83gjk-dnne7-kuyach.xyz:16677/", "top", False, "春满乡村"),
                "春满乡村（绝杀1.行）\n192期绝杀1.行【水水水】开:00√\n191期绝杀1.行【土土土】开虎29√\n山水诗意（四行中特）\n192期四行中特◎木水土火◎开:00准",
                ("192期", "水行"),
            ),
            (
                MODULE.Site("https://zxliojf.83gjk-dnne7-kuyach.xyz:16677/", "bottom", False, "山水诗意"),
                "春满乡村（绝杀1.行）\n192期绝杀1.行【水水水】开:00√\n山水诗意（四行中特）\n191期四行中特◎火水木土◎开虎29准\n192期四行中特◎木水土火◎开:00准\n别的资料（绝杀一行）\n192期【绝杀一行】【水行】",
                ("192期", "金行"),
            ),
        ]

        for site, document, expected in samples:
            with self.subTest(site=site.name):
                candidates = MODULE.parse_candidates_for_site(document, site)
                self.assertIn(expected, [(candidate.period, candidate.wuxing) for candidate in candidates])
                self.assertFalse(MODULE.has_conflicting_target_candidates(candidates, 192))

    def test_chunmanxiangcun_rejects_mixed_three_wuxing_characters(self):
        site = MODULE.Site("https://zxliojf.83gjk-dnne7-kuyach.xyz:16677/", "top", False, "春满乡村")
        document = "春满乡村（绝杀1.行）\n192期绝杀1.行【水火水】开:00√"
        self.assertEqual(MODULE.parse_candidates_for_site(document, site), [])

    def test_missing_failure_reason_is_explicit(self):
        self.assertEqual(
            MODULE.clarify_error_message(None, [], 163),
            "未抓到页面内容，无法检测 163期",
        )

    def test_failure_file_keeps_one_blank_line_between_sites(self):
        self.assertEqual(
            MODULE.format_failure_file_text(["站点A失败", "站点B失败"]),
            "站点A失败\n\n站点B失败\n",
        )
        self.assertNotEqual(MODULE.classify_failure_reason("未知异常"), "其他失败")

    def test_excluded_duplicate_sites_are_listed_but_not_ranked(self):
        ranked_lines = ["金行 普通站"]
        excluded_lines = ["水行 澳门第二四不像", "土行 天青润薮"]

        output = MODULE.build_success_output_lines(ranked_lines, excluded_lines)

        self.assertIn("重复目录-不参与排行", output)
        self.assertIn("水行 澳门第二四不像", output)
        self.assertIn("土行 天青润薮", output)
        ranking_text = "\n".join(output[output.index("排行表") :])
        self.assertIn("金行 1次", ranking_text)
        self.assertNotIn("水行 1次", ranking_text)
        self.assertNotIn("土行 1次", ranking_text)

    def test_success_output_lines_include_slow_site_stats_sorted_descending(self):
        site_a = MODULE.Site("https://example.com/a", "top", False, "快站")
        site_b = MODULE.Site("https://example.com/b", "bottom", False, "慢站")
        outcomes = {
            0: (site_a, ["金行 190期 快站"], None, [], 1.2),
            1: (site_b, ["水行 190期 慢站"], None, [], 8.5),
        }

        output = MODULE.build_success_output_lines(["金行 快站", "水行 慢站"], [], outcomes)

        slow_index = output.index("慢站耗时统计 Top 2：")
        self.assertIn("慢站 | 8.50s | 成功", output[slow_index + 1])
        self.assertIn("快站 | 1.20s | 成功", output[slow_index + 2])

    def test_validate_image_ocr_lines_requires_python_recheck_and_confidence(self):
        accepted = MODULE.validate_image_ocr_lines([
            {
                "period": 163,
                "wuxing": "火行",
                "wuxingScore": 42,
                "wuxingGap": 12,
                "independentPeriod": 163,
                "independentWuxing": "火行",
                "raw": "163期【图片识别】【火行】开:图片识别 对",
            },
            {
                "period": 163,
                "wuxing": "金行",
                "wuxingScore": 41,
                "wuxingGap": 3,
                "raw": "163期【图片识别】【金行】开:图片识别 对",
            },
            {
                "period": 162,
                "wuxing": "红波",
                "wuxingScore": 30,
                "wuxingGap": 15,
                "raw": "162期【图片识别】【红波】开:图片识别 对",
            },
        ], 163)

        self.assertEqual(accepted, ["163期【图片识别】【火行】开:图片识别 对"])

    def test_validate_image_ocr_rejects_ocr_only_or_disagreeing_recheck(self):
        base = {
            "period": 163,
            "wuxing": "火行",
            "wuxingScore": 42,
            "wuxingGap": 12,
            "raw": "163期【图片识别】【火行】开:图片识别 对",
        }

        self.assertEqual(MODULE.validate_image_ocr_lines([base], 163), [])
        self.assertEqual(
            MODULE.validate_image_ocr_lines([{**base, "independentPeriod": 163, "independentWuxing": "金行"}], 163),
            [],
        )

    def test_corrupt_history_cache_is_not_overwritten(self):
        site = MODULE.Site("https://example.com/a", "top", False, "测试站")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "history.json"
            original = "{broken-json"
            path.write_text(original, encoding="utf-8")
            outcomes = {0: (site, ["金行 190期 测试站"], None, [], 1.0)}

            with self.assertRaises(ValueError):
                MODULE.update_history_cache_from_outcomes([(0, site)], outcomes, 190, path)

            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_history_cache_deep_structure_damage_is_not_overwritten(self):
        site = MODULE.Site("https://example.com/a", "top", False, "测试站")
        invalid_caches = [
            {"version": 1, "sites": ["not-an-object"]},
            {"version": 1, "sites": [{"name": "测试站", "url": site.url, "region": "top", "history": {}}]},
            {"version": 1, "sites": [{"name": "测试站", "url": site.url, "region": "top", "history": [{"period": "190", "wuxing": "金行"}]}]},
            {"version": 1, "sites": [{"name": "测试站", "url": site.url, "region": "top", "history": [{"period": 190, "wuxing": "红波"}]}]},
        ]

        for invalid_cache in invalid_caches:
            with self.subTest(invalid_cache=invalid_cache), tempfile.TemporaryDirectory() as tmpdir:
                path = Path(tmpdir) / "history.json"
                original = json.dumps(invalid_cache, ensure_ascii=False)
                path.write_text(original, encoding="utf-8")
                outcomes = {0: (site, ["金行 190期 测试站"], None, [], 1.0)}

                with self.assertRaises(ValueError):
                    MODULE.update_history_cache_from_outcomes([(0, site)], outcomes, 190, path)

                self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_history_cache_rejects_same_site_period_wuxing_conflict(self):
        site = MODULE.Site("https://example.com/a", "top", False, "测试站")
        cache = {}
        MODULE.update_history_cache_entries(cache, [(site, 190, "金行")])
        before = json.loads(json.dumps(cache, ensure_ascii=False))

        with self.assertRaises(ValueError):
            MODULE.update_history_cache_entries(cache, [(site, 190, "木行")])

        self.assertEqual(cache, before)

    def test_history_cache_conflict_identity_uses_url_and_region_after_rename(self):
        old_site = MODULE.Site("https://example.com/a", "top", False, "旧名字")
        renamed_site = MODULE.Site("https://example.com/a", "top", False, "新名字")
        cache = {}
        MODULE.update_history_cache_entries(cache, [(old_site, 190, "金行")])
        before = json.loads(json.dumps(cache, ensure_ascii=False))

        with self.assertRaises(ValueError):
            MODULE.update_history_cache_entries(cache, [(renamed_site, 190, "木行")])

        self.assertEqual(cache, before)

    def test_http_404_detection_prefers_http_error_response_status(self):
        response_500 = requests.Response()
        response_500.status_code = 500
        response_500.url = "https://example.com/article/404"
        misleading = requests.HTTPError("500 error for url containing 404", response=response_500)
        response_404 = requests.Response()
        response_404.status_code = 404
        actual = requests.HTTPError("request failed", response=response_404)

        self.assertFalse(MODULE.is_http_404_error(misleading))
        self.assertTrue(MODULE.is_http_404_error(actual))

    def test_save_history_cache_uses_atomic_replace(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "history.json"
            MODULE.save_history_cache({"version": 1, "sites": []}, path)

            self.assertEqual(json.loads(path.read_text(encoding="utf-8-sig"))["sites"], [])
            self.assertEqual(list(path.parent.glob(f".{path.name}.*.tmp")), [])

    def test_retry_scrapes_use_separate_pools_and_accumulate_elapsed(self):
        http_sites = [(index, MODULE.Site(f"https://http{index}.example", "top", False, f"H{index}")) for index in range(4)]
        browser_sites = [(10 + index, MODULE.Site(f"https://browser{index}.example", "top", True, f"B{index}")) for index in range(3)]
        outcomes = {
            index: (site, [], "ReadTimeout", [], 1.5)
            for index, site in http_sites + browser_sites
        }
        active = {"http": 0, "browser": 0}
        peak = {"http": 0, "browser": 0}
        lock = threading.Lock()

        def fake_scrape(index, site, *_args):
            kind = "browser" if site.click_first else "http"
            with lock:
                active[kind] += 1
                peak[kind] = max(peak[kind], active[kind])
            time.sleep(0.03)
            with lock:
                active[kind] -= 1
            return index, site, [f"金行 190期 {site.name}"], None, [], 0.25

        with mock.patch.object(MODULE, "scrape_indexed_site", side_effect=fake_scrape):
            MODULE.run_retry_scrapes(
                outcomes, http_sites, browser_sites, 1, 45, False, 190,
                workers=8, browser_workers=2,
            )

        self.assertGreater(peak["http"], 1)
        self.assertLessEqual(peak["http"], 8)
        self.assertGreater(peak["browser"], 1)
        self.assertLessEqual(peak["browser"], 2)
        self.assertTrue(all(result[4] == 1.75 for result in outcomes.values()))

    def test_chromedriver_install_path_is_cached(self):
        MODULE.clear_runtime_caches()
        manager = mock.Mock()
        manager.install.return_value = "C:/driver/chromedriver.exe"

        self.assertEqual(MODULE.cached_chromedriver_path(lambda: manager), "C:/driver/chromedriver.exe")
        self.assertEqual(MODULE.cached_chromedriver_path(lambda: manager), "C:/driver/chromedriver.exe")
        manager.install.assert_called_once_with()

    def test_baofengzhouyu_uses_non_blocking_browser_page_load(self):
        baofeng_url = "https://pxgaayml.2wyk5-dwn70-cljflt.xyz:16677/topic/458324.html"

        self.assertEqual(MODULE.browser_page_load_strategy(baofeng_url), "none")
        self.assertEqual(MODULE.browser_page_load_strategy("https://example.com"), "normal")

    def test_dynamic_special_sites_use_visible_browser_text_only(self):
        urls = {
            "https://zxliojf.83gjk-dnne7-kuyach.xyz:16677/",
            "https://2.www39169b.com:888/#62111",
            "https://myvvqq.30dok-2s9fd-bibfmg.work/",
            "https://pxgaayml.2wyk5-dwn70-cljflt.xyz:16677/topic/458324.html",
        }
        for url in urls:
            with self.subTest(url=url):
                document = MODULE.compose_browser_document(
                    url,
                    "<script>193期 绝杀一行【水行】</script>",
                    "193期 绝杀一行【金行】",
                    [],
                )
                self.assertNotIn("水行", document)
                self.assertIn("金行", document)

    def test_target_signal_wait_requires_stable_matching_content(self):
        class Driver:
            def __init__(self):
                self.text = "加载中"
                self.page_source = ""

            def find_element(self, *_args):
                return mock.Mock(text=self.text)

        driver = Driver()
        condition = MODULE.target_signal_stability_condition(190, stable_rounds=2)
        self.assertFalse(condition(driver))
        driver.page_source = "<script>const hidden = '190期 绝杀一行【金行】';</script>"
        self.assertFalse(condition(driver))
        self.assertFalse(condition(driver))
        driver.text = "190期 绝杀一行【金行】"
        self.assertFalse(condition(driver))
        self.assertTrue(condition(driver))

    def test_target_signal_wait_ignores_unrelated_dynamic_page_changes(self):
        class Driver:
            def __init__(self):
                self.text = "193期：必杀一行【金行】开？00中"
                self.page_source = "<div>倒计时 00:00:02</div>"

            def find_element(self, *_args):
                return mock.Mock(text=self.text)

        driver = Driver()
        condition = MODULE.target_signal_stability_condition(193, stable_rounds=2)

        self.assertFalse(condition(driver))
        driver.page_source = "<div>倒计时 00:00:01</div>"
        self.assertTrue(condition(driver))

    def test_site_aware_wait_rejects_other_section_on_shared_url(self):
        class Driver:
            def __init__(self):
                self.text = "春满乡村（绝杀1.行）\n193期绝杀1.行【水水水】开:00√"

            def find_element(self, *_args):
                return mock.Mock(text=self.text)

        site = MODULE.Site(
            "https://zxliojf.83gjk-dnne7-kuyach.xyz:16677/",
            "bottom",
            False,
            "山水诗意",
        )
        driver = Driver()
        condition = MODULE.target_signal_stability_condition(193, stable_rounds=2, site=site)

        self.assertFalse(condition(driver))
        driver.text += "\n山水诗意（四行中特）\n193期四行中特◎木水土火◎开:00准"
        self.assertFalse(condition(driver))
        self.assertTrue(condition(driver))

    def test_site_aware_wait_requires_target_inside_direction_window(self):
        class Driver:
            def __init__(self):
                self.text = "\n".join(
                    [
                        "八步毛哥【必杀一行】",
                        "190期：必杀一行【木行】开兔16中",
                        "191期：必杀一行【水行】开虎29中",
                        "192期：必杀一行【土行】开马25中",
                        "193期：必杀一行【金行】开？00中",
                    ]
                )

            def find_element(self, *_args):
                return mock.Mock(text=self.text)

        site = MODULE.Site("https://2.www39169b.com:888/#62111", "top", True, "八步毛哥")
        condition = MODULE.target_signal_stability_condition(193, stable_rounds=2, site=site)

        driver = Driver()
        self.assertFalse(condition(driver))
        self.assertFalse(condition(driver))

    def test_browser_fallback_error_is_not_hidden_by_http_shell(self):
        site = MODULE.Site(
            "https://zqliou.kify1-fbyi6-lmeykn.xyz:16677/",
            "top",
            False,
            "信封论坛",
        )
        with (
            mock.patch.object(MODULE, "collect_documents", return_value=["澳门信封论坛升级公告"]),
            mock.patch.object(MODULE, "fetch_browser_text", side_effect=TimeoutError("browser target wait timed out")),
        ):
            lines, error, _ = MODULE.scrape_site_detailed(site, 1, 20, False, 193)

        self.assertEqual(lines, [])
        self.assertIn("browser target wait timed out", error or "")

    def test_http_old_period_does_not_hide_browser_target_period(self):
        site = MODULE.Site(
            "https://pxgaayml.2wyk5-dwn70-cljflt.xyz:16677/topic/458324.html",
            "top",
            False,
            "暴风骤雨",
        )
        old_http = "暴风骤雨\n192期：【绝杀一行】【金】开：马25准"
        current_browser = "暴风骤雨\n193期：【绝杀一行】【火】开：0000准"

        with (
            mock.patch.object(MODULE, "collect_documents", return_value=[old_http]),
            mock.patch.object(MODULE, "fetch_browser_text", return_value=current_browser),
        ):
            lines, error, _ = MODULE.scrape_site_detailed(site, 1, 20, False, 193)

        self.assertEqual(lines, ["火行 193期 暴风骤雨"])
        self.assertIsNone(error)

    def test_http_and_browser_same_period_conflict_is_rejected(self):
        site = MODULE.Site(
            "https://pxgaayml.2wyk5-dwn70-cljflt.xyz:16677/topic/458324.html",
            "top",
            False,
            "暴风骤雨",
        )
        http_document = "\n".join(
            [
                "暴风骤雨",
                "190期：【绝杀一行】【木】开：兔16准",
                "191期：【绝杀一行】【水】开：虎29准",
                "192期：【绝杀一行】【土】开：马25准",
                "193期：【绝杀一行】【金】开：0000准",
            ]
        )
        browser_document = "暴风骤雨\n193期：【绝杀一行】【火】开：0000准"

        with (
            mock.patch.object(MODULE, "collect_documents", return_value=[http_document]),
            mock.patch.object(MODULE, "fetch_browser_text", return_value=browser_document),
        ):
            lines, error, _ = MODULE.scrape_site_detailed(site, 1, 20, False, 193)

        self.assertEqual(lines, [])
        self.assertIn("五行冲突", error or "")

    def test_duplicate_periods_trigger_position_window(self):
        candidates = [
            MODULE.Candidate(period="151期", wuxing="金行", order=1, raw="first"),
            MODULE.Candidate(period="151期", wuxing="木行", order=2, raw="second"),
            MODULE.Candidate(period="152期", wuxing="水行", order=3, raw="third"),
            MODULE.Candidate(period="153期", wuxing="火行", order=4, raw="fourth"),
            MODULE.Candidate(period="154期", wuxing="土行", order=5, raw="fifth"),
            MODULE.Candidate(period="155期", wuxing="金行", order=6, raw="sixth"),
        ]

        self.assertTrue(MODULE.requires_strict_position_window(candidates))
        self.assertEqual(
            [candidate.raw for candidate in MODULE.position_window_candidates(candidates, "top")],
            ["first", "second", "third", "fourth", "fifth"],
        )
        self.assertEqual(
            [candidate.raw for candidate in MODULE.position_window_candidates(candidates, "bottom")],
            ["second", "third", "fourth", "fifth", "sixth"],
        )

    def test_strict_position_window_accepts_target_inside_window(self):
        documents = [
            "\n".join(
                f"{100 + index}期:【精杀一行】【金行】開：0000准"
                for index in range(31)
            ),
        ]

        _, candidates = MODULE.best_document_with_period_candidates(documents, 128, "bottom")

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].period, "128期")
        self.assertEqual(candidates[0].wuxing, "金行")

    def test_period_selection_does_not_reset_position_window_per_child_document(self):
        documents = [
            "\n".join(
                f"{200 + index}期:【绝杀一行】【金行】开:0000准"
                for index in range(31)
            ),
            "\n".join([
                "153期:【绝杀一行】【木行】开:0000准",
                "152期:【绝杀一行】【土行】开:狗45准",
                "151期:【绝杀一行】【火行】开:鼠31准",
            ]),
        ]

        _, candidates = MODULE.best_document_with_period_candidates(documents, 153, "top")

        self.assertEqual(candidates, [])

    def test_strict_position_window_reports_out_of_range_target(self):
        document = "\n".join(
            f"{100 + index}期:【绝杀一行】【金行】开:0000准"
            for index in range(31)
        )

        reason = MODULE.strict_position_window_failure_reason([document], "top", 130)

        self.assertIsNotNone(reason)
        self.assertIn("顶部只允许前5组", reason)
        self.assertIn("130期不在范围内", reason)

    def test_manual_period_must_be_inside_region_three_window(self):
        document = "\n".join([
            "159期:【绝杀一行】【金行】开:0000准",
            "158期:【绝杀一行】【木行】开:0000准",
            "157期:【绝杀一行】【水行】开:0000准",
            "156期:【绝杀一行】【火行】开:0000准",
        ])

        top_reason = MODULE.region_three_window_failure_reason([document], "top", 156)
        bottom_reason = MODULE.region_three_window_failure_reason([document], "bottom", 159)

        self.assertIsNotNone(top_reason)
        self.assertIn("顶部只允许前3条", top_reason)
        self.assertIn("156期不在范围内", top_reason)
        self.assertIsNotNone(bottom_reason)
        self.assertIn("底部只允许后3条", bottom_reason)
        self.assertIn("159期不在范围内", bottom_reason)
        self.assertIsNone(MODULE.region_three_window_failure_reason([document], "top", 159))
        self.assertIsNone(MODULE.region_three_window_failure_reason([document], "bottom", 156))

    def test_load_sites_accepts_region_alias(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sites.json"
            path.write_text(json.dumps([{"name": "测试站", "url": "https://example.com", "region": "bottom"}], ensure_ascii=False), encoding="utf-8")
            sites = MODULE.load_sites(path)
        self.assertEqual(sites[0].pick, "bottom")
        self.assertEqual(sites[0].name, "测试站")

    def test_should_retry_only_timeout_failures(self):
        self.assertTrue(MODULE.should_retry_failure("ReadTimeout: read timed out"))
        self.assertTrue(MODULE.should_retry_failure("请求超时"))
        self.assertFalse(MODULE.should_retry_failure("HTTP Error 502: Bad Gateway"))
        self.assertTrue(MODULE.should_retry_failure("curl exit 35: schannel: SSL/TLS connection failed"))
        self.assertFalse(MODULE.should_retry_failure("ConnectionError: Max retries exceeded"))
        self.assertFalse(MODULE.should_retry_failure("WebDriverException: net::ERR_CONNECTION_CLOSED"))

    def test_main_does_not_retry_explicit_502_failure(self):
        site = MODULE.Site("https://bad-gateway.example.com", "top", False, "bad gateway")
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "success.txt"
            fail = Path(tmpdir) / "fail.txt"
            history_cache = Path(tmpdir) / "history.json"
            argv = [
                "wuxing_crawler.py",
                "--period",
                "144",
                "--workers",
                "1",
                "--output",
                str(output),
                "--fail",
                str(fail),
                "--history-cache",
                str(history_cache),
            ]
            with mock.patch.object(MODULE, "load_sites", return_value=[site]), \
                 mock.patch.object(MODULE, "scrape_indexed_site", return_value=(0, site, [], "HTTP Error 502: Bad Gateway", [], 0.5)) as scrape_indexed_site, \
                 mock.patch.object(MODULE.sys, "argv", argv):
                MODULE.main()

            scrape_indexed_site.assert_called_once()
            self.assertTrue(output.exists())
            self.assertTrue(fail.exists())

    def test_progress_status_format_matches_terminal_requirement(self):
        outcomes = {}
        for index in range(42):
            site = MODULE.Site(f"https://example.com/{index}", "top", False, f"成功{index}")
            outcomes[index] = (site, [f"金行 191期 成功{index}"], None, [], 1.0)
        failed_site = MODULE.Site("https://example.com/failed", "top", False, "失败站")
        outcomes[42] = (failed_site, [], "请求超时", [], 2.0)

        line = MODULE.format_progress_status(
            outcomes,
            MODULE.Site("https://example.com/current", "top", False, "天猫优选"),
            163,
            started_at=100.0,
            now=136.4,
        )

        self.assertEqual(line, "[进度 43/163 26% 成功 42 失败 1 用时 36.4s] 当前: 天猫优选")

    def test_record_scrape_result_prints_single_live_progress_line(self):
        site = MODULE.Site("https://example.com/topic/1.html", "top", False, "测试站")
        outcomes = {}

        with mock.patch.object(MODULE.time, "perf_counter", return_value=101.25), mock.patch.object(
            MODULE, "print"
        ) as mocked_print:
            MODULE.record_scrape_result(
                outcomes,
                0,
                site,
                ["金行 144期 测试站"],
                None,
                [],
                1.25,
                total=1,
                progress_started_at=100.0,
            )

        mocked_print.assert_called_once_with(
            "\r[进度 1/1 100% 成功 1 失败 0 用时 1.2s] 当前: 测试站",
            end="",
            flush=True,
        )
        self.assertIn(0, outcomes)
        self.assertIn(0, outcomes)

    def test_build_slow_site_lines_lists_slowest_sites(self):
        site_a = MODULE.Site("https://example.com/a", "top", False, "快站")
        site_b = MODULE.Site("https://example.com/b", "bottom", False, "慢站")
        outcomes = {
            0: (site_a, ["金行 144期 快站"], None, [], 1.2),
            1: (site_b, [], "页面里未找到 144期", [], 8.5),
        }

        lines = MODULE.build_slow_site_lines(outcomes, limit=2)

        self.assertEqual(lines[0], "慢站耗时统计 Top 2：")
        self.assertIn("慢站", lines[1])
        self.assertIn("8.50s", lines[1])
        self.assertIn("失败", lines[1])

    def test_progress_label_uses_filtered_run_position(self):
        self.assertEqual(MODULE.progress_label(135, 1, {135: 1}), "[1/1] ")

    def test_main_does_not_create_fail_file_when_all_sites_succeed(self):
        site = MODULE.Site("https://example.com/topic/1.html", "top", False, "测试站")
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "success.txt"
            fail = Path(tmpdir) / "fail.txt"
            history_cache = Path(tmpdir) / "history.json"
            argv = [
                "wuxing_crawler.py",
                "--period",
                "144",
                "--output",
                str(output),
                "--fail",
                str(fail),
                "--history-cache",
                str(history_cache),
            ]
            with mock.patch.object(MODULE, "load_sites", return_value=[site]), \
                 mock.patch.object(MODULE, "scrape_indexed_site", return_value=(0, site, ["金行 144期 测试站"], None, [], 0.5)), \
                 mock.patch.object(MODULE.sys, "argv", argv):
                MODULE.main()
            self.assertTrue(output.exists())
            self.assertFalse(fail.exists())

    def test_main_reports_cache_conflict_without_losing_result_files(self):
        success_site = MODULE.Site("https://example.com/a", "top", False, "成功站")
        failed_site = MODULE.Site("https://example.com/b", "bottom", False, "失败站")
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "success.txt"
            fail = Path(tmpdir) / "fail.txt"
            history_cache = Path(tmpdir) / "history.json"
            argv = [
                "wuxing_crawler.py",
                "--period",
                "191",
                "--output",
                str(output),
                "--fail",
                str(fail),
                "--history-cache",
                str(history_cache),
            ]
            outcomes = {
                0: (0, success_site, ["金行 191期 成功站"], None, [], 0.5),
                1: (1, failed_site, [], "页面里未找到 191期", [], 0.5),
            }

            with mock.patch.object(MODULE, "load_sites", return_value=[success_site, failed_site]), mock.patch.object(
                MODULE, "scrape_indexed_site", side_effect=lambda index, *args: outcomes[index]
            ), mock.patch.object(
                MODULE,
                "update_history_cache_from_outcomes",
                side_effect=ValueError("八级心动 191期缓存五行冲突: 土行 / 火行"),
            ), mock.patch.object(MODULE.sys, "argv", argv), mock.patch.object(MODULE, "print") as mocked_print:
                MODULE.main()

            self.assertTrue(output.exists())
            self.assertTrue(fail.exists())
            self.assertTrue(
                any("历史缓存未更新" in str(call) and "缓存五行冲突" in str(call) for call in mocked_print.call_args_list)
            )

    def test_main_reports_cache_io_error_without_losing_result_files(self):
        success_site = MODULE.Site("https://example.com/a", "top", False, "成功站")
        failed_site = MODULE.Site("https://example.com/b", "bottom", False, "失败站")
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "success.txt"
            fail = Path(tmpdir) / "fail.txt"
            argv = [
                "wuxing_crawler.py",
                "--period",
                "191",
                "--output",
                str(output),
                "--fail",
                str(fail),
                "--history-cache",
                str(Path(tmpdir) / "history.json"),
            ]
            outcomes = {
                0: (0, success_site, ["金行 191期 成功站"], None, [], 0.5),
                1: (1, failed_site, [], "页面里未找到 191期", [], 0.5),
            }

            with mock.patch.object(MODULE, "load_sites", return_value=[success_site, failed_site]), mock.patch.object(
                MODULE, "scrape_indexed_site", side_effect=lambda index, *args: outcomes[index]
            ), mock.patch.object(
                MODULE, "update_history_cache_from_outcomes", side_effect=OSError("磁盘写入失败")
            ), mock.patch.object(MODULE.sys, "argv", argv), mock.patch.object(MODULE, "print") as mocked_print:
                MODULE.main()

            self.assertTrue(output.exists())
            self.assertTrue(fail.exists())
            self.assertTrue(any("历史缓存未更新" in str(call) for call in mocked_print.call_args_list))

    def test_main_removes_stale_fail_file_when_all_sites_succeed(self):
        site = MODULE.Site("https://example.com/topic/1.html", "top", False, "测试站")
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "success.txt"
            fail = Path(tmpdir) / "fail.txt"
            history_cache = Path(tmpdir) / "history.json"
            fail.write_text("旧失败\n", encoding="utf-8")
            argv = [
                "wuxing_crawler.py",
                "--period",
                "144",
                "--output",
                str(output),
                "--fail",
                str(fail),
                "--history-cache",
                str(history_cache),
            ]
            with mock.patch.object(MODULE, "load_sites", return_value=[site]), \
                 mock.patch.object(MODULE, "scrape_indexed_site", return_value=(0, site, ["金行 144期 测试站"], None, [], 0.5)), \
                 mock.patch.object(MODULE.sys, "argv", argv):
                MODULE.main()
            self.assertTrue(output.exists())
            self.assertFalse(fail.exists())

    def test_failed_site_dedicated_rows_match_current_formats(self):
        xinfeng = MODULE.Site(
            "https://zqliou.kify1-fbyi6-lmeykn.xyz:16677/", "top", False, "信封论坛"
        )
        xinfeng_doc = "澳门信封论坛『绝杀一行』\n201期:【绝杀一行】【土行】开:0000准\n201期绝杀一头【0头】开:0000准"
        self.assertEqual(
            [(item.period, item.wuxing) for item in MODULE.parse_candidates_for_site(xinfeng_doc, xinfeng)],
            [("201期", "土行")],
        )

        yiben = MODULE.Site(
            "https://mflmcobome.26222hi.app:2569/htm/bbs/top040.html", "bottom", False, "一本万利"
        )
        yiben_doc = "一本万利【绝杀一行】\n201期:绝杀一行开:00准\n【木】"
        self.assertEqual(
            [(item.period, item.wuxing) for item in MODULE.parse_candidates_for_site(yiben_doc, yiben)],
            [("201期", "木行")],
        )

    def test_yibenwanli_accepts_period_keyword_and_wuxing_split_across_lines(self):
        yiben = MODULE.Site(
            "https://mflmcobome.26222hi.app:2569/htm/bbs/top040.html", "bottom", False, "一本万利"
        )
        yiben_doc = "\n".join(
            (
                "200期:",
                "⚡️绝杀一行⚡️",
                "开: 龙39 准",
                "【金】",
                "201期:",
                "⚡️绝杀一行⚡️",
                "开: 00 准",
                "【木】",
            )
        )

        candidates = MODULE.parse_candidates_for_site(yiben_doc, yiben)

        self.assertEqual(
            [(item.period, item.wuxing) for item in candidates if item.period == "201期"],
            [("201期", "木行")],
        )

    def test_eight_level_heart_uses_its_own_section_without_clicking_other_topic(self):
        site = MODULE.Site(
            "https://cwdcaqzn.7mj0h-75k3q-cbuvqb.work:16677/#am", "top", True, "八级心动"
        )
        document = "八级心动【绝杀一行】\n201期绝杀一行【水行】开？00准\n201期:精选来者不笑(绝杀一行)"
        self.assertEqual(
            [(item.period, item.wuxing) for item in MODULE.parse_candidates_for_site(document, site)],
            [("201期", "水行")],
        )
        self.assertIn(site.url, MODULE.BROWSER_SKIP_CLICK_URLS)

    def test_eight_level_heart_anchor_is_its_own_section(self):
        url = "https://cwdcaqzn.7mj0h-75k3q-cbuvqb.work:16677/#am"

        self.assertRegex("八级心动【绝杀一行】", MODULE.SITE_CURRENT_BLOCK_ANCHORS[url])
        self.assertNotRegex("精选来者不笑【绝杀一行】", MODULE.SITE_CURRENT_BLOCK_ANCHORS[url])

    def test_yirujiwang_authoritative_group_stops_at_second_record(self):
        site = MODULE.Site(
            "https://eebysckd.2go6k-y0pfv-fqbdsm.xyz:16677/topic/626030.html",
            "top",
            False,
            "一如既往",
        )
        documents = [
            "201期: 一如既往 「精杀一行」",
            "一如既往 发表于\n201期精杀一行【火行】开：0000准\n200期精杀一行【金行】开：龙39准",
            "199期精杀一行【土行】开：羊36错",
            "203期精杀一行【水行】开：鼠18准\n202期精杀一行【土行】开：狗20错\n201期精杀一行【金行】开：羊47准",
            "上一篇：其他文章",
        ]
        selected = MODULE.site_authoritative_documents(documents, site)
        self.assertEqual(selected, [documents[1]])
        candidates = MODULE.combined_document_candidates(
            selected,
            parser_fn=lambda document: MODULE.parse_candidates_for_site(document, site),
        )
        self.assertEqual(
            [(item.period, item.wuxing) for item in candidates if item.period == "201期"],
            [("201期", "火行")],
        )


if __name__ == "__main__":
    unittest.main()







