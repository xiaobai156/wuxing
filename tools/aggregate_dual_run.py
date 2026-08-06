from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cli.common import build_runtime  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="汇总修复版2与旧版的全站只读双跑报告")
    parser.add_argument("--input-dir", type=Path, default=ROOT / "migration" / "dual-run-batches")
    parser.add_argument("--output", type=Path, default=ROOT / "migration" / "dual-run-full-report.json")
    parser.add_argument("--period", type=int, default=211)
    args = parser.parse_args()

    input_dir = args.input_dir if args.input_dir.is_absolute() else ROOT / args.input_dir
    output = args.output if args.output.is_absolute() else ROOT / args.output
    files = sorted(input_dir.glob("*.json"))
    expected = tuple(site.name for site in build_runtime().sites)
    rows: list[dict[str, object]] = []
    batch_errors: list[str] = []
    for path in files:
        try:
            report = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            batch_errors.append(f"{path.name}: 无法读取 JSON：{type(exc).__name__}: {exc}")
            continue
        if report.get("period") != args.period:
            batch_errors.append(f"{path.name}: 期数不匹配")
        if not report.get("complete"):
            batch_errors.append(f"{path.name}: 本批未完整执行")
        rows.extend(report.get("rows", ()))

    seen: set[str] = set()
    duplicates: list[str] = []
    for row in rows:
        name = str(row.get("name", ""))
        if name in seen:
            duplicates.append(name)
        seen.add(name)
    expected_set = set(expected)
    actual_set = {str(row.get("name", "")) for row in rows}
    missing = sorted(expected_set - actual_set)
    unexpected = sorted(actual_set - expected_set)
    differences = [row for row in rows if not row.get("same_result")]
    report = {
        "period": args.period,
        "cache_written": False,
        "formal_txt_written": False,
        "batch_count": len(files),
        "expected_site_count": len(expected),
        "row_count": len(rows),
        "same_count": sum(1 for row in rows if row.get("same_result")),
        "difference_count": len(differences),
        "batch_errors": batch_errors,
        "duplicate_names": sorted(set(duplicates)),
        "missing_names": missing,
        "unexpected_names": unexpected,
        "differences": differences,
        "complete": (
            not batch_errors
            and not duplicates
            and not missing
            and not unexpected
            and len(rows) == len(expected)
        ),
        "interpretation": "差异只记录新旧行为，不自动覆盖缓存或正式输出；差异归因需逐项证据审核。",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8-sig")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
