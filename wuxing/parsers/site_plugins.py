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


WENWENWEN_URL = "https://sepfsazm.th2pfx-4s7mu-aafjnm.xyz:16677/topic/680722.html"
HUANGFUQINGYA_URL = "https://msbqxti.zhx2n-7v5x3-ivdpud.xyz:16677/topic/682733.html"
PUTIANTONGQING_URL = "https://vbxl5.wp5pl-3ztz5-cwgbti.xyz/topic/222779.html"
DAZHUDI_URL = "https://jdjzpkce.osyaf-gxlte-otlblr.xyz:16677/"

# 稳稳稳：299期稳杀(一)行 【土行】 开0000√
_WENWENWEN_ROW_RE = re.compile(
    r"(?P<period>\d{1,4})\s*期\s*(?:稳|必|绝|精)?\s*杀\s*[\(（]?\s*[一1①]\s*[\)）]?\s*行"
    r"\s*[【\[]\s*(?P<wuxing>[金木水火土])\s*行?\s*[】\]]"
)
# 皇甫青崖：299期杀一行 【木 行 】 开 0000 √
_HUANGFU_ROW_RE = re.compile(
    r"(?P<period>\d{1,4})\s*期\s*杀\s*[\(（]?\s*[一1①]\s*[\)）]?\s*行"
    r"\s*[【\[]\s*(?P<wuxing>[金木水火土])\s*行?\s*[】\]]"
)
# 溥天同庆：299期：▼绝杀一行▼【木 】开 ？00准
_PUTIAN_ROW_RE = re.compile(
    r"(?P<period>\d{1,4})\s*期\s*[:：]?\s*▼?\s*(?:绝|必|精|稳)?\s*杀\s*[\(（]?\s*[一1①]\s*[\)）]?\s*行"
    r"\s*▼?\s*[【\[]\s*(?P<wuxing>[金木水火土])\s*行?\s*[】\]]"
)


def _rows_to_candidates(text: str, row_re: re.Pattern[str]) -> list[kernel.Candidate]:
    candidates: list[kernel.Candidate] = []
    for order, match in enumerate(row_re.finditer(text)):
        candidates.append(
            kernel.Candidate(
                period=f"{int(match.group('period'))}期",
                wuxing=f"{match.group('wuxing')}行",
                order=order,
                raw=kernel.clean_line(match.group(0)),
            )
        )
    return kernel.dedupe_candidates_only(candidates)


def parse_wenwenwen(document: str) -> list[kernel.Candidate]:
    """稳稳稳：稳杀(一)行 版式，五行括号内可能带空格。"""
    text = kernel.clean_line(kernel.html_to_text(document))
    return _rows_to_candidates(text, _WENWENWEN_ROW_RE)


def parse_huangfuqingya(document: str) -> list[kernel.Candidate]:
    """皇甫青崖：杀一行 版式（无绝杀前缀），括号内五行被拆开。"""
    text = kernel.clean_line(kernel.html_to_text(document))
    return _rows_to_candidates(text, _HUANGFU_ROW_RE)


def parse_putiantongqing(document: str) -> list[kernel.Candidate]:
    """溥天同庆：▼绝杀一行▼ 版式，历史从 150 期升序排列、当期在顶部。"""
    text = kernel.clean_line(kernel.html_to_text(document))
    return _rows_to_candidates(text, _PUTIAN_ROW_RE)


# 大地主：只取「五表主四行」栏目，行如 299期【水.木.火.土】，当期值取第一个五行。
# 该栏目用 ★ 分隔线与前后栏目（六表主双波、七表主单双等）隔开。
_DAZHUDI_SECTION_RE = re.compile(r"五表主四行")
_DAZHUDI_SECTION_END_RE = re.compile(r"六表主|七表主|土地公--精华资料")
_DAZHUDI_ROW_RE = re.compile(
    r"(?P<period>\d{1,4})\s*期\s*[【\[]\s*(?P<items>[金木水火土](?:\s*[.．、]\s*[金木水火土]){1,4})\s*[】\]]"
)


def parse_dazhudi_wubiao(document: str) -> list[kernel.Candidate]:
    """大地主：只认「五表主四行」区块，取每期第一个五行。

    必须限定在该栏目内：同一页还有「六表主双波」「七表主单双」等栏目，
    它们的括号内容不是五行，且绝杀一行栏目在本页不存在。
    """
    text = kernel.clean_line(kernel.html_to_text(document))
    start = _DAZHUDI_SECTION_RE.search(text)
    if not start:
        return []
    end = _DAZHUDI_SECTION_END_RE.search(text, start.end())
    section = text[start.end(): end.start() if end else len(text)]
    candidates: list[kernel.Candidate] = []
    for order, match in enumerate(_DAZHUDI_ROW_RE.finditer(section)):
        items = re.split(r"[.．、]", match.group("items"))
        first = items[0].strip() if items else ""
        if first not in {"金", "木", "水", "火", "土"}:
            continue
        candidates.append(
            kernel.Candidate(
                period=f"{int(match.group('period'))}期",
                wuxing=f"{first}行",
                order=order,
                raw=kernel.clean_line(match.group(0)),
            )
        )
    return kernel.dedupe_candidates_only(candidates)


