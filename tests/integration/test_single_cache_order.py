from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from cli.common import write_text as actual_write_text
from cli.single import build_arg_parser, run_single
from wuxing.domain.enums import Region, SourceKind
from wuxing.domain.models import Candidate, ScrapeResult, SiteConfig, SourceDocument, ValidationEvidence
from wuxing.services.scrape import CacheUpdateReport


class RecordingScrapeService:
    def __init__(self, result, events):
        self.result = result
        self.events = events

    def scrape(self, site_id, _request):
        self.events.append(("scrape", site_id))
        return self.result

    def update_cache(self, _results, _request):
        self.events.append("cache")
        return CacheUpdateReport(
            updated_sites=0,
            errors=("测试站 209期缓存更新未完成：模拟写入失败",),
        )


class SingleCacheOrderTests(unittest.TestCase):
    def test_single_cli_parser_keeps_cache_and_output_switches(self):
        args = build_arg_parser().parse_args([
            "209",
            "--config", "sites.json",
            "--cache", "cache.json",
            "--output", "success",
            "--fail", "failure",
            "--timeout", "30",
            "--workers", "2",
            "--show-browser",
            "--read-only",
        ])
        self.assertEqual(args.period, 209)
        self.assertEqual(args.config, "sites.json")
        self.assertEqual(args.cache, "cache.json")
        self.assertEqual(args.output, "success")
        self.assertEqual(args.fail, "failure")
        self.assertEqual(args.timeout, 30)
        self.assertEqual(args.workers, 2)
        self.assertTrue(args.show_browser)
        self.assertTrue(args.read_only)

    def test_single_writes_txt_before_cache_and_keeps_realtime_success(self):
        site = SiteConfig("site-test", "测试站", "https://example.com/test", Region.TOP, "test.v1")
        result = ScrapeResult.success(
            site=site,
            period=209,
            candidate=Candidate(
                209,
                "木行",
                "fixture-doc",
                0,
                "209期绝杀一行【木行】",
                "test.v1",
            ),
            elapsed_seconds=0.1,
            evidence=ValidationEvidence(True, True, True, True, True, True),
            documents=(SourceDocument(
                "fixture-doc",
                site.url,
                SourceKind.API,
                "209期绝杀一行【木行】",
                0,
            ),),
        )
        events = []
        runtime = SimpleNamespace(
            sites=(site,),
            scrape_service=RecordingScrapeService(result, events),
        )

        with TemporaryDirectory() as directory:
            output_dir = Path(directory) / "success"
            failure_dir = Path(directory) / "failure"
            stdout = StringIO()

            def record_write(path, text):
                events.append(("write", Path(path).name))
                return actual_write_text(path, text)

            with redirect_stdout(stdout), patch("cli.single.write_text", side_effect=record_write):
                run_single(209, runtime, output_dir, failure_dir)

            self.assertEqual(
                events,
                [
                    ("scrape", "site-test"),
                    ("write", "209期-五行.txt"),
                    ("write", "209期-五行-失败.txt"),
                    "cache",
                ],
            )
            self.assertIn("木行 测试站", (output_dir / "209期-五行.txt").read_text(encoding="utf-8-sig"))
            self.assertEqual((failure_dir / "209期-五行-失败.txt").read_text(encoding="utf-8-sig"), "")
            self.assertIn("缓存更新未完成", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
