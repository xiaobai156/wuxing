import unittest

from wuxing.sources.ocr import validate_ocr_entries


class OcrSourceTests(unittest.TestCase):
    def valid_entry(self) -> dict:
        return {
            "period": 209,
            "wuxing": "木行",
            "wuxingScore": 40,
            "wuxingGap": 20,
        "independentPeriod": 209,
        "periodEvidence": "209期",
        "periodEvidenceSource": "pixel_ocr",
        "periodScore": 20,
        "periodGap": 15,
        "independentWuxing": "木行",
            "independentWuxingScore": 35,
            "raw": "209期【图片识别】【木行】",
        }

    def test_ocr_requires_independent_period_and_wuxing_match(self):
        entry = self.valid_entry()
        self.assertEqual(validate_ocr_entries([entry], 209), ("209期【图片识别】【木行】",))

        entry["independentWuxing"] = "火行"
        self.assertEqual(validate_ocr_entries([entry], 209), ())

        entry = self.valid_entry()
        entry.pop("periodEvidence")
        self.assertEqual(validate_ocr_entries([entry], 209), ())

    def test_ocr_rejects_synthesized_period_evidence(self):
        entry = self.valid_entry()
        entry["periodEvidence"] = "209期"
        entry["periodEvidenceSource"] = "row_index"
        self.assertEqual(validate_ocr_entries([entry], 209), ())

        entry = self.valid_entry()
        entry["periodEvidence"] = "208期"
        self.assertEqual(validate_ocr_entries([entry], 209), ())

    def test_ocr_rejects_low_gap_and_wrong_target_period(self):
        entry = self.valid_entry()
        entry["wuxingGap"] = 2
        self.assertEqual(validate_ocr_entries([entry], 209), ())
        entry = self.valid_entry()
        entry["period"] = 207
        entry["independentPeriod"] = 207
        entry["raw"] = "207期【图片识别】【木行】"
        self.assertEqual(validate_ocr_entries([entry], 209), ())


if __name__ == "__main__":
    unittest.main()
