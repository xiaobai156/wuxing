# -*- coding: utf-8 -*-
"""封存「六玄」：改动边界校验（只读）。"""
import hashlib
import json
import sys
from pathlib import Path

BASE = Path(r"C:\Users\Administrator\Desktop\每天工具\爬虫合集")
PROJ = BASE / "杀五行_修复版2"
FAIL_DIR = BASE / "七类数据统一归纳失败"
NAME, URL, REGION = "六玄", "https://tjetjfr.jocy8-cy4wk-fmpeer.xyz".replace("tjetjfr", "tjetrfr") + ":16677/", "top"
BEFORE = {"sites.json": "6F68961FC1462F49", "recent_10_cache.json": "43E9F4259CD7CEA6"}
sys.path.insert(0, str(PROJ))


def h(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest().upper()[:16]


print("=== 1. 哈希 ===")
for fn, before in BEFORE.items():
    now = h(PROJ / fn)
    print(f"   {fn:24s} {before} -> {now}  {'未变(异常)' if before == now else '已变(预期)'}")

print()
print("=== 2. sites.json ===")
sites = json.loads((PROJ / "sites.json").read_text(encoding="utf-8-sig"))
hit = [s for s in sites if s.get("name") == NAME and s.get("url") == URL]
print(f"   总站点 {len(sites)} | 匹配 {len(hit)} 条")
print(f"   archived={hit[0].get('archived')}")
print(f"   其它字段={{ {', '.join(f'{k}={v!r}' for k, v in hit[0].items() if k != 'archived')} }}")
print(f"   archived 数={sum(1 for s in sites if s.get('archived'))} / active={sum(1 for s in sites if not s.get('archived'))}")
print(f"   行数 {len((PROJ / 'sites.json').read_text(encoding='utf-8-sig').splitlines())}")

print()
print("=== 3. recent_10_cache.json ===")
c = json.loads((PROJ / "recent_10_cache.json").read_text(encoding="utf-8-sig"))
e = next(x for x in c["sites"] if x.get("name") == NAME and x.get("url") == URL)
print(f"   updated_period={c.get('updated_period')} 条目数={len(c['sites'])} archived 条目={sum(1 for x in c['sites'] if x.get('archived'))}")
print(f"   {NAME} archived={e.get('archived')} history 期号={[x['period'] for x in e['history']]}")
print(f"   history[281]={e['history'][0]}")

print()
print("=== 4. 运行时 ===")
from cli.common import build_runtime
rt = build_runtime(str(PROJ / "sites.json"), str(PROJ / "recent_10_cache.json"))
print(f"   站点 {len(rt.sites)} | 含{NAME}: {NAME in {s.name for s in rt.sites}} | archived 残留 {sum(1 for s in rt.sites if getattr(s,'archived',False))}")

print()
print("=== 5. 是否残留该站失败记录 ===")
fs = list(FAIL_DIR.glob("*五行*"))
print(f"   现存的五行失败文件: {[f.name for f in fs] or '无'}")
for f in fs:
    t = f.read_text(encoding="utf-8-sig")
    if NAME in t:
        print(f"   !! {f.name} 含「{NAME}」")

print()
print("=== 6. 残留临时件 ===")
left = [str(p) for pat in ("*.tmp", ".*.tmp", "*.bak") for p in PROJ.rglob(pat)]
print("   " + (", ".join(left) if left else "无 .tmp/.bak 残留 OK"))
