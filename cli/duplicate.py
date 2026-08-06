from __future__ import annotations

import argparse
import json

from wuxing.services.duplicate import DuplicateService
from wuxing.storage.history_cache import HistoryCacheRepository

from .common import PROJECT_ROOT


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="只使用 recent_10_cache.json 的重复检测")
    parser.add_argument("name")
    parser.add_argument("history_json", help="{期号: 五行} JSON 文件")
    parser.add_argument("--cache", default=str(PROJECT_ROOT / "migration" / "recent_10_cache.v2.preview.json"))
    args = parser.parse_args(argv)
    history = json.loads(open(args.history_json, encoding="utf-8-sig").read())
    history = {int(period): str(wuxing) for period, wuxing in history.items()}
    report = DuplicateService(HistoryCacheRepository(args.cache)).compare_history(args.name, history)
    print(json.dumps(report.__dict__, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
