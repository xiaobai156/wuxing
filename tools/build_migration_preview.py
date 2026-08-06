from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from wuxing.config.site_loader import build_versioned_site_payload, load_site_configs  # noqa: E402
from wuxing.storage.migrations import build_legacy_cache_migration_preview  # noqa: E402


MIGRATION = ROOT / "migration"


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8-sig")


def main() -> int:
    sites_path = ROOT / "sites.json"
    cache_path = ROOT / "recent_10_cache.json"
    sites = load_site_configs(sites_path, allow_legacy=True)
    site_payload = build_versioned_site_payload(sites)
    legacy_cache = json.loads(cache_path.read_text(encoding="utf-8-sig"))
    preview = build_legacy_cache_migration_preview(legacy_cache, sites)

    write_json(MIGRATION / "sites.v2.preview.json", site_payload)
    if preview.conflicts:
        cache_written = False
    else:
        write_json(MIGRATION / "recent_10_cache.v2.preview.json", preview.cache)
        cache_written = True
    report = {
        "source_sites": str(sites_path),
        "source_cache": str(cache_path),
        "site_count": len(sites),
        "matched_site_count": len(preview.matched_site_ids),
        "missing_site_count": len(preview.missing_site_ids),
        "orphan_count": len(preview.orphan_labels),
        "conflict_count": len(preview.conflicts),
        "cache_preview_written": cache_written,
        "orphan_labels": list(preview.orphan_labels),
        "conflicts": list(preview.conflicts),
        "missing_site_ids": list(preview.missing_site_ids),
    }
    write_json(MIGRATION / "migration-report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not preview.conflicts else 2


if __name__ == "__main__":
    raise SystemExit(main())
