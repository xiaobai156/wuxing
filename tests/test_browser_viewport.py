"""站点级浏览器视口与滚动开关：巨型页面在大视口/滚动下会崩渲染进程。"""

from wuxing import registry_data
from wuxing.domain.enums import Region
from wuxing.domain.models import SiteConfig
from wuxing.sources.browser import PlaywrightBrowserBackend


def _site(**overrides) -> SiteConfig:
    base = {
        "site_id": "site-test-0001",
        "name": "测试站",
        "url": "https://example.invalid/",
        "region": Region.TOP,
        "rule_id": "site.site-test-0001.v1",
    }
    base.update(overrides)
    return SiteConfig(**base)


def test_default_viewport_matches_legacy_size():
    assert PlaywrightBrowserBackend._viewport(_site()) == {"width": 1280, "height": 1800}


def test_site_viewport_is_parsed():
    site = _site(browser_viewport="1280x720")
    assert PlaywrightBrowserBackend._viewport(site) == {"width": 1280, "height": 720}


def test_invalid_viewport_falls_back_to_default():
    for raw in ("", "1280", "axb", "1280x", "0x0"):
        assert PlaywrightBrowserBackend._viewport(_site(browser_viewport=raw)) == {
            "width": 1280,
            "height": 1800,
        }


def test_site_no_scroll_flag_disables_scroll():
    assert PlaywrightBrowserBackend._should_scroll(_site(browser_no_scroll=True)) is False


def test_legacy_no_scroll_url_list_still_respected():
    url = sorted(registry_data.BROWSER_NO_SCROLL_URLS)[0]
    assert PlaywrightBrowserBackend._should_scroll(_site(url=url)) is False


def test_ordinary_site_still_scrolls():
    assert PlaywrightBrowserBackend._should_scroll(_site()) is True
