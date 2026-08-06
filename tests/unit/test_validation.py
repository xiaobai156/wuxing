import unittest

from wuxing.domain.enums import Region, SourceKind
from wuxing.domain.models import Candidate, SiteConfig, SourceDocument
from wuxing.validation.authority import validate_authority_boundary
from wuxing.validation.conflict import detect_period_conflict
from wuxing.validation.position import evaluate_position_window
from wuxing.validation.result import validate_scrape_candidates


def site(region: Region = Region.TOP) -> SiteConfig:
    return SiteConfig(
        site_id="site-test",
        name="测试站",
        url="https://example.com/topic/1",
        region=region,
        rule_id="site.test.v1",
    )


def document(document_id: str = "doc-1", record_id: str | None = None) -> SourceDocument:
    return SourceDocument(
        document_id=document_id,
        url="https://example.com/topic/1",
        source_kind=SourceKind.PAGE,
        text="正文",
        order=0,
        record_id=record_id,
    )


def candidate(
    period: int,
    wuxing: str,
    order: int,
    document_id: str = "doc-1",
    record_id: str | None = None,
    raw: str | None = None,
) -> Candidate:
    raw = raw or f"{period}期绝杀一行【{wuxing}】"
    anchor = "绝杀一行" if "绝杀一行" in raw else ""
    return Candidate(
        period=period,
        wuxing=wuxing,
        source_document_id=document_id,
        order=order,
        raw=raw,
        rule_version="site.test.v1@config1",
        record_id=record_id,
        anchor=anchor,
        keyword=anchor,
    )


class PositionValidationTests(unittest.TestCase):
    def test_top_uses_first_three_candidates(self):
        candidates = tuple(candidate(period, "木行", index) for index, period in enumerate((209, 208, 207, 206)))
        decision = evaluate_position_window(candidates, Region.TOP, 206)
        self.assertFalse(decision.passed)
        self.assertEqual(decision.window_orders, (0, 1, 2))

    def test_bottom_uses_last_three_candidates(self):
        candidates = tuple(candidate(period, "木行", index) for index, period in enumerate((209, 208, 207, 206)))
        decision = evaluate_position_window(candidates, Region.BOTTOM, 209)
        self.assertFalse(decision.passed)
        self.assertEqual(decision.window_orders, (1, 2, 3))

    def test_target_in_window_passes(self):
        candidates = tuple(candidate(period, "木行", index) for index, period in enumerate((209, 208, 207, 206)))
        self.assertTrue(evaluate_position_window(candidates, Region.BOTTOM, 207).passed)


class ConflictValidationTests(unittest.TestCase):
    def test_same_period_different_wuxing_is_conflict(self):
        decision = detect_period_conflict((candidate(209, "木行", 0), candidate(209, "火行", 1)), 209)
        self.assertTrue(decision.conflict)
        self.assertIn("木行", decision.wuxing_values)

    def test_same_period_duplicate_wuxing_is_not_silently_collapsed(self):
        decision = detect_period_conflict((candidate(209, "木行", 0), candidate(209, "木行", 1)), 209)
        self.assertTrue(decision.duplicate)
        self.assertFalse(decision.conflict)


class AuthorityValidationTests(unittest.TestCase):
    def test_candidate_must_belong_to_selected_document(self):
        result = validate_authority_boundary(
            (document("doc-1"),),
            candidate(209, "木行", 0, document_id="doc-other"),
        )
        self.assertFalse(result.passed)

    def test_record_id_must_match_selected_document(self):
        result = validate_authority_boundary(
            (document("doc-1", record_id="record-a"),),
            candidate(209, "木行", 0, record_id="record-b"),
        )
        self.assertFalse(result.passed)


class ResultValidationTests(unittest.TestCase):
    def test_full_validation_rejects_conflict_before_success(self):
        docs = (document(),)
        result = validate_scrape_candidates(
            site(),
            209,
            (candidate(209, "木行", 0), candidate(209, "火行", 1)),
            docs,
        )
        self.assertFalse(result.passed)
        self.assertEqual(result.failure_code, "TARGET_CONFLICT")

    def test_full_validation_returns_unique_candidate(self):
        docs = (document(),)
        result = validate_scrape_candidates(
            site(),
            209,
            (candidate(209, "木行", 0),),
            docs,
        )
        self.assertTrue(result.passed)
        self.assertEqual(result.candidate.wuxing, "木行")

    def test_position_window_is_checked_before_outside_target_conflict(self):
        docs = (document(),)
        result = validate_scrape_candidates(
            site(),
            206,
            (
                candidate(209, "木行", 0),
                candidate(208, "水行", 1),
                candidate(207, "火行", 2),
                candidate(206, "金行", 3),
                candidate(206, "土行", 4),
            ),
            docs,
        )
        self.assertFalse(result.passed)
        self.assertEqual(result.failure_code, "POSITION_WINDOW")
        self.assertFalse(result.evidence.position_pass)

    def test_candidate_without_target_anchor_is_rejected(self):
        docs = (document(),)
        result = validate_scrape_candidates(
            site(),
            209,
            (candidate(209, "木行", 0, raw="209期【木行】"),),
            docs,
        )
        self.assertFalse(result.passed)
        self.assertEqual(result.failure_code, "KEYWORD_MISMATCH")
        self.assertFalse(result.evidence.keyword_pass)

    def test_dot_separated_one_row_anchor_is_accepted(self):
        docs = (document(),)
        target = Candidate(
            period=209,
            wuxing="木行",
            source_document_id="doc-1",
            order=0,
            raw="209期绝杀1.行【木行】",
            rule_version="site.test.v1@config1",
            anchor="绝杀1.行",
            keyword="绝杀1.行",
        )

        result = validate_scrape_candidates(site(), 209, (target,), docs)

        self.assertTrue(result.passed)

    def test_logical_document_rejects_cross_component_candidate(self):
        logical = SourceDocument(
            "logical-1",
            "https://example.com/topic/1",
            SourceKind.PAGE,
            "标题\n209期绝杀一行【木行】",
            0,
            metadata=(
                ("logical_block", "explicit"),
                ("component_match_texts", '["标题", "209期绝杀一行【木行】"]'),
            ),
        )
        result = validate_scrape_candidates(
            site(),
            209,
            (candidate(209, "木行", 0, document_id="logical-1", raw="标题 209期绝杀一行【木行】"),),
            (logical,),
        )
        self.assertFalse(result.passed)
        self.assertEqual(result.failure_code, "AUTHORITY_NOT_UNIQUE")


if __name__ == "__main__":
    unittest.main()
