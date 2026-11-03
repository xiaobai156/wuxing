import base64
import json
from dataclasses import replace

import pytest

from cli.common import build_runtime
from wuxing.domain.enums import (
    FailureCode,
    FetchStrategy,
    Region,
    ResultStatus,
    SourceKind,
    WritePolicy,
)
from wuxing.domain.errors import FetchError
from wuxing.domain.models import ScrapeRequest, SiteConfig, SourceDocument
from wuxing.registry import build_site_registry
from wuxing.services.scrape import LiveSourceGateway, ScrapeService
from wuxing.sources.article_api import decode_article_api_document
from wuxing.sources.browser import BrowserCapture, BrowserPlan, BrowserSource

TARGET_SITES = {
    "广西仔第二版": "水行",
    "澳门第三四不像": "金行",
    "眉飞色舞": "火行",
    "雷锋": "木行",
}


class ScriptedGateway:
    def __init__(self):
        self.fallback_calls: list[str] = []

    def fetch(self, rule, request):
        return (
            SourceDocument(
                document_id=f"http-{rule.site.site_id}",
                url=rule.site.url,
                source_kind=SourceKind.PAGE,
                text="页面正文没有有效目标候选",
                order=0,
            ),
        )

    def fetch_fallback(self, rule, request):
        self.fallback_calls.append(rule.site.name)
        if rule.site.name == "广西仔第二版":
            text = (
                "【稳杀一行】\n"
                "228期★杀1行【水】开0000准\n"
                "227期★杀1行【金】开兔16准\n"
                "226期★杀1行【火】开虎17准\n"
                "225期★杀1行【木】开马01准"
            )
        elif rule.site.name == "澳门第三四不像":
            text = (
                "澳门第三四不像\n"
                "228期 绝杀一行 【金行 】 开 ？00 准\n"
                "227期 绝杀一行 【土行 】 开 兔16 准\n"
                "226期 绝杀一行 【火行 】 开 虎17 准\n"
                "225期 绝杀一行 【木行 】 开 马01 准"
            )
        elif rule.site.name == "眉飞色舞":
            text = (
                "228期【绝杀一行】【火】开0000准\n"
                "227期【绝杀一行】【土】开兔16准\n"
                "226期【绝杀一行】【水】开虎17准"
            )
        else:
            text = (
                "228期:绝杀一行【 杀木行】&开:0000对\n"
                "227期:绝杀一行【 杀土行】&开:兔16对\n"
                "226期:绝杀一行【 杀金行】&开:虎17对"
            )
        return (
            SourceDocument(
                document_id=f"browser-{rule.site.site_id}",
                url=rule.site.url,
                source_kind=SourceKind.BROWSER,
                text=text,
                order=0,
                rendered=True,
                metadata=(("capture_part", "page_source"),),
            ),
        )


def _service_for_sites(tmp_path, names: tuple[str, ...], browser_fallback: bool | None = None):
    runtime = build_runtime(
        config_path="sites.json",
        cache_path=tmp_path / "cache.json",
    )
    selected = tuple(site for site in runtime.sites if site.name in names)
    if browser_fallback is not None:
        selected = tuple(replace(site, browser_fallback=browser_fallback) for site in selected)
    gateway = ScriptedGateway()
    service = ScrapeService(build_site_registry(selected), gateway)
    return service, gateway, selected


def test_verified_topic_sites_use_browser_text_fallback_without_url_anchors(tmp_path):
    service, gateway, selected = _service_for_sites(tmp_path, tuple(TARGET_SITES))

    assert {site.name: site.browser_fallback for site in selected} == {
        name: True for name in TARGET_SITES
    }
    assert all(
        service.registry.require(site.site_id).fetch_strategy is FetchStrategy.HTTP_THEN_BROWSER
        for site in selected
    )

    results = tuple(
        service.scrape(
            site.site_id,
            ScrapeRequest(periods=(228,), write_policy=WritePolicy.READ_ONLY),
        )
        for site in selected
    )

    assert all(result.status is ResultStatus.SUCCESS for result in results)
    assert {
        result.site.name: result.candidate.wuxing
        for result in results
        if result.candidate
    } == TARGET_SITES
    assert all(result.attempts == 2 for result in results)
    assert gateway.fallback_calls == [site.name for site in selected]


def test_unflagged_http_site_does_not_get_topic_browser_fallback(tmp_path):
    service, gateway, selected = _service_for_sites(
        tmp_path,
        ("广西仔第二版",),
        browser_fallback=False,
    )

    result = service.scrape(
        selected[0].site_id,
        ScrapeRequest(periods=(228,), write_policy=WritePolicy.READ_ONLY),
    )

    assert result.status is ResultStatus.FAILURE
    assert result.failure_code is FailureCode.TARGET_NOT_FOUND
    assert result.attempts == 1
    assert gateway.fallback_calls == []


