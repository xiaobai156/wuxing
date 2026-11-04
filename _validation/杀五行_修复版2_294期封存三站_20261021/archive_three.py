# -*- coding: utf-8 -*-
"""封存三站：sites.json 内联 archived:true（tags 后），缓存 region 与 history 之间插 archived:true。

只改这两处，保留原 history/url/region/tags 与文件编码、换行。
"""
from __future__ import annotations

import io
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\Administrator\Desktop\每天工具\爬虫合集\杀五行_修复版2")
NAMES = ["思念无涯", "爆庄赚钱", "澳爆出料"]


def read(path: Path) -> str:
    return path.read_bytes().decode("utf-8-sig")


def write(path: Path, text: str) -> None:
    data = ("\ufeff" + text).encode("utf-8")
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def archive_sites() -> int:
    path = ROOT / "sites.json"
    text = read(path)
    changed = 0
    for name in NAMES:
        # 定位该站条目
        anchor = f'"name": "{name}"'
        idx = text.find(anchor)
        if idx < 0:
            raise SystemExit(f"sites.json 找不到站点：{name}")
        tags_idx = text.find('"tags": [', idx)
        if tags_idx < 0:
            raise SystemExit(f"{name} 缺少 tags 字段，拒绝猜测插入位置")
        close_idx = text.find("]", tags_idx)
        if close_idx < 0:
            raise SystemExit(f"{name} tags 数组未闭合")
        # 已封存则跳过
        seg_end = text.find("}", close_idx)
        if '"archived"' in text[close_idx:seg_end]:
            print(f"[skip] {name} 已封存")
            continue
        text = text[: close_idx + 1] + ', "archived": true' + text[close_idx + 1:]
        changed += 1
        print(f"[site] {name} -> archived:true")
    if changed:
        write(path, text)
    return changed


def archive_cache() -> int:
    path = ROOT / "recent_10_cache.json"
    text = read(path)
    changed = 0
    for name in NAMES:
        anchor = f'"name": "{name}"'
        idx = text.find(anchor)
        if idx < 0:
            raise SystemExit(f"缓存找不到站点：{name}")
        region_idx = text.find('"region"', idx)
        if region_idx < 0:
            raise SystemExit(f"{name} 缓存缺少 region 字段")
        # region 的值结束位置
        colon = text.find(":", region_idx)
        comma = text.find(",", colon)
        if comma < 0:
            raise SystemExit(f"{name} region 后无逗号，结构异常")
        nxt = text[comma + 1: comma + 40].lstrip()
        if nxt.startswith('"archived"'):
            print(f"[skip] {name} 缓存已封存")
            continue
        insert = ', "archived": true'
        text = text[: comma + 1] + insert + text[comma + 1:]
        changed += 1
        print(f"[cache] {name} -> archived:true")
    if changed:
        write(path, text)
    return changed


def main() -> int:
    a = archive_sites()
    b = archive_cache()
    print(f"改动：sites={a} cache={b}")
    # 校验 JSON 仍可解析
    for name in ("sites.json", "recent_10_cache.json"):
        json.loads((ROOT / name).read_text(encoding="utf-8-sig"))
        print(f"{name} JSON OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
