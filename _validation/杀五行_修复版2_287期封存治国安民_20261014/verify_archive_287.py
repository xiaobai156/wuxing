# 只读校验：封存 治国安民 之后
import hashlib
import json
import sys
from pathlib import Path

PROJ = Path(r"C:\Users\Administrator\Desktop\每天工具\爬虫合集\杀五行_修复版2")
BASE = PROJ.parent
sys.path.insert(0, str(PROJ))
from cli.common import build_runtime  # noqa: E402

SITES = PROJ / "sites.json"
CACHE = PROJ / "recent_10_cache.json"
SUCC = BASE / "七类数据统一归纳" / "287期-五行.txt"
FAIL = BASE / "七类数据统一归纳失败" / "287期-五行-失败.txt"
NAME = "治国安民"


def sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest().upper()[:16]


sites = json.loads(SITES.read_text(encoding="utf-8-sig"))
print("sites.json 行数:", len(SITES.read_text(encoding="utf-8-sig").splitlines()), "| sha:", sha(SITES))
print("  站点总数:", len(sites), "| archived:", sum(1 for s in sites if s.get("archived")), "| active:", sum(1 for s in sites if not s.get("archived")))
entry = [s for s in sites if s.get("name") == NAME]
print("  目标条目:", entry)

cache = json.loads(CACHE.read_text(encoding="utf-8-sig"))
print("cache 条目:", len(cache["sites"]), "| archived:", sum(1 for e in cache["sites"] if e.get("archived")), "| updated_period:", cache["updated_period"], "| sha:", sha(CACHE))
ce = [e for e in cache["sites"] if e.get("name") == NAME][0]
print("  目标条目 archived:", ce.get("archived"), "| 字段:", list(ce.keys()))
print("  history 期号:", [h["period"] for h in ce["history"]], "| 期数:", len(ce["history"]))

runtime = build_runtime(SITES, CACHE)
print("build_runtime 站点数:", len(runtime.sites), "| 含治国安民:", any(s.name == NAME for s in runtime.sites), "| archived 残留:", sum(1 for s in runtime.sites if getattr(s, "archived", False)))

print("287期-五行.txt 未动:", sha(SUCC) == "41AE8ABC8F48C065", "| sha:", sha(SUCC), "| 存在:", SUCC.exists())
print("287期-五行-失败.txt 已删除:", not FAIL.exists())
for pat in ("*.tmp", "*.bak"):
    hits = [str(p) for p in list(BASE.glob(pat)) + list(PROJ.glob(pat)) if p.is_file()]
    print(f"  {pat}:", len(hits))