YIHUBAIYING_URL = "https://kfsujebc.djiz8-4tqt6-hubani.xyz:16677/topic/280932.html"
_YIHUBAIYING_ROW_RE = re.compile(
    r"(?P<period>\d{1,4})\s*期\s*[:：]?\s*〓?\s*[【\[]\s*(?:稳|绝|必|精)?\s*杀\s*[\(（]?\s*[一1①]\s*[\)）]?\s*行"
    r"\s*[】\]]\s*〓?\s*[【\[]\s*(?P<wuxing>[金木水火土])\s*行?\s*[】\]]"
)


def parse_yihubaiying(document: str) -> list[kernel.Candidate]:
    """一呼百应：页面有两个 301 期块（当期块 + 旧周期循环块），只取第一段连续块。

    当期块在页面最前、值多为占位（开：00赢）；后面的旧周期块会带广告尾巴且期号更大（302/303），
    取第一段可避免同页同期冲突和方向窗口被旧块拖失败。
    """
    text = kernel.clean_line(kernel.html_to_text(document))
    candidates: list[kernel.Candidate] = []
    previous_period: int | None = None
    for match in _YIHUBAIYING_ROW_RE.finditer(text):
        period = int(match.group("period"))
        # 第一段连续块结束条件：期号不再递增（旧周期块通常从大期号重新开始）
        if previous_period is not None and period != previous_period + 1:
            break
        previous_period = period
        candidates.append(
            kernel.Candidate(
                period=f"{period}期",
                wuxing=f"{match.group('wuxing')}行",
                order=len(candidates),
                raw=kernel.clean_line(match.group(0)),
            )
        )
    return kernel.dedupe_candidates_only(candidates)


BEIJIANLIANG_URL = "https://mfhfepu.ow55j-i5hbb-icetss.xyz/topic/768602.html"
_BEIJIANLIANG_ROW_RE = re.compile(
    r"(?P<period>\d{1,4})\s*期\s*四行中特\s*[（(]\s*(?P<items>[金木水火土]{4})\s*[)）]"
)
_WUXING_ORDER = "金木水火土"


def parse_beijianliang(document: str) -> list[kernel.Candidate]:
    """北悸安涼：栏目「四行中特」列出 4 行，取**未列出的那一行**。

    页面只给「木水金土」这种 4 行串，没有「X行」字样，通用解析认不出。
    取哪个：用缓存 292–301 共 10 期逐期核对，排除法（五行里没被列出的那个）10/10 吻合，
    取首个、取末个都对不上，故按排除法定值。
    """
    text = kernel.clean_line(kernel.html_to_text(document))
    candidates: list[kernel.Candidate] = []
    for match in _BEIJIANLIANG_ROW_RE.finditer(text):
        listed = match.group("items")
        rest = [item for item in _WUXING_ORDER if item not in listed]
        if len(rest) != 1:
            continue
        candidates.append(
            kernel.Candidate(
                period=f"{int(match.group('period'))}期",
                wuxing=f"{rest[0]}行",
                order=len(candidates),
                raw=kernel.clean_line(match.group(0)),
            )
        )
    return kernel.dedupe_candidates_only(candidates)


SITE_PLUGINS = {
    BAJIXINDONG_URL: parse_bajixindong,
    TONGXIN_YELI_URL: parse_tongxin_yeli,
    WENWENWEN_URL: parse_wenwenwen,
    HUANGFUQINGYA_URL: parse_huangfuqingya,
    PUTIANTONGQING_URL: parse_putiantongqing,
    DAZHUDI_URL: parse_dazhudi_wubiao,
    YIHUBAIYING_URL: parse_yihubaiying,
    BEIJIANLIANG_URL: parse_beijianliang,
}
SITE_PLUGINS_BY_ID = {BAJIXINDONG_PARSER_ID: parse_bajixindong}


__all__ = [
    "BAJIXINDONG_PARSER_ID",
    "BAJIXINDONG_URL",
    "TONGXIN_YELI_URL",
    "WENWENWEN_URL",
    "HUANGFUQINGYA_URL",
    "PUTIANTONGQING_URL",
    "DAZHUDI_URL",
    "YIHUBAIYING_URL",
    "BEIJIANLIANG_URL",
    "SITE_PLUGINS",
    "SITE_PLUGINS_BY_ID",
    "parse_bajixindong",
    "parse_tongxin_yeli",
    "parse_wenwenwen",
    "parse_huangfuqingya",
    "parse_putiantongqing",
    "parse_dazhudi_wubiao",
    "parse_yihubaiying",
    "parse_beijianliang",
]
