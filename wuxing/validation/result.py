from __future__ import annotations

from dataclasses import dataclass
import re

from wuxing import registry_data
from wuxing.domain.enums import FailureCode
from wuxing.domain.models import Candidate, SiteConfig, SourceDocument, ValidationEvidence

from .authority import validate_authority_boundary
from .conflict import detect_period_conflict
from .position import evaluate_position_window


TARGET_ANCHOR_RE = re.compile(
    r"(?:绝杀|必杀|精杀|稳杀|死禁|殺|杀)\s*[（(]?\s*[一1①➀⑴㈠⒈]\s*[.。．、]?\s*[)）]?\s*行"
    r"|[一二三四五①②③④⑤\d]\s*行\s*中\s*特|五\s*[丢表]\s*主\s*四\s*行"
)


@dataclass(frozen=True)
class ValidationDecision:
    passed: bool
    candidate: Candidate | None
    failure_code: FailureCode | None
    reason: str
    evidence: ValidationEvidence


def _failure(
    code: FailureCode,
    reason: str,
    evidence: ValidationEvidence,
) -> ValidationDecision:
    return ValidationDecision(
        passed=False,
        candidate=None,
        failure_code=code,
        reason=reason,
        evidence=evidence,
    )


_TAG_STRIP_RE = re.compile(r"<[^>]+>")
_ONE_EQUIVALENTS = frozenset("一1①➀⑴㈠⒈壹")


def _plain(text: str) -> str:
    """去标签、解 HTML 实体、归一空白，便于做栏目/锚点匹配。"""
    import html as _html

    stripped = _TAG_STRIP_RE.sub(" ", text)
    unescaped = _html.unescape(stripped)
    return re.sub(r"[ \t\u3000]+", " ", unescaped)


def _compact_with_positions(text: str) -> tuple[str, list[int]]:
    """去掉所有空白、归一「一/1/①」写法，并记录每个字符在原文中的位置。"""
    chars: list[str] = []
    positions: list[int] = []
    for offset, char in enumerate(text):
        if char.isspace():
            continue
        chars.append("1" if char in _ONE_EQUIVALENTS else char)
        positions.append(offset)
    return "".join(chars), positions


def _locate_candidate_line(text: str, candidate: Candidate) -> int:
    """在纯文本中定位候选所在位置；定位不到返回 -1。

    候选 raw 可能跨多行或含原文没有的空白，因此依次尝试：
    精确匹配 → 去空白匹配 → 首行匹配 → 前缀匹配 → 期号+五行。
    """
    raw = (candidate.raw or "").strip()
    if raw:
        probes = [raw]
        head = raw.splitlines()[0].strip() if raw.splitlines() else ""
        if head and head != raw:
            probes.append(head)
        probes.append(raw[:40])
        compact, positions = _compact_with_positions(text)
        for probe in probes:
            if not probe:
                continue
            index = text.find(probe)
            if index >= 0:
                return index
            needle = "".join(
                "1" if char in _ONE_EQUIVALENTS else char
                for char in probe
                if not char.isspace()
            )
            if not needle:
                continue
            hit = compact.find(needle)
            if hit >= 0:
                return positions[hit]
    period = candidate.period
    wuxing = candidate.wuxing.replace(" ", "")
    pattern = re.compile(
        rf"(?<!\d){period}\s*期[^\n]{{0,60}}?{re.escape(wuxing)}"
    )
    match = pattern.search(text)
    if match:
        return match.start()
    return -1


def _line_window(text: str, position: int, before: int = 400, after: int = 400) -> str:
    if position < 0:
        return ""
    return text[max(0, position - before): position + after]


def _keyword_proven_by_document(
    document: SourceDocument | None,
    candidate: Candidate,
    site_anchor_pattern: str = "",
) -> bool:
    """栏目锚点必须由「候选所在区块」证明，禁止整页扫描、禁止用候选 raw 自证。

    判定在去标签纯文本上做，邻域覆盖同一条记录（含标题行与值行）：
    1. 站点配置的栏目/作者锚点命中该区块；
    2. 文档 metadata 携带的锚点命中该区块；
    3. 候选所在行本身含目标栏目词（绝杀一行等）；
    4. 区块内出现候选锚点或目标栏目词。
    """
    if document is None:
        return False
    text = _plain(document.text or "")
    if not text.strip():
        return False
    position = _locate_candidate_line(text, candidate)
    if position < 0:
        return False
    scope = _line_window(text, position)
    if not scope:
        return False
    for configured in (site_anchor_pattern, document.metadata_map.get("required_text_pattern", "")):
        if not configured:
            continue
        try:
            if re.search(configured, scope) is not None:
                return True
        except re.error:
            continue
    raw = candidate.raw or ""
    if raw and TARGET_ANCHOR_RE.search(raw) is not None:
        return True
    if candidate.anchor and re.search(re.escape(candidate.anchor), scope) is not None:
        return True
    return TARGET_ANCHOR_RE.search(scope) is not None


