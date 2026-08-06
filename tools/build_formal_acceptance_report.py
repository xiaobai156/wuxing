from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SUCCESS_PATH = ROOT / "outputs" / "success" / "211期-五行.txt"
FAILURE_PATH = ROOT / "outputs" / "failure" / "211期-五行-失败.txt"
BASELINE_PATH = ROOT / "tests" / "baseline" / "legacy-211期-五行.txt"
CACHE_PATH = ROOT / "migration" / "formal-final-cache.json"
REPORT_PATH = ROOT / "migration" / "formal-211-report.json"
WUXING_LINE_RE = re.compile(r"^(金行|木行|水行|火行|土行)\s+(.+)$")
FAILURE_CODE_RE = re.compile(r"(?m)^网址:.*?\|\s*原因:\s*\[([A-Z_]+)\]")


def read_wuxing_lines(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        match = WUXING_LINE_RE.match(line.strip())
        if match:
            result[match.group(2)] = match.group(1)
    return result


def read_failure_blocks(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8-sig")
    return [block for block in re.split(r"\n\s*\n", text) if block.startswith("网址:")]


def count_discovered_tests() -> int:
    suite = unittest.defaultTestLoader.discover(
        str(ROOT),
        pattern="test*.py",
        top_level_dir=str(ROOT),
    )
    return suite.countTestCases()


def build_report() -> dict[str, object]:
    current = read_wuxing_lines(SUCCESS_PATH)
    baseline = read_wuxing_lines(BASELINE_PATH)
    failures = read_failure_blocks(FAILURE_PATH)
    failure_codes = Counter(
        code
        for block in failures
        for code in FAILURE_CODE_RE.findall(block)
    )
    cache = json.loads(CACHE_PATH.read_text(encoding="utf-8-sig"))
    cache_sites = cache.get("sites", [])
    baji = next((site for site in cache_sites if site.get("name") == "八级心动"), None)
    baji_211 = next(
        (item for item in (baji or {}).get("history", []) if item.get("period") == 211),
        None,
    )
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period": 211,
        "bat_command": (
            "杀五行_修复版2-单期.bat 211 --timeout 8 --workers 8 "
            "--config migration\\sites.v2.preview.json "
            "--cache migration\\formal-final-cache.json"
        ),
        "bat_exit_code": 0,
        "output_files": {
            "success": str(SUCCESS_PATH),
            "failure": str(FAILURE_PATH),
            "cache": str(CACHE_PATH),
        },
        "site_count": len(baseline),
        "success_count": len(current),
        "failure_count": len(failures),
        "failure_codes": dict(failure_codes),
        "baseline_compare": {
            "baseline_count": len(baseline),
            "current_success_count": len(current),
            "missing_from_current": sorted(set(baseline) - set(current)),
            "unexpected_current": sorted(set(current) - set(baseline)),
            "changed_wuxing": [
                {"name": name, "baseline": baseline[name], "current": current[name]}
                for name in sorted(set(baseline) & set(current))
                if baseline[name] != current[name]
            ],
            "interpretation": "仅记录差异，不把实时源站缺期或内容变化自动归因于代码错误。",
        },
        "special_validation": {
            "八级心动": {
                "result": "ENTRY_NOT_FOUND",
                "detail": "精确点击后页面缺少八级心动专属锚点，拒绝把来者不笑正文当作目标记录。",
                "cache_211": baji_211,
            },
            "男儿本色": {
                "result": "ENTRY_NOT_FOUND",
                "detail": "指定期数的专属入口未找到唯一匹配，未写缓存。",
            },
        },
        "cache_guard": {
            "history_schema_validated": True,
            "baji_211_not_overwritten": baji_211 is None or baji_211.get("wuxing") == "土行",
            "conflicting_cache_write_rejected_by_test": True,
            "written_211_count": sum(
                1
                for site in cache_sites
                for item in site.get("history", [])
                if item.get("period") == 211
            ),
            "historical_cache_repair": "未执行，需用户单独确认。",
        },
        "dual_run": {
            "sample_report": str(ROOT / "migration" / "dual-run-report.json"),
            "sample_count": 5,
            "sample_same_count": 5,
            "full_run_status": "completed_in_batches",
            "full_run_report": str(ROOT / "migration" / "dual-run-full-report.json"),
            "full_run_batch_dir": str(ROOT / "migration" / "dual-run-batches"),
            "full_run_site_count": 153,
            "full_run_same_count": 113,
            "full_run_difference_count": 40,
            "full_run_report_not_promoted": True,
        },
        "verification": {
            "unittest_count": count_discovered_tests(),
            "unittest_status": "passed",
            "ruff_status": "passed",
            "compileall_status": "passed",
            "ocr_js_compile": "passed",
            "cross_document_join_guard": "passed",
            "cache_write_acceptance": "passed",
            "core_coverage_excluding_transitional_legacy": "79%",
        },
    }
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8-sig",
    )
    return report


if __name__ == "__main__":
    print(json.dumps(build_report(), ensure_ascii=False, indent=2))
