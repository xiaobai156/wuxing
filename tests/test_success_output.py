from pathlib import Path

import pytest

from wuxing.domain.enums import Region, SourceKind
from wuxing.domain.models import Candidate, ScrapeResult, SiteConfig, SourceDocument, ValidationEvidence
from wuxing.reporting.success import format_success_file_lines, format_success_output_lines
from cli.common import append_success_lines
from cli.single import build_arg_parser


def test_success_txt_does_not_include_slow_site_statistics():
    site = SiteConfig(
        site_id="site-output",
        name="测试站",
        url="https://example.com/output",
        region=Region.TOP,
        rule_id="output.v1",
    )
    document = SourceDocument(
        document_id="output-doc",
        url=site.url,
        source_kind=SourceKind.PAGE,
        text="212期绝杀一行【木行】",
        order=0,
    )
    result = ScrapeResult.success(
        site=site,
        period=212,
        candidate=Candidate(
            period=212,
            wuxing="木行",
            source_document_id=document.document_id,
            order=0,
            raw=document.text,
            rule_version="output.v1",
        ),
        elapsed_seconds=2.5,
        evidence=ValidationEvidence(True, True, True, True, True, True),
        documents=(document,),
    )

    assert format_success_file_lines((result,)) == ["木行 测试站"]


def test_repair_append_preserves_old_bytes_and_adds_only_missing_sites(tmp_path):
    target = tmp_path / "238期-五行.txt"
    original = b"\xef\xbb\xbf" + "木行 原站\r\n".encode("utf-8")
    target.write_bytes(original)

    with pytest.raises(ValueError, match="同站冲突"):
        append_success_lines(target, ["火行 原站", "水行 新站", "水行 新站"])

    assert target.read_bytes() == original
    assert not Path(f"{target}.lock").exists()


def test_repair_append_mode_is_explicit():
    args = build_arg_parser().parse_args(["238", "--repair-append-success"])

    assert args.repair_append_success is True


def test_success_output_appends_picture_style_dense_ranking():
    assert format_success_output_lines(
        ["金行 甲", "木行 乙", "金行 丙", "重复目录-不参与排行", "水行 排除站"]
    ) == [
        "金行 甲",
        "木行 乙",
        "金行 丙",
        "重复目录-不参与排行",
        "水行 排除站",
        "",
        "内容\t次数\t排名",
        "金行\t2\t1",
        "木行\t1\t2",
    ]


def test_append_rebuilds_one_ranking_without_duplicates(tmp_path):
    target = tmp_path / "252期-五行.txt"
    append_success_lines(target, ["金行 甲", "木行 乙"])
    first = target.read_text(encoding="utf-8-sig")
    append_success_lines(target, ["水行 丙"])
    second = target.read_text(encoding="utf-8-sig")

    assert second.count("内容\t次数\t排名") == 1
    assert "金行\t1\t1" in second
    assert "木行\t1\t1" in second
    assert "水行\t1\t1" in second
    assert first != second
