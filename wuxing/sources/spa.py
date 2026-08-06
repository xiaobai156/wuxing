from __future__ import annotations

import json
import re
from urllib.parse import urlparse

from wuxing.domain.enums import SourceKind
from wuxing.domain.errors import FetchError
from wuxing.domain.models import SiteConfig, SourceDocument


def spa_user_id_from_url(url: str) -> str | None:
    fragment = urlparse(url).fragment
    match = re.search(r"(?:^|/)users/(\d+)(?:$|[/?])", fragment)
    return match.group(1) if match else None


def spa_api_urls(site: SiteConfig) -> tuple[str, str]:
    user_id = spa_user_id_from_url(site.url)
    parsed = urlparse(site.url)
    if not user_id or not parsed.scheme or not parsed.netloc:
        raise FetchError("SPA页面URL缺少用户ID或站点来源")
    base = f"{parsed.scheme}://{parsed.netloc}"
    return (
        f"{base}/api/v1/users/{user_id}",
        f"{base}/api/v1/users/{user_id}/forums?per_page=20",
    )


def _name_matches(nickname: str, site: SiteConfig) -> bool:
    aliases = {"可爱孤儿": {"可爱孤儿", "可怕孤儿"}}.get(site.name, {site.name})
    return nickname in aliases or nickname.startswith(site.name)


def validate_spa_profile(profile: object, site: SiteConfig) -> None:
    if not isinstance(profile, dict):
        raise FetchError("SPA用户记录不是对象")
    expected_id = spa_user_id_from_url(site.url)
    actual_id = str(profile.get("id", "")).strip()
    if not expected_id or actual_id != expected_id:
        raise FetchError(f"SPA用户ID不一致：JSON={actual_id or '缺失'} URL={expected_id or '缺失'}")
    nickname = str(profile.get("nickname", "")).strip()
    if not nickname or not _name_matches(nickname, site):
        raise FetchError(f"SPA用户名不匹配：JSON={nickname or '缺失'} EXPECTED={site.name}")


def decode_spa_forum_documents(payload_text: str, site: SiteConfig) -> tuple[SourceDocument, ...]:
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        raise FetchError("SPA文章接口返回的不是有效JSON") from exc
    expected_user_id = spa_user_id_from_url(site.url)
    if not expected_user_id:
        raise FetchError("SPA页面URL缺少用户ID")

    records: list[dict] = []

    def visit(value: object) -> None:
        if isinstance(value, dict):
            if {"id", "user_id", "content"}.issubset(value):
                if str(value.get("user_id", "")).strip() == expected_user_id:
                    records.append(value)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(payload)
    if not records:
        raise FetchError(f"SPA接口没有用户{expected_user_id}的文章")

    seen_ids: set[str] = set()
    documents: list[SourceDocument] = []
    for order, record in enumerate(records):
        record_id = str(record.get("id", "")).strip()
        if not record_id or record_id in seen_ids:
            raise FetchError(f"SPA文章ID重复或缺失：{record_id or '缺失'}")
        seen_ids.add(record_id)
        topic = str(record.get("topic", "")).strip()
        content = record.get("content")
        if not topic or not isinstance(content, str) or not content.strip():
            raise FetchError(f"SPA文章{record_id}标题或正文缺失")
        documents.append(SourceDocument(
            document_id=f"spa-{site.site_id}-{record_id}",
            url=site.url,
            source_kind=SourceKind.SPA,
            text=f"[SPA_STRUCTURED_USER_RECORD]\n{topic}\n{content}",
            order=order,
            record_id=record_id,
            metadata=(
                ("user_id", expected_user_id),
                ("topic", topic),
                ("author", str(record.get("author", record.get("nickname", ""))).strip()),
            ),
        ))
    return tuple(documents)
