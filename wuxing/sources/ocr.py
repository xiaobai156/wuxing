from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import io
import math
import re
from threading import RLock
from typing import Any

from wuxing.domain.errors import FetchError
from wuxing.domain.models import VALID_WUXING


PERIOD_RE = re.compile(r"(?<!\d)(\d{1,4})\s*期")
WUXING_RE = re.compile(r"([金木水火土]\s*行)")
PADDLE_OCR_ENGINE = "paddleocr_cpu"
OCR_MIN_CONFIDENCE = 0.80
PADDLE_OCR_INSTALL_MESSAGE = (
    "PaddleOCR v3 CPU 依赖或模型初始化不可用，请使用 Python 3.10 安装 PaddleOCR CPU 依赖后重试。"
)
PADDLE_OCR_RUNTIME_MESSAGE = "PaddleOCR v3 CPU 图像、识别结果或推理过程无效，已拒绝。"

_MISSING = object()
_PADDLE_OCR_LOCK = RLock()
_PADDLE_OCR_INSTANCE: object | None = None


@dataclass(frozen=True)
class _OcrBox:
    text: str
    score: float
    left: float
    top: float
    right: float
    bottom: float

    @property
    def center_y(self) -> float:
        return (self.top + self.bottom) / 2.0

    @property
    def height(self) -> float:
        return max(1.0, self.bottom - self.top)


@dataclass(frozen=True)
class _RowCandidate:
    period: int
    wuxing: str
    raw: str
    confidence: float


@dataclass(frozen=True)
class _PairedCandidate:
    primary: _RowCandidate
    independent: _RowCandidate


class _MalformedPaddleResult(ValueError):
    pass


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value)).strip()


def _normalize_wuxing(value: object) -> str:
    normalized = re.sub(r"\s+", "", _clean(value))
    return normalized if normalized in VALID_WUXING else ""


def _coerce_period(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, float) and not value.is_integer():
        return None
    try:
        period = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return period if period > 0 else None


