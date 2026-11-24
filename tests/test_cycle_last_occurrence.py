from wuxing.domain.models import Candidate
from wuxing.registry import _last_cycle_occurrence

RULE = "site.demo.v1@config2"


def _candidate(period: int, wuxing: str, order: int) -> Candidate:
    return Candidate(
        period=period,
        wuxing=wuxing,
        source_document_id="doc-demo",
        order=order,
        raw=f"{period}期 {wuxing}",
        rule_version=RULE,
    )


def test_last_cycle_occurrence_keeps_later_duplicate():
    # 整年循环页：开头 324 是去年同期旧记录，结尾 324 才是本期。
    candidates = [
        _candidate(324, "火行", 1000000),
        _candidate(325, "水行", 1000001),
        _candidate(326, "金行", 1000002),
        _candidate(327, "木行", 1000003),
        _candidate(324, "木行", 1000388),
        _candidate(325, "土行", 1000389),
        _candidate(326, "木行", 1000390),
    ]

    kept = _last_cycle_occurrence(candidates)

    assert [(item.period, item.wuxing) for item in kept] == [
        (327, "木行"),
        (324, "木行"),
        (325, "土行"),
        (326, "木行"),
    ]
    assert [item.order for item in kept] == sorted(item.order for item in kept)


def test_last_cycle_occurrence_without_duplicates_is_unchanged():
    candidates = [_candidate(period, "金行", period) for period in range(320, 327)]

    kept = _last_cycle_occurrence(candidates)

    assert [item.period for item in kept] == list(range(320, 327))
