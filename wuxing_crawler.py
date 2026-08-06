import argparse
import base64
import html
import json
import re
import subprocess
import sys
import threading
import time
import warnings
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import urljoin, urlparse

import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.exceptions import InsecureRequestWarning

try:
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover - requests-only environments can still run.
    BeautifulSoup = None


DEFAULT_COUNT = 1
DEFAULT_PERIOD = 0
DEFAULT_OUTPUT = None
DEFAULT_FAIL = None
DEFAULT_OUTPUT_DIR = Path(r"C:\Users\Administrator\Desktop\每天工具\爬虫合集\七类数据统一归纳")
DEFAULT_FAILURE_OUTPUT_DIR = Path(r"C:\Users\Administrator\Desktop\每天工具\爬虫合集\七类数据统一归纳失败")
DEFAULT_SITES_CONFIG = "sites.json"
DEFAULT_HISTORY_CACHE = "recent_10_cache.json"
DEFAULT_RETRY_TIMEOUT_MIN = 45
STRICT_POSITION_THRESHOLD = 30
STRICT_POSITION_WINDOW = 5
REGION_TARGET_WINDOW = 3
DOCUMENT_FETCH_WORKERS = 4
RETRY_HTTP_WORKERS = 8
RETRY_BROWSER_WORKERS = 2
OCR_WUXING_SCORE_LIMIT = 100
OCR_WUXING_MIN_GAP = 8
SPA_STRUCTURED_RECORD_MARKER = "[SPA_STRUCTURED_USER_RECORD]"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

