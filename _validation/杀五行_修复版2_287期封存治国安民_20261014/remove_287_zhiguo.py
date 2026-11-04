# 封存 治国安民：从 287 期失败清单中移除该站记录（用项目自身 _remove_records：锁 + sha256 CAS + 原子替换）
import hashlib
import sys
from pathlib import Path

PROJ = Path(r"C:\Users\Administrator\Desktop\每天工具\爬虫合集\杀五行_修复版2")
BASE = PROJ.parent
sys.path.insert(0, str(PROJ))
import cli.retry_failed as rf  # noqa: E402

FAIL = BASE / "七类数据统一归纳失败" / "287期-五行-失败.txt"
raw, records = rf._read_snapshot(FAIL)
print("before:", len(raw), "B | 记录:", [(r["name"], r["period"]) for r in records])
target = next(r for r in records if r["name"] == "治国安民")
identity = rf._identity(target)
expected = rf._hash_bytes(raw)
new_hash = rf._remove_records(FAIL, identity, expected)
raw2, records2 = rf._read_snapshot(FAIL)
print("after:", len(raw2), "B | sha:", new_hash[:16].upper(), "| 剩余记录:", [(r["name"], r["period"]) for r in records2])
