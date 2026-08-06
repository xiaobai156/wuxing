from __future__ import annotations

from dataclasses import dataclass
import html
import re
from typing import Iterable
from urllib.parse import urlparse

try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None


SPA_STRUCTURED_RECORD_MARKER = "[SPA_STRUCTURED_USER_RECORD]"


TAG_RE = re.compile(r"<[^>]+>")


PERIOD_RE = re.compile(r"(?<!\d)(\d{1,4})\s*期")


WUXING_RE = re.compile(r"([金木水火土]\s*行)")


BRACKET_WUXING_RE = re.compile(r"[【\[\(（《〖]\s*([金木水火土](?:\s*行|(?:[.\s、，/]*[金木水火土]){0,4}))\s*[】\]\)）》〗]")


ONE_MARKER = r"[一1①➀⑴㈠⒈]"


KILL_ONE_LINE_RE = re.compile(rf"(?:绝|必|必中|殺|杀)?\s*[必绝]?\s*杀\s*[\(（]?\s*{ONE_MARKER}\s*[\)）]?\s*[.。．、]?\s*行|必\s*杀\s*[一1]\s*[.。．、]?\s*行")


TARGET_SECTION_RE = re.compile(rf"(?:{KILL_ONE_LINE_RE.pattern}|[一二三四五①②③④⑤\d]?\s*行\s*中\s*特|五\s*[丢表]\s*主\s*四\s*行)")


NOISE_SECTION_RE = re.compile(r"广告(?:栏目)?|推广|赞助|上一篇|下一篇|其他栏目|推荐(?:栏目)?|导航(?:栏目)?|相关推荐|热门推荐")


VALID_WUXING = {"金行", "木行", "水行", "火行", "土行"}


SITE_SPECIFIC_CANDIDATE_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "https://mxiscni.nkh6s-vfni4-lwgfvw.xyz:16677/topic/257907.html": (
        re.compile(
            rf"(?P<period>\d{{1,4}})\s*期\s*[:：]?\s*绝\s*杀\s*[\(（]?\s*{ONE_MARKER}\s*[\)）]?\s*行\s*[【\[]\s*(?P<wuxing>[金木水火土])\s*行\s*[】\]]"
        ),
    ),
    "https://ekhivjcg.llnnt-l11x5-bywtoe.xyz:16677/topic/469882.html": (
        re.compile(
            rf"(?P<period>\d{{1,4}})\s*期.{{0,20}}?绝杀\s*{ONE_MARKER}\s*行.{{0,20}}?杀\s*(?P<wuxing>[金木水火土])\s*行"
        ),
    ),
    "https://fzzmqscl.bdppk-lyf4y-teyajr.xyz:16677/topic/439186.html": (
        re.compile(
            rf"(?P<period>\d{{1,4}})\s*期\s*[【\[]?\s*绝杀\s*{ONE_MARKER}\s*行\s*[】\]]?\s*[《【\[]?\s*(?P<wuxing>[金木水火土])\s*行\s*[》】\]]?"
        ),
    ),
    "https://3.www112291a.com:2053/gengxin/16.html": (
        re.compile(
            rf"(?P<period>\d{{1,4}})\s*期\s*[:：]?\s*绝\s*杀\s*{ONE_MARKER}\s*行\s*[【\[]\s*(?P<wuxing>[金木水火土])\s*行\s*[】\]]"
        ),
    ),
    "https://myvvqq.30dok-2s9fd-bibfmg.work/": (
        re.compile(
            rf"(?P<period>\d{{1,4}})\s*期\s*[:：]?\s*绝\s*杀\s*[\(（]?\s*{ONE_MARKER}\s*[\)）]?\s*行\s*[【\[]\s*(?P<wuxing>[金木水火土])\s*行\s*[】\]]"
        ),
    ),
    "https://ykeejph.z9koz-18xjn-pvglgy.xyz:16677/topic/682107.html": (
        re.compile(
            rf"(?P<period>\d{{1,4}})\s*期\s*[:：]?\s*绝\s*杀\s*{ONE_MARKER}\s*行\s*[【\[]\s*(?P<wuxing>[金木水火土])\s*行\s*[】\]]"
        ),
    ),
    "https://fhktrabu.zbfrm-uzct1-pmycbu.xyz:16677/topic/469065.html": (
        re.compile(
            r"(?P<period>\d{1,4})\s*期\s*[:：]?\s*[【\[]\s*绝\s*杀\s*一\s*行\s*[】\]]\s*[【\[〖]\s*(?P<wuxing>[金木水火土])\s*行\s*[】\]〗]"
        ),
    ),
    "https://g63.52619c.com:8443/tie1/1614.html": (
        re.compile(
            rf"(?P<period>\d{{1,4}})\s*期\s*稳\s*杀\s*{ONE_MARKER}\s*行\s*[【\[]\s*(?P<wuxing>[金木水火土])\s*(?:行)?\s*[】\]]"
        ),
    ),
    "https://useaul.z3rj5-9jlwg-dynocd.xyz:16677/topic/384879.html": (
        re.compile(
            rf"(?P<period>\d{{1,4}})\s*期\s*[:：]?\s*绝\s*杀\s*{ONE_MARKER}\s*行\s*[【\[]\s*(?P<wuxing>[金木水火土])\s*行\s*[】\]]"
        ),
    ),
    "https://swnrapsd.74wyl-mm601-cbpzhn.xyz:16677/": (
        re.compile(
            rf"(?P<period>\d{{1,4}})\s*期\s*稳\s*杀\s*[（(]?\s*{ONE_MARKER}\s*[)）]?\s*行\s*"
            r"[【\[]\s*(?P<wuxing>[金木水火土])\s*(?:行)?\s*[】\]]"
        ),
    ),
    "https://huqtzej.vvlq2-j4i8n-lisghq.xyz:16677/": (
        re.compile(
            rf"(?P<period>\d{{1,4}})\s*期\s*稳\s*杀\s*{ONE_MARKER}\s*行\s*[【\[]\s*(?P<wuxing>[金木水火土])\s*行\s*[】\]]"
        ),
    ),
    "https://993345.com/gsb1.aspx?id=1482": (
        re.compile(
            rf"(?P<period>\d{{1,4}})\s*期\s*[:：]?\s*必\s*杀\s*{ONE_MARKER}\s*行\s*[【\[]\s*(?P<wuxing>[金木水火土])\s*行\s*[】\]]"
        ),
    ),
    "https://2.www39169b.com:888/#62111": (
        re.compile(
            rf"(?P<period>\d{{1,4}})\s*期\s*[:：]?\s*必\s*杀\s*{ONE_MARKER}\s*行\s*[【\[]\s*(?P<wuxing>[金木水火土])\s*行\s*[】\]]"
        ),
    ),
    "https://wxaxdfc.523mo-z7mla-owjdon.xyz:16677/": (
        re.compile(
            rf"绝杀\s*一\s*行.{{0,80}}?(?P<period>\d{{1,4}})\s*期\s*稳\s*杀\s*[（(]?\s*{ONE_MARKER}\s*[)）]?\s*行\s*"
            r"[【\[]\s*(?P<wuxing>[金木水火土])(?:\s*(?P=wuxing)){0,2}\s*[】\]]"
        ),
    ),
}


SITE_SPECIFIC_POSITION_RULE_URLS = {
    "https://mxiscni.nkh6s-vfni4-lwgfvw.xyz:16677/topic/257907.html",
    "https://ekhivjcg.llnnt-l11x5-bywtoe.xyz:16677/topic/469882.html",
    "https://fzzmqscl.bdppk-lyf4y-teyajr.xyz:16677/topic/439186.html",
    "https://3.www112291a.com:2053/gengxin/16.html",
    "https://myvvqq.30dok-2s9fd-bibfmg.work/",
    "https://ykeejph.z9koz-18xjn-pvglgy.xyz:16677/topic/682107.html",
    "https://fhktrabu.zbfrm-uzct1-pmycbu.xyz:16677/topic/469065.html",
    "https://mflmcobome.26222hi.app:2569/htm/bbs/top040.html",
    "https://hl.www25195a.com/read.php?tid=607",
    "https://g63.52619c.com:8443/tie1/1614.html",
    "https://useaul.z3rj5-9jlwg-dynocd.xyz:16677/topic/384879.html",
    "https://huqtzej.vvlq2-j4i8n-lisghq.xyz:16677/",
    "https://993345.com/gsb1.aspx?id=1482",
    "https://2.www39169b.com:888/#62111",
    "https://wxaxdfc.523mo-z7mla-owjdon.xyz:16677/",
    "https://tulprhfc.wghcb-bnmgm-hyymaz.work:16655/topic/453352.html",
    "https://yylxuru.en4hs-c1zt6-qzcdin.xyz:16677/",
    "https://zqliou.kify1-fbyi6-lmeykn.xyz:16677/",
    "https://eebysckd.2go6k-y0pfv-fqbdsm.xyz:16677/topic/626030.html",
    "https://cwdcaqzn.7mj0h-75k3q-cbuvqb.work:16677/#am",
}


