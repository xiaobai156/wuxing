# 只读校验：封存 峥嵘岁月 后的改动边界
from __future__ import annotations

import json
from pathlib import Path

BASE = Path(r"C:\Users\Administrator\Desktop\每天工具\爬虫合集")
PROJ = BASE / "杀五行_修复版2"
VAL = BASE / r"_validation\杀五行_修复版2_274期封存峥嵘岁月_20261001"

NAME = "峥嵘岁月"
URL = "https://hlhl.69281.com/read.php?tid=827"


def diff_lines(before: Path, after: Path, label: str) -> None:
    a = before.read_text(encoding="utf-8-sig").splitlines()
    b = after.read_text(encoding="utf-8-sig").splitlines()
    print(f"\n=== {label} 行差异 ===")
    print(f"行数 {len(a)} -> {len(b)}")
    import difflib

    changes = [row for row in difflib.unified_diff(a, b, lineterm="", n=1)
               if row.startswith(("+", "-")) and not row.startswith(("+++", "---"))]
    for row in changes:
        print("  ", row)
    print("  变更行数:", len(changes))


def main() -> int:
    print("=== 1. sites.json ===")
    sites = json.loads((PROJ / "sites.json").read_text(encoding="utf-8-sig"))
    target = [s for s in sites if s["name"] == NAME and s["url"] == URL]
    print("唯一匹配:", len(target) == 1)
    print("archived:", target[0].get("archived"))
    print("其它字段:", {k: v for k, v in target[0].items() if k != "archived"})
    print("总站点:", len(sites), "| archived:",
          sum(1 for s in sites if s.get("archived")),
          "| active:", sum(1 for s in sites if not s.get("archived")))
    diff_lines(VAL / "sites.封存前.json", PROJ / "sites.json", "sites.json")

    print("\n=== 2. recent_10_cache.json ===")
    cache = json.loads((PROJ / "recent_10_cache.json").read_text(encoding="utf-8-sig"))
    entry = next(s for s in cache["sites"]
                 if s["name"] == NAME and s["url"] == URL and s["region"] == "bottom")
    print("archived:", entry.get("archived"))
    print("history 期数:", [h["period"] for h in entry["history"]])
    print("updated_period:", cache["updated_period"], "| sites:", len(cache["sites"]))
    diff_lines(VAL / "recent_10_cache.封存前.json", PROJ / "recent_10_cache.json",
               "recent_10_cache.json")

    print("\n=== 2b. 缓存逐站一致性（除目标站外必须完全一致）===")
    before = json.loads((VAL / "recent_10_cache.封存前.json").read_text(encoding="utf-8-sig"))
    b_by = {(s["name"], s["url"], s["region"]): s for s in before["sites"]}
    a_by = {(s["name"], s["url"], s["region"]): s for s in cache["sites"]}
    print("键集合一致:", set(b_by) == set(a_by))
    changed_keys = [k for k in b_by if b_by[k] != a_by[k]]
    print("发生变化的站点:", changed_keys)
    print("仅目标站变化:", changed_keys == [(NAME, URL, "bottom")])
    b_hist = {h["period"]: h for h in b_by[(NAME, URL, "bottom")]["history"]}
    a_hist = {h["period"]: h for h in entry["history"]}
    print("目标站 history 未变:", b_hist == a_hist)

    print("\n=== 3. 运行时不含该站 ===")
    import sys

    sys.path.insert(0, str(PROJ))
    from cli.common import build_runtime  # noqa: E402

    runtime = build_runtime()
    names = {s.name for s in runtime.sites}
    print("runtime 站点数:", len(runtime.sites), "| 含峥嵘岁月:", NAME in names)
    print("runtime 中 archived 残留:",
          [s.name for s in runtime.sites if s.archived])

    print("\n=== 4. 失败清单 ===")
    failure = BASE / r"七类数据统一归纳失败\274期-五行-失败.txt"
    print("274 失败文件存在:", failure.exists())

    print("\n=== 5. 成功 TXT 未被改动 ===")
    import hashlib

    success = BASE / r"七类数据统一归纳\274期-五行.txt"
    before_hash = hashlib.sha256((VAL / "274期-五行.封存前.txt").read_bytes()).hexdigest()
    after_hash = hashlib.sha256(success.read_bytes()).hexdigest()
    print("封存前:", before_hash[:16], "| 封存后:", after_hash[:16],
          "| 一致:", before_hash == after_hash)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
