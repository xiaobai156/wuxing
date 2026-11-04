# -*- coding: utf-8 -*-
"""285 期封存「彻头彻尾 + 汝嫣澍茵」结果校验（只读）。"""
import hashlib
import json
import sys
from pathlib import Path

BASE = Path(r"C:\Users\Administrator\Desktop\每天工具\爬虫合集")
PROJ = BASE / "杀五行_修复版2"
VAL = BASE / "_validation" / "杀五行_修复版2_285期封存彻头彻尾汝嫣澍茵_20261012"
OK = BASE / "七类数据统一归纳"
FAIL = BASE / "七类数据统一归纳失败"
sys.path.insert(0, str(PROJ))
from cli.common import build_runtime  # noqa: E402

TARGETS = ("彻头彻尾", "汝嫣澍茵")


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest().upper()[:16]


print("=== 1. 哈希 ===")
for label, cur, pre in (
    ("sites.json", PROJ / "sites.json", VAL / "sites.封存前.json"),
    ("recent_10_cache.json", PROJ / "recent_10_cache.json", VAL / "recent_10_cache.封存前.json"),
    ("285期-五行-失败.txt", FAIL / "285期-五行-失败.txt", VAL / "285期-五行-失败.封存前.txt"),
    ("285期-五行.txt", OK / "285期-五行.txt", VAL / "285期-五行.封存前.txt"),
):
    same = sha(cur) == sha(pre)
    print(f"  {label}: 前 {sha(pre)} -> 后 {sha(cur)} ({Path(cur).stat().st_size} B)  {'未变' if same else '已变'}")

print("\n=== 2. sites.json ===")
cfg = json.loads((PROJ / "sites.json").read_text(encoding="utf-8-sig"))
items = cfg if isinstance(cfg, list) else cfg["sites"]
arch = [s for s in items if s.get("archived")]
print(f"  顶层 list  站点 {len(items)}  archived {len(arch)}  active {len(items) - len(arch)}")
for t in TARGETS:
    e = next(s for s in items if s["name"] == t)
    print(f"  {t}: archived={e.get('archived')}  url={e['url'][:60]}  字段={list(e)}")
pre_cfg = json.loads((VAL / "sites.封存前.json").read_text(encoding="utf-8-sig"))
pre_items = pre_cfg if isinstance(pre_cfg, list) else pre_cfg["sites"]
diff = [s["name"] for a, s in zip(pre_items, items) if a != s]
print(f"  与封存前 diff 条目: {diff}（应仅两站，且顺序/条数不变）")

print("\n=== 3. recent_10_cache.json ===")
cur = json.loads((PROJ / "recent_10_cache.json").read_text(encoding="utf-8-sig"))
pre = json.loads((VAL / "recent_10_cache.封存前.json").read_text(encoding="utf-8-sig"))
print(f"  updated_period {pre['updated_period']} -> {cur['updated_period']}；条目 {len(pre['sites'])} -> {len(cur['sites'])}")
print(f"  站点集合一致: {[x['name'] for x in pre['sites']] == [x['name'] for x in cur['sites']]}")
changed = []
for a, b in zip(pre["sites"], cur["sites"]):
    if a != b:
        changed.append((b["name"], a.get("archived"), b.get("archived"), a.get("history") == b.get("history")))
print(f"  变动条目 {len(changed)}:")
for c in changed:
    print(f"    {c[0]}: archived {c[1]} -> {c[2]}  history 未变={c[3]}")
pa = sum(1 for x in pre["sites"] if x.get("archived"))
ca = sum(1 for x in cur["sites"] if x.get("archived"))
print(f"  archived 条目 {pa} -> {ca}")

print("\n=== 4. 运行时 ===")
rt = build_runtime()
names = [s.name for s in rt.sites]
print(f"  build_runtime 站点数: {len(rt.sites)}")
for t in TARGETS:
    print(f"    {t} 在运行时中: {t in names}")
print("  archived 残留站点:", [s.name for s in rt.sites if getattr(s, 'archived', False)])

print("\n=== 5. 失败 TXT ===")
fp = FAIL / "285期-五行-失败.txt"
t = fp.read_text(encoding="utf-8-sig")
recs = [l for l in t.splitlines() if l.lstrip().startswith("失败")]
print(f"  {fp.name}: {fp.stat().st_size} B  sha {sha(fp)}  记录 {len(recs)}")
for l in t.splitlines():
    if l.strip():
        print("   ", l.strip()[:140])

print("\n=== 6. 成功 TXT 未改 ===")
print(f"  285期-五行.txt sha {sha(OK / '285期-五行.txt')} (应 A77B07318C496A03)")

print("\n=== 7. 临时/备份残留 ===")
for pat in ("*.tmp", "*.bak"):
    for d in (PROJ, OK, FAIL, VAL):
        h = list(d.glob(pat))
        if h:
            print(f"  {d.name}/{pat}: {[x.name for x in h]}")
print("  扫描完成")
