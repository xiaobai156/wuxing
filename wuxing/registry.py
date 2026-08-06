from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Callable, Iterable

from wuxing.config.schema import SITE_SCHEMA_VERSION
from wuxing.domain.enums import FetchStrategy, SourceKind
from wuxing.domain.errors import ConfigError
from wuxing.domain.models import Candidate, SiteConfig, SourceDocument
from wuxing.parsers import kernel
from wuxing.sources.article_api import article_id_from_url, decode_article_api_document, is_article_detail_url
from wuxing.sources.browser import BrowserPlan
from wuxing.sources.ocr_script import IMAGE_OCR_JS
from wuxing.sources.spa import decode_spa_forum_documents

from . import registry_data
from .parsers.site_plugins import SITE_PLUGINS, SITE_PLUGINS_BY_ID


Parser = Callable[[tuple[SourceDocument, ...]], tuple[Candidate, ...]]
AuthoritySelector = Callable[[tuple[SourceDocument, ...], int | None], tuple[SourceDocument, ...]]
ApiDecoder = Callable[[str], tuple[SourceDocument, ...]]

TARGET_ANCHOR_RE = re.compile(
    r"(?:绝杀|必杀|精杀|稳杀|死禁|殺|杀)\s*[（(]?\s*[一1①➀⑴㈠⒈]\s*[.。．、]?\s*[)）]?\s*行"
    r"|[一二三四五①②③④⑤\d]\s*行\s*中\s*特|五\s*[丢表]\s*主\s*四\s*行"
)


def _legacy_kernel_site(site: SiteConfig) -> kernel.Site:
    return kernel.Site(
        url=site.url,
        pick=site.region.value,
        click_first=site.click_first,
        name=site.name,
        api_url=site.api_url,
    )


def _period_number(value: str) -> int:
    digits = "".join(character for character in value if character.isdigit())
    if not digits:
        raise ValueError(f"解析器返回无效期号：{value!r}")
    return int(digits)


def _convert_candidate(
    site: SiteConfig,
    document: SourceDocument,
    candidate: kernel.Candidate,
) -> Candidate:
    anchor_match = TARGET_ANCHOR_RE.search(candidate.raw)
    anchor = anchor_match.group(0) if anchor_match else ""
    block_start = document.text.find(candidate.raw)
    block_end = block_start + len(candidate.raw) if block_start >= 0 else None
    return Candidate(
        period=_period_number(candidate.period),
        wuxing=candidate.wuxing,
        source_document_id=document.document_id,
        order=document.order * 1_000_000 + candidate.order,
        raw=candidate.raw,
        rule_version=f"{site.rule_id}@config{site.config_version}",
        record_id=document.record_id,
        anchor=anchor,
        keyword=anchor,
        block_start=block_start if block_start >= 0 else None,
        block_end=block_end,
        source_url=document.url,
        document_order=document.order,
    )


def _collapse_same_document_parser_artifacts(
    candidates: list[kernel.Candidate],
) -> list[kernel.Candidate]:
    """Remove only nested text echoes from one document; keep separate targets."""
    kept: list[kernel.Candidate] = []
    grouped: dict[tuple[str, str], list[kernel.Candidate]] = {}
    for candidate in candidates:
        grouped.setdefault((candidate.period, candidate.wuxing), []).append(candidate)
    for group in grouped.values():
        group = sorted(group, key=lambda candidate: len(candidate.raw), reverse=True)
        accepted: list[kernel.Candidate] = []
        for candidate in group:
            normalized = "".join(candidate.raw.split())
            if any(normalized == "".join(existing.raw.split()) for existing in accepted):
                continue
            accepted.append(candidate)
        kept.extend(accepted)
    return sorted(kept, key=lambda candidate: candidate.order)


def _collapse_cross_document_exact_echoes(candidates: list[Candidate]) -> list[Candidate]:
    """Remove exact repeated history rows while retaining value conflicts."""
    kept: list[Candidate] = []
    seen: set[tuple[int, str, str]] = set()
    for candidate in sorted(candidates, key=lambda item: item.order):
        key = (candidate.period, candidate.wuxing, "".join(candidate.raw.split()))
        if key in seen:
            continue
        seen.add(key)
        kept.append(candidate)
    return kept


