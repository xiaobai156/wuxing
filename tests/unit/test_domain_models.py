import unittest

from wuxing.domain.enums import FailureCode, Region, ResultStatus, SourceKind
from wuxing.domain.models import Candidate, ScrapeResult, SiteConfig, SourceDocument, ValidationEvidence


class DomainModelTests(unittest.TestCase):
    def test_region_normalizes_all_supported_aliases(self):
        for value in ("top", "顶部", "上"):
            self.assertIs(Region.from_value(value), Region.TOP)
        for value in ("bottom", "尾部", "底部", "下"):
            self.assertIs(Region.from_value(value), Region.BOTTOM)

    def test_source_document_keeps_provenance_and_stable_digest(self):
        document = SourceDocument(
            document_id="doc-1",
            url="https://example.com/topic/1",
            source_kind=SourceKind.API,
            text="209期精杀一行【木行】",
            order=3,
            parent_document_id="root",
            record_id="article-7",
        )

        self.assertEqual(document.record_id, "article-7")
        self.assertEqual(document.parent_document_id, "root")
        self.assertEqual(len(document.content_sha256), 64)
        self.assertEqual(document.content_sha256, document.content_sha256)

    def test_candidate_rejects_non_standard_wuxing(self):
        with self.assertRaises(ValueError):
            Candidate(
                period=209,
                wuxing="青行",
                source_document_id="doc-1",
                order=0,
                raw="209期【青行】",
                rule_version="rule.v1",
            )

    def test_success_result_requires_one_candidate(self):
        site = SiteConfig("site-1", "测试站", "https://example.com", Region.TOP, "test.v1")
        candidate = Candidate(209, "木行", "doc-1", 0, "209期绝杀一行【木行】", "test.v1")

        result = ScrapeResult.success(
            site=site,
            period=209,
            candidate=candidate,
            elapsed_seconds=1.25,
            evidence=ValidationEvidence(True, True, True, True, True, True),
        )

        self.assertIs(result.status, ResultStatus.SUCCESS)
        self.assertEqual(result.candidate, candidate)
        self.assertIsNone(result.failure_code)

    def test_success_result_requires_complete_validation_evidence(self):
        site = SiteConfig("site-1", "测试站", "https://example.com", Region.TOP, "test.v1")
        candidate = Candidate(209, "木行", "doc-1", 0, "209期绝杀一行【木行】", "test.v1")

        with self.assertRaises(ValueError):
            ScrapeResult.success(site=site, period=209, candidate=candidate, elapsed_seconds=1.25)

    def test_failure_result_cannot_carry_candidate(self):
        site = SiteConfig("site-1", "测试站", "https://example.com", Region.TOP, "test.v1")

        result = ScrapeResult.failure(
            site=site,
            period=209,
            code=FailureCode.TARGET_NOT_FOUND,
            reason="页面里未找到209期",
            elapsed_seconds=2.0,
        )

        self.assertIs(result.status, ResultStatus.FAILURE)
        self.assertIsNone(result.candidate)
        self.assertIs(result.failure_code, FailureCode.TARGET_NOT_FOUND)


if __name__ == "__main__":
    unittest.main()
