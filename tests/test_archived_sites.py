import json
from pathlib import Path

from cli.common import build_runtime
from wuxing.config.site_loader import load_site_configs


TARGETS = {
    "财神驾到",
    "历史最猛",
    "财神致富",
    "富豪爆彩",
    "糖果妹妹",
    "开奖欢喜",
    "宝典军师",
    "轰动大陆",
    "发财之道",
}
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_archived_sites_are_excluded_from_active_runtime_and_marked_in_cache(tmp_path):
    config_path = PROJECT_ROOT / "sites.json"
    cache_path = PROJECT_ROOT / "recent_10_cache.json"

    configured = {
        site.name: site
        for site in load_site_configs(config_path, allow_legacy=True)
        if site.name in TARGETS
    }
    assert set(configured) == TARGETS
    assert all(site.archived for site in configured.values())

    runtime = build_runtime(config_path=config_path, cache_path=tmp_path / "cache.json")
    assert TARGETS.isdisjoint({site.name for site in runtime.sites})

    cache = json.loads(cache_path.read_text(encoding="utf-8-sig"))
    cached = {
        (site["name"], site["url"], site["region"]): site
        for site in cache["sites"]
    }
    for site in configured.values():
        entry = cached[(site.name, site.url, site.region.value)]
        assert entry.get("archived") is True