class StaticBrowserBackend:
    def capture(self, site, period, timeout, show_browser, plan):
        return BrowserCapture(
            current_url=site.url,
            page_source="<html></html>",
            body_text="页面正文",
            record_text="237期稳杀(1)行【水】开0000准",
            record_html="<div><span>237期</span><span>稳杀(1)行</span><span>【水】</span></div>",
        )


def test_visible_text_only_record_uses_rendered_text():
    site = SiteConfig(
        site_id="million",
        name="百万资料",
        url="https://example.invalid/",
        region=Region.TOP,
        rule_id="million.v1",
    )
    documents = BrowserSource(StaticBrowserBackend()).fetch(
        site,
        237,
        10,
        False,
        BrowserPlan(record_selector=".swiper-slide-active", visible_text_only=True),
    )

    assert documents[0].text == "237期稳杀(1)行【水】开0000准"


def test_zhugeshentong_uses_complete_http_document(tmp_path):
    runtime = build_runtime(config_path="sites.json", cache_path=tmp_path / "cache.json")
    site = next(site for site in runtime.sites if site.name == "诸葛神通")

    assert runtime.registry.require(site.site_id).fetch_strategy is FetchStrategy.HTTP_THEN_BROWSER


def test_zhugeshentong_four_line_reverse_accepts_one_record_split_across_lines(tmp_path):
    runtime = build_runtime(config_path="sites.json", cache_path=tmp_path / "cache.json")
    site = next(site for site in runtime.sites if site.name == "诸葛神通")
    rule = runtime.registry.require(site.site_id)
    document = SourceDocument(
        document_id="zhugeshentong-244",
        url=site.url,
        source_kind=SourceKind.PAGE,
        text=(
            "243期:\n『诸葛神通』\n四行中特\n【火.金.木.水】开:土21错\n"
            "244期:\n『诸葛神通』\n四行中特\n【火.金.水.土】开:00准\n"
            "金:04.05\n木:08.09"
        ),
        order=0,
    )

    candidates = rule.parse((document,))

    assert [(item.period, item.wuxing) for item in candidates] == [
        (243, "土行"),
        (244, "木行"),
    ]


def test_million_uses_browser_tab_click_flow(tmp_path):
    runtime = build_runtime(config_path="sites.json", cache_path=tmp_path / "cache.json")
    site = next(site for site in runtime.sites if site.name == "百万资料")

    assert runtime.registry.require(site.site_id).fetch_strategy is FetchStrategy.BROWSER_FIRST


def test_million_parser_accepts_wuxing_split_by_html_spans(tmp_path):
    runtime = build_runtime(config_path="sites.json", cache_path=tmp_path / "cache.json")
    site = next(site for site in runtime.sites if site.name == "百万资料")
    rule = runtime.registry.require(site.site_id)
    document = SourceDocument(
        document_id="million-244",
        url=site.url,
        source_kind=SourceKind.SCRIPT,
        text=(
            "<p><span>244期稳杀(1)行</span><span>【火】</span><span>开0000准</span></p>"
            "<p><span>243期稳杀(1)行</span><span>【水】</span><span>开狗21准</span></p>"
        ),
        order=0,
    )

    candidates = rule.parse((document,))

    assert [(item.period, item.wuxing) for item in candidates] == [
        (244, "火行"),
        (243, "水行"),
    ]


def test_head_dizzy_parser_stops_at_period_cycle_rollover(tmp_path):
    runtime = build_runtime(config_path="sites.json", cache_path=tmp_path / "cache.json")
    site = next(site for site in runtime.sites if site.name == "头昏眼花")
    rule = runtime.registry.require(site.site_id)
    document = SourceDocument(
        document_id="head-dizzy",
        url=site.url,
        source_kind=SourceKind.BROWSER,
        text=(
            "绝杀贴237期【绝杀一行】已更新 作者:头昏眼花 "
            "237期:绝杀①行【火行】 236期:绝杀①行【木行】 "
            "001期:绝杀①行【水行】 365期:绝杀①行【土行】 "
            "237期:绝杀①行【金行】"
        ),
        order=0,
        rendered=True,
    )

    candidates = rule.parse((document,))

    assert [(candidate.period, candidate.wuxing) for candidate in candidates] == [
        (237, "火行"),
        (236, "木行"),
        (1, "水行"),
    ]


def test_manager_four_line_reverse_allows_trailing_separator():
    runtime = build_runtime(config_path="sites.json", cache_path="unused-cache.json")
    site = next(site for site in runtime.sites if site.name == "齐天大胜")
    rule = runtime.registry.require(site.site_id)
    document = SourceDocument(
        document_id="qitian-dasheng-243",
        url=site.url,
        source_kind=SourceKind.API,
        text="243期：【齐天大胜】④行中特【金.土.火.木.】开:00准",
        order=0,
    )

    candidates = rule.parse((document,))

    assert [(item.period, item.wuxing) for item in candidates] == [(243, "水行")]