CHUNMAN_SHANSHUI_URLS = {
    "https://zxliojf.83gjk-dnne7-kuyach.xyz:16677/",
    "https://akqasqa.drr11-soh5x-jcaafg.xyz:16677/",
}


MANAGER_ARTICLE_SITE_RULES: dict[str, tuple[str, str]] = {
    "https://cahgjib.5blx9-z8506-ekiwxc.work:29488/article/admin/6a1449c2597e16d57eacb67a?url=lqz": ("彻头彻尾", "four"),
    "https://drxgkjt.uu1oc-eyjpt-uxyccu.xyz:29400/article/manager/6a33e71adfa16552b923d2b7?url=jyb": ("齐天大胜", "four"),
    "https://hquomm.20t3f-0yztv-jiozun.xyz:29444/article/manager/6a4c273b57dc857ae1c07d6d?url=dgd": ("金馬快报", "single"),
    "https://hquomm.20t3f-0yztv-jiozun.xyz:29444/article/manager/6a329d0cb8abbf5af1a54e88?url=dgd": ("云容月貌", "single"),
    "https://hquomm.20t3f-0yztv-jiozun.xyz:29444/article/manager/6a329de9887a9b338e851fd5?url=dgd": ("投资创造", "four"),
    "https://knfoaep.ivqs8-1depw-yoirtw.xyz:29444/article/manager/6a095494291caff3edcb8a59?url=lf": ("宝贝花园", "four"),
    "https://mbsqhpk.8ivvt-u3cx5-enwlld.xyz:29400/article/manager/6a33d03ddfa16552b923d05c?url=lhzj": ("醉梦人生", "four"),
    "https://mbsqhpk.8ivvt-u3cx5-enwlld.xyz:29400/article/manager/6a33d060dfa16552b923d061?url=lhzj": ("战胜澳彩", "single"),
    "https://rmpsmal.hi84f-zpj90-mvqksp.xyz:29477/article/manager/6a32717e621d58df1e1bbfc2?url=jfh": ("云过天空", "four"),
    "https://xjsjbkv.b3e4x-wxhjo-lbdbjg.xyz:29477/article/manager/6a323b97f21d7a093399eeeb?url=jbx": ("黑白分明", "single"),
    "https://xjsjbkv.b3e4x-wxhjo-lbdbjg.xyz:29477/article/manager/6a324f8ad2455bc872d9a63f?url=jbx": ("四海兄弟", "single"),
    "https://xjsjbkv.b3e4x-wxhjo-lbdbjg.xyz:29477/article/manager/6a397a60018539c611cb8977?url=jbx": ("夹枪带棒", "single"),
    "https://xjsjbkv.b3e4x-wxhjo-lbdbjg.xyz:29477/article/manager/6a451a5157dc857ae1be5256?url=jbx": ("财到来料", "single"),
    "https://xjsjbkv.b3e4x-wxhjo-lbdbjg.xyz:29477/article/manager/6a326fedc50767750c400757?url=jbx": ("兰韵犹芳", "single"),
    "https://wigrzse.3acpt-tc9xa-kzxasm.xyz:29444/article/manager/6a20da1dca6da63e15d01fc8?url=pg": ("典则俊雅", "single"),
}


SITE_CURRENT_BLOCK_ANCHORS: dict[str, re.Pattern[str]] = {
    "https://993345.com/gsb1.aspx?id=1482": re.compile(r"天下无双.*必杀\s*一\s*行"),
    "https://yylxuru.en4hs-c1zt6-qzcdin.xyz:16677/": re.compile(r"▼\s*绝杀\s*一\s*行\s*▼"),
    "https://ekhivjcg.llnnt-l11x5-bywtoe.xyz:16677/topic/469882.html": re.compile(r"损人利己.*发文"),
    "https://useaul.z3rj5-9jlwg-dynocd.xyz:16677/topic/384879.html": re.compile(r"满汉全席.*发文"),
    "https://zqliou.kify1-fbyi6-lmeykn.xyz:16677/": re.compile(r"澳门信封论坛.*绝杀\s*一\s*行"),
    "https://huqtzej.vvlq2-j4i8n-lisghq.xyz:16677/": re.compile(r"藏宝图\s*稳杀\s*一\s*行"),
    "https://myvvqq.30dok-2s9fd-bibfmg.work/": re.compile(r"一身仙气\s*[（(]\s*绝杀\s*一\s*行\s*[)）]"),
    "https://nyekjhvz.kr4ar-cgeaj-aekfox.xyz:16677/": re.compile(r"澳门创富\s*『绝杀一行』"),
    "https://e7rzi6.t5ti5-at6k5-fugxpa.work/topic/469841.html": re.compile(r"特料帖\s*\d+期.{0,80}?作者\s*[:：]\s*桃李不言"),
    "https://e7rzi6.t5ti5-at6k5-fugxpa.work/topic/227015.html": re.compile(r"绝杀料\s*\d+期.{0,80}?作者\s*[:：]\s*同心叶力"),
    "https://zcphjs.ce83x-ms2rz-orwude.work:12277/#/users/3475": re.compile(r"随便项链\s+\d{4}-\d{2}-\d{2}.{0,80}?\d+\s+绝杀一行\s+澳彩"),
    "https://zcphjs.ce83x-ms2rz-orwude.work:12277/#/users/3031": re.compile(r"可[爱怕]孤儿\s+\d{4}-\d{2}-\d{2}.{0,80}?\d+\s+绝杀一行\s+澳彩"),
    "https://zcphjs.ce83x-ms2rz-orwude.work:12277/#/users/116157": re.compile(
        r"笨鸟先飞a?\s+\d{4}-\d{2}-\d{2}.{0,80}?\d+\s+\d+期.{0,80}?绝杀一行.{0,80}?澳彩"
    ),
    "https://jldzuea.0xkqd-q7ng5-boerfb.xyz:16677/topic/677608.html": re.compile(r"\d+期\s*[:：]\s*精品推荐.{0,120}?发表于"),
    "https://fzzmqscl.bdppk-lyf4y-teyajr.xyz:16677/topic/439186.html": re.compile(r"高手贴\s*\d+期.{0,80}?绝杀一行.{0,80}?作者\s*[:：]\s*信口雌黄"),
    "https://swnrapsd.74wyl-mm601-cbpzhn.xyz:16677/": re.compile(r"百万资料库.{0,120}?\d+期\s*稳杀\s*[（(]?\s*1\s*[)）]?\s*行"),
    "https://cwaskgxv.hzpd5-2r09a-wieopn.xyz:16677/topic/282016.html": re.compile(r"\d+期.{0,50}?绝杀一行.{0,50}?已公开\s*猪狗不如\s*发表于"),
    "https://dzuojaf.rua12-mwvo8-oriqfc.xyz:16677/topic/461725.html": re.compile(r"精华料\s*\d+期.{0,50}?必杀一行.{0,50}?而立之年\s*发表于"),
    "https://ykeejph.z9koz-18xjn-pvglgy.xyz:16677/topic/677751.html": re.compile(r"\d+期\s*歧路亡羊.{0,80}?绝杀一行.{0,80}?歧路亡羊\s*发表于"),
    "https://evvuoswc.2n3pw-mjk5d-wndmjh.xyz:16677/topic/287366.html": re.compile(r"\d+期.{0,30}?浮生未歇.{0,50}?绝杀一行.{0,50}?浮生未歇\s*发表于"),
    "https://cwdcaqzn.7mj0h-75k3q-cbuvqb.work:16677/#am": re.compile(r"八级心动.{0,40}?绝杀\s*一\s*行"),
    "https://fhktrabu.zbfrm-uzct1-pmycbu.xyz:16677/topic/469065.html": re.compile(r"\d+期.{0,80}?绝杀一行.{0,80}?异口同声\s*发表于"),
    "https://eebysckd.2go6k-y0pfv-fqbdsm.xyz:16677/topic/626101.html": re.compile(r"\d+期\s*[:：]\s*提心吊胆.{0,50}?精杀一行.{0,50}?提心吊胆\s*发表于"),
    "https://hhsmgw.rcl5b-akta2-ylzzwv.xyz:16677/topic/282006.html": re.compile(r"\d+期.{0,50}?绝杀一行.{0,50}?已公开\s*迷迷糊糊\s*发表于"),
}


