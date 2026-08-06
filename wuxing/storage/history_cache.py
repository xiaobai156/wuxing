from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
from typing import Iterable

from wuxing.config.schema import HISTORY_SCHEMA_VERSION
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
        if not self.site_id or self.period <= 0:
            raise ValueError("缓存更新必须包含 site_id 和正期号")
        if self.wuxing not in VALID_WUXING:
            raise ValueError(f"缓存更新不是标准五行：{self.wuxing}")
        if not isinstance(self.region, Region):
            object.__setattr__(self, "region", Region.from_value(self.region))


def empty_history_cache() -> dict[str, object]:
    return {"schema_version": HISTORY_SCHEMA_VERSION, "updated_period": 0, "sites": []}


def validate_history_cache(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise CacheError("历史缓存根节点必须是对象")
    if payload.get("schema_version") != HISTORY_SCHEMA_VERSION:
        raise CacheError(f"历史缓存 schema_version 必须是 {HISTORY_SCHEMA_VERSION}")
    sites = payload.get("sites")
    if not isinstance(sites, list):
        raise CacheError("历史缓存 sites 必须是数组")
    seen: set[str] = set()
    for index, site in enumerate(sites, start=1):
        if not isinstance(site, dict):
            raise CacheError(f"历史缓存第{index}个站点必须是对象")
        site_id = site.get("site_id")
        if not isinstance(site_id, str) or not site_id:
            raise CacheError(f"历史缓存第{index}个站点缺少 site_id")
        if site_id in seen:
            raise CacheError(f"历史缓存 site_id 重复：{site_id}")
        seen.add(site_id)
        history = site.get("history")
        if not isinstance(history, list):
            raise CacheError(f"历史缓存 {site_id} 的 history 必须是数组")
        if len(history) > HISTORY_LIMIT:
            raise CacheError(f"历史缓存 {site_id} 最多保留10期，实际{len(history)}期")
        periods: set[int] = set()
        for item in history:
            if not isinstance(item, dict):
                raise CacheError(f"历史缓存 {site_id} 的历史项必须是对象")
            period = item.get("period")
            wuxing = item.get("wuxing")
            if isinstance(period, bool) or not isinstance(period, int) or period <= 0:
                raise CacheError(f"历史缓存 {site_id} 存在无效期号")
            if period in periods:
                raise CacheError(f"历史缓存 {site_id} 的 {period}期重复")
            if wuxing not in VALID_WUXING:
                raise CacheError(f"历史缓存 {site_id} 的 {period}期不是标准五行")
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
    sites = [dict(site) for site in cache["sites"]]
    by_id = {site["site_id"]: site for site in sites}
    maximum_period = int(cache.get("updated_period", 0) or 0)
    for update in updates:
        site = by_id.get(update.site_id)
        if site is None:
            site = {
                "site_id": update.site_id,
                "name": update.name,
                "url": update.url,
                "region": update.region.value,
                "history": [],
            }
            sites.append(site)
            by_id[update.site_id] = site
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
        "schema_version": HISTORY_SCHEMA_VERSION,
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