def test_lottery_article_api_requires_matching_resource_and_record_id():
    article_id = "0123456789abcdef01234567"
    site = SiteConfig(
        site_id="lottery-api",
        name="测试作者",
        url=f"https://example.invalid/article/lottery/{article_id}?url=jdb",
        api_url=f"https://example.invalid/api/proxy/lottery-articles/{article_id}",
        region=Region.BOTTOM,
        rule_id="lottery-api.v1",
    )
    def encode(value):
        return base64.b64encode(value.encode()).decode()
    payload = json.dumps({
        "data": {
            "id": article_id,
            "authorNickname": "测试作者",
            "title": encode("绝杀一行"),
            "html": encode("237期 测试作者 绝杀一行【木】\n238期 测试作者 绝杀一行【土】\n239期 测试作者 绝杀一行【水】"),
            "formSections": [
                {"type": "mainarticle", "name": "主条目"},
                {"type": "banner", "name": "底部"},
            ],
        }
    })

    document = decode_article_api_document(payload, site)
    assert document.record_id == article_id

    wrong_api = replace(
        site,
        api_url=f"https://example.invalid/api/proxy/manager-articles/{article_id}",
    )
    with pytest.raises(FetchError, match="API路径"):
        decode_article_api_document(payload, wrong_api)


class WrongViewRecordBackend:
    def capture(self, site, period, timeout, show_browser, plan):
        return BrowserCapture(
            current_url="https://example.invalid/view.php?id=556",
            page_source="<html></html>",
            body_text="大哥财富 239期 绝杀一行【火】",
            record_text="大哥财富 239期 绝杀一行【火】",
        )


def test_view_page_browser_rejects_wrong_query_record_id():
    site = SiteConfig(
        site_id="view-663",
        name="大哥财富",
        url="https://example.invalid/view.php?id=663",
        region=Region.BOTTOM,
        rule_id="view-663.v1",
    )
    with pytest.raises(FetchError, match="记录ID不一致"):
        BrowserSource(WrongViewRecordBackend()).fetch(
            site,
            239,
            10,
            False,
            BrowserPlan(record_selector="body", required_text_pattern="大哥财富"),
        )


def test_new_name_scoped_rule_stops_at_target_document_boundary(tmp_path):
    runtime = build_runtime(config_path="sites.json", cache_path=tmp_path / "cache.json")
    site = next(site for site in runtime.sites if site.name == "天天宝典")
    rule = runtime.registry.require(site.site_id)
    document = SourceDocument(
        document_id="name-scoped",
        url=site.url,
        source_kind=SourceKind.PAGE,
        text=(
            "239期：【天天宝典】【绝杀1行】 作者：天天宝典 "
            "237期:绝杀1行【木】 238期:绝杀1行【木】 239期:绝杀1行【水】 "
            "下一篇：239期:绝杀1行【火】"
        ),
        order=0,
    )

    candidates = rule.parse((document,))
    assert [(item.period, item.wuxing) for item in candidates] == [
        (237, "木行"),
        (238, "木行"),
        (239, "水行"),
    ]


class ClickThroughHttpClient:
    def fetch_text(self, url, timeout):
        if url.endswith("/topic/257907.html"):
            return (
                '<a href="/topic/1079493.html">'
                '242期：【男儿本色】☆绝杀一行☆实力见证！ 百万资料库 123'
                "</a>"
            )
        return "<html>详情脚本尚未渲染</html>"


class ClickThroughBrowserBackend:
    def __init__(self):
        self.calls = []

    def capture(self, site, period, timeout, show_browser, plan):
        self.calls.append((site.url, period, plan.record_selector, plan.visible_text_only))
        return BrowserCapture(
            current_url=site.url,
            page_source="<html></html>",
            body_text="",
            record_text=(
                "242期：【男儿本色】☆绝杀一行☆实力见证！\n"
                "242期:绝杀(1)行【土行】开:0000准\n"
                "241期:绝杀(1)行【木行】开:马49准\n"
                "240期:绝杀(1)行【水行】开:龙27准"
            ),
        )


def test_click_through_detail_uses_playwright_rendered_exact_body(tmp_path):
    runtime = build_runtime(config_path="sites.json", cache_path=tmp_path / "cache.json")
    site = next(site for site in runtime.sites if site.name == "男儿本色")
    backend = ClickThroughBrowserBackend()
    gateway = LiveSourceGateway(
        http_client=ClickThroughHttpClient(),
        browser_source=BrowserSource(backend),
    )
    service = ScrapeService(build_site_registry((site,)), gateway)

    result = service.scrape(
        site.site_id,
        ScrapeRequest(periods=(242,), write_policy=WritePolicy.READ_ONLY),
    )

    assert result.status is ResultStatus.SUCCESS
    assert result.candidate and result.candidate.wuxing == "土行"
    assert backend.calls == [
        (
            "https://mxiscni.nkh6s-vfni4-lwgfvw.xyz:16677/topic/1079493.html",
            242,
            "body",
            True,
        )
    ]