SCRIPT_RE = re.compile(r"<script\b[^>]*\bsrc=[\"']([^\"']+)[\"']", re.I)
IFRAME_RE = re.compile(r"<iframe\b[^>]*\bsrc=[\"']([^\"']+)[\"']", re.I)
STRDECODE_RE = re.compile(r"strdecode\(\s*[\"']([^\"']+)[\"']\s*\)", re.I)
PAGE_DATA_RE = re.compile(r"__PAGE_DATA__\s*=\s*[\"']([^\"']+)[\"']", re.I)
TAG_RE = re.compile(r"<[^>]+>")
PERIOD_RE = re.compile(r"(?<!\d)(\d{1,4})\s*期")
WUXING_RE = re.compile(r"([金木水火土]\s*行)")
WUXING_CHAR_RE = re.compile(r"[【\[\(（《〖]?\s*([金木水火土])\s*(?:行)?\s*[】\]\)）》〗]?")
BRACKET_WUXING_RE = re.compile(r"[【\[\(（《〖]\s*([金木水火土](?:\s*行|(?:[.\s、，/]*[金木水火土]){0,4}))\s*[】\]\)）》〗]")
ONE_MARKER = r"[一1①➀⑴㈠⒈]"
ROW_RE = re.compile(
    r"(?P<period>\d{1,4})\s*期\s*[:：]?\s*"
    rf".{{0,80}}?(?:绝|殺|杀)?\s*杀\s*[\(（]?\s*{ONE_MARKER}\s*[\)）]?\s*行"
    r".{0,80}?(?P<wuxing>[金木水火土]\s*行)",
    re.S,
)
KILL_ONE_LINE_RE = re.compile(rf"(?:绝|必|必中|殺|杀)?\s*[必绝]?\s*杀\s*[\(（]?\s*{ONE_MARKER}\s*[\)）]?\s*[.。．、]?\s*行|必\s*杀\s*[一1]\s*[.。．、]?\s*行")
TARGET_SECTION_RE = re.compile(rf"(?:{KILL_ONE_LINE_RE.pattern}|[一二三四五①②③④⑤\d]?\s*行\s*中\s*特|五\s*[丢表]\s*主\s*四\s*行)")
NOISE_SECTION_RE = re.compile(r"广告(?:栏目)?|推广|赞助|上一篇|下一篇|其他栏目|推荐(?:栏目)?|导航(?:栏目)?|相关推荐|热门推荐")
VALID_WUXING = {"金行", "木行", "水行", "火行", "土行"}
VALID_WUXING_ORDER = {"金行": 0, "木行": 1, "水行": 2, "火行": 3, "土行": 4}
RANKING_EXCLUDED_SITE_NAMES = {"澳门第二四不像", "信封论坛", "天青润薮"}
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
BROWSER_TAB_CLICK_PATTERNS: dict[str, re.Pattern[str]] = {
    "https://swnrapsd.74wyl-mm601-cbpzhn.xyz:16677/": re.compile(r"^杀一行$"),
}
BROWSER_FIRST_URLS = {
    "https://jldzuea.0xkqd-q7ng5-boerfb.xyz:16677/topic/677608.html",
    "https://fzzmqscl.bdppk-lyf4y-teyajr.xyz:16677/topic/439186.html",
    "https://fhktrabu.zbfrm-uzct1-pmycbu.xyz:16677/topic/469065.html",
    "https://zxliojf.83gjk-dnne7-kuyach.xyz:16677/",
    "https://eebysckd.2go6k-y0pfv-fqbdsm.xyz:16677/topic/626065.html",
    "https://pwqviw.1tcpi-45qgo-qddfnk.work:16677/topic/291140.html",
    "https://ykeejph.z9koz-18xjn-pvglgy.xyz:16677/topic/682107.html",
}
BROWSER_VISIBLE_TEXT_ONLY_URLS = {
    "https://jldzuea.0xkqd-q7ng5-boerfb.xyz:16677/topic/677608.html",
    "https://fzzmqscl.bdppk-lyf4y-teyajr.xyz:16677/topic/439186.html",
    "https://fhktrabu.zbfrm-uzct1-pmycbu.xyz:16677/topic/469065.html",
    "https://swnrapsd.74wyl-mm601-cbpzhn.xyz:16677/",
    "https://yylxuru.en4hs-c1zt6-qzcdin.xyz:16677/",
    "https://ekhivjcg.llnnt-l11x5-bywtoe.xyz:16677/topic/469882.html",
    "https://useaul.z3rj5-9jlwg-dynocd.xyz:16677/topic/384879.html",
    "https://zqliou.kify1-fbyi6-lmeykn.xyz:16677/",
    "https://993345.com/gsb1.aspx?id=1482",
    "https://zxliojf.83gjk-dnne7-kuyach.xyz:16677/",
    "https://2.www39169b.com:888/#62111",
    "https://myvvqq.30dok-2s9fd-bibfmg.work/",
    "https://pxgaayml.2wyk5-dwn70-cljflt.xyz:16677/topic/458324.html",
}
BROWSER_SKIP_CLICK_URLS = {
    "https://2.www39169b.com:888/#62111",
    "https://buzfwpox.pwp8o-vfhi5-xmrytn.xyz:16677/topic/464877.html",
    "https://zcphjs.ce83x-ms2rz-orwude.work:12277/#/users/3475",
    "https://zcphjs.ce83x-ms2rz-orwude.work:12277/#/users/3031",
    "https://swnrapsd.74wyl-mm601-cbpzhn.xyz:16677/",
    "https://fzzmqscl.bdppk-lyf4y-teyajr.xyz:16677/topic/439186.html",
    "https://evvuoswc.2n3pw-mjk5d-wndmjh.xyz:16677/topic/287366.html",
    "https://zcphjs.ce83x-ms2rz-orwude.work:12277/#/users/116157",
    "https://skgdjjmz.l54vq-9httr-cmdnip.work:29477/article/admin/6a042f7e4ea5c20141013e17?url=xdr",
    "https://flrmed.u3l95-7ktwf-clwwtq.work:29455/article/admin/6a13fd7b741e3e91a04e59d1?url=sgnn",
    "https://cwdcaqzn.7mj0h-75k3q-cbuvqb.work:16677/#am",
}
BROWSER_NON_BLOCKING_LOAD_URLS = {
    "https://pxgaayml.2wyk5-dwn70-cljflt.xyz:16677/topic/458324.html",
    "https://2.www39169b.com:888/#62111",
}
ARTICLE_API_AUTHORITATIVE_ONLY_URLS = {
    "https://cahgjib.5blx9-z8506-ekiwxc.work:29488/article/admin/6a1449c2597e16d57eacb67a?url=lqz",
}
BROWSER_EXACT_CLICK_HREFS = {
    "https://cwdcaqzn.7mj0h-75k3q-cbuvqb.work:16677/#am": "/topic/793011.html",
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
CLICK_THROUGH_DETAIL_URLS = {
    "https://mxiscni.nkh6s-vfni4-lwgfvw.xyz:16677/topic/257907.html",
}
SITE_CURRENT_BLOCK_ANCHORS: dict[str, re.Pattern[str]] = {
    "https://993345.com/gsb1.aspx?id=1482": re.compile(r"天下无双.*必杀\s*一\s*行"),
    "https://yylxuru.en4hs-c1zt6-qzcdin.xyz:16677/": re.compile(r"▼\s*绝杀\s*一\s*行\s*▼"),
    "https://ekhivjcg.llnnt-l11x5-bywtoe.xyz:16677/topic/469882.html": re.compile(r"损人利己.*发文"),
    "https://swnrapsd.74wyl-mm601-cbpzhn.xyz:16677/": re.compile(r"\d+期\s*稳杀\s*[（(]?\s*1\s*[)）]?\s*行"),
    "https://useaul.z3rj5-9jlwg-dynocd.xyz:16677/topic/384879.html": re.compile(r"满汉全席.*发文"),
    "https://zqliou.kify1-fbyi6-lmeykn.xyz:16677/": re.compile(r"澳门信封论坛.*绝杀\s*一\s*行"),
    "https://huqtzej.vvlq2-j4i8n-lisghq.xyz:16677/": re.compile(r"藏宝图\s*稳杀\s*一\s*行"),
    "https://myvvqq.30dok-2s9fd-bibfmg.work/": re.compile(r"一身仙气\s*[（(]\s*绝杀\s*一\s*行\s*[)）]"),
    "https://nyekjhvz.kr4ar-cgeaj-aekfox.xyz:16677/": re.compile(r"澳门创富\s*『绝杀一行』"),
    "https://e7rzi6.t5ti5-at6k5-fugxpa.work/topic/469841.html": re.compile(r"特料帖\s*\d+期.{0,80}?作者\s*[:：]\s*桃李不言"),
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
NANERBENSE_TITLE_RE = re.compile(
    r"(?P<period>\d{1,4})\s*期\s*[:：]\s*[【\[]\s*男儿本色\s*[】\]]\s*[☆★]\s*绝杀\s*一\s*行\s*[☆★]\s*实力见证"
)
FETCH_TEXT_CACHE: dict[str, str] = {}
DOCUMENTS_CACHE: dict[tuple[str, int], tuple[str, ...]] = {}
BROWSER_TEXT_CACHE: dict[tuple[str, int, bool, int | None, str, str], str] = {}
RUNTIME_CACHE_LOCK = threading.RLock()
HISTORY_CACHE_THREAD_LOCK = threading.RLock()
CHROMEDRIVER_PATH: str | None = None
SITE_SPECIFIC_ONLY_URLS = SITE_SPECIFIC_POSITION_RULE_URLS | set(SITE_CURRENT_BLOCK_ANCHORS) | {
    "https://buzfwpox.pwp8o-vfhi5-xmrytn.xyz:16677/topic/464877.html",
    "https://pxgaayml.2wyk5-dwn70-cljflt.xyz:16677/topic/458324.html",
    "https://buvwlreg.drr11-soh5x-jcaafg.xyz:16677/",
    "https://jdjzpkce.osyaf-gxlte-otlblr.xyz:16677/",
} | CHUNMAN_SHANSHUI_URLS | set(MANAGER_ARTICLE_SITE_RULES)

# Strict parsing principle:
# 1. Body locator words: prefer the real result block instead of titles or navigation text.
# 2. Period number: parse around the target issue number.
# 3. Strict keywords: only trust blocks matched by the target phrases.
# 4. Quantity validation: if the block does not yield exactly one valid wuxing result, fail.

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


class DocumentFetchError(RuntimeError):
    pass


class CurlFetchError(RuntimeError):
    pass


SITES: list[Site] = []


def clear_runtime_caches() -> None:
    global CHROMEDRIVER_PATH
    with RUNTIME_CACHE_LOCK:
        FETCH_TEXT_CACHE.clear()
        DOCUMENTS_CACHE.clear()
        BROWSER_TEXT_CACHE.clear()
        CHROMEDRIVER_PATH = None


def site_uses_browser_first(site: Site) -> bool:
    if site_uses_api_first(site) or site_uses_spa_api_first(site):
        return False
    return site.click_first or "#/" in site.url or site.url in BROWSER_FIRST_URLS


def site_browser_click_first(site: Site) -> bool:
    return site.click_first and site.url not in BROWSER_SKIP_CLICK_URLS


def site_uses_click_through_detail(site: Site) -> bool:
    return site.url in CLICK_THROUGH_DETAIL_URLS


def is_article_admin_site(site: Site) -> bool:
    return "/article/admin/" in site.url or is_article_manager_site(site)


def is_article_manager_site(site: Site) -> bool:
    return "/article/manager/" in site.url


def site_uses_api_first(site: Site) -> bool:
    return is_article_admin_site(site) and bool(site.api_url)


def spa_user_id_from_url(url: str) -> str | None:
    match = re.search(r"^/users/(\d+)(?:$|[/?#])", urlparse(url).fragment)
    return match.group(1) if match else None


def site_uses_spa_api_first(site: Site) -> bool:
    return spa_user_id_from_url(site.url) is not None

def load_sites(config_path: str | Path | None = None) -> list[Site]:
    path = Path(config_path or DEFAULT_SITES_CONFIG)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent / path
    if not path.exists():
        return SITES

    raw_sites = json.loads(path.read_text(encoding="utf-8-sig"))
    sites: list[Site] = []
    for index, item in enumerate(raw_sites, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"{path} item {index} is not an object")
        url = clean_line(str(item.get("url", "")))
        pick = clean_line(str(item.get("region", item.get("pick", "")))).lower()
        if not url:
            raise ValueError(f"{path} item {index} missing url")
        if pick not in {"top", "bottom"}:
            raise ValueError(f"{path} item {index} region/pick must be top or bottom")
        sites.append(
            Site(
                url=url,
                pick=pick,
                click_first=bool(item.get("click_first", False)),
                name=clean_line(str(item.get("name", ""))),
                api_url=clean_line(str(item.get("api_url", ""))),
            )
        )
    return sites


def resolve_project_path(value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent / path
    return path.resolve()


def site_history_identity(site: Site) -> dict[str, object]:
    return {
        "name": site.name,
        "url": site.url,
        "region": site.pick,
        "click_first": site.click_first,
    }


def same_history_site(entry: dict, site: Site) -> bool:
    return (
        entry.get("url", "") == site.url
        and entry.get("region", "") == site.pick
    )


def load_history_cache(path: str | Path = DEFAULT_HISTORY_CACHE) -> dict:
    cache_path = resolve_project_path(path)
    if not cache_path.exists():
        return {"version": 1, "sites": []}
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise ValueError(f"历史缓存 JSON 损坏，拒绝覆盖: {cache_path}") from exc
    if not isinstance(cache, dict):
        raise ValueError(f"历史缓存根节点不是对象，拒绝覆盖: {cache_path}")
    if not isinstance(cache.get("sites"), list):
        raise ValueError(f"历史缓存 sites 不是数组，拒绝覆盖: {cache_path}")
    for site_index, site_entry in enumerate(cache["sites"]):
        if not isinstance(site_entry, dict):
            raise ValueError(f"历史缓存 sites[{site_index}] 不是对象，拒绝覆盖: {cache_path}")
        history = site_entry.get("history")
        if not isinstance(history, list):
            raise ValueError(f"历史缓存 sites[{site_index}].history 不是数组，拒绝覆盖: {cache_path}")
        for history_index, history_item in enumerate(history):
            if not isinstance(history_item, dict):
                raise ValueError(
                    f"历史缓存 sites[{site_index}].history[{history_index}] 不是对象，拒绝覆盖: {cache_path}"
                )
            history_period = history_item.get("period")
            if isinstance(history_period, bool) or not isinstance(history_period, int):
                raise ValueError(
                    f"历史缓存 sites[{site_index}].history[{history_index}].period 不是整数，拒绝覆盖: {cache_path}"
                )
            history_wuxing = history_item.get("wuxing")
            if not isinstance(history_wuxing, str) or not is_valid_wuxing(history_wuxing):
                raise ValueError(
                    f"历史缓存 sites[{site_index}].history[{history_index}].wuxing 不是标准五行，拒绝覆盖: {cache_path}"
                )
    cache.setdefault("version", 1)
    return cache


def save_history_cache(cache: dict, path: str | Path = DEFAULT_HISTORY_CACHE) -> None:
    cache_path = resolve_project_path(path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = cache_path.with_name(f".{cache_path.name}.{threading.get_ident()}.{time.time_ns()}.tmp")
    try:
        temp_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8-sig")
        temp_path.replace(cache_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


@contextmanager
def history_cache_lock(path: str | Path = DEFAULT_HISTORY_CACHE):
    cache_path = resolve_project_path(path)
    lock_path = cache_path.with_name(f"{cache_path.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY_CACHE_THREAD_LOCK:
        lock_file = lock_path.open("a+b")
        try:
            lock_file.seek(0, 2)
            if lock_file.tell() == 0:
                lock_file.write(b"\0")
                lock_file.flush()
            lock_file.seek(0)
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
            else:  # pragma: no cover - production launcher is Windows.
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            lock_file.seek(0)
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:  # pragma: no cover - production launcher is Windows.
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            lock_file.close()


def mutate_history_cache(path: str | Path, mutator: Callable[[dict], dict | None]) -> dict:
    with history_cache_lock(path):
        cache = load_history_cache(path)
        updated = mutator(cache)
        result = cache if updated is None else updated
        save_history_cache(result, path)
        return result


def update_history_cache_entries(
    cache: dict,
    entries: Iterable[tuple[Site, int, str]],
    keep: int = 10,
) -> dict:
    entries = list(entries)
    sites_cache = cache.get("sites", [])
    if not isinstance(sites_cache, list):
        raise ValueError("历史缓存 sites 不是数组，拒绝更新")

    known: dict[tuple[str, str, int], str] = {}
    for item in sites_cache:
        if not isinstance(item, dict):
            continue
        identity = (str(item.get("url", "")), str(item.get("region", "")))
        for history_item in item.get("history", []):
            if not isinstance(history_item, dict):
                continue
            try:
                history_period = int(history_item.get("period"))
            except Exception:
                continue
            known[(*identity, history_period)] = clean_line(str(history_item.get("wuxing", "")))
    for site, period, wuxing in entries:
        key = (site.url, site.pick, period)
        previous = known.get(key)
        if previous and previous != wuxing:
            raise ValueError(f"{site.name or site.url} {period}期缓存五行冲突: {previous} / {wuxing}")
        known[key] = wuxing

    cache.setdefault("version", 1)
    cache.setdefault("sites", sites_cache)

    for site, period, wuxing in entries:
        if not is_valid_wuxing(wuxing):
            continue
        site_entry = next((item for item in sites_cache if isinstance(item, dict) and same_history_site(item, site)), None)
        if site_entry is None:
            site_entry = site_history_identity(site)
            site_entry["history"] = []
            sites_cache.append(site_entry)
        else:
            site_entry.update(site_history_identity(site))
            site_entry.setdefault("history", [])

        history = [
            item for item in site_entry.get("history", [])
            if isinstance(item, dict) and item.get("period") != period
        ]
        history.append({"period": period, "wuxing": wuxing})
        history.sort(key=lambda item: int(item.get("period", 0)), reverse=True)
        site_entry["history"] = history[:keep]
    return cache


def signature_from_history_cache(
    cache: dict,
    site: Site,
    period: int,
    periods: int,
    lookback: int,
) -> tuple[tuple[int, str], ...] | None:
    site_entry = next((item for item in cache.get("sites", []) if isinstance(item, dict) and same_history_site(item, site)), None)
    if not site_entry:
        return None
    by_period: dict[int, str] = {}
    for item in site_entry.get("history", []):
        if not isinstance(item, dict):
            continue
        try:
            item_period = int(item.get("period"))
        except Exception:
            continue
        wuxing = str(item.get("wuxing", ""))
        if is_valid_wuxing(wuxing):
            by_period[item_period] = wuxing

    values: list[tuple[int, str]] = []
    for target_period in range(period, max(period - lookback, 0), -1):
        wuxing = by_period.get(target_period)
        if not wuxing:
            continue
        values.append((target_period, wuxing))
        if len(values) >= periods:
            return tuple(values)
    return tuple(values) if values else None


def site_matches(site: Site, query: str) -> bool:
    query = clean_line(query).lower()
    if not query:
        return True
    return query in site.name.lower() or query in site.url.lower()


def filter_sites(sites: list[Site], query: str | None) -> list[tuple[int, Site]]:
    indexed_sites = list(enumerate(sites))
    if not query:
        return indexed_sites
    return [(index, site) for index, site in indexed_sites if site_matches(site, query)]


def site_needs_browser(site: Site) -> bool:
    return site_uses_browser_first(site)


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


def decode_strdecode_blocks(text: str) -> list[str]:
    decoded = []
    for match in list(STRDECODE_RE.finditer(text)) + list(PAGE_DATA_RE.finditer(text)):
        value = match.group(1)
        try:
            raw = base64.b64decode(value + ("=" * (-len(value) % 4)))
        except Exception:
            continue
        decoded.append(raw.decode("utf-8", errors="ignore"))
    return decoded


def expand_decoded_documents(documents: Iterable[str], max_rounds: int = 4) -> list[str]:
    expanded: list[str] = []
    seen: set[str] = set()
    pending = list(documents)

    for _ in range(max_rounds):
        next_pending: list[str] = []
        for document in pending:
            if document not in seen:
                seen.add(document)
                expanded.append(document)
            for decoded in decode_strdecode_blocks(document):
                if decoded not in seen:
                    next_pending.append(decoded)
        if not next_pending:
            break
        pending = next_pending

    return expanded


def create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    adapter = HTTPAdapter(pool_connections=32, pool_maxsize=32, max_retries=0)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def decode_response_content(raw: bytes, encoding: str | None = None) -> str:
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig", errors="ignore")
    return raw.decode(encoding or "utf-8", errors="ignore")


def is_gateway_response(response: requests.Response) -> bool:
    return response.status_code in {502, 503, 504}


def is_schannel_error_text(text: str) -> bool:
    lowered = text.lower()
    return "schannel" in lowered or "curl exit 35" in lowered or "curl: (35)" in lowered


def should_try_curl_fallback(error: Exception) -> bool:
    text = f"{type(error).__name__}: {error}".lower()
    return (
        "ssl" in text
        or "tls" in text
        or "handshake" in text
        or "certificate" in text
        or "connection aborted" in text
        or "filenotfounderror" in text
        or "no such file or directory" in text
        or "eof occurred in violation" in text
        or "wrong version number" in text
    )


def fetch_text_with_curl(url: str, timeout: int) -> str:
    command = [
        "curl",
        "-L",
        "-k",
        "--ssl-no-revoke",
        "--http1.1",
        "--connect-timeout",
        str(max(3, min(timeout, 10))),
        "--max-time",
        str(max(5, timeout)),
        "-A",
        DEFAULT_HEADERS["User-Agent"],
        url,
    ]
    completed = subprocess.run(command, capture_output=True, timeout=max(8, timeout + 3))
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="ignore").strip()
        message = f"curl exit {completed.returncode}: {stderr}"
        if is_schannel_error_text(message):
            raise CurlFetchError("curl TLS handshake failed (schannel exit 35)") from None
        raise CurlFetchError(message) from None
    return repair_mojibake(decode_response_content(completed.stdout))


def fetch_text(session: requests.Session, url: str, timeout: int) -> str:
    with RUNTIME_CACHE_LOCK:
        cached = FETCH_TEXT_CACHE.get(url)
    if cached is not None:
        return cached

    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = session.get(url, timeout=timeout, verify=False)
            if is_gateway_response(response):
                last_error = requests.HTTPError(f"HTTP Error {response.status_code}: Bad Gateway", response=response)
                if attempt < 1:
                    time.sleep(0.5)
                    continue
                raise last_error
            response.raise_for_status()
            raw = response.content
            encoding = "utf-8-sig" if raw.startswith(b"\xef\xbb\xbf") else response.apparent_encoding or response.encoding or "utf-8"
            text = repair_mojibake(decode_response_content(raw, encoding))
            with RUNTIME_CACHE_LOCK:
                FETCH_TEXT_CACHE[url] = text
            return text
        except Exception as exc:
            last_error = exc
            if isinstance(exc, requests.HTTPError) and getattr(exc.response, "status_code", None) == 502:
                break
            if should_try_curl_fallback(exc):
                try:
                    text = fetch_text_with_curl(url, timeout)
                    with RUNTIME_CACHE_LOCK:
                        FETCH_TEXT_CACHE[url] = text
                    return text
                except Exception as curl_exc:
                    last_error = curl_exc
                    break
            if attempt < 2:
                time.sleep(0.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


def repair_mojibake(text: str) -> str:
    return text


def should_fetch_script(page_url: str, script_url: str) -> bool:
    parsed_page = urlparse(page_url)
    parsed_script = urlparse(script_url)
    same_origin = (
        parsed_script.scheme == parsed_page.scheme
        and parsed_script.netloc == parsed_page.netloc
    )
    script_path = parsed_script.path.lower()
    return (
        "/upload/script/" in script_url
        or (same_origin and script_path.endswith(".js"))
        or (same_origin and script_path.endswith("/view_content.php"))
    )


def unescape_js_html(document: str) -> str:
    return document.replace("\\'", "'").replace('\\"', '"')


def fetch_pending_texts(session: requests.Session, urls: list[str], timeout: int) -> list[tuple[str, str | None, Exception | None]]:
    if len(urls) <= 1:
        results: list[tuple[str, str | None, Exception | None]] = []
        for url in urls:
            try:
                results.append((url, fetch_text(session, url, timeout), None))
            except Exception as exc:
                results.append((url, None, exc))
        return results

    ordered_results: list[tuple[str, str | None, Exception | None] | None] = [None] * len(urls)

    def fetch_one(index: int, url: str) -> tuple[int, str, str | None, Exception | None]:
        try:
            with create_session() as child_session:
                return index, url, fetch_text(child_session, url, timeout), None
        except Exception as exc:
            return index, url, None, exc

    with ThreadPoolExecutor(max_workers=min(DOCUMENT_FETCH_WORKERS, len(urls))) as executor:
        futures = [executor.submit(fetch_one, index, url) for index, url in enumerate(urls)]
        for future in as_completed(futures):
            index, url, text, error = future.result()
            ordered_results[index] = (url, text, error)

    return [result for result in ordered_results if result is not None]


def collect_documents(session: requests.Session, url: str, timeout: int) -> list[str]:
    cache_key = (url, timeout)
    with RUNTIME_CACHE_LOCK:
        cached = DOCUMENTS_CACHE.get(cache_key)
    if cached is not None:
        return list(cached)

    documents: list[str] = []
    seen_documents: set[str] = set()
    pending = [url]
    fetched_urls: set[str] = set()
    errors: list[Exception] = []

    for _ in range(3):
        next_pending: list[str] = []
        current_urls: list[str] = []
        for current_url in pending:
            if current_url in fetched_urls:
                continue
            fetched_urls.add(current_url)
            current_urls.append(current_url)

        for current_url, page_html, error in fetch_pending_texts(session, current_urls, timeout):
            if error is not None or page_html is None:
                exc = error or DocumentFetchError("empty page content")
                errors.append(exc)
                continue

            current_documents = expand_decoded_documents([page_html])
            for document in current_documents:
                if document in seen_documents:
                    continue
                seen_documents.add(document)
                documents.append(document)

            for document in current_documents:
                link_document = unescape_js_html(document)
                for script_url in SCRIPT_RE.findall(link_document):
                    full_script_url = urljoin(current_url, script_url)
                    if should_fetch_script(current_url, full_script_url):
                        next_pending.append(full_script_url)
                for iframe_url in IFRAME_RE.findall(link_document):
                    full_iframe_url = urljoin(current_url, iframe_url)
                    if same_origin(current_url, full_iframe_url):
                        next_pending.append(full_iframe_url)
        if not next_pending:
            break
        pending = next_pending

    first_document = documents[0] if documents else ""
    decoded_only = [document for document in documents if document != first_document]
    if decoded_only:
        documents.append("\n".join(decoded_only))

    if not documents and errors:
        raise DocumentFetchError(f"cannot fetch page content: {type(errors[-1]).__name__}: {errors[-1]}")

    with RUNTIME_CACHE_LOCK:
        DOCUMENTS_CACHE[cache_key] = tuple(documents)
    return documents


def same_origin(parent_url: str, child_url: str) -> bool:
    parent = urlparse(parent_url)
    child = urlparse(child_url)
    return child.scheme in {"http", "https"} and (parent.scheme, parent.netloc) == (child.scheme, child.netloc)


def click_through_target_urls(listing_html: str, site: Site, period: int | None) -> list[str]:
    if not site_uses_click_through_detail(site):
        return []

    urls: list[str] = []
    for match in re.finditer(r'<a\b[^>]*\bhref=["\'](?P<href>[^"\']+)["\'][^>]*>(?P<body>.*?)</a>', listing_html, re.I | re.S):
        title = clean_line(html_to_text(match.group("body")))
        title_match = NANERBENSE_TITLE_RE.search(title)
        if not title_match:
            continue
        if period is not None and int(title_match.group("period")) != period:
            continue
        full_url = urljoin(site.url, match.group("href"))
        if full_url not in urls:
            urls.append(full_url)
    return urls


def collect_click_through_detail_documents(site: Site, timeout: int, period: int | None) -> list[str]:
    with create_session() as session:
        listing_html = fetch_text(session, site.url, timeout)
        target_urls = click_through_target_urls(listing_html, site, period)
        if period is not None and len(target_urls) != 1:
            target = f"{period}期"
            detail = "未找到" if not target_urls else "不唯一"
            raise DocumentFetchError(f"{target} 男儿本色绝杀一行专属入口{detail}，已丢入失败")
        if not target_urls:
            raise DocumentFetchError("男儿本色绝杀一行专属入口未找到，已丢入失败")
        return collect_documents(session, target_urls[0], timeout)


IMAGE_OCR_JS = r"""
const period = arguments[0] || 0;
if (!period) return [];

function isInk(data, w, x, y) {
  const k = (y * w + x) * 4;
  const r = data[k], g = data[k + 1], b = data[k + 2];
  return (r < 130 && g < 130 && b < 130) || (r > 120 && g < 90 && b < 90);


function bitsFromImage(ctx, x1, y1, w, h) {
  const data = ctx.getImageData(x1, y1, w, h).data;
  const bits = [];
  for (let gy = 0; gy < 20; gy++) {
    for (let gx = 0; gx < 20; gx++) {
      let ink = 0, total = 0;
      const sx = Math.floor(gx * w / 20), ex = Math.floor((gx + 1) * w / 20);
      const sy = Math.floor(gy * h / 20), ey = Math.floor((gy + 1) * h / 20);
      for (let y = sy; y < ey; y++) {
        for (let x = sx; x < ex; x++) {
          const k = (y * w + x) * 4;
          if (data[k] < 150 && data[k + 1] < 150 && data[k + 2] < 150) ink++;
          total++;
        }
      }
      bits.push(ink > total * 0.15 ? 1 : 0);
    }
  }
  return bits;
}

function bitsForChar(ch, font) {
  const canvas = document.createElement("canvas");
  canvas.width = 90;
  canvas.height = 90;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "white";
  ctx.fillRect(0, 0, 90, 90);
  ctx.fillStyle = "black";
  ctx.font = font;
  ctx.textBaseline = "top";
  ctx.fillText(ch, 12, 6);
  const data = ctx.getImageData(0, 0, 90, 90).data;
  let x1 = 90, y1 = 90, x2 = 0, y2 = 0;
  for (let y = 0; y < 90; y++) {
    for (let x = 0; x < 90; x++) {
      const k = (y * 90 + x) * 4;
      if (data[k] < 150 && data[k + 1] < 150 && data[k + 2] < 150) {
        x1 = Math.min(x1, x); x2 = Math.max(x2, x);
        y1 = Math.min(y1, y); y2 = Math.max(y2, y);
      }
    }
  }
  return bitsFromImage(ctx, x1, y1, x2 - x1 + 1, y2 - y1 + 1);
}

function bitDistance(a, b) {
  let d = 0;
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) d++;
  return d;
}

function classifyTextChar(ctx, x1, y1, w, h, items, fonts, limit) {
  const actual = bitsFromImage(ctx, x1, y1, w, h);
  let best = null;
  let second = null;
  for (const font of fonts) {
    for (const item of items) {
      const score = bitDistance(actual, bitsForChar(item[1], font));
      if (!best || score < best.score) {
        second = best;
        best = { value: item[2], score };
      } else if (!second || score < second.score) {
        second = { value: item[2], score };
      }
    }
  }
  if (!best || best.score >= limit) return null;
  return {
    value: best.value,
    score: best.score,
    gap: second ? second.score - best.score : limit - best.score,
  };
}

function classifyWuxing(ctx, x1, y1, w, h) {
  const chars = [
    ["閲?, "\u91d1", "閲戣"],
    ["鏈?, "\u6728", "鏈ㄨ"],
    ["姘?, "\u6c34", "姘磋"],
    ["鐏?, "\u706b", "鐏"],
    ["鍦?, "\u571f", "鍦熻"],
  ];
  const fonts = [
    "42px Arial",
    "bold 42px Arial",
    "42px Microsoft YaHei",
    "bold 42px Microsoft YaHei",
    "42px SimHei",
    "bold 42px SimHei",
  ];
  return classifyTextChar(ctx, x1, y1, w, h, chars, fonts, 100);
}

function classifyStatus(ctx, x1, y1, w, h) {
  const chars = [
    ["瀵?, "\u5bf9", "瀵?],
    ["閿?, "\u9519", "閿?],
    ["鍑?, "\u51c6", "鍑?],
    ["涓?, "\u4e2d", "涓?],
    ["璧?, "\u8d62", "璧?],
  ];
  const fonts = [
    "34px Arial",
    "bold 34px Arial",
    "34px Microsoft YaHei",
    "bold 34px Microsoft YaHei",
    "34px SimHei",
    "bold 34px SimHei",
  ];
  return classifyTextChar(ctx, x1, y1, w, h, chars, fonts, 120);
}

function periodBandsForImage(img) {
  const canvas = document.createElement("canvas");
  canvas.width = img.naturalWidth;
  canvas.height = img.naturalHeight;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(img, 0, 0);
  const w = canvas.width, h = canvas.height;
  const data = ctx.getImageData(0, 0, w, h).data;
  const ys = [];
  for (let y = 0; y < h; y++) {
    let count = 0;
    for (let x = 0; x < w; x += 3) if (isInk(data, w, x, y)) count++;
    if (count > 20) ys.push(y);
  }
  let bands = [];
  for (const y of ys) {
    if (!bands.length || y - bands[bands.length - 1].end > 3) bands.push({ start: y, end: y });
    else bands[bands.length - 1].end = y;
  }
  bands = bands
    .filter((b) => b.end - b.start >= 28 && b.end - b.start <= 40)
    .map((b) => ({ start: b.start, end: b.end, mid: Math.round((b.start + b.end) / 2) }));
  return { ctx, w, h, bands };
}

function componentsInRow(ctx, w, mid) {
  const data = ctx.getImageData(0, 0, w, ctx.canvas.height).data;
  const cols = [];
  const xStart = Math.floor(w * 0.55);
  const xEnd = Math.floor(w * 0.98);
  for (let x = xStart; x < xEnd; x++) {
    let count = 0;
    for (let y = Math.max(0, mid - 24); y <= Math.min(ctx.canvas.height - 1, mid + 24); y++) {
      if (isInk(data, w, x, y)) count++;
    }
    if (count > 1) cols.push(x);
  }
  const comps = [];
  for (const x of cols) {
    if (!comps.length || x - comps[comps.length - 1].x2 > 2) comps.push({ x1: x, x2: x });
    else comps[comps.length - 1].x2 = x;
  }
  return comps.map((c) => ({ ...c, w: c.x2 - c.x1 + 1 })).filter((c) => c.w > 4);
}

function componentBox(ctx, comp, mid) {
  const w = ctx.canvas.width;
  const h = ctx.canvas.height;
  const data = ctx.getImageData(0, 0, w, h).data;
  let x1 = comp.x2, x2 = comp.x1, y1 = Math.min(h - 1, mid + 24), y2 = Math.max(0, mid - 24);
  for (let y = Math.max(0, mid - 24); y <= Math.min(h - 1, mid + 24); y++) {
    for (let x = comp.x1; x <= comp.x2; x++) {
      const k = (y * w + x) * 4;
      if (data[k] < 150 && data[k + 1] < 150 && data[k + 2] < 150) {
        x1 = Math.min(x1, x); x2 = Math.max(x2, x);
        y1 = Math.min(y1, y); y2 = Math.max(y2, y);
      }
    }
  }
  return { x1, y1, w: x2 - x1 + 1, h: y2 - y1 + 1 };
}

const images = Array.from(document.images)
  .filter((img) => img.naturalWidth > 700 && img.naturalHeight > 900)
  .sort((a, b) => (a.getBoundingClientRect().top + window.scrollY) - (b.getBoundingClientRect().top + window.scrollY));

const latestDraw = "寮€:鍥剧墖璇嗗埆";

for (const img of images) {
  const item = periodBandsForImage(img);
  if (item.bands.length < 15) continue;
  let index = period - 100;
  if (index < 0 || index >= item.bands.length) index = item.bands.length - 1;
  const lines = [];
  for (const targetPeriod of [period - 1, period]) {
    let targetIndex = targetPeriod - 100;
    if (targetIndex < 0 || targetIndex >= item.bands.length) continue;
    const band = item.bands[targetIndex];
    const comps = componentsInRow(item.ctx, item.w, band.mid);
    const charComp = comps.find((c) => c.x1 > item.w * 0.68 && c.w >= 20 && c.w <= 45);
    if (!charComp) continue;
    const box = componentBox(item.ctx, charComp, band.mid);
    const wuxing = classifyWuxing(item.ctx, box.x1, box.y1, box.w, box.h);
    if (!wuxing) continue;
    const statusComp = comps.slice().reverse().find((c) => c.x1 > item.w * 0.78 && c.w >= 18 && c.w <= 45);
    let status = "";
    let statusScore = null;
    if (statusComp) {
      const statusBox = componentBox(item.ctx, statusComp, band.mid);
      const statusResult = classifyStatus(item.ctx, statusBox.x1, statusBox.y1, statusBox.w, statusBox.h);
      if (statusResult) {
        status = statusResult.value;
        statusScore = statusResult.score;
      }
    }
    const openComp = comps.find((c) => c.x1 > item.w * 0.76 && c.x1 < item.w * 0.88 && c.w >= 20 && c.w <= 45);
    let openWuxing = "";
    let openWuxingScore = null;
    if (openComp) {
      const openBox = componentBox(item.ctx, openComp, band.mid);
      const openResult = classifyWuxing(item.ctx, openBox.x1, openBox.y1, openBox.w, openBox.h);
      if (openResult) {
        openWuxing = openResult.value.replace("琛?, "");
        openWuxingScore = openResult.score;
      }
    }
    const openText = targetPeriod === period - 1 ? latestDraw : `寮€:${openWuxing || "鍥剧墖璇嗗埆"}`;
    const raw = `${targetPeriod}鏈?銆愬浘鐗囪瘑鍒€戙€?{wuxing.value}銆?${openText} ${status || ""}`;
    lines.push({
      period: targetPeriod,
      wuxing: wuxing.value,
      wuxingScore: wuxing.score,
      wuxingGap: wuxing.gap,
      openWuxing,
      openWuxingScore,
      status,
      statusScore,
      raw,
    });
  }
  if (lines.some((line) => line.period === period)) return lines;
}
return [];
"""


def fetch_browser_text(
    url: str,
    timeout: int,
    click_first: bool,
    show_browser: bool,
    period: int | None = None,
    site: Site | None = None,
) -> str:
    def fetch_uncached() -> str:
        if site is None:
            return fetch_browser_text_uncached(url, timeout, click_first, show_browser, period)
        return fetch_browser_text_uncached(url, timeout, click_first, show_browser, period, site=site)

    if show_browser:
        return fetch_uncached()
    cache_key = (url, timeout, click_first, period, site.name if site else "", site.pick if site else "")
    with RUNTIME_CACHE_LOCK:
        cached = BROWSER_TEXT_CACHE.get(cache_key)
    if cached is not None:
        return cached
    text = fetch_uncached()
    with RUNTIME_CACHE_LOCK:
        BROWSER_TEXT_CACHE[cache_key] = text
    return text


def compose_browser_document(
    url: str,
    page_source: str,
    body_text: str,
    image_lines: list,
    site: Site | None = None,
) -> str:
    ocr_text = format_image_ocr_lines(image_lines)
    if url in BROWSER_VISIBLE_TEXT_ONLY_URLS or (
        site is not None and (is_article_admin_site(site) or site_uses_spa_api_first(site))
    ):
        return body_text + "\n" + ocr_text
    return page_source + "\n" + body_text + "\n" + ocr_text


def spa_profile_name_matches(nickname: str, site: Site) -> bool:
    nickname = clean_line(nickname)
    aliases = {
        "可爱孤儿": {"可爱孤儿", "可怕孤儿"},
    }.get(site.name, {site.name})
    return nickname in aliases or nickname.startswith(site.name)


def validate_spa_profile(profile: object, site: Site) -> None:
    if not isinstance(profile, dict):
        raise DocumentFetchError("SPA 用户接口返回的用户记录不是对象，拒绝解析")
    expected_id = spa_user_id_from_url(site.url)
    actual_id = clean_line(str(profile.get("id", "")))
    if not expected_id or actual_id != expected_id:
        raise DocumentFetchError(
            f"SPA 用户ID不一致: JSON={actual_id or '缺失'} URL={expected_id or '缺失'}，拒绝解析"
        )
    nickname = clean_line(str(profile.get("nickname", "")))
    if not nickname or not spa_profile_name_matches(nickname, site):
        raise DocumentFetchError(
            f"SPA 用户不匹配: JSON={nickname or '缺失'} EXPECTED={site.name or '缺失'}，拒绝解析"
        )


def decode_spa_forums_documents(payload_text: str, site: Site) -> list[str]:
    try:
        payload = json.loads(payload_text)
    except Exception as exc:
        raise DocumentFetchError("SPA 文章接口返回的不是有效 JSON，拒绝解析") from exc

    expected_user_id = spa_user_id_from_url(site.url)
    if not expected_user_id:
        raise DocumentFetchError("SPA 页面URL缺少用户ID，拒绝解析")

    records: list[dict] = []

    def visit(value: object) -> None:
        if isinstance(value, dict):
            if "id" in value and "user_id" in value and "content" in value:
                if clean_line(str(value.get("user_id"))) == expected_user_id:
                    records.append(value)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(payload)
    if not records:
        raise DocumentFetchError(f"SPA 接口没有用户 {expected_user_id} 的文章记录，拒绝解析")

    seen_ids: set[str] = set()
    documents: list[str] = []
    for record in records:
        article_id = clean_line(str(record.get("id", "")))
        if not article_id or article_id in seen_ids:
            raise DocumentFetchError(f"SPA 文章ID重复或缺失: {article_id or '缺失'}，拒绝解析")
        seen_ids.add(article_id)
        topic = clean_line(str(record.get("topic", "")))
        content = record.get("content")
        if not topic or not isinstance(content, str) or not clean_line(content):
            raise DocumentFetchError(f"SPA 文章 {article_id} 标题或正文缺失，拒绝解析")
        documents.append(f"{SPA_STRUCTURED_RECORD_MARKER}\n{topic}\n{content}")
    return documents


def validate_browser_record_boundary(
    site: Site,
    current_url: str,
    page_source: str,
    body_text: str,
) -> None:
    if site_uses_spa_api_first(site):
        expected_user_id = spa_user_id_from_url(site.url)
        current_user_id = spa_user_id_from_url(current_url)
        if not expected_user_id or current_user_id != expected_user_id:
            raise DocumentFetchError(
                f"SPA 浏览器用户ID不一致: 当前={current_user_id or '缺失'} 目标={expected_user_id or '缺失'}"
            )
        if not spa_profile_name_matches(clean_line(body_text), site) and site.name not in page_source:
            raise DocumentFetchError("SPA 浏览器正文作者不匹配，拒绝解析")
        return

    if not is_article_admin_site(site):
        return
    expected_id = article_id_from_url(site.url)
    current_id = article_id_from_url(current_url)
    if not expected_id or current_id != expected_id:
        raise DocumentFetchError(
            f"浏览器文章ID不一致: 当前={current_id or '缺失'} 目标={expected_id or '缺失'}"
        )
    if expected_id not in page_source:
        raise DocumentFetchError(f"浏览器页面未包含目标文章ID {expected_id}，拒绝解析")
    if site.name and site.name not in page_source and site.name not in body_text:
        raise DocumentFetchError("浏览器页面作者不匹配，拒绝解析")


def cached_chromedriver_path(manager_factory) -> str:
    global CHROMEDRIVER_PATH
    with RUNTIME_CACHE_LOCK:
        if CHROMEDRIVER_PATH is None:
            CHROMEDRIVER_PATH = manager_factory().install()
        return CHROMEDRIVER_PATH


def browser_page_load_strategy(url: str) -> str:
    return "none" if url in BROWSER_NON_BLOCKING_LOAD_URLS else "normal"


def select_unique_click_target(elements: Iterable, period: int | None):
    if period is None:
        raise DocumentFetchError("click_first 缺少指定期数，拒绝点击")
    matches = []
    for element in elements:
        text = clean_line(getattr(element, "text", ""))
        periods = {int(match.group(1)) for match in PERIOD_RE.finditer(text)}
        if periods == {period} and TARGET_SECTION_RE.search(text):
            matches.append(element)
    if len(matches) != 1:
        detail = "未找到" if not matches else f"找到{len(matches)}条"
        raise DocumentFetchError(f"{period}期 click_first 目标{detail}，要求唯一匹配，拒绝点击")
    return matches[0]


def select_site_click_target(elements: Iterable, url: str, period: int | None):
    exact_path = BROWSER_EXACT_CLICK_HREFS.get(url)
    if not exact_path:
        return select_unique_click_target(elements, period)
    matches = [
        element for element in elements
        if urlparse(str(getattr(element, "get_attribute", lambda _name: "")("href") or "")).path == exact_path
    ]
    if len(matches) != 1:
        detail = "未找到" if not matches else f"找到{len(matches)}条"
        raise DocumentFetchError(f"精确点击 {exact_path} {detail}，要求唯一匹配，拒绝点击")
    return matches[0]


def select_unique_tab_target(elements: Iterable, label_pattern: re.Pattern[str]):
    matches = [element for element in elements if label_pattern.fullmatch(clean_line(getattr(element, "text", "")))]
    if len(matches) != 1:
        detail = "未找到" if not matches else f"找到{len(matches)}条"
        raise DocumentFetchError(f"专属标签 {label_pattern.pattern} {detail}，要求唯一匹配，拒绝切换")
    return matches[0]


def target_signal_stability_condition(
    period: int | None,
    stable_rounds: int = 2,
    site: Site | None = None,
    minimum_stable_seconds: float = 0.0,
):
    previous_signature: tuple[tuple[str, str, str], ...] | None = None
    matching_rounds = 0
    signature_started_at = 0.0

    def condition(driver):
        nonlocal previous_signature, matching_rounds, signature_started_at
        try:
            body_text = str(driver.find_element("tag name", "body").text)
        except Exception:
            previous_signature = None
            matching_rounds = 0
            signature_started_at = 0.0
            return False
        parsed_candidates = parse_candidates_for_site(body_text, site) if site else parse_candidates(body_text)
        scoped_candidates = region_target_window_candidates(parsed_candidates, site.pick) if site else parsed_candidates
        target_candidates = filter_candidates_by_period(scoped_candidates, period)
        if not target_candidates:
            previous_signature = None
            matching_rounds = 0
            signature_started_at = 0.0
            return False
        signature = tuple(sorted({
            (candidate.period, candidate.wuxing, clean_line(candidate.raw))
            for candidate in target_candidates
        }))
        if signature == previous_signature:
            matching_rounds += 1
        else:
            matching_rounds = 1
            signature_started_at = time.monotonic()
        previous_signature = signature
        stable_time = time.monotonic() - signature_started_at
        return driver if matching_rounds >= max(1, stable_rounds) and stable_time >= minimum_stable_seconds else False

    return condition


def validate_image_ocr_lines(image_lines: list, period: int | None) -> list[str]:
    validated: list[str] = []
    for entry in image_lines:
        if not isinstance(entry, dict):
            continue

        raw = clean_line(str(entry.get("raw", "")))
        wuxing = clean_line(str(entry.get("wuxing", "")))
        try:
            entry_period = int(entry.get("period"))
            score = int(entry.get("wuxingScore"))
            gap = int(entry.get("wuxingGap"))
            independent_period = int(entry.get("independentPeriod"))
        except Exception:
            continue
        independent_wuxing = clean_line(str(entry.get("independentWuxing", "")))
        if independent_period != entry_period or independent_wuxing != wuxing:
            continue
        if period is not None and entry_period not in {period, period - 1}:
            continue
        if not is_valid_wuxing(wuxing):
            continue
        if score >= OCR_WUXING_SCORE_LIMIT or gap < OCR_WUXING_MIN_GAP:
            continue
        raw_period_match = PERIOD_RE.search(raw)
        raw_wuxing_match = WUXING_RE.search(raw)
        if not raw_period_match or not raw_wuxing_match:
            continue
        if int(raw_period_match.group(1)) != entry_period:
            continue
        if normalize_wuxing(raw_wuxing_match.group(1)) != wuxing:
            continue
        validated.append(raw)
    return validated


def format_image_ocr_lines(image_lines: list[str]) -> str:
    return "\n".join(clean_line(line) for line in image_lines if clean_line(line))


def fetch_browser_text_uncached(
    url: str,
    timeout: int,
    click_first: bool,
    show_browser: bool,
    period: int | None = None,
    site: Site | None = None,
) -> str:
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait
        from webdriver_manager.chrome import ChromeDriverManager
        from selenium.webdriver.chrome.service import Service
    except Exception as exc:
        raise RuntimeError(f"娴忚鍣ㄤ緷璧栦笉鍙敤: {exc}") from exc

    options = Options()
    if not show_browser:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--window-size=1280,1800")
    options.page_load_strategy = browser_page_load_strategy(url)

    try:
        driver = webdriver.Chrome(service=Service(cached_chromedriver_path(ChromeDriverManager)), options=options)
    except Exception:
        driver = webdriver.Chrome(options=options)
    try:
        driver.set_page_load_timeout(timeout)
        driver.get(url)
        WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        scroll_page_to_end(driver)

        tab_pattern = BROWSER_TAB_CLICK_PATTERNS.get(url)
        if tab_pattern:
            driver.execute_script(
                "document.querySelectorAll('[onclick*=closePopp]').forEach((element) => element.click()); "
                "if (typeof window.closePopp === 'function') { window.closePopp(); } "
                "document.querySelectorAll('[class*=index_popup]').forEach((element) => element.remove());"
            )
            tab_target = select_unique_tab_target(
                driver.find_elements(By.CSS_SELECTOR, "a, button, [role='tab'], li, div"),
                tab_pattern,
            )
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", tab_target)
            time.sleep(0.3)
            tab_target.click()
            WebDriverWait(driver, timeout).until(
                lambda current: bool(
                    filter_candidates_by_period(
                        parse_baiwanziliao_candidates(current.find_element(By.TAG_NAME, "body").text), period
                    )
                )
            )
            scroll_page_to_end(driver)

        if click_first:
            clickable = driver.find_elements(By.CSS_SELECTOR, "a, button, [role='link']")
            target = select_site_click_target(clickable, url, period)
            exact_href = BROWSER_EXACT_CLICK_HREFS.get(url)
            if exact_href:
                driver.get(urljoin(url, target.get_attribute("href")))
                WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            else:
                target.click()
            scroll_page_to_end(driver)

        if tab_pattern:
            WebDriverWait(driver, timeout).until(
                lambda current: bool(
                    filter_candidates_by_period(
                        parse_baiwanziliao_candidates(current.find_element(By.TAG_NAME, "body").text), period
                    )
                )
            )
        else:
            WebDriverWait(driver, timeout).until(
                target_signal_stability_condition(period, site=site, minimum_stable_seconds=1.5)
            )

        image_lines: list[str] = []
        if period:
            try:
                image_lines = validate_image_ocr_lines(driver.execute_script(IMAGE_OCR_JS, period) or [], period)
            except Exception:
                image_lines = []

        body_text = driver.find_element(By.TAG_NAME, "body").text
        page_source = driver.page_source
        if site is not None:
            validate_browser_record_boundary(site, getattr(driver, "current_url", url), page_source, body_text)
        return compose_browser_document(
            url,
            page_source,
            body_text,
            image_lines,
            site=site,
        )
    finally:
        driver.quit()


def scroll_page_to_end(driver) -> None:
    last_height = 0
    stable_rounds = 0
    for _ in range(8):
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.8)
            height = int(driver.execute_script("return document.body.scrollHeight") or 0)
        except Exception:
            break
        if height <= last_height:
            stable_rounds += 1
            if stable_rounds >= 2:
                break
        else:
            stable_rounds = 0
            last_height = height


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
        candidates.append(Candidate(period=period, wuxing=f"{wuxing_char}行", order=index, raw=line))

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
    latest: dict[tuple[str, str], Candidate] = {}
    for candidate in candidates:
        key = (candidate.period, candidate.wuxing)
        current = latest.get(key)
        if current is None or candidate.order > current.order:
            latest[key] = candidate
    return sorted(latest.values(), key=lambda item: item.order)


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


def pick_candidates(candidates: list[Candidate], pick: str, count: int) -> list[Candidate]:
    if not candidates:
        return []
    count = max(1, count)
    ordered = sorted(candidates, key=lambda item: item.order)
    # "top" / "bottom" are exact page-position rules:
    # top must take the earliest matching block in the page,
    # bottom must take the latest matching block in the page.
    if pick == "bottom":
        return ordered[-count:]
    return ordered[:count]


def candidate_pick_score(candidate: Candidate, pick: str) -> tuple[int, int]:
    period_number = candidate_period_number(candidate)
    if pick == "bottom":
        return (period_number, candidate.order)
    return (period_number, -candidate.order)


def latest_region_candidate(candidates: Iterable[Candidate], pick: str) -> Candidate | None:
    candidates = list(candidates)
    if not candidates:
        return None
    return pick_candidates(candidates, pick, 1)[0]


def reindex_candidates(candidates: Iterable[Candidate], offset: int) -> list[Candidate]:
    return [
        Candidate(
            period=candidate.period,
            wuxing=candidate.wuxing,
            order=offset + candidate.order,
            raw=candidate.raw,
        )
        for candidate in candidates
    ]


def combined_document_candidates(
    documents: Iterable[str],
    parser_fn=parse_candidates,
) -> list[Candidate]:
    combined: list[Candidate] = []
    for document_index, document in enumerate(documents):
        candidates = filter_valid_wuxing_candidates(parser_fn(document))
        combined.extend(reindex_candidates(candidates, document_index * 100000))
    unique: list[Candidate] = []
    seen: set[tuple[str, str]] = set()
    for candidate in sorted(combined, key=lambda item: item.order):
        key = (candidate.period, candidate.wuxing)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def authoritative_window_candidates(
    documents: Iterable[str],
    parser_fn=parse_candidates,
) -> list[Candidate]:
    documents = list(documents)
    if not documents:
        return []
    primary_candidates = filter_valid_wuxing_candidates(parser_fn(documents[0]))
    if primary_candidates:
        return primary_candidates
    return combined_document_candidates(documents, parser_fn=parser_fn)


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
            return ["\n".join(section)]
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


def requires_strict_position_window(candidates: Iterable[Candidate]) -> bool:
    candidates = list(candidates)
    if len(candidates) > STRICT_POSITION_THRESHOLD:
        return True
    periods = [candidate.period for candidate in candidates]
    return len(periods) != len(set(periods))


def position_window_candidates(candidates: Iterable[Candidate], pick: str) -> list[Candidate]:
    ordered = sorted(candidates, key=lambda item: item.order)
    if not requires_strict_position_window(ordered):
        return ordered
    if pick == "bottom":
        return ordered[-STRICT_POSITION_WINDOW:]
    return ordered[:STRICT_POSITION_WINDOW]


def region_target_window_candidates(candidates: Iterable[Candidate], pick: str) -> list[Candidate]:
    return pick_candidates(sorted(candidates, key=lambda item: item.order), pick, REGION_TARGET_WINDOW)


def filter_candidates_by_period(candidates: list[Candidate], period: int | None) -> list[Candidate]:
    if period is None:
        return candidates
    target = f"{period}期"
    return [candidate for candidate in candidates if candidate.period == target]


def extract_site_name(document: str, fallback_url: str = "") -> str:
    lines = text_lines(document)
    for line in lines:
        if not TARGET_SECTION_RE.search(line):
            continue
        if PERIOD_RE.search(line):
            continue
        name = clean_site_name(line)
        if name:
            return name

    if BeautifulSoup is not None:
        soup = BeautifulSoup(document, "html.parser")
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        if title:
            name = clean_site_name(title)
            if name:
                return name

    if fallback_url:
        parsed = urlparse(fallback_url)
        return parsed.netloc or fallback_url
    return "鏈煡缃戠珯"


def clean_site_name(text: str) -> str:
    text = clean_line(text)
    text = re.sub(r"绔欓暱鎺ㄨ崘|鏈€鍏锋潈濞佹腐婢冲叚鍚堝僵\d+鍊峔d+\.cc", "", text)
    text = text.strip(" -_|\t")
    if re.fullmatch(r"[銆怽[\(锛堛€庛€宂?\s*缁漒s*鏉€\s*[涓€1]\s*琛孿s*[銆慭]\)锛夈€忋€峕?", text):
        return ""
    bracket_match = re.match(r"(.+?)[銆庛€屻€怽[]\s*缁漒s*鏉€\s*[涓€1]\s*琛孿s*[銆忋€嶃€慭]]", text)
    if bracket_match:
        return clean_line(bracket_match.group(1))
    return text


def format_candidate(candidate: Candidate, site_name: str) -> str:
    return f"{candidate.wuxing} {candidate.period} {site_name}"


def format_fail_line(site: Site, reason: str) -> str:
    region_label = "顶部" if site.pick == "top" else "底部"
    site_name = site.name or "未命名"
    return f"网址: {site.url} | 名称: {site_name} | 方向: {region_label} | 原因: {reason}"


def format_failure_file_text(fail_lines: Iterable[str]) -> str:
    lines = [str(line).rstrip("\r\n") for line in fail_lines]
    return "\n\n".join(lines) + "\n" if lines else ""


def is_valid_wuxing(value: str) -> bool:
    return clean_line(value) in VALID_WUXING


def filter_valid_wuxing_candidates(candidates: Iterable[Candidate]) -> list[Candidate]:
    return [candidate for candidate in candidates if is_valid_wuxing(candidate.wuxing)]


def has_conflicting_target_candidates(candidates: Iterable[Candidate], period: int) -> bool:
    target = f"{period}期"
    values = {
        candidate.wuxing
        for candidate in candidates
        if candidate.period == target and is_valid_wuxing(candidate.wuxing)
    }
    return len(values) > 1


def ambiguous_target_candidates_reason(site: Site, candidates: Iterable[Candidate], period: int) -> str | None:
    target = f"{period}期"
    target_candidates = [
        candidate
        for candidate in candidates
        if candidate.period == target and is_valid_wuxing(candidate.wuxing)
    ]
    unique_sources = {
        (candidate.period, candidate.wuxing, clean_line(candidate.raw))
        for candidate in target_candidates
    }
    if len(unique_sources) <= 1:
        return None
    if site.url in SITE_SPECIFIC_ONLY_URLS:
        return None
    return f"{period}期同站出现多个高可信候选，且未配置专属解析/专属目标块校验，已丢入失败"


def has_non_wuxing_target_candidate(documents: Iterable[str], period: int | None, parser_fn=parse_candidates) -> bool:
    target = f"{period}期" if period is not None else None
    for document in documents:
        for candidate in parser_fn(document):
            if target is not None and candidate.period != target:
                continue
            if not is_valid_wuxing(candidate.wuxing):
                return True
    return False


def period_wuxing_values(
    documents: Iterable[str],
    period: int,
    parser_fn=parse_candidates,
    include_raw: bool = True,
) -> set[str]:
    target = f"{period}期"
    values: set[str] = set()
    for document in documents:
        raw_candidates = parse_raw_candidates(document) if include_raw else []
        parsed_candidates = parser_fn(document)
        for candidate in raw_candidates + parsed_candidates:
            if candidate.period == target and is_valid_wuxing(candidate.wuxing):
                values.add(candidate.wuxing)
    return values


def format_success_output_line(line: str) -> str:
    return re.sub(r"^(金行|木行|水行|火行|土行)\s+\d+期\s+", r"\1 ", line).strip()


def build_ranking_lines(success_lines: list[str], title: str = "行数次数排行") -> list[str]:
    counts: Counter[str] = Counter()
    for line in success_lines:
        head = line.split(maxsplit=1)[0] if line.strip() else ""
        for wuxing in re.findall(r"金行|木行|水行|火行|土行", head):
            counts[wuxing] += 1

    if not counts:
        return []

    ranking = sorted(counts.items(), key=lambda item: (-item[1], VALID_WUXING_ORDER.get(item[0], 99)))
    return ["", title] + [
        f"{rank}. {wuxing} {count}次" for rank, (wuxing, count) in enumerate(ranking, start=1)
    ]


def build_excluded_ranking_lines(excluded_lines: list[str]) -> list[str]:
    if not excluded_lines:
        return []
    return ["", "重复目录-不参与排行"] + excluded_lines


def build_success_output_lines(
    ranked_lines: list[str],
    excluded_lines: list[str],
    outcomes: dict[int, tuple[Site, list[str], str | None, list[str], float]] | None = None,
) -> list[str]:
    output_lines = (
        ranked_lines
        + build_excluded_ranking_lines(excluded_lines)
        + build_ranking_lines(ranked_lines, "排行表")
    )
    if outcomes is not None:
        output_lines += [""] + build_slow_site_lines(outcomes)
    return output_lines


def infer_file_label(lines: Iterable[str], fallback: int) -> int:
    periods: list[int] = []
    for line in lines:
        match = PERIOD_RE.search(line)
        if match:
            periods.append(int(match.group(1)))
    return max(periods) if periods else fallback


def line_period_number(line: str) -> int | None:
    match = PERIOD_RE.search(line)
    return int(match.group(1)) if match else None


def line_wuxing_value(line: str) -> str | None:
    match = re.search(r"金行|木行|水行|火行|土行", line)
    return match.group(0) if match else None


def candidate_period_number(candidate: Candidate) -> int:
    match = PERIOD_RE.search(candidate.period)
    return int(match.group(1)) if match else 0


def best_document_with_candidates(documents: Iterable[str], pick: str = "top", parser_fn=parse_candidates) -> tuple[str, list[Candidate]]:
    best_document = ""
    best_candidates: list[Candidate] = []
    best_score: tuple[int, int, int] = (-1, -1, -1)
    for document in documents:
        candidates = filter_valid_wuxing_candidates(parser_fn(document))
        if not candidates:
            continue
        picked_for_score = pick_candidates(candidates, pick, 1)[0]
        pick_score = candidate_pick_score(picked_for_score, pick)
        score = (pick_score[0], pick_score[1], len(candidates))
        if score > best_score:
            best_document = document
            best_candidates = candidates
            best_score = score
    return best_document, best_candidates


def best_document_with_period_candidates(documents: Iterable[str], period: int, pick: str = "top", parser_fn=parse_candidates) -> tuple[str, list[Candidate]]:
    candidates = authoritative_window_candidates(documents, parser_fn=parser_fn)
    scoped_candidates = region_target_window_candidates(candidates, pick)
    if not scoped_candidates:
        return "", []

    target = f"{period}期"
    target_candidates = [candidate for candidate in scoped_candidates if candidate.period == target]
    if target_candidates:
        return "", pick_candidates(target_candidates, pick, 1)
    return "", []


def nearest_region_candidates(documents: Iterable[str], pick: str, parser_fn=parse_candidates) -> list[Candidate]:
    candidates = combined_document_candidates(documents, parser_fn=parser_fn)
    if not candidates:
        return []
    return pick_candidates(position_window_candidates(candidates, pick), pick, 1)


def strict_position_window_failure_reason(
    documents: Iterable[str],
    pick: str,
    period: int,
    parser_fn=parse_candidates,
) -> str | None:
    target = f"{period}期"
    region_label = "顶部" if pick == "top" else "底部"
    window_label = "前5组" if pick == "top" else "后5组"
    candidates = authoritative_window_candidates(documents, parser_fn=parser_fn)
    if not candidates or not requires_strict_position_window(candidates):
        return None
    if not any(candidate.period == target for candidate in candidates):
        return None
    scoped_candidates = position_window_candidates(candidates, pick)
    if not any(candidate.period == target for candidate in scoped_candidates):
        return (
            f"候选超过{STRICT_POSITION_THRESHOLD}组或同期多条，"
            f"{region_label}只允许{window_label}，{target}不在范围内，已丢入失败"
        )
    return None


def region_three_window_failure_reason(
    documents: Iterable[str],
    pick: str,
    period: int,
    parser_fn=parse_candidates,
) -> str | None:
    target = f"{period}期"
    region_label = "顶部" if pick == "top" else "底部"
    window_label = "前3条" if pick == "top" else "后3条"
    candidates = authoritative_window_candidates(documents, parser_fn=parser_fn)
    if not candidates:
        return None
    window_candidates = region_target_window_candidates(candidates, pick)
    if any(candidate.period == target for candidate in window_candidates):
        return None
    return f"{region_label}只允许{window_label}高可信候选，{target}不在范围内，已丢入失败"


def best_site_name(documents: Iterable[str], fallback_url: str) -> str:
    fallback = ""
    for document in documents:
        name = extract_site_name(document, fallback_url="")
        if not name:
            continue
        if not fallback:
            fallback = name
        if name != "鏈煡缃戠珯" and not PERIOD_RE.search(name):
            return name
    if fallback:
        return fallback
    parsed = urlparse(fallback_url)
    return parsed.netloc or fallback_url


def has_strict_target_phrase(lines: list[str]) -> bool:
    for index in range(len(lines)):
        window = clean_line(" ".join(lines[index : index + 3]))
        if TARGET_SECTION_RE.search(window):
            return True
    return False


def explain_missing_reason(documents: list[str], period: int | None) -> str:
    target = f"{period}期" if period is not None else "指定期"
    if not documents:
        return f"未抓到页面内容，无法检测 {target}"
    raw_candidates = [candidate for document in documents for candidate in parse_candidates(document)]
    if period is not None and not any(candidate.period == target for candidate in raw_candidates):
        return f"页面里未找到 {target}"
    return f"{target} 未解析到唯一标准五行"


def clarify_error_message(error: str | None, documents: list[str], period: int | None) -> str:
    if not error:
        return explain_missing_reason(documents, period)
    lowered = error.lower()
    if "nosuchdriverexception" in lowered:
        return "浏览器驱动不可用"
    if "timeout" in lowered or "timed out" in lowered:
        return "请求超时"
    if "http error 502" in lowered or ("502" in lowered and "bad gateway" in lowered):
        return "HTTP 502 网关异常"
    if "ssl" in lowered or "tls" in lowered or "schannel" in lowered or "curl exit 35" in lowered:
        return "SSL/TLS 握手失败"
    if error.startswith("未找到") and documents:
        return explain_missing_reason(documents, period)
    return error


def classify_failure_reason(reason: str) -> str:
    lowered = reason.lower()
    if "timeout" in lowered or "请求超时" in reason:
        return "请求超时"
    if "502" in reason or "bad gateway" in lowered:
        return "HTTP 502"
    if "ssl" in lowered or "tls" in lowered or "schannel" in lowered:
        return "SSL/TLS异常"
    if "连接失败" in reason or "connection" in lowered:
        return "连接失败"
    if "非当期" in reason or "不是当期" in reason:
        return "非当期数据"
    if "五行" in reason:
        return "五行解析异常"
    return "未分类失败"


def is_http_404_error(error: Exception | str | None) -> bool:
    if error is None:
        return False
    if isinstance(error, requests.HTTPError):
        status_code = getattr(error.response, "status_code", None)
        if status_code is not None:
            return status_code == 404
    text = str(error).lower()
    return "404" in text and ("http" in text or "not found" in text)


def article_id_from_url(url: str) -> str | None:
    path = urlparse(url).path.rstrip("/")
    match = re.search(r"/(?:article/(?:admin|manager)|manager-articles)/([^/]+)$", path)
    return match.group(1) if match else None


def iter_json_objects(value: object) -> Iterable[dict]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from iter_json_objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_json_objects(child)


def locate_unique_json_record(payload: object, expected_id: str) -> dict:
    matches = [
        record
        for record in iter_json_objects(payload)
        if clean_line(str(record.get("id", ""))) == expected_id
    ]
    if len(matches) != 1:
        detail = "未找到" if not matches else f"找到{len(matches)}条"
        raise DocumentFetchError(f"article API 目标文章ID {expected_id} {detail}，多个或缺失，拒绝解析")
    return matches[0]


def decode_base64_field(record: dict, field: str, label: str) -> str:
    encoded = record.get(field)
    if not isinstance(encoded, str) or not encoded:
        raise DocumentFetchError(f"article API 缺少 Base64 {label}，拒绝解析")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise DocumentFetchError(f"article API {label} 不是严格 Base64，拒绝解析") from exc
    try:
        return raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise DocumentFetchError(f"article API {label} 不是有效 UTF-8，拒绝解析") from exc


def validate_article_record(record: dict, site: Site) -> str:
    expected_author = MANAGER_ARTICLE_SITE_RULES.get(site.url, (site.name, ""))[0] or site.name
    actual_author = clean_line(str(record.get("authorNickname", "")))
    if not actual_author or (expected_author and actual_author != expected_author):
        raise DocumentFetchError(
            f"article API 作者不匹配: JSON={actual_author or '缺失'} EXPECTED={expected_author or '缺失'}，拒绝解析"
        )

    decode_base64_field(record, "title", "标题")
    sections = record.get("formSections")
    if not isinstance(sections, list):
        raise DocumentFetchError("article API 栏目字段缺失或不是数组，拒绝解析")
    main_sections = [
        section
        for section in sections
        if isinstance(section, dict)
        and (
            clean_line(str(section.get("type", ""))).lower() == "mainarticle"
            or clean_line(str(section.get("name", ""))) in {"主条目", "主表单", "主文章"}
        )
    ]
    if len(main_sections) != 1:
        raise DocumentFetchError(
            f"article API 主栏目不唯一: 找到{len(main_sections)}个，拒绝解析"
        )
    if site.pick not in {"top", "bottom"}:
        raise DocumentFetchError(f"article API 方向无效: {site.pick or '缺失'}，拒绝解析")
    document = decode_base64_field(record, "html", "正文")
    if not clean_line(document):
        raise DocumentFetchError("article API 目标正文为空，拒绝解析")
    return document


def decode_article_admin_api_document(payload_text: str, site: Site) -> str:
    try:
        payload = json.loads(payload_text)
    except Exception as exc:
        raise DocumentFetchError("article API 返回的不是有效 JSON，拒绝浏览器兜底") from exc

    api_id = article_id_from_url(site.api_url)
    page_id = article_id_from_url(site.url)
    if not page_id:
        raise DocumentFetchError("article API 或页面 URL 缺少文章 ID，拒绝浏览器兜底")
    page_url = urlparse(site.url)
    api_url = urlparse(site.api_url)
    if (page_url.scheme.lower(), page_url.netloc.lower()) != (
        api_url.scheme.lower(),
        api_url.netloc.lower(),
    ):
        raise DocumentFetchError("article 页面与API不同源，拒绝浏览器兜底")
    expected_api_path = f"/api/proxy/manager-articles/{page_id}"
    if api_url.path != expected_api_path:
        raise DocumentFetchError("article API路径不匹配，拒绝浏览器兜底")
    if not api_id:
        raise DocumentFetchError("article API URL缺少文章 ID，拒绝浏览器兜底")
    if isinstance(payload, dict) and payload.get("id") is not None and clean_line(str(payload.get("id"))) != api_id:
        raise DocumentFetchError(
            f"article ID不一致: JSON={clean_line(str(payload.get('id'))) or '缺失'} API={api_id} PAGE={page_id}，拒绝浏览器兜底"
        )
    record = locate_unique_json_record(payload, api_id)
    if clean_line(str(record.get("id", ""))) != page_id:
        raise DocumentFetchError("article 页面与目标记录ID不一致，拒绝解析")
    if (
        record.get("html") == ""
        and not record.get("authorNickname")
        and not record.get("title")
        and not record.get("formSections")
    ):
        raise DocumentFetchError("article API 返回空壳，允许浏览器按同ID边界兜底")
    return validate_article_record(record, site)


def documents_have_target_signal(documents: Iterable[str], period: int | None) -> bool:
    for document in documents:
        text = clean_line(html_to_text(document))
        if period is not None and f"{period}期" not in text:
            continue
        if not TARGET_SECTION_RE.search(text):
            continue
        if WUXING_RE.search(text) or BRACKET_WUXING_RE.search(text):
            return True
    return False


def article_admin_should_render_fallback(
    site: Site,
    documents: list[str],
    error: Exception | str | None,
    period: int | None,
) -> bool:
    if not is_article_admin_site(site):
        return False
    if error is not None and "API 返回空壳" in str(error):
        return True
    if site_uses_api_first(site):
        if is_http_404_error(error):
            return True
        if error is not None:
            return False
        if site.url in ARTICLE_API_AUTHORITATIVE_ONLY_URLS and documents:
            return False
        return bool(documents and not documents_have_target_signal(documents, period))
    if is_http_404_error(error):
        return True
    if documents and not documents_have_target_signal(documents, period):
        return True
    return False


def collect_article_admin_api_documents(site: Site, timeout: int) -> tuple[list[str], Exception | None]:
    if not site_uses_api_first(site):
        return [], None
    try:
        with create_session() as session:
            payload_text = fetch_text(session, site.api_url, timeout)
        return [decode_article_admin_api_document(payload_text, site)], None
    except Exception as exc:
        return [], exc


def spa_api_urls(site: Site) -> tuple[str, str]:
    user_id = spa_user_id_from_url(site.url)
    parsed = urlparse(site.url)
    if not user_id or not parsed.scheme or not parsed.netloc:
        raise DocumentFetchError("SPA 页面URL缺少用户ID或站点来源，拒绝解析")
    base = f"{parsed.scheme}://{parsed.netloc}"
    return f"{base}/api/v1/users/{user_id}", f"{base}/api/v1/users/{user_id}/forums?per_page=20"


def collect_spa_api_documents(site: Site, timeout: int) -> tuple[list[str], Exception | None]:
    if not site_uses_spa_api_first(site):
        return [], None
    try:
        profile_url, forums_url = spa_api_urls(site)
        with create_session() as session:
            profile_payload = json.loads(fetch_text(session, profile_url, timeout))
            validate_spa_profile(profile_payload, site)
            forums_payload = fetch_text(session, forums_url, timeout)
        return decode_spa_forums_documents(forums_payload, site), None
    except Exception as exc:
        return [], exc


def scrape_site_detailed(site: Site, count: int, timeout: int, show_browser: bool, period: int | None) -> tuple[list[str], str | None, list[str]]:
    documents: list[str] = []
    browser_fallback_error: Exception | None = None
    try:
        browser_timeout = max(timeout, 20)
        parsed_candidate_cache: dict[str, tuple[Candidate, ...]] = {}

        def parser_fn(document: str) -> list[Candidate]:
            cached = parsed_candidate_cache.get(document)
            if cached is None:
                cached = tuple(parse_candidates_for_site(document, site))
                parsed_candidate_cache[document] = cached
            return list(cached)

        def select_candidates(documents: list[str]) -> tuple[str, list[Candidate]]:
            if period is None:
                return best_document_with_candidates(documents, site.pick, parser_fn=parser_fn)
            return best_document_with_period_candidates(documents, period, site.pick, parser_fn=parser_fn)

        def target_conflict_reason(documents: list[str]) -> str | None:
            if period is None:
                return None
            values = period_wuxing_values(
                documents,
                period,
                parser_fn=parser_fn,
                include_raw=site.url not in SITE_SPECIFIC_ONLY_URLS,
            )
            if len(values) > 1:
                return f"{period}期同站出现多个高可信候选且五行冲突，已丢入失败"
            return None

        uses_api_first = site_uses_api_first(site)
        uses_spa_api = site_uses_spa_api_first(site)
        api_error: Exception | None = None
        if uses_api_first:
            documents, api_error = collect_article_admin_api_documents(site, timeout)
            if (
                api_error is not None
                and not is_http_404_error(api_error)
                and "API 返回空壳" not in str(api_error)
            ):
                return [], f"{type(api_error).__name__}: {api_error}", documents
        elif uses_spa_api:
            documents, api_error = collect_spa_api_documents(site, timeout)
            if api_error is not None and not is_http_404_error(api_error):
                return [], f"{type(api_error).__name__}: {api_error}", documents

        uses_browser_first = site_uses_browser_first(site)
        if not documents and uses_browser_first:
            document = fetch_browser_text(
                site.url, browser_timeout, site_browser_click_first(site), show_browser, period, site=site
            )
            documents = [document]
        elif not documents and not uses_api_first and not uses_spa_api:
            if site_uses_click_through_detail(site):
                documents = collect_click_through_detail_documents(site, timeout, period)
            else:
                with create_session() as session:
                    documents = collect_documents(session, site.url, timeout)

        if article_admin_should_render_fallback(site, documents, api_error, period) or (
            uses_spa_api and is_http_404_error(api_error)
        ):
            document = fetch_browser_text(
                site.url, browser_timeout, site_browser_click_first(site), show_browser, period, site=site
            )
            documents = [document]
            api_error = None

        conflict_documents = documents
        if site.url in {
            "https://ekhivjcg.llnnt-l11x5-bywtoe.xyz:16677/topic/469882.html",
            "https://zqliou.kify1-fbyi6-lmeykn.xyz:16677/",
            "https://eebysckd.2go6k-y0pfv-fqbdsm.xyz:16677/topic/626030.html",
            "https://cwdcaqzn.7mj0h-75k3q-cbuvqb.work:16677/#am",
        }:
            conflict_documents = site_authoritative_documents(
                documents, site, parser_fn=parser_fn, period=period
            )
        conflict_reason = target_conflict_reason(conflict_documents)
        if conflict_reason:
            return [], conflict_reason, documents
        documents = site_authoritative_documents(documents, site, parser_fn=parser_fn, period=period)
        document, candidates = select_candidates(documents)
        if not candidates and not uses_browser_first and not uses_api_first and not uses_spa_api:
            try:
                http_documents = list(documents)
                browser_document = fetch_browser_text(
                    site.url, browser_timeout, False, show_browser, period, site=site
                )
                conflict_documents = http_documents + [browser_document]
                conflict_scope = conflict_documents
                if is_article_admin_site(site) or site_uses_spa_api_first(site):
                    conflict_documents = [browser_document]
                    conflict_scope = conflict_documents
                elif site.url == "https://ekhivjcg.llnnt-l11x5-bywtoe.xyz:16677/topic/469882.html":
                    conflict_scope = site_authoritative_documents(
                        conflict_documents, site, parser_fn=parser_fn, period=period
                    )
                conflict_reason = target_conflict_reason(conflict_scope)
                if conflict_reason:
                    return [], conflict_reason, conflict_documents
                if is_article_admin_site(site) or site_uses_spa_api_first(site) or site.url in BROWSER_VISIBLE_TEXT_ONLY_URLS:
                    documents = [browser_document]
                else:
                    documents = conflict_documents
                documents = site_authoritative_documents(documents, site, parser_fn=parser_fn, period=period)
                document, candidates = select_candidates(documents)
            except Exception as exc:
                browser_fallback_error = exc
                if not documents:
                    return [], f"{type(exc).__name__}: {exc}", documents

        if not candidates:
            if browser_fallback_error is not None:
                return [], f"{type(browser_fallback_error).__name__}: {browser_fallback_error}", documents
            if period is not None:
                if site.url in ARTICLE_API_AUTHORITATIVE_ONLY_URLS:
                    authoritative_candidates = [
                        candidate
                        for source_document in documents
                        for candidate in parser_fn(source_document)
                    ]
                    if not any(candidate.period == f"{period}期" for candidate in authoritative_candidates):
                        return [], f"页面里未找到 {period}期", documents
                region_reason = region_three_window_failure_reason(documents, site.pick, period, parser_fn=parser_fn)
                if region_reason:
                    return [], region_reason, documents
                strict_reason = strict_position_window_failure_reason(documents, site.pick, period, parser_fn=parser_fn)
                if strict_reason:
                    return [], strict_reason, documents
                nearest = nearest_region_candidates(documents, site.pick, parser_fn=parser_fn)
                if nearest:
                    picked = latest_region_candidate(nearest, site.pick)
                    region_label = "顶部" if site.pick == "top" else "底部"
                    return [], f"{region_label}最近候选是 {picked.period}，不是指定 {period}期，已丢入失败", documents
            if has_non_wuxing_target_candidate(documents, period, parser_fn=parser_fn):
                target_label = f"{period}期" if period is not None else ""
                return [], f"{target_label}解析结果不是标准五行（金木水火土），已丢入失败", documents
            return [], explain_missing_reason(documents, period), documents

        if period is not None:
            region_reason = region_three_window_failure_reason(documents, site.pick, period, parser_fn=parser_fn)
            if region_reason:
                return [], region_reason, documents

        if period is not None and has_conflicting_target_candidates(candidates, period):
            return [], f"{period}期同站出现多个高可信候选且五行冲突，已丢入失败", documents

        if period is not None:
            ambiguous_reason = ambiguous_target_candidates_reason(site, candidates, period)
            if ambiguous_reason:
                return [], ambiguous_reason, documents

        site_name = site.name or best_site_name(documents, site.url)
        selected = filter_valid_wuxing_candidates(pick_candidates(candidates, site.pick, count))
        if not selected:
            return [], "解析结果不是标准五行（金木水火土），已丢入失败", documents
        return [format_candidate(item, site_name) for item in selected], None, documents
    except Exception as exc:
        return [], f"{type(exc).__name__}: {exc}", documents


def scrape_site(site: Site, count: int, timeout: int, show_browser: bool, period: int | None) -> tuple[list[str], str | None]:
    lines, error, _ = scrape_site_detailed(site, count, timeout, show_browser, period)
    return lines, error


def scrape_indexed_site(index: int, site: Site, count: int, timeout: int, show_browser: bool, period: int | None) -> tuple[int, Site, list[str], str | None, list[str], float]:
    started_at = time.perf_counter()
    lines, error, documents = scrape_site_detailed(site, count, timeout, show_browser, period)
    return index, site, lines, error, documents, time.perf_counter() - started_at


def print_success(prefix: str, url: str, lines: list[str]) -> None:
    if len(lines) == 1:
        print(f"{prefix} {url} -> {lines[0]}")
    else:
        print(f"{prefix} {url} -> 成功 {len(lines)} 条")


def progress_label(index: int, total: int | None, positions: dict[int, int] | None = None) -> str:
    if total is None or total <= 0:
        return ""
    current = positions.get(index, index + 1) if positions else index + 1
    return f"[{current}/{total}] "


def format_progress_status(
    outcomes: dict[int, tuple[Site, list[str], str | None, list[str], float]],
    current_site: Site,
    total: int,
    started_at: float,
    now: float | None = None,
) -> str:
    completed = len(outcomes)
    success_count = sum(1 for _, lines, _, _, _ in outcomes.values() if lines)
    failed_count = completed - success_count
    percent = int(completed * 100 / total) if total > 0 else 0
    elapsed = max(0.0, (time.perf_counter() if now is None else now) - started_at)
    return (
        f"[进度 {completed}/{total} {percent}% 成功 {success_count} 失败 {failed_count} "
        f"用时 {elapsed:.1f}s] 当前: {current_site.name or current_site.url}"
    )


def print_progress_status(
    outcomes: dict[int, tuple[Site, list[str], str | None, list[str], float]],
    current_site: Site,
    total: int | None,
    started_at: float,
) -> None:
    if total is None or total <= 0:
        return
    print(f"\r{format_progress_status(outcomes, current_site, total, started_at)}", end="", flush=True)


def record_scrape_result(
    outcomes: dict[int, tuple[Site, list[str], str | None, list[str], float]],
    index: int,
    site: Site,
    lines: list[str],
    error: str | None,
    documents: list[str],
    elapsed_seconds: float = 0.0,
    prefix: str = "",
    total: int | None = None,
    progress_positions: dict[int, int] | None = None,
    progress_started_at: float | None = None,
) -> None:
    outcomes[index] = (site, lines, error, documents, elapsed_seconds)
    started_at = progress_started_at if progress_started_at is not None else time.perf_counter() - elapsed_seconds
    print_progress_status(outcomes, site, total, started_at)


def build_slow_site_lines(
    outcomes: dict[int, tuple[Site, list[str], str | None, list[str], float]],
    limit: int = 10,
) -> list[str]:
    rows = sorted(
        (
            (elapsed_seconds, site, bool(lines))
            for site, lines, _, _, elapsed_seconds in outcomes.values()
            if elapsed_seconds > 0
        ),
        key=lambda item: item[0],
        reverse=True,
    )
    if not rows:
        return ["慢站耗时统计：无可统计数据"]
    limit = max(1, limit)
    shown = rows[:limit]
    return [f"慢站耗时统计 Top {len(shown)}："] + [
        f"{rank}. {site.name or '未命名'} | {elapsed_seconds:.2f}s | {'成功' if ok else '失败'} | {site.url}"
        for rank, (elapsed_seconds, site, ok) in enumerate(shown, start=1)
    ]


def print_slow_site_summary(
    outcomes: dict[int, tuple[Site, list[str], str | None, list[str], float]],
    limit: int = 10,
) -> None:
    print("")
    for line in build_slow_site_lines(outcomes, limit=limit):
        print(line)


def run_initial_scrapes(
    http_sites: list[tuple[int, Site]],
    browser_sites: list[tuple[int, Site]],
    count: int,
    timeout: int,
    show_browser: bool,
    period: int,
    workers: int,
    browser_workers: int,
    browser_dependency_error: str | None,
    total: int | None = None,
    progress_positions: dict[int, int] | None = None,
    progress_started_at: float | None = None,
) -> dict[int, tuple[Site, list[str], str | None, list[str], float]]:
    progress_started_at = time.perf_counter() if progress_started_at is None else progress_started_at
    outcomes: dict[int, tuple[Site, list[str], str | None, list[str], float]] = {}
    http_executor = ThreadPoolExecutor(max_workers=max(1, workers))
    browser_executor = ThreadPoolExecutor(max_workers=max(1, browser_workers)) if browser_sites and not browser_dependency_error else None
    futures = {}
    try:
        for index, site in http_sites:
            future = http_executor.submit(scrape_indexed_site, index, site, count, timeout, show_browser, period)
            futures[future] = (index, site)
        if browser_dependency_error:
            for index, site in browser_sites:
                record_scrape_result(
                    outcomes,
                    index,
                    site,
                    [],
                    browser_dependency_error,
                    [],
                    total=total,
                    progress_positions=progress_positions,
                    progress_started_at=progress_started_at,
                )
        elif browser_executor is not None:
            for index, site in browser_sites:
                future = browser_executor.submit(scrape_indexed_site, index, site, count, timeout, show_browser, period)
                futures[future] = (index, site)

        for future in as_completed(futures):
            index, site, lines, error, documents, elapsed_seconds = future.result()
            record_scrape_result(
                outcomes,
                index,
                site,
                lines,
                error,
                documents,
                elapsed_seconds,
                total=total,
                progress_positions=progress_positions,
                progress_started_at=progress_started_at,
            )
    finally:
        http_executor.shutdown(wait=True)
        if browser_executor is not None:
            browser_executor.shutdown(wait=True)
    return outcomes


def run_retry_scrapes(
    outcomes: dict[int, tuple[Site, list[str], str | None, list[str], float]],
    http_sites: list[tuple[int, Site]],
    browser_sites: list[tuple[int, Site]],
    count: int,
    timeout: int,
    show_browser: bool,
    period: int,
    workers: int = RETRY_HTTP_WORKERS,
    browser_workers: int = RETRY_BROWSER_WORKERS,
    total: int | None = None,
    progress_positions: dict[int, int] | None = None,
    progress_started_at: float | None = None,
) -> None:
    progress_started_at = time.perf_counter() if progress_started_at is None else progress_started_at
    retry_groups = (
        (http_sites, min(RETRY_HTTP_WORKERS, max(1, workers))),
        (browser_sites, min(RETRY_BROWSER_WORKERS, max(1, browser_workers))),
    )
    executors: list[ThreadPoolExecutor] = []
    futures = {}
    try:
        if any(
            not outcomes.get(index, (site, [], None, [], 0.0))[1]
            and should_retry_failure(outcomes.get(index, (site, [], None, [], 0.0))[2])
            for sites, _ in retry_groups
            for index, site in sites
        ):
            clear_runtime_caches()
        for sites, max_workers in retry_groups:
            pending = [
                (index, site)
                for index, site in sites
                if not outcomes.get(index, (site, [], None, [], 0.0))[1]
                and should_retry_failure(outcomes.get(index, (site, [], None, [], 0.0))[2])
            ]
            if not pending:
                continue
            executor = ThreadPoolExecutor(max_workers=max_workers)
            executors.append(executor)
            for index, site in pending:
                future = executor.submit(scrape_indexed_site, index, site, count, timeout, show_browser, period)
                futures[future] = (index, site)

        for future in as_completed(futures):
            index, site, lines, error, documents, retry_elapsed = future.result()
            previous_elapsed = outcomes.get(index, (site, [], None, [], 0.0))[4]
            record_scrape_result(
                outcomes,
                index,
                site,
                lines,
                error,
                documents,
                previous_elapsed + retry_elapsed,
                prefix="[RETRY] ",
                total=total,
                progress_positions=progress_positions,
                progress_started_at=progress_started_at,
            )
    finally:
        for executor in executors:
            executor.shutdown(wait=True)


def check_browser_dependencies() -> str | None:
    missing: list[str] = []
    for module_name in ("selenium", "webdriver_manager"):
        try:
            __import__(module_name)
        except Exception:
            missing.append(module_name)
    if missing:
        return "浏览器依赖不可用，缺少：" + "、".join(missing)
    return None


def resolve_output_path(value: str | None, default_name: str, output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path:
    path = Path(value) if value else output_dir / default_name
    if not path.is_absolute():
        path = output_dir / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def should_retry_failure(error: str | None) -> bool:
    if not error:
        return False
    lowered = error.lower()
    explicit_no_retry_markers = (
        "http error 502",
        "bad gateway",
        "max retries exceeded",
        "net::err_",
        "nosuchdriverexception",
    )
    if any(marker in lowered for marker in explicit_no_retry_markers):
        return False
    retry_markers = (
        "timeout",
        "timed out",
        "read timed out",
        "connect timed out",
        "connectionerror",
        "connection aborted",
        "filenotfounderror",
        "no such file or directory",
        "请求超时",
        "璇锋眰瓒呮椂",
        "ssl",
        "tls",
        "schannel",
        "curl exit 35",
        "curl tls",
        "页面里未找到",
    )
    return any(marker in lowered for marker in retry_markers)


def update_history_cache_from_outcomes(
    selected_sites: list[tuple[int, Site]],
    outcomes: dict[int, tuple[Site, list[str], str | None, list[str], float]],
    period: int,
    cache_path: str | Path = DEFAULT_HISTORY_CACHE,
) -> int:
    entries: list[tuple[Site, int, str]] = []
    for index, site in selected_sites:
        _, lines, _, _, _ = outcomes.get(index, (site, [], None, [], 0.0))
        for line in lines:
            line_period = line_period_number(line)
            wuxing = line_wuxing_value(line)
            if line_period == period and wuxing:
                entries.append((site, period, wuxing))
                break
    if not entries:
        return 0

    def apply_updates(cache: dict) -> dict:
        update_history_cache_entries(cache, entries, keep=10)
        cache["updated_period"] = period
        return cache

    mutate_history_cache(cache_path, apply_updates)
    return len(entries)


def main() -> None:
    if __name__ == "__main__":
        print("旧版单期入口已封闭：请使用 杀五行_修复版2-单期.bat，避免绕过统一校验")
        raise SystemExit(2)

    parser = argparse.ArgumentParser(description="抓取绝杀一行五行")
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT, help="每个网站抓多少期，默认 1")
    parser.add_argument("--period", type=int, required=True, help="必须手动指定期号，例如 --period 148")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="成功结果 txt")
    parser.add_argument("--fail", default=DEFAULT_FAIL, help="失败结果 txt")
    parser.add_argument("--sites-config", default=DEFAULT_SITES_CONFIG, help="站点配置 JSON，默认 sites.json")
    parser.add_argument("--site", default="", help="只抓名称或网址包含该关键词的站点")
    parser.add_argument("--timeout", type=int, default=20, help="单站超时秒数")
    parser.add_argument("--workers", type=int, default=8, help="并发数，默认 8")
    parser.add_argument("--browser-workers", type=int, default=2, help="浏览器站点并发数，默认 2")
    parser.add_argument("--show-browser", action="store_true", help="显示浏览器窗口")
    parser.add_argument("--history-cache", default=DEFAULT_HISTORY_CACHE, help="最近10期历史缓存 JSON")
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")
    warnings.simplefilter("ignore", InsecureRequestWarning)
    requests.packages.urllib3.disable_warnings()

    if args.period <= 0:
        print("必须手动指定大于 0 的期号，例如：--period 148")
        sys.exit(2)

    try:
        sites = load_sites(args.sites_config)
    except Exception as exc:
        print(f"站点配置读取失败：{type(exc).__name__}: {exc}")
        sys.exit(2)

    selected_sites = filter_sites(sites, args.site)
    if not selected_sites:
        print(f"没有找到匹配站点：{args.site}")
        sys.exit(2)
    if args.site:
        print(f"单站/关键词模式：{args.site}，匹配 {len(selected_sites)} 个站点")

    target_period = args.period
    total_sites = len(selected_sites)
    progress_positions = {index: position for position, (index, _) in enumerate(selected_sites, start=1)}
    workers = max(1, args.workers)
    http_sites = [(index, site) for index, site in selected_sites if not site_needs_browser(site)]
    browser_sites = [(index, site) for index, site in selected_sites if site_needs_browser(site)]
    browser_dependency_error = check_browser_dependencies() if browser_sites else None
    if browser_dependency_error:
        print(browser_dependency_error)

    progress_started_at = time.perf_counter()
    outcomes = run_initial_scrapes(
        http_sites=http_sites,
        browser_sites=browser_sites,
        count=max(1, args.count),
        timeout=args.timeout,
        show_browser=args.show_browser,
        period=target_period,
        workers=workers,
        browser_workers=max(1, args.browser_workers),
        browser_dependency_error=browser_dependency_error,
        total=total_sites,
        progress_positions=progress_positions,
        progress_started_at=progress_started_at,
    )

    retry_timeout = max(args.timeout * 3, DEFAULT_RETRY_TIMEOUT_MIN)
    run_retry_scrapes(
        outcomes,
        http_sites,
        [] if browser_dependency_error else browser_sites,
        max(1, args.count),
        retry_timeout,
        args.show_browser,
        target_period,
        workers=workers,
        browser_workers=max(1, args.browser_workers),
        total=total_sites,
        progress_positions=progress_positions,
        progress_started_at=progress_started_at,
    )

    all_success_lines = [
        line
        for index, site in selected_sites
        for line in outcomes.get(index, (site, [], None, [], 0.0))[1]
    ]
    file_label = target_period

    success_lines: list[str] = []
    excluded_ranking_lines: list[str] = []
    fail_lines: list[str] = []
    fail_counts: Counter[str] = Counter()
    for index, site in selected_sites:
        _, lines, error, documents, _ = outcomes.get(index, (site, [], "未执行", [], 0.0))
        if lines:
            line_periods = [line_period_number(line) for line in lines]
            if all(period == file_label for period in line_periods):
                formatted_lines = [format_success_output_line(line) for line in lines]
                if site.name in RANKING_EXCLUDED_SITE_NAMES:
                    excluded_ranking_lines.extend(formatted_lines)
                else:
                    success_lines.extend(formatted_lines)
            else:
                found_periods = "、".join(
                    f"{period}期" if period is not None else "未知期号"
                    for period in line_periods
                )
                reason = f"抓到 {found_periods}，不是当期 {file_label}期，已丢入失败"
                fail_counts[classify_failure_reason(reason)] += 1
                fail_lines.append(format_fail_line(site, reason))
        else:
            reason = clarify_error_message(error, documents, target_period)
            fail_counts[classify_failure_reason(reason)] += 1
            fail_lines.append(format_fail_line(site, reason))

    output_path = resolve_output_path(args.output, f"{file_label}期-五行.txt")
    fail_path = resolve_output_path(
        args.fail,
        f"{file_label}期-五行-失败.txt",
        output_dir=DEFAULT_FAILURE_OUTPUT_DIR,
    )
    output_lines = build_success_output_lines(success_lines, excluded_ranking_lines, outcomes)
    output_path.write_text("\n".join(output_lines) + ("\n" if output_lines else ""), encoding="utf-8-sig")
    cache_error: str | None = None
    try:
        cached_count = update_history_cache_from_outcomes(selected_sites, outcomes, target_period, args.history_cache)
    except (ValueError, OSError) as exc:
        cached_count = 0
        cache_error = str(exc)
    print(f"\n成功 {len(success_lines) + len(excluded_ranking_lines)} 行，保存到 {output_path}")
    if cache_error:
        print(f"历史缓存未更新：{cache_error}")
    else:
        print(f"历史缓存更新 {cached_count} 个站点，保存到 {resolve_project_path(args.history_cache)}")
    if fail_lines:
        fail_path.write_text(format_failure_file_text(fail_lines), encoding="utf-8-sig")
        print(f"失败 {len(fail_lines)} 个网站，保存到 {fail_path}")
        print("失败分类：" + "，".join(f"{name} {count}个" for name, count in fail_counts.most_common()))
    else:
        if fail_path.exists():
            fail_path.unlink()
        print("失败 0 个网站，未生成失败文件")
    print_slow_site_summary(outcomes)


if __name__ == "__main__":
    print("旧版入口已封闭：请使用 杀五行_修复版2-单期.bat，避免绕过统一校验")
    raise SystemExit(2)












