from __future__ import annotations

import re

from . import kernel


BAJIXINDONG_URL = "https://cwdcaqzn.7mj0h-75k3q-cbuvqb.work:16677/#am"
BAJIXINDONG_PARSER_ID = "parser.bajixindong.v2"
TONGXIN_YELI_URL = "https://e7rzi6.t5ti5-at6k5-fugxpa.work/topic/227015.html"
_TONGXIN_YELI_ANCHOR_RE = re.compile(r"绝杀料\s*\d+期.{0,80}?作者\s*[:：]\s*同心叶力")
_TONGXIN_YELI_BOUNDARY_RE = re.compile(r"澳门开奖站|页面继续往下走|上一篇|下一篇|返回列表")
_BAJIXINDONG_OCR_RE = re.compile(
    r"八级心动\s*绝杀\s*一\s*行\s*(?P<period>\d{1,4})\s*期.*?"
    r"[【\[]?(?P<wuxing>[金木水火土])\s*行?[】\]]?"
)
_BAJIXINDONG_OCR_LEGACY_RE = re.compile(
    r"(?P<wuxing>[金木水火土]行)\s*(?P<period>\d{1,4})\s*期\s*八级心动"
)


def parse_bajixindong(document: str) -> list[kernel.Candidate]:
    """Keep the visible row and validated OCR row as separate evidence.

    The page can contain a hidden or unrelated text row with the same period.
    OCR is already validated by the browser source; retaining it here lets the
    shared conflict validator reject contradictory evidence instead of choosing
    whichever row happens to appear first.
    """
    candidates = list(kernel.parse_bajixixindong_candidates(document))
    for index, line in enumerate(kernel.text_lines(document)):
        match = _BAJIXINDONG_OCR_RE.search(line)
        if match:
            wuxing = f"{match.group('wuxing')}行" if len(match.group('wuxing')) == 1 else match.group("wuxing")
            period = match.group("period")
        else:
            legacy_match = _BAJIXINDONG_OCR_LEGACY_RE.search(line)
            if not legacy_match:
                continue
            wuxing = legacy_match.group("wuxing")
            period = legacy_match.group("period")
        candidates.append(
            kernel.Candidate(
                f"{int(period)}期",
                wuxing,
                -1_000_000 + index,
                kernel.clean_line(line),
            )
        )
    return kernel.dedupe_candidates_only(candidates)


def parse_tongxin_yeli(document: str) -> list[kernel.Candidate]:
    """Keep the rendered tail when the page repeats a period after a cycle wrap.

    The page contains an ascending block followed by a zero-padded cycle. For
    a repeated period, the bottom-direction source is the final rendered row;
    keeping that occurrence also prevents an earlier cycle from creating a
    false same-period conflict.
    """
    text = kernel.clean_line(kernel.html_to_text(document))
    anchor = _TONGXIN_YELI_ANCHOR_RE.search(text)
    if not anchor:
        return []

    candidates: list[kernel.Candidate] = []
    last_match_end = anchor.end()
    for order, match in enumerate(kernel.SITE_CURRENT_BLOCK_ROW_RE.finditer(text, anchor.start())):
        gap = text[last_match_end : match.start()]
        if _TONGXIN_YELI_BOUNDARY_RE.search(gap):
            break
        candidates.append(
            kernel.Candidate(
                period=f"{int(match.group('period'))}期",
                wuxing=f"{match.group('wuxing')}行",
                order=order,
                raw=kernel.clean_line(match.group(0)),
            )
        )
        last_match_end = match.end()
    last_by_period = {candidate.period: candidate for candidate in candidates}
    return sorted(last_by_period.values(), key=lambda candidate: candidate.order)


SITE_PLUGINS = {
    BAJIXINDONG_URL: parse_bajixindong,
    TONGXIN_YELI_URL: parse_tongxin_yeli,
}
SITE_PLUGINS_BY_ID = {BAJIXINDONG_PARSER_ID: parse_bajixindong}


__all__ = [
    "BAJIXINDONG_PARSER_ID",
    "BAJIXINDONG_URL",
    "TONGXIN_YELI_URL",
    "SITE_PLUGINS",
    "SITE_PLUGINS_BY_ID",
    "parse_bajixindong",
    "parse_tongxin_yeli",
]
