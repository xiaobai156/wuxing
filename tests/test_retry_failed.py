from pathlib import Path

import pytest

from cli.retry_failed import (
    _hash_bytes,
    _parse_text,
    _remove_records,
    load_failure_records,
    retry_failed,
)


def _failure(name: str, period: str, *, tab: bool = False) -> str:
    gap = "\t" if tab else " "
    return f"失败{gap}{name} https://example.com/{name} 方向: top 期数: {period}\n阶段: 网络抓取 原因: 测试\n"


def test_failure_parser_handles_tab_and_deduplicates_without_crossing_lines(tmp_path):
    path = tmp_path / "失败.txt"
    path.write_text(
        "\n" + _failure("甲", "0252", tab=True) + "\n" + _failure("甲", "252") + "失败分类统计\n",
        encoding="utf-8-sig",
    )

    records = load_failure_records(path)

    assert records == ({"name": "甲", "url": "https://example.com/甲", "region": "top", "period": 252},)


def test_failure_parser_rejects_unreadable_mixed_period_records(tmp_path):
    path = tmp_path / "失败.txt"
    text = _failure("甲", "252", tab=True) + "\n失败\t乙 不是有效记录\n"

    with pytest.raises(ValueError):
        _parse_text(text, path)


def test_remove_records_removes_all_duplicate_source_rows_atomically(tmp_path):
    path = tmp_path / "失败.txt"
    text = _failure("甲", "252") + "\n" + _failure("甲", "252") + "\n" + _failure("乙", "252")
    path.write_text(text, encoding="utf-8-sig")
    raw = path.read_bytes()
    identity = ("甲", "https://example.com/甲", "top", 252)

    _remove_records(path, identity, _hash_bytes(raw))

    remaining = path.read_text(encoding="utf-8-sig")
    assert "甲" not in remaining
    assert "乙" in remaining


def test_remove_records_rejects_changed_file(tmp_path):
    path = tmp_path / "失败.txt"
    path.write_text(_failure("甲", "252"), encoding="utf-8-sig")
    expected = _hash_bytes(path.read_bytes())
    path.write_text(_failure("乙", "252"), encoding="utf-8-sig")

    with pytest.raises(RuntimeError, match="发生变化"):
        _remove_records(path, ("甲", "https://example.com/甲", "top", 252), expected)

    assert "乙" in path.read_text(encoding="utf-8-sig")


def test_remove_records_deletes_txt_once_last_record_is_gone(tmp_path):
    """失败清单清空后不留空壳文件。"""
    path = tmp_path / "失败.txt"
    path.write_text(_failure("甲", "252"), encoding="utf-8-sig")
    expected = _hash_bytes(path.read_bytes())

    changed = _remove_records(path, ("甲", "https://example.com/甲", "top", 252), expected)

    assert changed is None
    assert not path.exists()


def test_remove_records_keeps_file_when_other_records_remain(tmp_path):
    path = tmp_path / "失败.txt"
    path.write_text(_failure("甲", "252") + "\n" + _failure("乙", "252"), encoding="utf-8-sig")
    expected = _hash_bytes(path.read_bytes())

    changed = _remove_records(path, ("甲", "https://example.com/甲", "top", 252), expected)

    assert changed is not None
    assert path.exists()
    assert "乙" in path.read_text(encoding="utf-8-sig")


@pytest.mark.parametrize("payload", [b"", b"\xef\xbb\xbf", b"\xef\xbb\xbf\r\n  \r\n"])
def test_retry_failed_deletes_failure_txt_without_records(tmp_path, payload):
    """没有任何失败记录的失败 TXT 直接删除，不再报错留壳。"""
    path = tmp_path / "失败.txt"
    path.write_bytes(payload)

    assert retry_failed(path) == 0
    assert not path.exists()