def _coerce_confidence(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        confidence = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
        return None
    return confidence


def _allowed_periods(target_period: int | None) -> frozenset[int] | None:
    if target_period is None:
        return None
    target = _coerce_period(target_period)
    if target is None:
        return frozenset()
    # 只接受指定期，禁止把前一期值带进当期候选（跨期借值）。
    return frozenset({target})


def _entry_value(entry: Mapping[object, object], *keys: str) -> object:
    for key in keys:
        if key in entry:
            return entry[key]
    return _MISSING


def _canonical_raw(raw: object, period: int, wuxing: str) -> str | None:
    if not isinstance(raw, str):
        return None
    cleaned = _clean(raw)
    period_matches = list(PERIOD_RE.finditer(cleaned))
    wuxing_matches = list(WUXING_RE.finditer(cleaned))
    if len(period_matches) != 1 or len(wuxing_matches) != 1:
        return None
    if _coerce_period(period_matches[0].group(1)) != period:
        return None
    if _normalize_wuxing(wuxing_matches[0].group(1)) != wuxing:
        return None

    # Keep the OCR row text while normalizing only the evidenced tokens so the
    # downstream parser always sees exactly ``<period>期`` and one standard row.
    normalized = PERIOD_RE.sub(f"{period}期", cleaned, count=1)
    normalized = WUXING_RE.sub(wuxing, normalized, count=1)
    if (
        len(list(PERIOD_RE.finditer(normalized))) != 1
        or len(list(WUXING_RE.finditer(normalized))) != 1
    ):
        return None
    return normalized


def _validated_entry(entry: object, target_period: int | None) -> tuple[int, str, str, str] | None:
    if not isinstance(entry, Mapping):
        return None
    if entry.get("engine") != PADDLE_OCR_ENGINE:
        return None

    period = _coerce_period(entry.get("period"))
    independent_period = _coerce_period(
        _entry_value(entry, "independent_period", "independentPeriod")
    )
    wuxing = _normalize_wuxing(entry.get("wuxing", ""))
    independent_wuxing = _normalize_wuxing(
        _entry_value(entry, "independent_wuxing", "independentWuxing")
    )
    primary_confidence = _coerce_confidence(
        _entry_value(entry, "primary_confidence", "primaryConfidence", "confidence")
    )
    independent_confidence = _coerce_confidence(
        _entry_value(
            entry,
            "independent_confidence",
            "independentConfidence",
        )
    )
    primary_raw = _entry_value(entry, "primary_raw", "primaryRaw", "raw")
    independent_raw = _entry_value(entry, "independent_raw", "independentRaw")
    allowed = _allowed_periods(target_period)
    if (
        period is None
        or independent_period is None
        or not wuxing
        or not independent_wuxing
        or primary_confidence is None
        or independent_confidence is None
        or primary_raw is _MISSING
        or independent_raw is _MISSING
        or independent_period != period
        or independent_wuxing != wuxing
        or primary_confidence < OCR_MIN_CONFIDENCE
        or independent_confidence < OCR_MIN_CONFIDENCE
        or allowed is not None
        and period not in allowed
    ):
        return None

    normalized_primary_raw = _canonical_raw(primary_raw, period, wuxing)
    normalized_independent_raw = _canonical_raw(independent_raw, period, wuxing)
    if normalized_primary_raw is None or normalized_independent_raw is None:
        return None
    return period, wuxing, normalized_primary_raw, normalized_independent_raw


def validate_ocr_entries(entries: Iterable[object], target_period: int | None) -> tuple[str, ...]:
    """Accept only normalized, independent PaddleOCR evidence rows.

    Validation intentionally does not read the former pixel-distance/source fields.
    Exact duplicate evidence signatures are collapsed. Different wuxing or
    normalized primary/independent raw evidence remains ambiguous and is omitted.
    """

    validated: list[tuple[int, str, str, str]] = []
    for entry in entries:
        candidate = _validated_entry(entry, target_period)
        if candidate is not None:
            validated.append(candidate)

    representatives: dict[int, tuple[str, str, str]] = {}
    ambiguous: set[int] = set()
    for period, wuxing, primary_raw, independent_raw in validated:
        signature = (wuxing, primary_raw, independent_raw)
        if period in ambiguous:
            continue
        previous = representatives.get(period)
        if previous is None:
            representatives[period] = signature
        elif previous != signature:
            ambiguous.add(period)
            representatives.pop(period, None)

    returned_periods: set[int] = set()
    result: list[str] = []
    for period, wuxing, primary_raw, independent_raw in validated:
        signature = (wuxing, primary_raw, independent_raw)
        if period in ambiguous or period in returned_periods:
            continue
        if representatives.get(period) == signature:
            result.append(primary_raw)
            returned_periods.add(period)
    return tuple(result)


def _object_value(value: object, key: str) -> object:
    if isinstance(value, Mapping):
        return value.get(key, _MISSING)
    try:
        return getattr(value, key)
    except (AttributeError, TypeError):
        return _MISSING


def _payload(value: object, depth: int = 0) -> object | None:
    if depth > 4:
        return None
    texts = _object_value(value, "rec_texts")
    scores = _object_value(value, "rec_scores")
    rec_polys = _object_value(value, "rec_polys")
    dt_polys = _object_value(value, "dt_polys")
    if (
        texts is not _MISSING
        and scores is not _MISSING
        and (rec_polys is not _MISSING or dt_polys is not _MISSING)
    ):
        return value
    nested = _object_value(value, "res")
    if nested is not _MISSING and nested is not value:
        return _payload(nested, depth + 1)
    return None


def _is_iterable_result(value: object) -> bool:
    return not isinstance(value, (str, bytes, bytearray, Mapping)) and isinstance(value, Iterable)


def _result_payloads(value: object) -> list[object]:
    direct = _payload(value)
    if direct is not None:
        return [direct]
    nested = _object_value(value, "res")
    if nested is not _MISSING and nested is not value and _is_iterable_result(nested):
        return _result_payloads(nested)
    if not _is_iterable_result(value):
        raise _MalformedPaddleResult("PaddleOCR result has no complete recognition payload")
    try:
        items = list(value)
    except Exception as exc:
        raise _MalformedPaddleResult("PaddleOCR result is not iterable") from exc
    if not items:
        return []
    payloads: list[object] = []
    for item in items:
        item_payload = _payload(item)
        if item_payload is None:
            raise _MalformedPaddleResult("PaddleOCR result item has no complete recognition payload")
        payloads.append(item_payload)
    return payloads


def _sequence(value: object, field: str) -> list[object]:
    if isinstance(value, (str, bytes, bytearray, Mapping)):
        raise _MalformedPaddleResult(f"PaddleOCR {field} is not a sequence")
    try:
        if hasattr(value, "tolist"):
            value = value.tolist()
        return list(value)
    except Exception as exc:
        raise _MalformedPaddleResult(f"PaddleOCR {field} is not a sequence") from exc


def _coordinate(value: object) -> float:
    if isinstance(value, bool):
        raise _MalformedPaddleResult("PaddleOCR polygon coordinate is invalid")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise _MalformedPaddleResult("PaddleOCR polygon coordinate is invalid") from exc
    if not math.isfinite(result):
        raise _MalformedPaddleResult("PaddleOCR polygon coordinate is invalid")
    return result


def _polygon_bounds(polygon: object) -> tuple[float, float, float, float]:
    if hasattr(polygon, "tolist"):
        polygon = polygon.tolist()
    if isinstance(polygon, (str, bytes, bytearray, Mapping)):
        raise _MalformedPaddleResult("PaddleOCR polygon is invalid")
    try:
        values = list(polygon)
    except Exception as exc:
        raise _MalformedPaddleResult("PaddleOCR polygon is invalid") from exc
    if not values:
        raise _MalformedPaddleResult("PaddleOCR polygon is empty")

    # Accept a defensive x0,y0,x1,y1 representation as well as Paddle's usual
    # four-point polygon. Both forms remain geometry-only evidence.
    try:
        flat = [_coordinate(value) for value in values]
    except _MalformedPaddleResult:
        flat = []
    if len(values) == 4 and len(flat) == 4:
        left, top, right, bottom = flat
        if right < left or bottom < top:
            raise _MalformedPaddleResult("PaddleOCR polygon bounds are invalid")
        return left, top, right, bottom

    points: list[tuple[float, float]] = []
    for point in values:
        if hasattr(point, "tolist"):
            point = point.tolist()
        if isinstance(point, (str, bytes, bytearray, Mapping)):
            raise _MalformedPaddleResult("PaddleOCR polygon point is invalid")
        try:
            coordinates = list(point)
        except Exception as exc:
            raise _MalformedPaddleResult("PaddleOCR polygon point is invalid") from exc
        if len(coordinates) < 2:
            raise _MalformedPaddleResult("PaddleOCR polygon point is invalid")
        points.append((_coordinate(coordinates[0]), _coordinate(coordinates[1])))
    if len(points) < 4:
        raise _MalformedPaddleResult("PaddleOCR polygon has too few points")
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def _boxes_from_payload(payload: object) -> list[_OcrBox]:
    texts_value = _object_value(payload, "rec_texts")
    scores_value = _object_value(payload, "rec_scores")
    rec_polys = _object_value(payload, "rec_polys")
    if rec_polys is _MISSING or rec_polys is None:
        rec_polys = _object_value(payload, "dt_polys")
    if texts_value is _MISSING or scores_value is _MISSING or rec_polys is _MISSING:
        raise _MalformedPaddleResult("PaddleOCR result fields are incomplete")

    texts = _sequence(texts_value, "rec_texts")
    scores = _sequence(scores_value, "rec_scores")
    polygons = _sequence(rec_polys, "rec_polys/dt_polys")
    if len(texts) != len(scores) or len(texts) != len(polygons):
        raise _MalformedPaddleResult("PaddleOCR result fields have different lengths")

    boxes: list[_OcrBox] = []
    for text, score, polygon in zip(texts, scores, polygons):
        if not isinstance(text, str):
            raise _MalformedPaddleResult("PaddleOCR recognition text is invalid")
        confidence = _coerce_confidence(score)
        if confidence is None:
            raise _MalformedPaddleResult("PaddleOCR recognition confidence is invalid")
        normalized_text = _clean(text)
        if not normalized_text or confidence < OCR_MIN_CONFIDENCE:
            continue
        left, top, right, bottom = _polygon_bounds(polygon)
        if right <= left or bottom <= top:
            raise _MalformedPaddleResult("PaddleOCR polygon has no area")
        boxes.append(_OcrBox(normalized_text, confidence, left, top, right, bottom))
    return boxes


def _same_row(row: list[_OcrBox], box: _OcrBox) -> bool:
    row_top = min(item.top for item in row)
    row_bottom = max(item.bottom for item in row)
    row_height = max(1.0, row_bottom - row_top)
    overlap = max(0.0, min(row_bottom, box.bottom) - max(row_top, box.top))
    shorter_height = min(row_height, box.height)
    if overlap / shorter_height >= 0.35:
        return True
    row_center = (row_top + row_bottom) / 2.0
    return abs(row_center - box.center_y) <= 0.45 * min(row_height, box.height)


def _reading_rows(boxes: list[_OcrBox]) -> list[list[_OcrBox]]:
    rows: list[list[_OcrBox]] = []
    for box in sorted(boxes, key=lambda item: (item.center_y, item.left, item.top)):
        matches = [index for index, row in enumerate(rows) if _same_row(row, box)]
        if not matches:
            rows.append([box])
            continue
        if len(matches) > 1:
            # A box that fits multiple visual rows is ambiguous; leaving it out
            # prevents evidence from being combined across row boundaries.
            continue
        rows[matches[0]].append(box)
    return sorted(
        (sorted(row, key=lambda item: (item.left, item.top)) for row in rows),
        key=lambda row: (min(item.top for item in row), min(item.left for item in row)),
    )


def _row_candidate(row: list[_OcrBox], allowed: frozenset[int] | None) -> _RowCandidate | None:
    text_parts: list[str] = []
    box_spans: list[tuple[int, int, _OcrBox]] = []
    cursor = 0
    for item in row:
        if not item.text:
            continue
        if text_parts:
            cursor += 1
        start = cursor
        text_parts.append(item.text)
        cursor += len(item.text)
        box_spans.append((start, cursor, item))
    row_text = _clean(" ".join(text_parts))
    period_matches = list(PERIOD_RE.finditer(row_text))
    wuxing_matches = list(WUXING_RE.finditer(row_text))
    if len(period_matches) != 1 or len(wuxing_matches) != 1:
        return None
    period = _coerce_period(period_matches[0].group(1))
    wuxing = _normalize_wuxing(wuxing_matches[0].group(1))
    if period is None or not wuxing or allowed is not None and period not in allowed:
        return None
    evidence_boxes = [
        item
        for start, end, item in box_spans
        if any(
            match.start() < end and match.end() > start
            for match in (*period_matches, *wuxing_matches)
        )
    ]
    if not evidence_boxes:
        return None
    confidence = min(item.score for item in evidence_boxes)
    if confidence < OCR_MIN_CONFIDENCE:
        return None
    raw = _canonical_raw(row_text, period, wuxing)
    if raw is None:
        return None
    return _RowCandidate(period, wuxing, raw, confidence)


def _recognize_pass(engine: object, image: Any, allowed: frozenset[int] | None) -> list[_RowCandidate]:
    predict = getattr(engine, "predict")
    result = predict(image)
    boxes: list[_OcrBox] = []
    for payload in _result_payloads(result):
        boxes.extend(_boxes_from_payload(payload))
    return [
        candidate
        for row in _reading_rows(boxes)
        if (candidate := _row_candidate(row, allowed)) is not None
    ]


def _merge_candidates(
    target: dict[int, _RowCandidate],
    ambiguous: set[int],
    candidates: Iterable[_RowCandidate],
) -> None:
    for candidate in candidates:
        period = candidate.period
        if period in ambiguous:
            continue
        previous = target.get(period)
        if previous is None:
            target[period] = candidate
            continue
        if (previous.wuxing, previous.raw) == (candidate.wuxing, candidate.raw):
            if candidate.confidence > previous.confidence:
                target[period] = candidate
            continue
        if period in target:
            ambiguous.add(period)
            target.pop(period, None)


def _merge_paired_candidates(
    target: dict[int, _PairedCandidate],
    ambiguous: set[int],
    candidates: Iterable[_PairedCandidate],
) -> None:
    for candidate in candidates:
        period = candidate.primary.period
        if period in ambiguous:
            continue
        previous = target.get(period)
        if previous is None:
            target[period] = candidate
            continue
        previous_signature = (
            previous.primary.wuxing,
            previous.primary.raw,
            previous.independent.wuxing,
            previous.independent.raw,
        )
        candidate_signature = (
            candidate.primary.wuxing,
            candidate.primary.raw,
            candidate.independent.wuxing,
            candidate.independent.raw,
        )
        if previous_signature == candidate_signature:
            target[period] = _PairedCandidate(
                primary=(
                    candidate.primary
                    if candidate.primary.confidence > previous.primary.confidence
                    else previous.primary
                ),
                independent=(
                    candidate.independent
                    if candidate.independent.confidence > previous.independent.confidence
                    else previous.independent
                ),
            )
            continue
        if period in target:
            ambiguous.add(period)
            target.pop(period, None)


def _decode_image_pair(image_bytes: object, np: Any, image_module: Any, image_ops: Any) -> tuple[Any, Any]:
    if not isinstance(image_bytes, (bytes, bytearray, memoryview)):
        raise ValueError("OCR image must be in-memory bytes")
    encoded = bytes(image_bytes)
    if not encoded:
        raise ValueError("OCR image is empty")
    with image_module.open(io.BytesIO(encoded)) as image:
        rgb = image.convert("RGB")
        original = np.asarray(rgb, dtype=np.uint8).copy()
        grayscale = image_ops.autocontrast(rgb.convert("L"))
        width, height = grayscale.size
        enhanced = grayscale.resize(
            (max(1, width * 2), max(1, height * 2)),
            image_module.Resampling.LANCZOS,
        )
        enhanced_rgb = np.asarray(enhanced.convert("RGB"), dtype=np.uint8).copy()
    return original, enhanced_rgb


def _load_paddle_ocr() -> object:
    global _PADDLE_OCR_INSTANCE
    with _PADDLE_OCR_LOCK:
        if _PADDLE_OCR_INSTANCE is not None:
            return _PADDLE_OCR_INSTANCE
        try:
            from paddleocr import PaddleOCR

            _PADDLE_OCR_INSTANCE = PaddleOCR(
                text_detection_model_name="PP-OCRv5_mobile_det",
                text_recognition_model_name="PP-OCRv5_mobile_rec",
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                device="cpu",
            )
        except Exception as exc:
            raise FetchError(PADDLE_OCR_INSTALL_MESSAGE) from exc
        return _PADDLE_OCR_INSTANCE


def recognize_paddle_ocr_images(
    images: Iterable[bytes], target_period: int | None
) -> tuple[dict[str, object], ...]:
    """Recognize in-memory images with two independent CPU PaddleOCR passes."""

    try:
        image_values = tuple(images)
        if not image_values:
            return ()
        try:
            from PIL import Image, ImageOps
            import numpy as np
        except Exception as exc:
            raise FetchError(PADDLE_OCR_INSTALL_MESSAGE) from exc

        allowed = _allowed_periods(target_period)
        with _PADDLE_OCR_LOCK:
            engine = _load_paddle_ocr()
            primary: dict[int, _RowCandidate] = {}
            independent: dict[int, _RowCandidate] = {}
            paired: dict[int, _PairedCandidate] = {}
            primary_ambiguous: set[int] = set()
            independent_ambiguous: set[int] = set()
            paired_ambiguous: set[int] = set()
            for image_bytes in image_values:
                original, enhanced = _decode_image_pair(image_bytes, np, Image, ImageOps)
                primary_candidates = _recognize_pass(engine, original, allowed)
                independent_candidates = _recognize_pass(engine, enhanced, allowed)
                _merge_candidates(primary, primary_ambiguous, primary_candidates)
                _merge_candidates(independent, independent_ambiguous, independent_candidates)

                image_primary: dict[int, _RowCandidate] = {}
                image_independent: dict[int, _RowCandidate] = {}
                image_primary_ambiguous: set[int] = set()
                image_independent_ambiguous: set[int] = set()
                _merge_candidates(image_primary, image_primary_ambiguous, primary_candidates)
                _merge_candidates(image_independent, image_independent_ambiguous, independent_candidates)
                paired_candidates: list[_PairedCandidate] = []
                for period in image_primary.keys() & image_independent.keys():
                    primary_candidate = image_primary[period]
                    independent_candidate = image_independent[period]
                    if primary_candidate.wuxing != independent_candidate.wuxing:
                        paired_ambiguous.add(period)
                        continue
                    paired_candidates.append(_PairedCandidate(primary_candidate, independent_candidate))
                paired_ambiguous.update(image_primary_ambiguous)
                paired_ambiguous.update(image_independent_ambiguous)
                _merge_paired_candidates(paired, paired_ambiguous, paired_candidates)

            entries: list[dict[str, object]] = []
            for period, pair in paired.items():
                primary_candidate = pair.primary
                independent_candidate = pair.independent
                if (
                    period in primary_ambiguous
                    or period in independent_ambiguous
                    or period in paired_ambiguous
                    or primary.get(period) is None
                    or independent.get(period) is None
                    or primary_candidate.wuxing != independent_candidate.wuxing
                    or primary_candidate.period != independent_candidate.period
                ):
                    continue
                entries.append(
                    {
                        "engine": PADDLE_OCR_ENGINE,
                        "period": period,
                        "wuxing": primary_candidate.wuxing,
                        "raw": primary_candidate.raw,
                        "confidence": primary_candidate.confidence,
                        "independentPeriod": independent_candidate.period,
                        "independentWuxing": independent_candidate.wuxing,
                        "independentRaw": independent_candidate.raw,
                        "independentConfidence": independent_candidate.confidence,
                    }
                )
            return tuple(entries)
    except FetchError:
        raise
    except Exception as exc:
        raise FetchError(PADDLE_OCR_RUNTIME_MESSAGE) from exc
