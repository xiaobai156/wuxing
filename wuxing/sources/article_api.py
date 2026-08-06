from __future__ import annotations

import base64
import json
import re
from urllib.parse import urlparse

from wuxing.domain.enums import SourceKind
from wuxing.domain.enums import Region
from wuxing.domain.errors import FetchError
from wuxing.domain.models import SiteConfig, SourceDocument
from wuxing import registry_data


ARTICLE_ID_RE = re.compile(r"^[0-9a-fA-F]{24}$")
ARTICLE_ID_TOKEN_RE = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{24}(?![0-9a-fA-F])")
ARTICLE_DETAIL_PATH_RE = re.compile(r"/article/(?:admin|manager)/([^/]+)$")
MANAGER_API_PATH_RE = re.compile(r"/manager-articles/([^/]+)$")


def article_id_from_url(url: str) -> str | None:
    path = urlparse(url).path.rstrip("/")
    match = ARTICLE_DETAIL_PATH_RE.search(path) or MANAGER_API_PATH_RE.search(path)
    if not match or not ARTICLE_ID_RE.fullmatch(match.group(1)):
        return None
    return match.group(1)


def is_article_detail_url(url: str) -> bool:
    return ARTICLE_DETAIL_PATH_RE.search(urlparse(url).path.rstrip("/")) is not None


def require_article_id(url: str, label: str = "article页面") -> str:
    path = urlparse(url).path.rstrip("/")
    match = ARTICLE_DETAIL_PATH_RE.search(path) or MANAGER_API_PATH_RE.search(path)
    identifier = match.group(1) if match else ""
    if not identifier or not ARTICLE_ID_RE.fullmatch(identifier):
        raise FetchError(f"{label}记录ID格式无效：{identifier or '缺失'}")
    return identifier


def iter_json_objects(value: object):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from iter_json_objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_json_objects(child)


def locate_unique_record(payload: object, expected_id: str) -> dict:
    matches = [
        record for record in iter_json_objects(payload)
        if str(record.get("id", "")).strip() == expected_id
    ]
    if len(matches) != 1:
        detail = "未找到" if not matches else f"找到{len(matches)}条"
        raise FetchError(f"article API 目标文章ID {expected_id} {detail}，拒绝解析")
    return matches[0]


def decode_base64_field(record: dict, field: str, label: str) -> str:
    encoded = record.get(field)
    if not isinstance(encoded, str) or not encoded:
        raise FetchError(f"article API 缺少Base64{label}")
    try:
        raw = base64.b64decode(encoded, validate=True)
        return raw.decode("utf-8", errors="strict")
    except Exception as exc:
        raise FetchError(f"article API {label}不是严格Base64 UTF-8") from exc


def decode_article_api_document(
    payload_text: str,
    site: SiteConfig,
    expected_author: str | None = None,
) -> SourceDocument:
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        raise FetchError("article API 返回的不是有效JSON") from exc

    page_id = require_article_id(site.url, "article页面")
    api_id = require_article_id(site.api_url, "article API")
    if page_id != api_id:
        raise FetchError("article页面与API文章ID不一致或缺失")
    page = urlparse(site.url)
    api = urlparse(site.api_url)
    if (page.scheme.lower(), page.netloc.lower()) != (api.scheme.lower(), api.netloc.lower()):
        raise FetchError("article页面与API不同源")
    if api.path != f"/api/proxy/manager-articles/{page_id}":
        raise FetchError("article API路径与页面记录ID不匹配")

    record = locate_unique_record(payload, page_id)
    if not any(record.get(field) for field in ("authorNickname", "title", "html", "formSections")):
        raise FetchError("article API 返回空壳，允许浏览器按同ID边界兜底")
    author = str(record.get("authorNickname", "")).strip()
    required_author = expected_author or site.name
    if not author or author != required_author:
        raise FetchError(
            f"article API作者不匹配：JSON={author or '缺失'} EXPECTED={required_author}"
        )
    title = decode_base64_field(record, "title", "标题")
    if not title.strip():
        raise FetchError("article API标题为空")
    sections = record.get("formSections")
    if not isinstance(sections, list):
        raise FetchError("article API栏目字段缺失")
    main_sections = [
        section for section in sections
        if isinstance(section, dict)
        and (
            str(section.get("type", "")).strip().lower() == "mainarticle"
            or str(section.get("name", "")).strip() in {"主条目", "主表单", "主文章"}
        )
    ]
    if len(main_sections) != 1:
        raise FetchError(f"article API主栏目不唯一：找到{len(main_sections)}个")
    direction_values = [
        record.get(field)
        for field in ("direction", "region", "pick", "position")
        if record.get(field) not in (None, "")
    ]
    if not direction_values:
        section_direction_values = []
        for section in sections:
            if not isinstance(section, dict):
                continue
            section_name = section.get("name")
            try:
                Region.from_value(section_name)
            except ValueError:
                continue
            section_direction_values.append(section_name)
        if len(section_direction_values) > 1:
            raise FetchError(
                f"article API方向栏目不唯一：{section_direction_values}"
            )
        direction_values = section_direction_values
    if not direction_values:
        if site.url in registry_data.ARTICLE_API_CONFIGURED_REGION_FALLBACK_URLS:
            direction_values = [site.region.value]
    if not direction_values:
        raise FetchError("article API方向字段缺失，拒绝解析")
    try:
        actual_regions = {Region.from_value(value) for value in direction_values}
    except ValueError as exc:
        raise FetchError(f"article API方向字段无效：{direction_values}") from exc
    if len(actual_regions) != 1:
        raise FetchError(f"article API方向字段冲突：{direction_values}")
    actual_region = next(iter(actual_regions))
    if actual_region is not site.region:
        raise FetchError(
            f"article API方向不匹配：JSON={actual_region.value} EXPECTED={site.region.value}"
        )
    body = decode_base64_field(record, "html", "正文")
    if not body.strip():
        raise FetchError("article API正文为空")
    return SourceDocument(
        document_id=f"api-{site.site_id}-{page_id}",
        url=site.api_url,
        source_kind=SourceKind.API,
        text=body,
        order=0,
        record_id=page_id,
        metadata=(
            ("author", author),
            ("title", title.strip()),
            ("title_sha256", __import__("hashlib").sha256(title.encode()).hexdigest()),
            ("main_section_count", "1"),
            ("direction", actual_region.value),
        ),
    )
