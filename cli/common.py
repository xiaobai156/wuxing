from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from wuxing.config.site_loader import load_site_configs
from wuxing.domain.models import SiteConfig
from wuxing.registry import SiteRegistry, build_site_registry
from wuxing.services.scrape import LiveSourceGateway, ScrapeService
from wuxing.storage.history_cache import HistoryCacheRepository


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUCCESS_DIR = PROJECT_ROOT / "outputs" / "success"
DEFAULT_FAILURE_DIR = PROJECT_ROOT / "outputs" / "failure"
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
    sites = tuple(load_site_configs(config_path, allow_legacy=isinstance(payload, list)))
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
