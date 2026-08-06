from __future__ import annotations

import re
from typing import Iterable

from wuxing.domain.models import VALID_WUXING


PERIOD_RE = re.compile(r"(?<!\d)(\d{1,4})\s*期")
WUXING_RE = re.compile(r"([金木水火土]\s*行)")
OCR_SCORE_LIMIT = 100
OCR_MIN_GAP = 8
OCR_PERIOD_SCORE_LIMIT = 80
OCR_PERIOD_MIN_GAP = 5
OCR_PERIOD_SOURCES = frozenset({"pixel_ocr", "dom_text"})


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value)).strip()


def validate_ocr_entries(entries: Iterable[object], target_period: int | None) -> tuple[str, ...]:
    validated: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        try:
            period = int(entry.get("period"))
            score = int(entry.get("wuxingScore"))
            gap = int(entry.get("wuxingGap"))
            independent_period = int(entry.get("independentPeriod"))
            period_score = int(entry.get("periodScore"))
            period_gap = int(entry.get("periodGap"))
            independent_score = int(entry.get("independentWuxingScore"))
        except (TypeError, ValueError):
            continue
        wuxing = _clean(entry.get("wuxing", ""))
        independent_wuxing = _clean(entry.get("independentWuxing", ""))
        raw = _clean(entry.get("raw", ""))
        period_evidence = _clean(entry.get("periodEvidence", ""))
        period_source = _clean(entry.get("periodEvidenceSource", ""))
        period_matches = list(PERIOD_RE.finditer(period_evidence))
        if (
            independent_period != period
            or independent_wuxing != wuxing
            or period_source not in OCR_PERIOD_SOURCES
            or len(period_matches) != 1
            or int(period_matches[0].group(1)) != period
        ):
            continue
        if target_period is not None and period not in {target_period, target_period - 1}:
            continue
        if (
            wuxing not in VALID_WUXING
            or score >= OCR_SCORE_LIMIT
            or independent_score >= 90
            or gap < OCR_MIN_GAP
            or period_score >= OCR_PERIOD_SCORE_LIMIT
            or period_gap < OCR_PERIOD_MIN_GAP
        ):
            continue
        period_match = PERIOD_RE.search(raw)
        wuxing_match = WUXING_RE.search(raw)
        if not period_match or not wuxing_match:
            continue
        if int(period_match.group(1)) != period or _clean(wuxing_match.group(1)) != wuxing:
            continue
        validated.append(raw)
    return tuple(validated)