LONGEST_AUTHORITATIVE_BLOCK_URLS = {
    "https://myvvqq.30dok-2s9fd-bibfmg.work/",
}


HEADER_PERIOD_CYCLE_URLS = {
    "https://jldzuea.0xkqd-q7ng5-boerfb.xyz:16677/topic/677608.html",
    "https://fzzmqscl.bdppk-lyf4y-teyajr.xyz:16677/topic/439186.html",
    "https://fhktrabu.zbfrm-uzct1-pmycbu.xyz:16677/topic/469065.html",
}


SITE_CURRENT_BLOCK_ROW_RE = re.compile(
    rf"(?P<period>\d{{1,4}})\s*期(?:(?!\d{{1,4}}\s*期).){{0,35}}?(?:绝|必|精|稳)?\s*杀\s*[\(（]?\s*{ONE_MARKER}\s*[\)）]?\s*行"
    r"(?:(?!\d{1,4}\s*期).){0,35}?[【\[\(（《〖]\s*(?:杀)?\s*(?P<wuxing>[金木水火土])\s*(?:行)?\s*[】\]\)）》〗]"
)


SITE_CURRENT_BLOCK_BOUNDARY_RE = re.compile(
    r"旧(?:附加脚本|帖子|栏目)|(?:上一篇|下一篇|相关推荐|推荐阅读|推荐栏目)\s*[:：]|返回列表"
)


SITE_SPECIFIC_ONLY_URLS = SITE_SPECIFIC_POSITION_RULE_URLS | set(SITE_CURRENT_BLOCK_ANCHORS) | {
    "https://buzfwpox.pwp8o-vfhi5-xmrytn.xyz:16677/topic/464877.html",
    "https://pxgaayml.2wyk5-dwn70-cljflt.xyz:16677/topic/458324.html",
    "https://buvwlreg.drr11-soh5x-jcaafg.xyz:16677/",
    "https://jdjzpkce.osyaf-gxlte-otlblr.xyz:16677/",
} | CHUNMAN_SHANSHUI_URLS | set(MANAGER_ARTICLE_SITE_RULES)


@dataclass(frozen=True)
class Site:
    url: str
    pick: str
    click_first: bool = False
    name: str = ""
    api_url: str = ""


@dataclass(frozen=True)
class Candidate:
    period: str
    wuxing: str
    order: int
    raw: str


def spa_user_id_from_url(url: str) -> str | None:
    match = re.search(r"^/users/(\d+)(?:$|[/?#])", urlparse(url).fragment)
    return match.group(1) if match else None


def site_uses_spa_api_first(site: Site) -> bool:
    return spa_user_id_from_url(site.url) is not None


