from wuxing.parsers.site_plugins import parse_tongxin_yeli


def test_tongxin_yeli_bottom_tail_uses_last_period_occurrence():
    document = """
    绝杀料256期:【绝杀一行】作者:同心叶力
    255期【绝杀一行】【杀水行】
    256期【绝杀一行】【杀木行】
    257期【绝杀一行】【杀金行】
    001期【绝杀一行】【杀火行】
    254期【绝杀一行】【杀木行】
    255期【绝杀一行】【杀火行】
    256期【绝杀一行】【杀金行】
    """

    candidates = parse_tongxin_yeli(document)

    target = [candidate for candidate in candidates if candidate.period == "256期"]
    assert [(candidate.period, candidate.wuxing) for candidate in candidates[-3:]] == [
        ("254期", "木行"),
        ("255期", "火行"),
        ("256期", "金行"),
    ]
    assert [(candidate.period, candidate.wuxing) for candidate in target] == [("256期", "金行")]
