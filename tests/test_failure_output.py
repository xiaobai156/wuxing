"""失败清单输出：没有失败记录时不留空壳文件。"""

from cli.common import write_failure_text


def test_write_failure_text_creates_file_when_failures_exist(tmp_path):
    target = tmp_path / "311期-五行-失败.txt"

    result = write_failure_text(target, "失败 甲 https://example.com/甲 方向: top 期数: 311\n")

    assert result == target
    assert target.exists()
    assert "甲" in target.read_text(encoding="utf-8-sig")


def test_write_failure_text_drops_empty_shell(tmp_path):
    target = tmp_path / "311期-五行-失败.txt"
    target.write_bytes(b"\xef\xbb\xbf")

    assert write_failure_text(target, "") is None
    assert not target.exists()


def test_write_failure_text_deletes_stale_file_when_no_failures(tmp_path):
    target = tmp_path / "311期-五行-失败.txt"
    target.write_text("失败 甲 https://example.com/甲 方向: top 期数: 311\n", encoding="utf-8-sig")

    assert write_failure_text(target, "  \n\n") is None
    assert not target.exists()
