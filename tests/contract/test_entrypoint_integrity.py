from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class EntrypointIntegrityTests(unittest.TestCase):
    def test_legacy_batch_entries_do_not_bypass_decoupled_cli(self):
        duplicate_bat = (ROOT / "爬虫-每天杀一行 - 检测重复.bat").read_text(encoding="utf-8-sig")
        self.assertNotIn("wuxing_duplicate_flexible.py", duplicate_bat)
        self.assertIn("cli.duplicate", duplicate_bat)

        single_bat = (ROOT / "爬虫-每天杀一行.bat").read_text(encoding="utf-8-sig")
        multi_bat = (ROOT / "爬虫-每天杀一行-多期.bat").read_text(encoding="utf-8-sig")
        self.assertNotIn("wuxing_crawler.py", single_bat)
        self.assertNotIn("wuxing_multi_period.py", multi_bat)
        self.assertIn("cli.single", single_bat)
        self.assertIn("cli.multi", multi_bat)

        crawler_source = (ROOT / "wuxing_crawler.py").read_text(encoding="utf-8-sig")
        duplicate_source = (ROOT / "wuxing_duplicate_flexible.py").read_text(encoding="utf-8-sig")
        self.assertIn("旧版入口已封闭", crawler_source)
        self.assertIn("旧版入口已封闭", duplicate_source)

    def test_ocr_script_no_longer_derives_period_from_row_index(self):
        source = (ROOT / "wuxing/sources/ocr_script.py").read_text(encoding="utf-8")
        self.assertNotIn("targetPeriod - 100", source)
        self.assertNotIn("independentPeriod: targetPeriod", source)
        self.assertIn("periodEvidence", source)


if __name__ == "__main__":
    unittest.main()
