import unittest

from wuxing.domain.enums import FailureCode, Region
from wuxing.domain.models import ScrapeResult, SiteConfig
from wuxing.reporting.failure import format_failure_file_text, format_failure_line


class ReportingTests(unittest.TestCase):
    def test_failure_line_contains_name_url_direction_and_period(self):
        site = SiteConfig("site-a", "甲站", "https://example.com/a", Region.BOTTOM, "a.v1")
        result = ScrapeResult.failure(
            site=site,
            period=209,
            code=FailureCode.TARGET_NOT_FOUND,
            reason="页面里未找到209期",
            elapsed_seconds=1.0,
        )

        line = format_failure_line(result)

        self.assertEqual(
            line,
            "失败 甲站 https://example.com/a 方向: bottom 期数: 209\n"
            "阶段: 指定期数校验 原因: 页面里未找到209期",
        )

    def test_failure_file_has_one_blank_line_between_sites(self):
        text = format_failure_file_text(["第一站", "第二站"])

        self.assertEqual(text, "第一站\n\n第二站\n")

    def test_failure_line_uses_screenshot_layout_and_failure_stage(self):
        site = SiteConfig("site-a", "甲站", "https://example.com/a", Region.BOTTOM, "a.v1")
        result = ScrapeResult.failure(
            site=site,
            period=216,
            code=FailureCode.POSITION_WINDOW,
            reason="216期不是最后一条专属历史边界行",
            elapsed_seconds=1.0,
        )

        self.assertEqual(
            format_failure_line(result),
            "失败 甲站 https://example.com/a 方向: bottom 期数: 216\n"
            "阶段: 指定期数校验 原因: 216期不是最后一条专属历史边界行",
        )

    def test_failure_file_adds_category_summary_after_entries(self):
        first = ScrapeResult.failure(
            site=SiteConfig("site-a", "甲站", "https://example.com/a", Region.BOTTOM, "a.v1"),
            period=216,
            code=FailureCode.POSITION_WINDOW,
            reason="216期不在底部窗口",
            elapsed_seconds=1.0,
        )
        second = ScrapeResult.failure(
            site=SiteConfig("site-b", "乙站", "https://example.com/b", Region.TOP, "b.v1"),
            period=216,
            code=FailureCode.TARGET_NOT_FOUND,
            reason="页面里未找到216期的有效候选",
            elapsed_seconds=1.0,
        )

        self.assertEqual(
            format_failure_file_text([first, second]),
            "失败 甲站 https://example.com/a 方向: bottom 期数: 216\n"
            "阶段: 指定期数校验 原因: 216期不在底部窗口\n\n"
            "失败 乙站 https://example.com/b 方向: top 期数: 216\n"
            "阶段: 指定期数校验 原因: 页面里未找到216期的有效候选\n\n"
            "失败分类统计\n"
            "方向范围外 1条\n"
            "指定期数缺失 1条\n",
        )

    def test_failure_reason_is_kept_on_the_second_logical_line(self):
        result = ScrapeResult.failure(
            site=SiteConfig("site-a", "甲站", "https://example.com/a", Region.TOP, "a.v1"),
            period=216,
            code=FailureCode.INTERNAL_ERROR,
            reason="第一行\n第二行",
            elapsed_seconds=1.0,
        )

        self.assertEqual(
            format_failure_line(result),
            "失败 甲站 https://example.com/a 方向: top 期数: 216\n"
            "阶段: 内部处理 原因: 第一行 第二行",
        )


if __name__ == "__main__":
    unittest.main()
