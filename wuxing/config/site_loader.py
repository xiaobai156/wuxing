from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable

from wuxing.domain.errors import ConfigError
from wuxing.domain.enums import Region
from wuxing.domain.models import SiteConfig

from .schema import SITE_SCHEMA_VERSION


def _legacy_site_id(index: int, url: str) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:10]
    return f"site-{index:04d}-{digest}"


def _legacy_rule_id(site_id: str) -> str:
    return f"site.{site_id}.v1"


def _shared_source_id(url: str) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    return f"shared-{digest}"


def _parse_site(
    item: object,
    index: int,
    legacy: bool,
    legacy_shared_source_id: str = "",
) -> SiteConfig:
    if not isinstance(item, dict):
        raise ConfigError(f"站点配置第{index}项必须是对象")
    try:
        name = str(item.get("name", "")).strip()
        url = str(item.get("url", "")).strip()
        region = Region.from_value(item.get("region", item.get("pick", "")))
        site_id = str(item.get("site_id", "")).strip()
        rule_id = str(item.get("rule_id", "")).strip()
        if legacy:
            site_id = site_id or _legacy_site_id(index, url)
            rule_id = rule_id or _legacy_rule_id(site_id)
        parser_id = str(item.get("parser_id", "")).strip()
        if not parser_id:
            parser_id = (
                "parser.bajixindong.v2"
                if url == "https://cwdcaqzn.7mj0h-75k3q-cbuvqb.work:16677/#am"
                else f"parser.{site_id}.v2"
            )
        return SiteConfig(
            site_id=site_id,
            name=name,
            url=url,
            region=region,
            rule_id=rule_id,
            parser_id=parser_id,
            shared_source_id=str(item.get("shared_source_id", legacy_shared_source_id)).strip(),
            api_url=str(item.get("api_url", "")).strip(),
            click_first=bool(item.get("click_first", False)),
            enabled=bool(item.get("enabled", True)),
            config_version=int(item.get("config_version", 1)),
        )
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"站点配置第{index}项无效：{exc}") from exc


def _validate_unique(sites: Iterable[SiteConfig]) -> list[SiteConfig]:
    result = list(sites)
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    seen_urls: dict[str, str] = {}
    for site in result:
        if site.site_id in seen_ids:
            raise ConfigError(f"site_id 重复：{site.site_id}")
        if site.name in seen_names:
            raise ConfigError(f"目录名重复：{site.name}")
        previous_shared_source_id = seen_urls.get(site.url)
        if previous_shared_source_id is not None:
            if not site.shared_source_id or site.shared_source_id != previous_shared_source_id:
                raise ConfigError(f"URL 重复且未声明相同 shared_source_id：{site.url}")
        seen_ids.add(site.site_id)
        seen_names.add(site.name)
        seen_urls[site.url] = site.shared_source_id
    return result


def load_site_configs(path: str | Path, allow_legacy: bool = False) -> list[SiteConfig]:
    config_path = Path(path)
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"站点配置读取失败：{exc}") from exc

    if isinstance(payload, list):
        if not allow_legacy:
            raise ConfigError("旧版站点配置必须显式使用 allow_legacy=True 迁移")
        raw_sites = payload
        legacy = True
    elif isinstance(payload, dict):
        if payload.get("schema_version") != SITE_SCHEMA_VERSION:
            raise ConfigError(f"sites.json schema_version 必须是 {SITE_SCHEMA_VERSION}")
        raw_sites = payload.get("sites")
        if not isinstance(raw_sites, list):
            raise ConfigError("sites.json 的 sites 必须是数组")
        legacy = False
    else:
        raise ConfigError("站点配置根节点必须是数组或版本化对象")

    legacy_url_counts: dict[str, int] = {}
    if legacy:
        for item in raw_sites:
            if isinstance(item, dict):
                url = str(item.get("url", "")).strip()
                legacy_url_counts[url] = legacy_url_counts.get(url, 0) + 1
    sites = []
    for index, item in enumerate(raw_sites, start=1):
        legacy_shared_source_id = ""
        if legacy and isinstance(item, dict):
            url = str(item.get("url", "")).strip()
            if legacy_url_counts.get(url, 0) > 1:
                legacy_shared_source_id = _shared_source_id(url)
        sites.append(_parse_site(item, index, legacy, legacy_shared_source_id))
    if not sites:
        raise ConfigError("站点配置不能为空")
    return _validate_unique(site for site in sites if site.enabled)


def build_versioned_site_payload(sites: Iterable[SiteConfig]) -> dict[str, object]:
    items = []
    for site in _validate_unique(sites):
        items.append({
            "site_id": site.site_id,
            "rule_id": site.rule_id,
            "parser_id": site.parser_id,
            "name": site.name,
            "url": site.url,
            "region": site.region.value,
            "shared_source_id": site.shared_source_id,
            "click_first": site.click_first,
            "api_url": site.api_url,
            "enabled": site.enabled,
            "config_version": site.config_version,
        })
    return {"schema_version": SITE_SCHEMA_VERSION, "sites": items}
