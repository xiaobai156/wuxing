from __future__ import annotations

from wuxing.domain.models import BatchResult


def format_progress(current: int, total: int, batch: BatchResult, elapsed_seconds: float, site_name: str) -> str:
    percent = int(current * 100 / total) if total else 100
    return (
        f"[进度 {current}/{total} {percent}% 成功 {len(batch.successes)} "
        f"失败 {len(batch.failures)} 用时 {elapsed_seconds:.1f}s] 当前: {site_name}"
    )