def validate_scrape_candidates(
    site: SiteConfig,
    period: int,
    candidates: tuple[Candidate, ...] | list[Candidate],
    authoritative_documents: tuple[SourceDocument, ...] | list[SourceDocument],
) -> ValidationDecision:
    candidates = tuple(candidates)
    documents = tuple(authoritative_documents)
    period_candidates = tuple(candidate for candidate in candidates if candidate.period == period)
    evidence = ValidationEvidence(
        period_pass=bool(period_candidates),
        authority_pass=False,
        keyword_pass=bool(period_candidates),
        wuxing_pass=all(candidate.wuxing in {"金行", "木行", "水行", "火行", "土行"} for candidate in period_candidates),
        conflict_pass=False,
    )
    if not period_candidates:
        return _failure(
            FailureCode.TARGET_NOT_FOUND,
            f"页面里未找到 {period}期的有效候选",
            evidence,
        )

    position = evaluate_position_window(candidates, site.region, period)
    if not position.passed:
        return _failure(
            FailureCode.POSITION_WINDOW,
            position.reason,
            ValidationEvidence(
                period_pass=True,
                position_pass=False,
                authority_pass=False,
                keyword_pass=False,
                wuxing_pass=True,
                conflict_pass=False,
                details=(position.reason,),
            ),
        )

    window_orders = set(position.window_orders)
    window_candidates = tuple(candidate for candidate in candidates if candidate.order in window_orders)
    window_period_candidates = tuple(
        candidate for candidate in window_candidates if candidate.period == period
    )
    # 栏目/关键词必须由「候选所在文档」证明，不能用候选自己的 raw 自证。
    document_by_id = {document.document_id: document for document in documents}
    site_anchor = registry_data.BROWSER_REQUIRED_TEXT_PATTERNS.get(site.url)
    site_anchor_pattern = site_anchor.pattern if site_anchor else ""
    keyword_pass = all(
        _keyword_proven_by_document(
            document_by_id.get(candidate.source_document_id),
            candidate,
            site_anchor_pattern,
        )
        for candidate in window_period_candidates
    )
    if not keyword_pass:
        return _failure(
            FailureCode.KEYWORD_MISMATCH,
            f"{period}期候选缺少同块栏目锚点或关键词",
            ValidationEvidence(
                period_pass=True,
                position_pass=True,
                authority_pass=False,
                keyword_pass=False,
                wuxing_pass=True,
                conflict_pass=False,
                details=(position.reason,),
            ),
        )

    authority_results = tuple(
        validate_authority_boundary(documents, candidate)
        for candidate in window_period_candidates
    )
    if not all(result.passed for result in authority_results):
        detail = next(result.reason for result in authority_results if not result.passed)
        return _failure(
            FailureCode.AUTHORITY_NOT_UNIQUE,
            detail,
            ValidationEvidence(
                period_pass=True,
                position_pass=True,
                authority_pass=False,
                keyword_pass=True,
                wuxing_pass=True,
                conflict_pass=False,
                details=(position.reason,),
            ),
        )

    conflict = detect_period_conflict(window_candidates, period)
    if conflict.conflict:
        return _failure(
            FailureCode.TARGET_CONFLICT,
            conflict.reason,
            ValidationEvidence(
                period_pass=True,
                position_pass=True,
                authority_pass=True,
                keyword_pass=True,
                wuxing_pass=True,
                conflict_pass=False,
                details=(position.reason,),
            ),
        )
    if conflict.duplicate:
        return _failure(
            FailureCode.DUPLICATE_WUXING,
            conflict.reason,
            ValidationEvidence(
                period_pass=True,
                position_pass=True,
                authority_pass=True,
                keyword_pass=True,
                wuxing_pass=True,
                conflict_pass=False,
                details=(position.reason,),
            ),
        )

    evidence = ValidationEvidence(
        period_pass=True,
        position_pass=position.passed,
        authority_pass=True,
        keyword_pass=True,
        wuxing_pass=True,
        conflict_pass=True,
        details=(position.reason,),
    )
    if not position.passed:
        return _failure(FailureCode.POSITION_WINDOW, position.reason, evidence)

    return ValidationDecision(
        passed=True,
        candidate=period_candidates[0],
        failure_code=None,
        reason="期号、权威边界、方向窗口、五行和同期唯一性均通过",
        evidence=evidence,
    )
