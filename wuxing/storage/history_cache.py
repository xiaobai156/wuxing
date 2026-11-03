from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
from typing import Iterable

from wuxing.config.settings import HISTORY_LIMIT
from wuxing.domain.errors import CacheConflictError, CacheError
from wuxing.domain.enums import Region
from wuxing.domain.models import VALID_WUXING

from .file_lock import exclusive_file_lock


@dataclass(frozen=True)
class HistoryUpdate:
    site_id: str
    name: str
    url: str
    region: Region
    period: int
    wuxing: str
    source_digest: str
    rule_version: str
    captured_at: str

    def __post_init__(self) -> None:
        if self.period <= 0:
            raise ValueError("缓存更新必须包含正期号")
        if self.wuxing not in VALID_WUXING:
            raise ValueError(f"缓存更新不是标准五行：{self.wuxing}")
        if not isinstance(self.region, Region):
            object.__setattr__(self, "region", Region.from_value(self.region))


def empty_history_cache() -> dict[str, object]:
    return {"version": 1, "updated_period": 0, "sites": []}


def _cache_site_identity(site: dict[str, object], index: int) -> tuple[str, str, str]:
    name = str(site.get("name", "")).strip()
    url = str(site.get("url", "")).strip()
    if not name or not url:
        raise CacheError(f"历史缓存第{index}个站点缺少 name 或 url")
    try:
        region = Region.from_value(site.get("region", "")).value
    except ValueError as exc:
        raise CacheError(f"历史缓存第{index}个站点方向无效") from exc
    return name, url, region


def validate_history_cache(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise CacheError("历史缓存根节点必须是对象")
    sites = payload.get("sites")
    if not isinstance(sites, list):
        raise CacheError("历史缓存 sites 必须是数组")
    seen: set[tuple[str, str, str]] = set()
    for index, site in enumerate(sites, start=1):
        if not isinstance(site, dict):
            raise CacheError(f"历史缓存第{index}个站点必须是对象")
        identity = _cache_site_identity(site, index)
        if identity in seen:
            raise CacheError(f"历史缓存站点身份重复：{identity[0]} | {identity[1]} | {identity[2]}")
        seen.add(identity)
        history = site.get("history")
        if not isinstance(history, list):
            raise CacheError(f"历史缓存 {identity[0]} 的 history 必须是数组")
        if len(history) > HISTORY_LIMIT:
            raise CacheError(f"历史缓存 {identity[0]} 最多保留10期，实际{len(history)}期")
        periods: set[int] = set()
        for item in history:
            if not isinstance(item, dict):
                raise CacheError(f"历史缓存 {identity[0]} 的历史项必须是对象")
            period = item.get("period")
            wuxing = item.get("wuxing")
            if isinstance(period, bool) or not isinstance(period, int) or period <= 0:
                raise CacheError(f"历史缓存 {identity[0]} 存在无效期号")
            if period in periods:
                raise CacheError(f"历史缓存 {identity[0]} 的 {period}期重复")
            if wuxing not in VALID_WUXING:
                raise CacheError(f"历史缓存 {identity[0]} 的 {period}期不是标准五行")
            periods.add(period)
    return payload


def apply_history_updates(
    cache: dict[str, object],
    updates: Iterable[HistoryUpdate],
    keep: int = HISTORY_LIMIT,
) -> dict[str, object]:
    validate_history_cache(cache)
    if keep <= 0 or keep > HISTORY_LIMIT:
        raise CacheError(f"缓存历史最多只能保留10期，收到 keep={keep}")
    sites = []
    by_identity: dict[tuple[str, str, str], dict[str, object]] = {}
    for index, raw_site in enumerate(cache["sites"], start=1):
        site = dict(raw_site)
        site.pop("site_id", None)
        identity = _cache_site_identity(site, index)
        sites.append(site)
        by_identity[identity] = site
    maximum_period = int(cache.get("updated_period", 0) or 0)
    for update in updates:
        identity = (update.name.strip(), update.url.strip(), update.region.value)
        site = by_identity.get(identity)
        if site is None:
            site = {
                "name": update.name,
                "url": update.url,
                "region": update.region.value,
                "history": [],
            }
            sites.append(site)
            by_identity[identity] = site
        existing_history = [dict(item) for item in site.get("history", [])]
        existing = next((item for item in existing_history if item["period"] == update.period), None)
        if existing is not None and existing["wuxing"] != update.wuxing:
            raise CacheConflictError(
                f"{update.name} {update.period}期缓存冲突：已有{existing['wuxing']}，新值{update.wuxing}"
            )
        replacement = {
            "period": update.period,
            "wuxing": update.wuxing,
            "captured_at": update.captured_at,
            "source_digest": update.source_digest,
            "rule_version": update.rule_version,
        }
        if existing is None:
            existing_history.append(replacement)
        else:
            existing_history = [replacement if item["period"] == update.period else item for item in existing_history]
        site.update({
            "name": update.name,
            "url": update.url,
            "region": update.region.value,
            "history": sorted(existing_history, key=lambda item: item["period"], reverse=True)[:keep],
        })
        maximum_period = max(maximum_period, update.period)
    result: dict[str, object] = {
        "version": int(cache.get("version", 1) or 1),
        "updated_period": maximum_period,
        "sites": sites,
    }
    return validate_history_cache(result)


class HistoryCacheRepository:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> dict[str, object]:
        if not self.path.exists():
            return empty_history_cache()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CacheError(f"历史缓存读取失败：{exc}") from exc
        return validate_history_cache(payload)

    def apply_updates(self, updates: Iterable[HistoryUpdate]) -> dict[str, object]:
        updates = tuple(updates)
        if not updates:
            return self.load()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with exclusive_file_lock(self.path):
            current = self.load()
            updated = apply_history_updates(current, updates)
            self._atomic_write(updated)
            return self.load()

    def _atomic_write(self, payload: dict[str, object]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8-sig",
                newline="",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
                temp_path = Path(handle.name)
            validate_history_cache(json.loads(temp_path.read_text(encoding="utf-8-sig")))
            os.replace(temp_path, self.path)
        except (OSError, json.JSONDecodeError, CacheError) as exc:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
            if isinstance(exc, CacheError):
                raise
            raise CacheError(f"历史缓存原子写入失败：{exc}") from exc
