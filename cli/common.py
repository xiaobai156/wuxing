from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
from collections.abc import Iterable

from wuxing.config.settings import (
    DEFAULT_FAILURE_OUTPUT_DIR,
    DEFAULT_OUTPUT_DIR,
)
from wuxing.config.site_loader import load_site_configs
from wuxing.domain.models import SiteConfig, VALID_WUXING
from wuxing.registry import SiteRegistry, build_site_registry
from wuxing.services.scrape import LiveSourceGateway, ScrapeService
from wuxing.storage.file_lock import exclusive_file_lock
from wuxing.storage.history_cache import HistoryCacheRepository
from wuxing.reporting.success import RANKING_HEADER, format_ranking_lines


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUCCESS_DIR = DEFAULT_OUTPUT_DIR
DEFAULT_FAILURE_DIR = DEFAULT_FAILURE_OUTPUT_DIR
RANKING_EXCLUDED_NAMES = frozenset({"澳门第二四不像", "信封论坛", "天青润薮"})


@dataclass(frozen=True)
class Runtime:
    sites: tuple[SiteConfig, ...]
    registry: SiteRegistry
    scrape_service: ScrapeService
    cache_path: Path


def _default_config_path() -> Path:
    preview = PROJECT_ROOT / "migration" / "sites.v2.preview.json"
    return preview if preview.exists() else PROJECT_ROOT / "sites.json"


def _default_cache_path() -> Path:
    preview = PROJECT_ROOT / "migration" / "recent_10_cache.v2.preview.json"
    return preview if preview.exists() else PROJECT_ROOT / "recent_10_cache.json"


def build_runtime(
    config_path: str | Path | None = None,
    cache_path: str | Path | None = None,
) -> Runtime:
    config_path = Path(config_path) if config_path else _default_config_path()
    cache_path = Path(cache_path) if cache_path else _default_cache_path()
    payload = json.loads(config_path.read_text(encoding="utf-8-sig"))
    sites = tuple(
        site
        for site in load_site_configs(config_path, allow_legacy=isinstance(payload, list))
        if not getattr(site, "archived", False)
    )
    registry = build_site_registry(sites)
    repository = HistoryCacheRepository(cache_path)
    return Runtime(
        sites=sites,
        registry=registry,
        scrape_service=ScrapeService(registry, LiveSourceGateway(), repository),
        cache_path=cache_path,
    )


def write_text(path: str | Path, text: str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8-sig")
    return target


def _success_site_name(line: str) -> str | None:
    parts = line.strip().split(maxsplit=1)
    if len(parts) != 2 or parts[0] not in VALID_WUXING:
        return None
    return parts[1]


def append_success_lines(path: str | Path, lines: Iterable[str]) -> Path:
    """Atomically append previously missing success sites without changing old bytes."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    incoming: dict[str, str] = {}
    for raw_line in lines:
        line = raw_line.strip()
        site_name = _success_site_name(line)
        if site_name is None:
            continue
        existing = incoming.get(site_name)
        if existing is not None and existing != line:
            raise ValueError(f"成功追加存在同站冲突：{site_name}")
        incoming[site_name] = line

    with exclusive_file_lock(target):
        original = target.read_bytes() if target.exists() else b""
        original_text = original.decode("utf-8-sig") if original else ""
        ranking_position = original_text.find(RANKING_HEADER)
        base = original[: len(original_text[:ranking_position].encode("utf-8"))] if ranking_position >= 0 else original
        if original and original.startswith(b"\xef\xbb\xbf") and ranking_position >= 0:
            base = b"\xef\xbb\xbf" + original_text[:ranking_position].encode("utf-8")
        existing_text = base.decode("utf-8-sig") if base else ""
        existing_lines = {}
        for raw in existing_text.splitlines():
            site_name = _success_site_name(raw)
            if site_name is not None:
                existing_lines.setdefault(site_name, set()).add(raw.strip())
        for site_name, line in incoming.items():
            if site_name in existing_lines and existing_lines[site_name] != {line}:
                raise ValueError(f"成功追加存在同站冲突：{site_name}")
        existing_sites = set(existing_lines)
        additions = [
            line for site_name, line in incoming.items()
            if site_name not in existing_sites
        ]
        if not additions and ranking_position >= 0:
            return target

        newline = b"\r\n" if b"\r\n" in original else b"\n"
        block = newline.join(line.encode("utf-8") for line in additions) + newline
        if base:
            separator = b"" if base.endswith((b"\r", b"\n")) else newline
            data_payload = base + (separator + block if additions else b"")
        else:
            data_payload = (b"\xef\xbb\xbf" + block) if additions else b""
        data_text = data_payload.decode("utf-8-sig") if data_payload else ""
        try:
            excluded_index = data_text.splitlines().index("重复目录-不参与排行")
            rankable = data_text.splitlines()[:excluded_index]
        except ValueError:
            rankable = data_text.splitlines()
        ranking_lines = format_ranking_lines(rankable)
        payload = data_payload
        if ranking_lines:
            payload += (b"" if not payload or payload.endswith((b"\r", b"\n")) else newline)
            payload += newline.join(line.encode("utf-8") for line in ranking_lines) + newline

        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
                temp_path = Path(handle.name)
            os.replace(temp_path, target)
        except OSError:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
            raise
    return target
