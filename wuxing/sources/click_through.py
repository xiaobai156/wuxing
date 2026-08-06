from __future__ import annotations

from html.parser import HTMLParser
import re
from typing import Callable
from urllib.parse import urljoin

from wuxing.domain.errors import FetchError
from wuxing.domain.models import SiteConfig, SourceDocument

from .documents import DocumentCollector


ENTRY_RE = re.compile(
    r"(?P<period>\d{1,4})\s*期\s*[:：]\s*[【\[]\s*男儿本色\s*[】\]]\s*"
    r"[☆★]\s*绝杀\s*一\s*行\s*[☆★]\s*实力见证[！!]?(?:\s+百万资料库\s+\d+)?"
)


class _AnchorCollector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._href = ""
        self._text: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        self._href = dict(attrs).get("href", "")
        self._text = []

    def handle_data(self, data):
        if self._href:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href:
            self.links.append((self._href, re.sub(r"\s+", " ", "".join(self._text)).strip()))
            self._href = ""
            self._text = []


class ClickThroughSource:
    def __init__(self, fetch_text: Callable[[str, int], str]):
        self.fetch_text = fetch_text
        self.documents = DocumentCollector(fetch_text)

    def fetch(self, site: SiteConfig, period: int, timeout: int) -> tuple[SourceDocument, ...]:
        parser = _AnchorCollector()
        parser.feed(self.fetch_text(site.url, timeout))
        targets: list[str] = []
        for href, title in parser.links:
            match = ENTRY_RE.fullmatch(title)
            if match and int(match.group("period")) == period:
                detail_url = urljoin(site.url, href)
                if detail_url not in targets:
                    targets.append(detail_url)
        if len(targets) != 1:
            detail = "未找到" if not targets else f"找到{len(targets)}条"
            raise FetchError(f"{period}期男儿本色绝杀一行专属入口{detail}，要求唯一匹配")
        return self.documents.collect(targets[0], timeout)


__all__ = ["ClickThroughSource"]