def _make_parser(site: SiteConfig) -> Parser:
    kernel_site = _legacy_kernel_site(site)
    plugin = SITE_PLUGINS_BY_ID.get(site.parser_id) or SITE_PLUGINS.get(site.url)

    def parse(documents: tuple[SourceDocument, ...]) -> tuple[Candidate, ...]:
        converted: list[Candidate] = []
        for document in documents:
            parsed = plugin(document.text) if plugin else kernel.parse_candidates_for_site(document.text, kernel_site)
            parsed = _collapse_same_document_parser_artifacts(parsed)
            for candidate in parsed:
                converted.append(_convert_candidate(site, document, candidate))
        if kernel.spa_user_id_from_url(site.url) is not None:
            converted = _collapse_cross_document_exact_echoes(converted)
        return tuple(converted)

    return parse


def _authority_document(
    selected_text: str,
    source_documents: tuple[SourceDocument, ...],
) -> SourceDocument | None:
    exact = [document for document in source_documents if document.text == selected_text]
    return exact[0] if len(exact) == 1 else None


def _make_authority_selector(site: SiteConfig) -> AuthoritySelector:
    kernel_site = _legacy_kernel_site(site)

    def select(documents: tuple[SourceDocument, ...], period: int | None = None) -> tuple[SourceDocument, ...]:
        if is_article_detail_url(site.url):
            exact_browser_records = tuple(
                document for document in documents
                if document.metadata_map.get("capture_part") == "record"
                and document.metadata_map.get("record_scope") == "exact"
                and document.record_id == article_id_from_url(site.url)
            )
            if len(exact_browser_records) == 1:
                return exact_browser_records
            exact_api_records = tuple(
                document for document in documents
                if document.source_kind is SourceKind.API
                and document.record_id == article_id_from_url(site.url)
            )
            return exact_api_records if len(exact_api_records) == 1 else ()
        browser_parts = {
            document.metadata_map.get("capture_part"): document
            for document in documents
            if document.source_kind in {SourceKind.BROWSER, SourceKind.OCR}
            and document.metadata_map.get("capture_part")
        }
        if browser_parts:
            primary_part = "body" if site.url in registry_data.BROWSER_VISIBLE_TEXT_ONLY_URLS else "page_source"
            primary = browser_parts.get(primary_part) or browser_parts.get("body")
            if primary is None:
                return ()
            ocr = browser_parts.get("ocr")
            return (primary, ocr) if ocr is not None else (primary,)
        if kernel.spa_user_id_from_url(site.url) is not None and documents:
            target = f"{period}期" if period is not None else None
            selected = tuple(
                document
                for document in documents
                if target is None
                or any(
                    candidate.period == target
                    for candidate in kernel.parse_candidates_for_site(document.text, kernel_site)
                )
            )
            return selected
        selected = kernel.site_authoritative_documents(
            [document.text for document in documents],
            kernel_site,
            parser_fn=lambda text: kernel.parse_candidates_for_site(text, kernel_site),
            period=period,
        )
        return tuple(
            authority_document
            for text in selected
            if (authority_document := _authority_document(text, documents)) is not None
        )

    return select


def _fetch_strategy(site: SiteConfig) -> FetchStrategy:
    if site.api_url and "/article/" in site.url:
        return FetchStrategy.ARTICLE_API
    if kernel.spa_user_id_from_url(site.url) is not None:
        return FetchStrategy.SPA_API
    if site.url in registry_data.CLICK_THROUGH_DETAIL_URLS:
        return FetchStrategy.CLICK_THROUGH
    if site.url in registry_data.BROWSER_FIRST_URLS or site.click_first or "#/" in site.url:
        return FetchStrategy.BROWSER_FIRST
    return FetchStrategy.HTTP_THEN_BROWSER


