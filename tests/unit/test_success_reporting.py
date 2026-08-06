import unittest

from wuxing.domain.enums import Region
from wuxing.domain.models import Candidate, ScrapeResult, SiteConfig, ValidationEvidence
from wuxing.reporting.success import format_slow_site_lines, format_success_file_lines


def success(name: str, elapsed: float) -> ScrapeResult:
    site = SiteConfig(name, name, f"https://{name}.example", Region.TOP, f"{name}.v1")
    candidate = Candidate(209, "木行", f"doc-{name}", 0, "209期", "v1")
    return ScrapeResult.success(
        site,
        209,
        candidate,
        elapsed,
        evidence=ValidationEvidence(True, True, True, True, True, True),
    )


class SuccessReportingTests(unittest.TestCase):
    def test_slow_sites_are_sorted_descending(self):
        lines = format_slow_site_lines((success("慢站1", 1.0), success("慢站2", 4.0), success("慢站3", 2.0)))
        self.assertEqual(lines[1].split(" | ")[0], "1. 慢站2")
        self.assertEqual(lines[2].split(" | ")[0], "2. 慢站3")

    def test_success_file_keeps_excluded_section_and_slow_section(self):
        lines = format_success_file_lines((success("普通站", 1.0), success("信封论坛", 5.0)), frozenset({"信封论坛"}))
        self.assertIn("重复目录-不参与排行", lines)
        self.assertIn("慢站耗时统计 Top 2：", lines)


if __name__ == "__main__":
    unittest.main()
