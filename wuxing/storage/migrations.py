"""Migration previews only; replacing production data always requires user approval."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from wuxing.config.schema import HISTORY_SCHEMA_VERSION
from wuxing.domain.enums import Region
from wuxing.domain.models import SiteConfig, VALID_WUXING


@dataclass(frozen=True)
class CacheMigrationPreview:
    cache: dict[str, object]
    matched_site_ids: tuple[str, ...]
    orphan_labels: tuple[str, ...]
    missing_site_ids: tuple[str, ...]
    conflicts: tuple[str, ...]


def _legacy_identity(entry: dict) -> tuple[str, str, str]:
    name = str(entry.get("name", "")).strip()
    url = str(entry.get("url", "")).strip()
    try:
        region = Region.from_value(entry.get("region", "")).value
    except ValueError:
        region = str(entry.get("region", "")).strip()
    return name, url, region


def _convert_history(entry: dict, site: SiteConfig, conflicts: list[str]) -> list[dict[str, object]]:
    raw_history = entry.get("history", [])
    if not isinstance(raw_history, list):
        conflicts.append(f"{site.name} 的旧缓存 history 不是数组")
        return []
    by_period: dict[int, dict[str, object]] = {}
    for item in raw_history:
        if not isinstance(item, dict):
            conflicts.append(f"{site.name} 存在非对象历史项")
            continue
        period = item.get("period")
        wuxing = item.get("wuxing")
        if isinstance(period, bool) or not isinstance(period, int) or period <= 0:
            conflicts.append(f"{site.name} 存在无效历史期号：{period}")
            continue
        if wuxing not in VALID_WUXING:
            conflicts.append(f"{site.name} {period}期不是标准五行：{wuxing}")
            continue
        previous = by_period.get(period)
        if previous is not None and previous["wuxing"] != wuxing:
            conflicts.append(
                f"{site.name} {period}期旧缓存冲突：{previous['wuxing']} / {wuxing}"
            )
            continue
        by_period[period] = {
            "period": period,
            "wuxing": wuxing,
            "captured_at": "",
            "source_digest": "",
            "rule_version": site.rule_id,
        }
    return sorted(by_period.values(), key=lambda item: int(item["period"]), reverse=True)[:10]


def build_legacy_cache_migration_preview(
    legacy_payload: object,
    sites: Iterable[SiteConfig],
) -> CacheMigrationPreview:
    configured_sites = tuple(sites)
    conflicts: list[str] = []
    if not isinstance(legacy_payload, dict) or not isinstance(legacy_payload.get("sites"), list):
        conflicts.append("旧缓存根节点或 sites 结构无效")
        legacy_entries: list[dict] = []
    else:
        legacy_entries = [entry for entry in legacy_payload["sites"] if isinstance(entry, dict)]
        if len(legacy_entries) != len(legacy_payload["sites"]):
            conflicts.append("旧缓存包含非对象站点条目")

    entries_by_identity: dict[tuple[str, str, str], list[dict]] = {}
    for entry in legacy_entries:
        entries_by_identity.setdefault(_legacy_identity(entry), []).append(entry)

    configured_identities = {
        (site.name, site.url, site.region.value): site for site in configured_sites
    }
    matched: list[str] = []
    missing: list[str] = []
    converted_sites: list[dict[str, object]] = []
    maximum_period = int(legacy_payload.get("updated_period", 0) or 0) if isinstance(legacy_payload, dict) else 0

    for site in configured_sites:
        identity = (site.name, site.url, site.region.value)
        matches = entries_by_identity.get(identity, [])
        if not matches:
            missing.append(site.site_id)
            continue
        if len(matches) != 1:
            conflicts.append(f"{site.name} 匹配到 {len(matches)} 条旧缓存记录")
            continue
        history = _convert_history(matches[0], site, conflicts)
        matched.append(site.site_id)
        if history:
            maximum_period = max(maximum_period, max(int(item["period"]) for item in history))
        converted_sites.append({
            "site_id": site.site_id,
            "name": site.name,
            "url": site.url,
            "region": site.region.value,
            "history": history,
        })

    orphan_labels = []
    for entry in legacy_entries:
        if _legacy_identity(entry) not in configured_identities:
            orphan_labels.append(
                f"{str(entry.get('name', '')).strip()} | {str(entry.get('url', '')).strip()}"
            )

    cache_sites = [] if conflicts else converted_sites
    cache: dict[str, object] = {
        "schema_version": HISTORY_SCHEMA_VERSION,
        "updated_period": maximum_period,
        "sites": cache_sites,
    }
    return CacheMigrationPreview(
        cache=cache,
        matched_site_ids=tuple(matched),
        orphan_labels=tuple(orphan_labels),
        missing_site_ids=tuple(missing),
        conflicts=tuple(conflicts),
    )
