from __future__ import annotations

import base64
from collections import deque
import hashlib
import re
from typing import Callable
from urllib.parse import urljoin, urlparse

from wuxing.domain.enums import SourceKind
from wuxing.domain.errors import FetchError
from wuxing.domain.models import SourceDocument, sanitize_text


SCRIPT_RE = re.compile(r"<script\b[^>]*\bsrc=[\"']([^\"']+)[\"']", re.IGNORECASE)
IFRAME_RE = re.compile(r"<iframe\b[^>]*\bsrc=[\"']([^\"']+)[\"']", re.IGNORECASE)
STRDECODE_RE = re.compile(r"strdecode\(\s*[\"']([^\"']+)[\"']\s*\)", re.IGNORECASE)
PAGE_DATA_RE = re.compile(r"__PAGE_DATA__\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)


def same_origin(parent_url: str, child_url: str) -> bool:
    parent = urlparse(parent_url)
    child = urlparse(child_url)
    return child.scheme in {"http", "https"} and (
        parent.scheme.lower(),
        parent.netloc.lower(),
    ) == (child.scheme.lower(), child.netloc.lower())


def should_fetch_script(page_url: str, script_url: str) -> bool:
    parsed = urlparse(script_url)
    path = parsed.path.lower()
    return (
        "/upload/script/" in script_url
        or (same_origin(page_url, script_url) and path.endswith(".js"))
        or (same_origin(page_url, script_url) and path.endswith("/view_content.php"))
    )


def decoded_blocks(text: str) -> tuple[str, ...]:
    decoded: list[str] = []
    for match in list(STRDECODE_RE.finditer(text)) + list(PAGE_DATA_RE.finditer(text)):
        value = match.group(1)
        try:
            raw = base64.b64decode(value + "=" * (-len(value) % 4))
        except Exception:
            continue
        document = raw.decode("utf-8", errors="ignore")
        if document and document not in decoded:
            decoded.append(document)
    return tuple(decoded)


def document_id(url: str, source_kind: SourceKind, order: int, text: str) -> str:
    text = sanitize_text(text)
    digest = hashlib.sha256(f"{url}\0{source_kind.value}\0{order}\0{text}".encode()).hexdigest()[:20]
    return f"doc-{digest}"


class DocumentCollector:
    def __init__(self, fetch_text: Callable[[str, int], str], max_depth: int = 3):
        self.fetch_text = fetch_text
        self.max_depth = max_depth

    def collect(self, url: str, timeout: int) -> tuple[SourceDocument, ...]:
        pending = deque([(url, SourceKind.PAGE, None, 0)])
        fetched_urls: set[str] = set()
        seen_content: set[tuple[str, SourceKind, str]] = set()
        documents: list[SourceDocument] = []
        root_error: Exception | None = None

        while pending:
            current_url, source_kind, parent_id, depth = pending.popleft()
            if current_url in fetched_urls or depth > self.max_depth:
                continue
            fetched_urls.add(current_url)
            try:
                text = sanitize_text(self.fetch_text(current_url, timeout))
            except Exception as exc:
                if depth == 0:
                    root_error = exc
                continue
            if not text:
                if depth == 0:
                    root_error = FetchError("页面返回空内容")
                continue

            raw_document = self._append_document(
                documents,
                seen_content,
                current_url,
                source_kind,
                text,
                parent_id,
                metadata=(),
            )
            if raw_document is None:
                continue

            expanded = [(raw_document, text)]
            decoded_parent = raw_document
            for decoded in decoded_blocks(text):
                decoded_document = self._append_document(
                    documents,
                    seen_content,
                    current_url,
                    source_kind,
                    decoded,
                    decoded_parent.document_id,
                    metadata=(("decoded", "true"),),
                )
                if decoded_document is not None:
                    expanded.append((decoded_document, decoded))

            for owner, link_text in expanded:
                unescaped = link_text.replace("\\'", "'").replace('\\"', '"')
                for value in SCRIPT_RE.findall(unescaped):
                    child_url = urljoin(current_url, value)
                    if should_fetch_script(current_url, child_url):
                        pending.append((child_url, SourceKind.SCRIPT, owner.document_id, depth + 1))
                for value in IFRAME_RE.findall(unescaped):
                    child_url = urljoin(current_url, value)
                    if same_origin(current_url, child_url):
                        pending.append((child_url, SourceKind.IFRAME, owner.document_id, depth + 1))

        if not documents:
            detail = f"{type(root_error).__name__}: {root_error}" if root_error else "未知错误"
            raise FetchError(f"无法抓取页面内容：{detail}")
        return tuple(documents)

    @staticmethod
    def _append_document(
        documents: list[SourceDocument],
        seen_content: set[tuple[str, SourceKind, str]],
        url: str,
        source_kind: SourceKind,
        text: str,
        parent_id: str | None,
        metadata: tuple[tuple[str, str], ...],
    ) -> SourceDocument | None:
        key = (url, source_kind, text)
        if key in seen_content:
            return None
        seen_content.add(key)
        order = len(documents)
        result = SourceDocument(
            document_id=document_id(url, source_kind, order, text),
            url=url,
            source_kind=source_kind,
            text=text,
            order=order,
            parent_document_id=parent_id,
            metadata=metadata,
        )
        documents.append(result)
        return result