def normalize_text(text: str) -> str:
    text = html.unescape(text)
    replacements = {
        "\r": "\n",
        "\xa0": " ",
        "\u3000": " ",
        "［": "[",
        "］": "]",
        "﹙": "(",
        "﹚": ")",
        "①": "1",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return re.sub(r"[ \t]+", " ", text)


def html_to_text(document: str) -> str:
    if BeautifulSoup is not None:
        soup = BeautifulSoup(document, "html.parser")
        return normalize_text(soup.get_text("\n"))
    text = TAG_RE.sub("\n", document)
    return normalize_text(text)


def clean_line(text: str) -> str:
    return re.sub(r"\s+", " ", normalize_text(text)).strip()


def text_lines(document: str) -> list[str]:
    return [line for line in (clean_line(line) for line in html_to_text(document).splitlines()) if line]


def parse_raw_candidates(document: str) -> list[Candidate]:
    candidates: list[Candidate] = parse_highlighted_four_wuxing_candidates(document)
    seen: set[tuple[str, str, str]] = set()
    for candidate in candidates:
        seen.add((candidate.period, candidate.wuxing, candidate.raw))
    lines = text_lines(document)

    for index, line in enumerate(lines):
        period_match = PERIOD_RE.search(line)
        if not period_match:
            continue

        block_lines = [line]
        for follow_index in range(index + 1, min(len(lines), index + 8)):
            if PERIOD_RE.search(lines[follow_index]):
                break
            if NOISE_SECTION_RE.search(lines[follow_index]):
                break
            block_lines.append(lines[follow_index])

        block_text = clean_line(" ".join(block_lines))
        wuxing = extract_precise_wuxing_from_block(block_lines)
        if not wuxing:
            continue
        period = f"{int(period_match.group(1))}期"
        key = (period, wuxing, block_text)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(Candidate(period=period, wuxing=wuxing, order=index, raw=block_text))

    return dedupe_candidates_only(candidates)


def parse_highlighted_four_wuxing_candidates(
    document: str,
    include_first_without_highlight: bool = False,
) -> list[Candidate]:
    if "五表主四行" not in document or BeautifulSoup is None:
        return []

    candidates: list[Candidate] = []
    in_section = False
    for index, element in enumerate(BeautifulSoup(document, "html.parser").find_all(["p", "div", "td"])):
        line = clean_line(element.get_text(""))
        if not line:
            continue
        if "五表主四行" in line:
            in_section = True
            continue
        if in_section and "表主" in line and "五表主四行" not in line and candidates:
            break
        if not in_section:
            continue

        period_match = PERIOD_RE.search(line)
        if not period_match:
            continue
        highlighted: list[str] = []
        for span in element.find_all("span"):
            style = (span.get("style") or "").lower().replace(" ", "")
            text = clean_line(span.get_text(""))
            if "background-color:#ffff00" in style and re.fullmatch(r"[金木水火土]", text):
                highlighted.append(text)
        if len(highlighted) == 1:
            wuxing_char = highlighted[0]
        elif include_first_without_highlight:
            bracket_match = BRACKET_WUXING_RE.search(line)
            chars = re.findall(r"[金木水火土]", bracket_match.group(1) if bracket_match else "")
            if not chars:
                continue
            wuxing_char = chars[0]
        else:
            continue
        period = f"{int(period_match.group(1))}期"
        candidates.append(
            Candidate(
                period=period,
                wuxing=f"{wuxing_char}行",
                order=index,
                raw=f"五表主四行 {line}",
            )
        )

    return dedupe_candidates_only(candidates)


def parse_white_swan_candidates(document: str) -> list[Candidate]:
    candidates: list[Candidate] = []
    lines = text_lines(document)
    for index, line in enumerate(lines):
        if "四行中特" not in line or "⊙" not in line:
            if "四行中特" not in line:
                continue
            block_lines = [line]
            for follow in lines[index + 1 : index + 8]:
                if PERIOD_RE.search(follow):
                    break
                block_lines.append(follow)
                if "开" in follow:
                    break
            line = clean_line(" ".join(block_lines))
        period_match = PERIOD_RE.search(line)
        if not period_match:
            continue
        circle_match = re.search(r"[⊙◎]\s*([金木水火土][金木水火土\s.、，/]{1,12}[金木水火土])\s*[⊙◎]", line)
        if not circle_match:
            continue
        chars = re.findall(r"[金木水火土]", circle_match.group(1))
        if len(chars) == 3:
            wuxing_char = chars[-1]
        elif len(chars) >= 4:
            wuxing_char = chars[0]
        else:
            continue
        period_number = int(period_match.group(1))
        period = f"{period_number}期"
        candidates.append(Candidate(period=period, wuxing=f"{wuxing_char}行", order=-period_number, raw=line))
    return dedupe_candidates_only(candidates)


def section_lines(document: str, start_marker: str, stop_markers: Iterable[str] = ()) -> list[tuple[int, str]]:
    lines = text_lines(document)
    section: list[tuple[int, str]] = []
    in_section = False
    for index, line in enumerate(lines):
        if start_marker in line:
            in_section = True
        elif in_section and any(marker in line for marker in stop_markers):
            break
        if in_section:
            section.append((index, line))
    return section


def parse_yibenwanli_candidates(document: str) -> list[Candidate]:
    candidates: list[Candidate] = []
    lines = text_lines(document)
    for index, line in enumerate(lines):
        period_match = PERIOD_RE.search(line)
        if not period_match:
            continue
        block_lines = [line]
        has_target_keyword = any(keyword in line for keyword in ("绝杀一行", "死禁一行"))
        for follow in lines[index + 1 : min(len(lines), index + 8)]:
            if PERIOD_RE.search(follow):
                break
            block_lines.append(follow)
            has_target_keyword = has_target_keyword or any(
                keyword in follow for keyword in ("绝杀一行", "死禁一行")
            )
            if re.fullmatch(r"[【\[]\s*[金木水火土]\s*[】\]]", follow.strip()):
                break
        if not has_target_keyword:
            continue
        block_text = clean_line(" ".join(block_lines))
        wuxing_match = re.search(r"[【\[]\s*(?P<wuxing>[金木水火土])\s*[】\]]", block_text)
        if not wuxing_match:
            continue
        period = f"{int(period_match.group(1))}期"
        candidates.append(
            Candidate(period=period, wuxing=f"{wuxing_match.group('wuxing')}行", order=index, raw=block_text)
        )
    return dedupe_candidates_only(candidates)


def parse_screenshot_section_candidates(
    document: str,
    title_pattern: re.Pattern[str],
    row_pattern: re.Pattern[str],
    reverse_period_order: bool = False,
    max_section_lines: int = 24,
) -> list[Candidate]:
    candidates: list[Candidate] = []
    section_start_index: int | None = None
    for index, line in enumerate(text_lines(document)):
        if section_start_index is None and title_pattern.search(line):
            section_start_index = index
        if section_start_index is None:
            continue
        if index - section_start_index > max_section_lines:
            break
        if index and ("上一篇" in line or "下一篇" in line or "点击投注" in line or "2026年五行" in line):
            break
        match = row_pattern.search(line)
        if not match:
            continue
        period_number = int(match.group("period"))
        candidates.append(
            Candidate(
                period=f"{period_number}期",
                wuxing=f"{match.group('wuxing')}行",
                order=period_number if reverse_period_order else index,
                raw=line,
            )
        )
    return dedupe_candidates_only(candidates)


SCREENSHOT_ONE_LINE_ROW_RE = re.compile(
    rf"(?P<period>\d{{1,4}})\s*期.*?(?:绝\s*杀|必\s*杀|稳\s*杀)\s*[（(【\[]?\s*{ONE_MARKER}\s*[)）】\]]?\s*行.*?"
    r"[【\[〖《]\s*(?:杀)?\s*(?P<wuxing>[金木水火土])\s*(?:行)?\s*[】\]〗》]"
)


SCREENSHOT_ABSOLUTE_ONE_LINE_ROW_RE = re.compile(
    rf"(?P<period>\d{{1,4}})\s*期.*?绝\s*杀\s*[（(【\[]?\s*{ONE_MARKER}\s*[)）】\]]?\s*行.*?"
    r"[【\[〖《]\s*(?:杀)?\s*(?P<wuxing>[金木水火土])\s*(?:行)?\s*[】\]〗》]"
)


SCREENSHOT_STABLE_ONE_LINE_ROW_RE = re.compile(
    rf"(?P<period>\d{{1,4}})\s*期.*?稳\s*杀\s*[（(【\[]?\s*{ONE_MARKER}\s*[)）】\]]?\s*行.*?"
    r"[【\[〖《]\s*(?:杀)?\s*(?P<wuxing>[金木水火土])\s*(?:行)?\s*[】\]〗》]"
)


def parse_named_screenshot_candidates(
    document: str,
    title_pattern: re.Pattern[str],
    row_pattern: re.Pattern[str],
    require_title: bool = False,
    max_section_lines: int = 24,
) -> list[Candidate]:
    lines = text_lines(document)
    title_index = next(
        (index for index, line in enumerate(lines) if title_pattern.search(line)),
        None,
    )
    if require_title and title_index is None:
        return []
    start_index = title_index or 0
    candidates: list[Candidate] = []
    for index in range(start_index, len(lines)):
        if title_index is not None and index - start_index > max_section_lines:
            break
        line = lines[index]
        if index and any(marker in line for marker in ("上一篇", "下一篇", "点击投注", "2026年五行")):
            break
        if not PERIOD_RE.search(line):
            continue
        block_lines = [line]
        for follow in lines[index + 1 : min(len(lines), index + 8)]:
            if PERIOD_RE.search(follow):
                break
            if any(marker in follow for marker in ("上一篇", "下一篇", "点击投注", "2026年五行")):
                break
            block_lines.append(follow)
            if row_pattern.search(clean_line(" ".join(block_lines))):
                break
        block_text = clean_line(" ".join(block_lines))
        match = row_pattern.search(block_text)
        if not match:
            continue
        period_number = int(match.group("period"))
        candidates.append(
            Candidate(
                period=f"{period_number}期",
                wuxing=f"{match.group('wuxing')}行",
                order=index,
                raw=block_text,
            )
        )
    return dedupe_candidates_only(candidates)


def parse_tianxiawushuang_candidates(document: str) -> list[Candidate]:
    split_rows = parse_named_screenshot_candidates(
        document,
        re.compile(r"天下无双.*必杀\s*一\s*行"),
        SCREENSHOT_ONE_LINE_ROW_RE,
        require_title=True,
        max_section_lines=160,
    )
    return dedupe_candidates_only(
        Candidate(
            candidate.period,
            candidate.wuxing,
            int(candidate.period.removesuffix("期")),
            candidate.raw,
        )
        for candidate in split_rows
    )


def parse_aomenjingdiaotong_candidates(document: str) -> list[Candidate]:
    return parse_screenshot_section_candidates(
        document, re.compile(r"(?:澳门)?金吊桶.*绝杀\s*一\s*行|▼\s*绝杀\s*一\s*行\s*▼"), SCREENSHOT_ONE_LINE_ROW_RE
    )


def parse_sunrenliji_candidates(document: str) -> list[Candidate]:
    return parse_named_screenshot_candidates(document, re.compile(r"损人利己"), SCREENSHOT_ABSOLUTE_ONE_LINE_ROW_RE)


def parse_feipuliuquan_candidates(document: str) -> list[Candidate]:
    return parse_named_screenshot_candidates(document, re.compile(r"飞瀑流泉"), SCREENSHOT_STABLE_ONE_LINE_ROW_RE)


def parse_baofengzhouyu_candidates(document: str) -> list[Candidate]:
    return parse_named_screenshot_candidates(
        document,
        re.compile(r"高等帖|暴风骤雨"),
        SCREENSHOT_ABSOLUTE_ONE_LINE_ROW_RE,
        require_title=True,
    )


def parse_babumaoge_candidates(document: str) -> list[Candidate]:
    return parse_named_screenshot_candidates(
        document,
        re.compile(r"八步毛哥\s*[【\[]\s*必\s*杀\s*一\s*行\s*[】\]]"),
        SCREENSHOT_ONE_LINE_ROW_RE,
        require_title=True,
    )


SUNRENLIJI_HEADER_PERIOD_PATTERNS = (
    re.compile(r"(?:特码料|损人利己).*?(?P<period>\d{1,4})\s*期.*?绝\s*杀\s*一\s*行"),
    re.compile(r"(?P<period>\d{1,4})\s*期.*?绝\s*杀\s*一\s*行.*?损人利己"),
)


def sunrenliji_authoritative_documents(
    documents: Iterable[str],
    parser_fn=None,
) -> list[str]:
    documents = list(documents)
    if parser_fn is None:
        parser_fn = parse_candidates
    parsed_cache: dict[str, tuple[Candidate, ...]] = {}

    def candidates_for(document: str) -> list[Candidate]:
        cached = parsed_cache.get(document)
        if cached is None:
            cached = tuple(filter_valid_wuxing_candidates(parser_fn(document)))
            parsed_cache[document] = cached
        return list(cached)

    header_matches: list[tuple[int, int]] = []
    for index, document in enumerate(documents):
        text = clean_line(html_to_text(document))
        for pattern in SUNRENLIJI_HEADER_PERIOD_PATTERNS:
            match = pattern.search(text)
            if match:
                header_matches.append((index, int(match.group("period"))))
                break
    header_periods = {period for _, period in header_matches}
    if len(header_periods) != 1:
        return []

    header_period = f"{next(iter(header_periods))}期"
    standalone_headers = [index for index, _ in header_matches if not candidates_for(documents[index])]
    if standalone_headers:
        bound_documents: list[str] = []
        for header_index in standalone_headers:
            for document in documents[header_index + 1 : header_index + 4]:
                candidates = candidates_for(document)
                if candidates and candidates[0].period == header_period:
                    if document not in bound_documents:
                        bound_documents.append(document)
                    break
        return bound_documents

    self_contained = [
        documents[index]
        for index, _ in header_matches
        if candidates_for(documents[index]) and candidates_for(documents[index])[0].period == header_period
    ]
    return self_contained if len(self_contained) == 1 else []


def parse_manhquanxi_candidates(document: str) -> list[Candidate]:
    lines = text_lines(document)
    section_start = re.compile(r"满汉全席.*发文|\d+期.*绝杀\s*一\s*行")
    start_index = next((index for index, line in enumerate(lines) if section_start.search(line)), None)
    if start_index is None:
        return []

    candidates: list[Candidate] = []
    for index in range(start_index, min(len(lines), start_index + 25)):
        line = lines[index]
        if index > start_index and any(marker in line for marker in ("上一篇", "下一篇", "点击投注", "2026年五行")):
            break
        if not PERIOD_RE.search(line):
            continue
        block_lines = [line]
        for follow in lines[index + 1 : min(len(lines), index + 8)]:
            if PERIOD_RE.search(follow):
                break
            if any(marker in follow for marker in ("上一篇", "下一篇", "点击投注", "2026年五行")):
                break
            block_lines.append(follow)
        match = SCREENSHOT_ONE_LINE_ROW_RE.search(clean_line(" ".join(block_lines)))
        if not match:
            continue
        candidates.append(
            Candidate(
                period=f"{int(match.group('period'))}期",
                wuxing=f"{match.group('wuxing')}行",
                order=index,
                raw=clean_line(" ".join(block_lines)),
            )
        )
    return dedupe_candidates_only(candidates)


def parse_xinfengluntan_candidates(document: str) -> list[Candidate]:
    title_pattern = re.compile(r"澳门信封论坛.*绝\s*杀\s*一\s*行")
    row_pattern = re.compile(
        rf"(?P<period>\d{{1,4}})\s*期\s*[:：]?\s*[【\[]\s*绝\s*杀\s*{ONE_MARKER}\s*行\s*[】\]]\s*"
        rf"[【\[]\s*(?P<wuxing>[金木水火土])\s*行\s*[】\]]"
    )
    candidates: list[Candidate] = []
    lines = text_lines(document)
    title_index = next(
        (
            index
            for index in range(len(lines))
            if title_pattern.search(" ".join(lines[index : index + 3]))
        ),
        None,
    )
    if title_index is None:
        return []
    title_end_index = next(
        (
            index
            for index in range(title_index, min(len(lines), title_index + 3))
            if re.search(r"绝\s*杀\s*一\s*行", lines[index])
        ),
        title_index,
    )
    for index, line in enumerate(lines[title_end_index + 1 :], title_end_index + 1):
        if "澳门信封论坛" in line or any(marker in line for marker in ("上一篇", "下一篇", "点击投注")):
            break
        if not PERIOD_RE.search(line):
            continue
        block_lines = [line]
        for follow in lines[index + 1 : min(len(lines), index + 5)]:
            if PERIOD_RE.search(follow) or "澳门信封论坛" in follow:
                break
            block_lines.append(follow)
        block_text = clean_line(" ".join(block_lines))
        match = row_pattern.search(block_text)
        if not match:
            continue
        candidates.append(
            Candidate(
                f"{int(match.group('period'))}期",
                f"{match.group('wuxing')}行",
                index,
                block_text,
            )
        )
    return dedupe_candidates_only(candidates)


def parse_yirujiwang_candidates(document: str) -> list[Candidate]:
    row_pattern = re.compile(
        rf"(?P<period>\d{{1,4}})\s*期\s*精\s*杀\s*{ONE_MARKER}\s*行\s*"
        r"[【\[]\s*(?P<wuxing>[金木水火土])\s*行\s*[】\]]"
    )
    lines = text_lines(document)
    author_index = next(
        (
            index
            for index, line in enumerate(lines)
            if re.search(r"一如既往\s*发表于", line)
        ),
        None,
    )
    if author_index is not None:
        lines = lines[author_index + 1 :]
    candidates: list[Candidate] = []
    previous_period: int | None = None
    for index, line in enumerate(lines):
        matches = list(row_pattern.finditer(line))
        for match in matches:
            period_number = int(match.group("period"))
            if previous_period is not None:
                if period_number == previous_period:
                    # Keep same-period rows so the caller can reject a real conflict.
                    pass
                elif period_number == previous_period - 1:
                    previous_period = period_number
                else:
                    # A non-contiguous period marks the next article/section in an
                    # aggregated response; never let its rows enter this article.
                    return dedupe_candidates_only(candidates)
            else:
                previous_period = period_number
            candidates.append(
                Candidate(
                    f"{period_number}期",
                    f"{match.group('wuxing')}行",
                    index,
                    clean_line(line),
                )
            )
    return dedupe_candidates_only(candidates)


def yirujiwang_authoritative_documents(
    documents: Iterable[str],
    period: int | None = None,
) -> list[str]:
    documents = list(documents)
    authoritative: list[tuple[int, int, str]] = []
    target = f"{period}期" if period is not None else None
    for index, document in enumerate(documents):
        text = clean_line(html_to_text(document))
        if not re.search(r"一如既往\s*发表于", text):
            continue
        document_without_scripts = re.sub(
            r"<script\b[^>]*>.*?</script>",
            "",
            document,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if re.search(r"document\.writeln|utf8to16|strdecode", document_without_scripts):
            continue
        candidates = parse_yirujiwang_candidates(document)
        if not candidates:
            continue
        if target is not None and not any(candidate.period == target for candidate in candidates):
            continue
        authoritative.append((len(candidates), index, document))
    if authoritative:
        return [min(authoritative, key=lambda item: (item[0], item[1]))[2]]
    if period is not None:
        return []
    return documents


def parse_bajixixindong_candidates(document: str) -> list[Candidate]:
    current_row_pattern = re.compile(
        rf"(?P<period>\d{{1,4}})\s*期\s*绝\s*杀\s*{ONE_MARKER}\s*行\s*"
        r"[【\[]\s*(?P<wuxing>[金木水火土])\s*行\s*[】\]]"
    )
    legacy_row_pattern = re.compile(
        rf"(?P<period>\d{{1,4}})\s*期\s*[;；:]?\s*绝\s*杀\s*{ONE_MARKER}\s*行\s*"
        r"[：:]?\s*[（(]\s*(?P<wuxing>[金木水火土])\s*[）)]"
    )
    candidates: list[Candidate] = []
    lines = text_lines(document)
    has_own_section = any(re.search(r"八级心动.{0,40}?绝杀\s*一\s*行", line) for line in lines)
    row_patterns = (current_row_pattern,) if has_own_section else (current_row_pattern, legacy_row_pattern)
    for index, line in enumerate(lines):
        match = next((pattern.search(line) for pattern in row_patterns if pattern.search(line)), None)
        if not match:
            continue
        candidates.append(
            Candidate(
                f"{int(match.group('period'))}期",
                f"{match.group('wuxing')}行",
                index,
                clean_line(line),
            )
        )
    return dedupe_candidates_only(candidates)


def parse_baiwanziliao_candidates(document: str) -> list[Candidate]:
    candidates: list[Candidate] = []
    for index, line in enumerate(text_lines(document)):
        match = re.search(
            rf"(?P<period>\d{{1,4}})\s*期\s*稳杀\s*[（(]?\s*{ONE_MARKER}\s*[)）]?\s*行\s*"
            r"[【\[]\s*(?P<wuxing>[金木水火土])\s*[】\]]",
            line,
        )
        if match:
            candidates.append(Candidate(f"{int(match.group('period'))}期", f"{match.group('wuxing')}行", index, line))
    return dedupe_candidates_only(candidates)


def parse_chunmanxiangcun_candidates(document: str) -> list[Candidate]:
    candidates: list[Candidate] = []
    for index, line in section_lines(document, "春满乡村", ("山水诗意",)):
        match = re.search(
            r"(?P<period>\d{1,4})\s*期\s*绝\s*杀\s*1\s*[.。．、]?\s*行\s*[【\[]\s*(?P<wuxing>[金木水火土])(?P=wuxing){2}\s*[】\]]",
            line,
        )
        if not match:
            continue
        period = f"{int(match.group('period'))}期"
        candidates.append(Candidate(period=period, wuxing=f"{match.group('wuxing')}行", order=index, raw=line))
    return dedupe_candidates_only(candidates)


def parse_shanshuishiyi_candidates(document: str) -> list[Candidate]:
    candidates: list[Candidate] = []
    lines = section_lines(document, "山水诗意")
    for section_index, (index, line) in enumerate(lines):
        if section_index and TARGET_SECTION_RE.search(line) and "四行中特" not in line:
            break
        if "四行中特" not in line:
            continue
        block_lines = [line]
        for _, follow in lines[section_index + 1 : section_index + 10]:
            if PERIOD_RE.search(follow):
                break
            block_lines.append(follow)
            if block_lines.count("⊙") >= 2 or block_lines.count("◎") >= 2 or "开" in follow:
                break
        block_text = clean_line(" ".join(block_lines))
        period_match = PERIOD_RE.search(block_text)
        if not period_match:
            continue
        circle_match = re.search(r"[⊙◎]\s*([金木水火土][金木水火土\s.、，/]{2,12})\s*[⊙◎]", block_text)
        if not circle_match:
            continue
        chars = re.findall(r"[金木水火土]", circle_match.group(1))
        if len(chars) != 4 or len(set(chars)) != 4:
            continue
        missing = [char for char in "金木水火土" if char not in chars]
        if len(missing) != 1:
            continue
        wuxing = f"{missing[0]}行"
        period = f"{int(period_match.group(1))}期"
        candidates.append(Candidate(period=period, wuxing=wuxing, order=index, raw=block_text))
    return dedupe_candidates_only(candidates)


def parse_zhugeshentong_candidates(document: str) -> list[Candidate]:
    candidates: list[Candidate] = []
    for index, line in enumerate(text_lines(document)):
        if "诸葛神通" not in line or "四行中特" not in line:
            continue
        period_match = PERIOD_RE.search(line)
        if not period_match:
            continue
        wuxing = extract_precise_wuxing_from_block([line])
        if not wuxing:
            continue
        period = f"{int(period_match.group(1))}期"
        candidates.append(Candidate(period=period, wuxing=wuxing, order=index, raw=line))
    return dedupe_candidates_only(candidates)


def parse_pingtewangxin_candidates(document: str) -> list[Candidate]:
    candidates: list[Candidate] = []
    for line in text_lines(document):
        match = re.search(
            rf"(?P<period>\d{{1,4}})\s*期\s*[:：]?\s*绝\s*杀\s*[\(（]?\s*{ONE_MARKER}\s*[\)）]?\s*行\s*[【\[]\s*(?P<wuxing>[金木水火土])\s*行\s*[】\]]",
            line,
        )
        if not match:
            continue
        period_number = int(match.group("period"))
        candidates.append(
            Candidate(
                period=f"{period_number}期",
                wuxing=f"{match.group('wuxing')}行",
                order=period_number,
                raw=clean_line(line),
            )
        )
    return dedupe_candidates_only(candidates)


def parse_candidates(document: str) -> list[Candidate]:
    candidates = parse_raw_candidates(document)
    return dedupe_and_filter_candidates(candidates)


def dedupe_and_filter_candidates(candidates: list[Candidate]) -> list[Candidate]:
    if not candidates:
        return []
    unique: list[Candidate] = []
    seen: set[tuple[str, str, str]] = set()
    for candidate in candidates:
        key = (candidate.period, candidate.wuxing, candidate.raw)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return sorted(unique, key=lambda item: item.order)


def dedupe_candidates_only(candidates: list[Candidate]) -> list[Candidate]:
    unique: list[Candidate] = []
    seen: set[tuple[str, str, str]] = set()
    for candidate in candidates:
        key = (candidate.period, candidate.wuxing, candidate.raw)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return sorted(unique, key=lambda item: item.order)


def keep_latest_same_period_wuxing(candidates: list[Candidate]) -> list[Candidate]:
    """Keep every position; duplicate evidence is resolved by shared validation."""
    return sorted(candidates, key=lambda item: item.order)


def parse_current_site_block_candidates(document: str, anchor: re.Pattern[str]) -> list[Candidate]:
    text = clean_line(html_to_text(document))
    anchor_match = anchor.search(text)
    if not anchor_match:
        return []

    candidates: list[Candidate] = []
    direction = 0
    last_period: int | None = None
    last_match_end = anchor_match.end()
    for order, match in enumerate(SITE_CURRENT_BLOCK_ROW_RE.finditer(text, anchor_match.start())):
        period_number = int(match.group("period"))
        wuxing = f"{match.group('wuxing')}行"
        if last_period is not None:
            delta = period_number - last_period
            if delta == 0:
                gap = text[last_match_end : match.start()]
                if direction and SITE_CURRENT_BLOCK_BOUNDARY_RE.search(gap):
                    break
                candidates.append(
                    Candidate(
                        period=f"{period_number}期",
                        wuxing=wuxing,
                        order=order,
                        raw=clean_line(match.group(0)),
                    )
                )
                last_match_end = match.end()
                continue
            current_direction = 1 if delta > 0 else -1
            if direction and current_direction != direction:
                break
            direction = current_direction
        candidates.append(
            Candidate(
                period=f"{period_number}期",
                wuxing=wuxing,
                order=order,
                raw=clean_line(match.group(0)),
            )
        )
        last_period = period_number
        last_match_end = match.end()
    return candidates


def parse_header_period_cycle_candidates(document: str, anchor: re.Pattern[str]) -> list[Candidate]:
    text = clean_line(html_to_text(document))
    anchor_match = anchor.search(text)
    if not anchor_match:
        return []
    header_period_match = PERIOD_RE.search(anchor_match.group(0))
    if not header_period_match:
        return []
    header_period = int(header_period_match.group(1))

    segments: list[list[Candidate]] = []
    current: list[Candidate] = []
    last_period: int | None = None
    last_match_end = anchor_match.end()
    for order, match in enumerate(SITE_CURRENT_BLOCK_ROW_RE.finditer(text, anchor_match.start())):
        period_number = int(match.group("period"))
        gap = text[last_match_end : match.start()]
        if current and SITE_CURRENT_BLOCK_BOUNDARY_RE.search(gap):
            segments.append(current)
            current = []
            break
        if last_period is not None and period_number < last_period:
            if current:
                segments.append(current)
            current = []
        current.append(
            Candidate(
                period=f"{period_number}期",
                wuxing=f"{match.group('wuxing')}行",
                order=order,
                raw=clean_line(match.group(0)),
            )
        )
        last_period = period_number
        last_match_end = match.end()
    if current:
        segments.append(current)

    matching = [segment for segment in segments if int(segment[-1].period[:-1]) == header_period]
    if not matching:
        return []
    selected = matching[-1]
    return [
        Candidate(item.period, item.wuxing, order, item.raw)
        for order, item in enumerate(selected)
    ]


def manager_article_record_lines(document: str) -> list[tuple[int, str]]:
    if BeautifulSoup is None:
        return []
    soup = BeautifulSoup(document, "html.parser")
    parts: list[str] = []
    block_names = {"p", "div", "li", "tr", "table", "section", "article"}

    def append_node(node) -> None:
        name = getattr(node, "name", None)
        if name == "br":
            parts.append("\n")
            return
        if name is None:
            parts.append(str(node))
            return
        if name in block_names:
            parts.append("\n")
        for child in node.children:
            append_node(child)
        if name in block_names:
            parts.append("\n")

    append_node(soup)
    return [
        (index, clean_line(line))
        for index, line in enumerate("".join(parts).splitlines())
        if clean_line(line)
    ]


def exact_manager_name_pattern(name: str) -> re.Pattern[str]:
    escaped = re.escape(name)
    return re.compile(
        rf"(?:[【〖《『]\s*{escaped}\s*[】〗》』]|(?<!\w){escaped}(?!\w))"
    )


def manager_anchor_gap_is_clean(record: str, name_end: int, keyword_start: int) -> bool:
    return keyword_start >= name_end and re.search(r"\w", record[name_end:keyword_start]) is None


def parse_manager_article_candidates(document: str, site: Site) -> list[Candidate]:
    rule = MANAGER_ARTICLE_SITE_RULES.get(site.url)
    if not rule:
        return []
    expected_name, mode = rule
    name_pattern = exact_manager_name_pattern(expected_name)
    candidates: list[Candidate] = []
    for order, record in manager_article_record_lines(document):
        period_match = re.match(r"^\s*(?P<period>\d{1,4})\s*期", record)
        if not period_match or len(PERIOD_RE.findall(record)) != 1:
            continue
        name_match = name_pattern.search(record)
        if not name_match or NOISE_SECTION_RE.search(record):
            continue
        if mode == "four":
            matches = list(re.finditer(
                r"(?<!非)(?:四|4|④)\s*行\s*中\s*特.{0,24}?[【\[（(〖]"
                r"\s*(?P<values>[金木水火土](?:\s*[.、，/]\s*[金木水火土]){3})\s*[】\]）)〗]",
                record,
            ))
            first_target = next(
                (
                    index
                    for index, match in enumerate(matches)
                    if manager_anchor_gap_is_clean(record, name_match.end(), match.start())
                ),
                None,
            )
            if first_target is None:
                continue
            for match in matches[first_target:]:
                values = re.findall(r"[金木水火土]", match.group("values"))
                if len(values) != 4 or len(set(values)) != 4:
                    continue
                missing = [char for char in "金木水火土" if char not in values]
                if len(missing) == 1:
                    candidates.append(
                        Candidate(f"{int(period_match.group('period'))}期", f"{missing[0]}行", order, record)
                    )
        else:
            matches = list(re.finditer(
                rf"(?<!非)绝\s*杀\s*[（(]?\s*{ONE_MARKER}\s*[)）]?\s*行.{{0,24}}?"
                r"[【\[（(〖]\s*(?P<wuxing>[金木水火土])\s*(?:行)?\s*[】\]）)〗]",
                record,
            ))
            first_target = next(
                (
                    index
                    for index, match in enumerate(matches)
                    if manager_anchor_gap_is_clean(record, name_match.end(), match.start())
                ),
                None,
            )
            if first_target is None:
                continue
            for match in matches[first_target:]:
                candidates.append(
                    Candidate(
                        f"{int(period_match.group('period'))}期",
                        f"{match.group('wuxing')}行",
                        order,
                        record,
                    )
                )
    return dedupe_candidates_only(candidates)


def parse_site_specific_candidates(document: str, site: Site) -> list[Candidate]:
    if site.url in MANAGER_ARTICLE_SITE_RULES:
        return parse_manager_article_candidates(document, site)
    if site.url == "https://993345.com/gsb1.aspx?id=1482":
        return parse_tianxiawushuang_candidates(document)
    if site.url == "https://yylxuru.en4hs-c1zt6-qzcdin.xyz:16677/":
        return parse_aomenjingdiaotong_candidates(document)
    if site.url == "https://ekhivjcg.llnnt-l11x5-bywtoe.xyz:16677/topic/469882.html":
        return parse_sunrenliji_candidates(document)
    if site.url == "https://buzfwpox.pwp8o-vfhi5-xmrytn.xyz:16677/topic/464877.html":
        return parse_feipuliuquan_candidates(document)
    if site.url == "https://pxgaayml.2wyk5-dwn70-cljflt.xyz:16677/topic/458324.html":
        return parse_baofengzhouyu_candidates(document)
    if site.url == "https://2.www39169b.com:888/#62111":
        return parse_babumaoge_candidates(document)
    if site.url == "https://swnrapsd.74wyl-mm601-cbpzhn.xyz:16677/":
        return parse_baiwanziliao_candidates(document)
    if site.url == "https://useaul.z3rj5-9jlwg-dynocd.xyz:16677/topic/384879.html":
        return parse_manhquanxi_candidates(document)
    if site.url == "https://zqliou.kify1-fbyi6-lmeykn.xyz:16677/":
        return parse_xinfengluntan_candidates(document)
    if site.url == "https://eebysckd.2go6k-y0pfv-fqbdsm.xyz:16677/topic/626030.html":
        return parse_yirujiwang_candidates(document)
    if site.url == "https://cwdcaqzn.7mj0h-75k3q-cbuvqb.work:16677/#am":
        return parse_bajixixindong_candidates(document)
    current_block_anchor = SITE_CURRENT_BLOCK_ANCHORS.get(site.url)
    if current_block_anchor:
        if site.url in HEADER_PERIOD_CYCLE_URLS:
            current_cycle_candidates = parse_header_period_cycle_candidates(document, current_block_anchor)
            if current_cycle_candidates:
                return current_cycle_candidates
        current_block_candidates = parse_current_site_block_candidates(document, current_block_anchor)
        if current_block_candidates:
            return current_block_candidates
        if site.url == "https://myvvqq.30dok-2s9fd-bibfmg.work/":
            return []
    if site.url == "https://buvwlreg.drr11-soh5x-jcaafg.xyz:16677/":
        return parse_white_swan_candidates(document)
    if site.url == "https://jdjzpkce.osyaf-gxlte-otlblr.xyz:16677/":
        return parse_highlighted_four_wuxing_candidates(document, include_first_without_highlight=True)
    if site.url == "https://mflmcobome.26222hi.app:2569/htm/bbs/top040.html":
        return parse_yibenwanli_candidates(document)
    if site.url == "https://hl.www25195a.com/read.php?tid=607":
        return parse_zhugeshentong_candidates(document)
    if site.url == "https://tulprhfc.wghcb-bnmgm-hyymaz.work:16655/topic/453352.html":
        return parse_pingtewangxin_candidates(document)
    if site.url in CHUNMAN_SHANSHUI_URLS:
        if site.name == "春满乡村":
            return parse_chunmanxiangcun_candidates(document)
        if site.name == "山水诗意":
            return parse_shanshuishiyi_candidates(document)

    patterns = SITE_SPECIFIC_CANDIDATE_PATTERNS.get(site.url, ())
    if not patterns:
        return []

    if site.url in {
        "https://wxaxdfc.523mo-z7mla-owjdon.xyz:16677/",
        "https://swnrapsd.74wyl-mm601-cbpzhn.xyz:16677/",
    }:
        text = clean_line(html_to_text(document))
        candidates = []
        for pattern in patterns:
            for match in pattern.finditer(text):
                candidates.append(
                    Candidate(
                        period=f"{int(match.group('period'))}期",
                        wuxing=f"{match.group('wuxing')}行",
                        order=match.start(),
                        raw=clean_line(match.group(0)),
                    )
                )
        return dedupe_candidates_only(candidates)

    candidates: list[Candidate] = []
    for index, line in enumerate(text_lines(document)):
        for pattern in patterns:
            match = pattern.search(line)
            if not match:
                continue
            period = f"{int(match.group('period'))}期"
            wuxing = f"{match.group('wuxing')}行"
            candidates.append(
                Candidate(period=period, wuxing=wuxing, order=index, raw=clean_line(line))
            )
            break
    candidates = dedupe_candidates_only(candidates)
    if site.url == "https://fzzmqscl.bdppk-lyf4y-teyajr.xyz:16677/topic/439186.html":
        return keep_latest_same_period_wuxing(candidates)

    return candidates


def parse_candidates_for_site(document: str, site: Site) -> list[Candidate]:
    if site_uses_spa_api_first(site) and document.startswith(SPA_STRUCTURED_RECORD_MARKER):
        return parse_current_site_block_candidates(
            document,
            re.compile(re.escape(SPA_STRUCTURED_RECORD_MARKER)),
        )
    site_specific = parse_site_specific_candidates(document, site)
    general = parse_candidates(document)
    if site.url in SITE_SPECIFIC_ONLY_URLS:
        return dedupe_candidates_only(site_specific)
    return dedupe_candidates_only(site_specific + general)


def normalize_wuxing(value: str) -> str:
    value = clean_line(value).replace(" ", "")
    chars = re.findall(r"[金木水火土]", value)
    if not chars:
        return value
    unique_chars = list(dict.fromkeys(chars))
    return "/".join(f"{char}行" for char in unique_chars)


def extract_wuxing_from_text(text: str) -> str | None:
    if "行中特" in text or re.search(r"五\s*[丢表]\s*主\s*四\s*行", text):
        for match in BRACKET_WUXING_RE.finditer(text):
            chars = []
            for char in re.findall(r"[金木水火土]", match.group(1)):
                if char not in chars:
                    chars.append(char)
            if len(chars) == 4:
                missing = [char for char in "金木水火土" if char not in chars]
                if len(missing) == 1:
                    return f"{missing[0]}行"
        for match in re.finditer(r"[⊙◎]\s*([金木水火土][金木水火土\s.、，/]{1,12}[金木水火土])\s*[⊙◎]", text):
            chars = []
            for char in re.findall(r"[金木水火土]", match.group(1)):
                if char not in chars:
                    chars.append(char)
            if len(chars) == 3:
                return f"{chars[-1]}行"
            if len(chars) == 4:
                missing = [char for char in "金木水火土" if char not in chars]
                if len(missing) == 1:
                    return f"{missing[0]}行"
        return None
    bracket_match = BRACKET_WUXING_RE.search(text)
    if bracket_match:
        return normalize_wuxing(bracket_match.group(1))
    loose_bracket_match = re.search(r"[【\[\(（〖]\s*([金木水火土])(?:\s*行)?(?:\s|$)", text)
    if loose_bracket_match:
        return normalize_wuxing(loose_bracket_match.group(1))
    full_match = WUXING_RE.search(text)
    if full_match:
        return normalize_wuxing(full_match.group(1))
    open_match = re.search(r"([金木水火土])\s*[:：]?\s*\d{1,2}\s*(?:准|错|开|$)", text)
    if open_match:
        return normalize_wuxing(open_match.group(1))
    return None


def extract_precise_wuxing_from_line_text(text: str) -> str | None:
    text = clean_line(text)
    bracket_match = BRACKET_WUXING_RE.search(text)
    if bracket_match:
        wuxing = normalize_wuxing(bracket_match.group(1))
        return None if "/" in wuxing else wuxing

    full_line_match = re.fullmatch(r"[【\[\(（〖]?\s*([金木水火土])\s*(?:行)?\s*[】\]\)）〗]?", text)
    if full_line_match:
        return f"{full_line_match.group(1)}行"

    wuxing_match = WUXING_RE.search(text)
    if wuxing_match:
        wuxing = normalize_wuxing(wuxing_match.group(1))
        return None if "/" in wuxing else wuxing
    return None


def extract_precise_wuxing_from_block(block_lines: list[str]) -> str | None:
    block_text = clean_line(" ".join(block_lines))
    target_match = TARGET_SECTION_RE.search(block_text)
    if not target_match or not PERIOD_RE.search(block_text):
        return None

    segment = clean_line(block_text[target_match.start() :])
    if "行中特" in segment or re.search(r"五\s*[丢表]\s*主\s*四\s*行", segment):
        wuxing = extract_wuxing_from_text(block_text)
        return None if not wuxing or "/" in wuxing else wuxing

    target_line_index = None
    for index in range(len(block_lines)):
        window = clean_line(" ".join(block_lines[index : index + 3]))
        if TARGET_SECTION_RE.search(window):
            target_line_index = index
            break
    if target_line_index is None:
        return None

    tail_lines = block_lines[target_line_index : target_line_index + 8]
    tail_text = clean_line(" ".join(tail_lines))
    before_open = re.split(r"\s*开\s*[:：]?", tail_text, maxsplit=1)[0]
    candidates: list[str] = []

    def add_candidate(value: str | None) -> None:
        if not value or "/" in value or value in candidates:
            return
        candidates.append(value)

    add_candidate(extract_precise_wuxing_from_line_text(before_open))

    for match in re.finditer(r"杀\s*([金木水火土])\s*行", tail_text):
        add_candidate(f"{match.group(1)}行")

    for match in re.finditer(r"[【\[\(（〖]\s*([金木水火土])\s*[】\]\)）〗]", tail_text):
        add_candidate(f"{match.group(1)}行")

    for index in range(len(tail_lines) - 2):
        left = clean_line(tail_lines[index])
        middle = clean_line(tail_lines[index + 1])
        right = clean_line(tail_lines[index + 2])
        if left in {"【", "[", "(", "（"} and right in {"】", "]", ")", "）"} and re.fullmatch(r"[金木水火土]", middle):
            add_candidate(f"{middle}行")

    unique_candidates = list(dict.fromkeys(candidates))
    if len(unique_candidates) != 1:
        return None
    return unique_candidates[0]


def site_authoritative_documents(
    documents: Iterable[str],
    site: Site,
    parser_fn=parse_candidates,
    period: int | None = None,
) -> list[str]:
    documents = list(documents)
    if site.url == "https://zqliou.kify1-fbyi6-lmeykn.xyz:16677/":
        title_pattern = re.compile(r"澳门信封论坛.*绝\s*杀\s*一\s*行")
        section_pattern = re.compile(r"澳门信封论坛.*绝\s*杀")
        title_index = next(
            (
                index
                for index, document in enumerate(documents)
                if title_pattern.search(clean_line(html_to_text(document)))
            ),
            None,
        )
        if title_index is not None:
            section = [documents[title_index]]
            for document in documents[title_index + 1 :]:
                text = clean_line(html_to_text(document))
                if section_pattern.search(text) or SITE_CURRENT_BLOCK_BOUNDARY_RE.search(text):
                    break
                section.append(document)
            return section
        return documents
    if site.url == "https://eebysckd.2go6k-y0pfv-fqbdsm.xyz:16677/topic/626030.html":
        return yirujiwang_authoritative_documents(documents, period=period)
    if site.url == "https://cwdcaqzn.7mj0h-75k3q-cbuvqb.work:16677/#am":
        header_pattern = re.compile(r"八级心动\s*[【\[]?\s*绝\s*杀\s*一\s*行")
        header_index = next(
            (
                index
                for index, document in enumerate(documents)
                if header_pattern.search(clean_line(html_to_text(document)))
            ),
            None,
        )
        if header_index is None:
            return documents
        selected: list[str] = []
        for document in documents[header_index:]:
            text = clean_line(html_to_text(document))
            if selected and re.search(r"手起刀落|上一篇|下一篇", text):
                break
            selected.append(document)
        return selected
    if site.url == "https://ekhivjcg.llnnt-l11x5-bywtoe.xyz:16677/topic/469882.html":
        return sunrenliji_authoritative_documents(documents, parser_fn=parser_fn)
    anchor = SITE_CURRENT_BLOCK_ANCHORS.get(site.url)
    if not anchor:
        return documents
    anchored_documents: list[tuple[int, str]] = []
    for document in documents:
        text = clean_line(html_to_text(document))
        if not anchor.search(text):
            continue
        candidates = filter_valid_wuxing_candidates(parser_fn(document))
        if not candidates:
            continue
        if site.url in LONGEST_AUTHORITATIVE_BLOCK_URLS:
            anchored_documents.append((len(candidates), document))
        else:
            return [document]
    if anchored_documents:
        return [max(anchored_documents, key=lambda item: item[0])[1]]
    return documents


def is_valid_wuxing(value: str) -> bool:
    return clean_line(value) in VALID_WUXING


def filter_valid_wuxing_candidates(candidates: Iterable[Candidate]) -> list[Candidate]:
    return [candidate for candidate in candidates if is_valid_wuxing(candidate.wuxing)]
