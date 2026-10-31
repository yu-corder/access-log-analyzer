from collections import Counter
from datetime import date

from ala.aggregator import Report, aggregate, normalize_path
from ala.parser import parse_line


def entry(ip="192.0.2.1", ts="31/Oct/2026:10:00:00 +0900", req="GET / HTTP/1.1"):
    return parse_line(f'{ip} - - [{ts}] "{req}" 200 1 "-" "-"')


def test_daily_ip_path_counts():
    r = aggregate([
        entry(ip="a", req="GET /x HTTP/1.1"),
        entry(ip="a", req="GET /x?utm=1 HTTP/1.1"),
        entry(ip="b", ts="01/Nov/2026:00:00:00 +0900", req="GET /y HTTP/1.1"),
    ])
    assert r.total == 3
    assert r.daily == {date(2026, 10, 31): 2, date(2026, 11, 1): 1}
    assert r.ips == {"a": 2, "b": 1}
    assert r.paths == {"/x": 2, "/y": 1}


def test_day_boundary_uses_log_local_time():
    # 23:59:59 と 00:00:00 は別の日として数える（UTC に変換しない）
    r = aggregate([
        entry(ts="30/Oct/2026:23:59:59 +0900"),
        entry(ts="31/Oct/2026:00:00:00 +0900"),
    ])
    assert r.daily == {date(2026, 10, 30): 1, date(2026, 10, 31): 1}


def test_keep_query():
    r = aggregate([entry(req="GET /x?a=1 HTTP/1.1")], keep_query=True)
    assert r.paths == {"/x?a=1": 1}


def test_normalize_path_strips_query_and_fragment():
    assert normalize_path("/a?b=1#c") == "/a"
    assert normalize_path("/a#c") == "/a"


def test_unknown_path_counted_separately():
    r = aggregate([entry(req="-"), entry()])
    assert r.total == 2
    assert r.unknown_path == 1
    assert r.paths == {"/": 1}
    assert r.ips == {"192.0.2.1": 2}  # IP・日別の集計には含める


def test_since_until_inclusive():
    es = [entry(ts=f"{d:02d}/Oct/2026:12:00:00 +0900") for d in (1, 2, 3, 4)]
    r = aggregate(es, since=date(2026, 10, 2), until=date(2026, 10, 3))
    assert sorted(r.daily) == [date(2026, 10, 2), date(2026, 10, 3)]


def test_daily_series_fills_missing_days():
    r = aggregate([
        entry(ts="01/Oct/2026:12:00:00 +0900"),
        entry(ts="03/Oct/2026:12:00:00 +0900"),
    ])
    assert r.daily_series() == [
        (date(2026, 10, 1), 1), (date(2026, 10, 2), 0), (date(2026, 10, 3), 1),
    ]


def test_empty_input():
    r = aggregate([])
    assert r.total == 0
    assert r.daily_series() == []


def test_top_orders_by_count_then_key():
    c = Counter({"b": 2, "a": 2, "c": 5, "d": 1})
    assert Report.top(c, 3) == [("c", 5), ("a", 2), ("b", 2)]
    assert len(Report.top(c, None)) == 4
