"""browser_reveal_content：展开 content-visibility:auto 折叠区块的站点开关。"""

from __future__ import annotations

import json

from wuxing.config.site_loader import build_versioned_site_payload, load_site_configs
from wuxing.domain.enums import Region
from wuxing.domain.models import SiteConfig
from wuxing.sources.browser import PlaywrightBrowserBackend


def _site(**overrides) -> SiteConfig:
    base = {
        "site_id": "site-test-0002",
        "name": "测试站",
        "url": "https://example.invalid/",
        "region": Region.TOP,
        "rule_id": "site.site-test-0002.v1",
    }
    base.update(overrides)
    return SiteConfig(**base)


def _write_legacy(tmp_path, item: dict):
    path = tmp_path / "sites.json"
    path.write_text(json.dumps([item], ensure_ascii=False), encoding="utf-8")
    return path


def test_default_is_disabled():
    assert _site().browser_reveal_content is False


def test_legacy_item_parses_flag(tmp_path):
    path = _write_legacy(
        tmp_path,
        {
            "name": "展开站",
            "url": "https://example.invalid/",
            "region": "top",
            "browser_reveal_content": True,
        },
    )
    (site,) = load_site_configs(path, allow_legacy=True)
    assert site.browser_reveal_content is True


def test_legacy_item_without_flag_stays_disabled(tmp_path):
    path = _write_legacy(
        tmp_path,
        {"name": "普通站", "url": "https://example.invalid/", "region": "top"},
    )
    (site,) = load_site_configs(path, allow_legacy=True)
    assert site.browser_reveal_content is False


def test_payload_only_carries_flag_when_enabled():
    enabled = build_versioned_site_payload([_site(browser_reveal_content=True)])
    disabled = build_versioned_site_payload([_site()])
    assert enabled["sites"][0]["browser_reveal_content"] is True
    assert "browser_reveal_content" not in disabled["sites"][0]


def test_reveal_is_off_by_default_for_scroll_guard():
    # 展开属于额外放松，不能顺手影响滚动与视口策略。
    site = _site(browser_reveal_content=True)
    assert PlaywrightBrowserBackend._should_scroll(site) is True
    assert PlaywrightBrowserBackend._viewport(site) == {"width": 1280, "height": 1800}
