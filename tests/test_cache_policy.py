import json

from wuxing.domain.enums import FailureCode, Region, SourceKind, WritePolicy
from wuxing.domain.models import (
    Candidate,
    ScrapeRequest,
    ScrapeResult,
    SiteConfig,
    SourceDocument,
    ValidationEvidence,
)
from wuxing.services.scrape import ScrapeService
from wuxing.storage.history_cache import HistoryCacheRepository, HistoryUpdate


ALL_PASS = ValidationEvidence(True, True, True, True, True, True)


def make_site(index: int) -> SiteConfig:
    return SiteConfig(
        site_id=f"site-{index}",
        name=f"站点{index}",
        url=f"https://example.com/{index}",
        region=Region.TOP,
        rule_id=f"site-{index}.v1",
    )


def make_success(site: SiteConfig, period: int) -> ScrapeResult:
    document = SourceDocument(
        document_id=f"doc-{site.site_id}",
        url=site.url,
        source_kind=SourceKind.PAGE,
        text=f"{period}期绝杀一行【木行】",
        order=0,
    )
    candidate = Candidate(
        period=period,
        wuxing="木行",
        source_document_id=document.document_id,
        order=0,
        raw=document.text,
        rule_version="test.v1",
        source_url=site.url,
    )
    return ScrapeResult.success(
        site=site,
        period=period,
        candidate=candidate,
        elapsed_seconds=0.01,
        evidence=ALL_PASS,
        documents=(document,),
    )


def make_failure(site: SiteConfig, period: int) -> ScrapeResult:
    return ScrapeResult.failure(
        site=site,
        period=period,
        code=FailureCode.TARGET_NOT_FOUND,
        reason="测试失败",
        elapsed_seconds=0.01,
    )


def test_legacy_cache_without_schema_or_site_id_is_loadable_and_rewritten_without_them(tmp_path):
    path = tmp_path / "recent_10_cache.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "updated_period": 211,
                "sites": [
                    {
                        "name": "甲站",
                        "url": "https://example.com/a",
                        "region": "top",
                        "history": [{"period": 211, "wuxing": "木行"}],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8-sig",
    )

    repository = HistoryCacheRepository(path)
    repository.apply_updates(
        [
            HistoryUpdate(
                site_id="site-a",
                name="甲站",
                url="https://example.com/a",
                region=Region.TOP,
                period=212,
                wuxing="火行",
                source_digest="digest",
                rule_version="a.v1",
                captured_at="2026-08-13T00:00:00+08:00",
            )
        ]
    )

    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    assert "schema_version" not in payload
    assert all("site_id" not in site for site in payload["sites"])
    assert payload["sites"][0]["history"][0]["period"] == 212


def test_low_success_rate_still_writes_successful_sites(tmp_path):
    """成功即写：85% 成功率不再拦截，失败站不得拖累成功站写缓存。"""
    path = tmp_path / "recent_10_cache.json"
    repository = HistoryCacheRepository(path)
    service = ScrapeService(None, None, repository)
    period = 212
    results = tuple(
        make_success(make_site(index), period) if index < 17 else make_failure(make_site(index), period)
        for index in range(20)
    )

    report = service.update_cache(
        results,
        ScrapeRequest(periods=(period,), write_policy=WritePolicy.UPDATE_CACHE),
    )

    assert report.updated_sites == 17
    assert report.skipped_reason is None
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    assert len(payload["sites"]) == 17
    assert all(site["history"][0]["period"] == period for site in payload["sites"])


def test_no_success_does_not_create_cache(tmp_path):
    """全部失败时不写缓存，也不创建文件。"""
    path = tmp_path / "recent_10_cache.json"
    repository = HistoryCacheRepository(path)
    service = ScrapeService(None, None, repository)
    period = 212
    results = tuple(make_failure(make_site(index), period) for index in range(3))

    report = service.update_cache(
        results,
        ScrapeRequest(periods=(period,), write_policy=WritePolicy.UPDATE_CACHE),
    )

    assert report.updated_sites == 0
    assert report.skipped_reason is not None
    assert not path.exists()


def test_more_than_85_percent_success_updates_only_successful_sites_without_v2_fields(tmp_path):
    path = tmp_path / "recent_10_cache.json"
    repository = HistoryCacheRepository(path)
    service = ScrapeService(None, None, repository)
    period = 212
    results = tuple(
        make_success(make_site(index), period) if index < 18 else make_failure(make_site(index), period)
        for index in range(20)
    )

    report = service.update_cache(
        results,
        ScrapeRequest(periods=(period,), write_policy=WritePolicy.UPDATE_CACHE),
    )

    assert report.updated_sites == 18
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    assert "schema_version" not in payload
    assert len(payload["sites"]) == 18
    assert all("site_id" not in site for site in payload["sites"])
    assert all(site["history"][0]["period"] == period for site in payload["sites"])
