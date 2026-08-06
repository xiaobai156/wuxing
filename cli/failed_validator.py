from __future__ import annotations

import argparse

from wuxing.domain.enums import WritePolicy
from wuxing.domain.models import ScrapeRequest
from wuxing.services.batch import BatchService

from .common import build_runtime


def run_validation(period: int, site_ids: tuple[str, ...] | None = None, runtime=None):
    runtime = runtime or build_runtime()
    selected = site_ids or tuple(site.site_id for site in runtime.sites)
    batch = BatchService(runtime.scrape_service).run(
        selected,
        ScrapeRequest(periods=(period,), write_policy=WritePolicy.READ_ONLY),
        progress_callback=lambda current, total, result, elapsed, name: print(
            f"[验证 {current}/{total}] {name} 用时 {elapsed:.2f}s", flush=True
        ),
    )
    for result in batch.results:
        evidence = result.evidence
        print(
            f"{result.site.name} | 抓到期数={'是' if evidence.period_pass else '否'} | "
            f"五行={result.candidate.wuxing if result.candidate else '无'} | "
            f"方向={'通过' if evidence.position_pass else '失败'} | "
            f"锚点/关键词={'通过' if evidence.keyword_pass else '失败'} | "
            f"冲突={'通过' if evidence.conflict_pass else '失败'} | "
            f"原因={result.reason or '通过'}"
        )
    return batch


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="独立失败站点验证，不更新缓存和正式TXT")
    parser.add_argument("period", type=int)
    parser.add_argument("site_ids", nargs="*")
    parser.add_argument("--config")
    parser.add_argument("--cache")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    run_validation(args.period, tuple(args.site_ids) or None, build_runtime(args.config, args.cache))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