def _browser_plan(site: SiteConfig) -> BrowserPlan:
    tab_pattern = registry_data.BROWSER_TAB_CLICK_PATTERNS.get(site.url)
    required_text_pattern = registry_data.BROWSER_REQUIRED_TEXT_PATTERNS.get(site.url)
    click_text_pattern = ""
    if site.click_first and site.url not in registry_data.BROWSER_SKIP_CLICK_URLS:
        click_text_pattern = kernel.TARGET_SECTION_RE.pattern
    if not required_text_pattern and re.search(r"/article/(?:admin|manager)/", site.url):
        required_text_pattern = TARGET_ANCHOR_RE
    return BrowserPlan(
        tab_label_pattern=tab_pattern.pattern if tab_pattern else "",
        click_text_pattern=click_text_pattern,
        exact_click_path=registry_data.BROWSER_EXACT_CLICK_HREFS.get(site.url, ""),
        popup_close_selector=registry_data.BROWSER_POPUP_CLOSE_SELECTORS.get(site.url, ""),
        required_text_pattern=required_text_pattern.pattern if required_text_pattern else "",
        visible_text_only=site.url in registry_data.BROWSER_VISIBLE_TEXT_ONLY_URLS,
        ocr_script=IMAGE_OCR_JS if site.click_first else "",
    )


def _expected_author(site: SiteConfig) -> str:
    expected = kernel.MANAGER_ARTICLE_SITE_RULES.get(site.url)
    if expected and expected[0]:
        return expected[0]
    return site.name


def _api_decoder(site: SiteConfig, strategy: FetchStrategy) -> ApiDecoder | None:
    if strategy is FetchStrategy.ARTICLE_API:
        expected_author = _expected_author(site)

        def decode(payload_text: str) -> tuple[SourceDocument, ...]:
            return (decode_article_api_document(payload_text, site, expected_author),)

        return decode
    if strategy is FetchStrategy.SPA_API:
        return lambda payload_text: decode_spa_forum_documents(payload_text, site)
    return None


@dataclass(frozen=True)
class SiteRule:
    site_id: str
    rule_id: str
    parser_id: str
    rule_version: str
    site: SiteConfig
    fetch_strategy: FetchStrategy
    parser: Parser
    authority_selector: AuthoritySelector
    browser_plan: BrowserPlan
    expected_author: str
    api_decoder: ApiDecoder | None

    def parse(self, documents: Iterable[SourceDocument]) -> tuple[Candidate, ...]:
        return self.parser(tuple(documents))

    def select_authority(
        self,
        documents: Iterable[SourceDocument],
        period: int | None = None,
    ) -> tuple[SourceDocument, ...]:
        return self.authority_selector(tuple(documents), period)


class SiteRegistry:
    def __init__(self, rules: Iterable[SiteRule]):
        rules = tuple(rules)
        by_site = {rule.site_id: rule for rule in rules}
        if len(by_site) != len(rules):
            raise ConfigError("站点注册表存在重复 site_id")
        by_rule = {rule.rule_id: rule for rule in rules}
        if len(by_rule) != len(rules):
            raise ConfigError("站点注册表存在重复 rule_id")
        by_parser = {rule.parser_id: rule for rule in rules}
        if len(by_parser) != len(rules):
            raise ConfigError("站点注册表存在重复 parser_id")
        self._rules = rules
        self._by_site = by_site

    def __len__(self) -> int:
        return len(self._rules)

    def __iter__(self):
        return iter(self._rules)

    def require(self, site_id: str) -> SiteRule:
        try:
            return self._by_site[site_id]
        except KeyError as exc:
            raise ConfigError(f"未注册站点：{site_id}") from exc


def build_site_registry(sites: Iterable[SiteConfig]) -> SiteRegistry:
    rules: list[SiteRule] = []
    seen_urls: set[str] = set()
    for site in sites:
        if is_article_detail_url(site.url) and article_id_from_url(site.url) is None:
            raise ConfigError(f"动态 article URL 记录ID格式无效：{site.url}")
        if site.url in seen_urls and not site.shared_source_id:
            raise ConfigError(f"重复URL未声明共享来源：{site.url}")
        seen_urls.add(site.url)
        rules.append(SiteRule(
            site_id=site.site_id,
            rule_id=site.rule_id,
            parser_id=site.parser_id,
            rule_version=f"{site.rule_id}@config{site.config_version}",
            site=site,
            fetch_strategy=_fetch_strategy(site),
            parser=_make_parser(site),
            authority_selector=_make_authority_selector(site),
            browser_plan=_browser_plan(site),
            expected_author=_expected_author(site),
            api_decoder=_api_decoder(site, _fetch_strategy(site)),
        ))
    if not rules:
        raise ConfigError(f"站点注册表不能为空（配置 schema {SITE_SCHEMA_VERSION}）")
    return SiteRegistry(rules)


__all__ = ["SiteRegistry", "SiteRule", "build_site_registry"]
