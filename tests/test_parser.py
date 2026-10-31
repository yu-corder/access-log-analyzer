from datetime import datetime, timedelta, timezone

import pytest

from ala.parser import ParseError, parse_line, parse_request, parse_time

JST = timezone(timedelta(hours=9))


def test_combined_format():
    e = parse_line(
        '192.0.2.1 - alice [31/Oct/2026:10:15:30 +0900] "GET /posts/hello?x=1 HTTP/1.1" '
        '200 2048 "https://example.com/" "Mozilla/5.0 (Macintosh)"\n'
    )
    assert e.ip == "192.0.2.1"
    assert e.user == "alice"
    assert e.time == datetime(2026, 10, 31, 10, 15, 30, tzinfo=JST)
    assert (e.method, e.path, e.protocol) == ("GET", "/posts/hello?x=1", "HTTP/1.1")
    assert e.status == 200
    assert e.size == 2048
    assert e.referer == "https://example.com/"
    assert e.user_agent == "Mozilla/5.0 (Macintosh)"


def test_dash_fields_become_none_or_zero():
    e = parse_line('192.0.2.1 - - [31/Oct/2026:10:00:00 +0900] "GET / HTTP/1.1" 304 - "-" "-"')
    assert e.user is None
    assert e.size == 0
    assert e.referer is None
    assert e.user_agent is None


def test_common_format_without_referer_and_ua():
    e = parse_line('192.0.2.1 - - [31/Oct/2026:10:00:00 +0000] "GET / HTTP/1.1" 200 10')
    assert e.path == "/"
    assert e.referer is None and e.user_agent is None


def test_ipv6():
    e = parse_line('2001:db8::1 - - [31/Oct/2026:10:00:00 +0900] "GET / HTTP/1.1" 200 1 "-" "-"')
    assert e.ip == "2001:db8::1"


def test_escaped_quotes_inside_fields():
    e = parse_line(
        r'192.0.2.1 - - [31/Oct/2026:10:00:00 +0900] "GET /s?q=\"a\" HTTP/1.1" 200 1 "-" "Bot \"x\""'
    )
    assert e.path == r'/s?q=\"a\"'
    assert e.user_agent == r'Bot \"x\"'


def test_garbage_request_is_kept_without_path():
    # TLS ハンドシェイクを HTTP ポートに送られた場合など。行としては有効
    e = parse_line(r'192.0.2.1 - - [31/Oct/2026:10:00:00 +0900] "\x16\x03\x01" 400 157 "-" "-"')
    assert e.status == 400
    assert e.method is None and e.path is None


def test_crlf_line_ending():
    e = parse_line('192.0.2.1 - - [31/Oct/2026:10:00:00 +0900] "GET / HTTP/1.1" 200 1 "-" "-"\r\n')
    assert e.user_agent is None


@pytest.mark.parametrize(
    "line",
    [
        "",
        "   ",
        "this line is broken",
        # 途中で切れた行
        '192.0.2.1 - - [31/Oct/2026:10:00:00 +0900] "GET / HTTP/1.1" 200',
        '192.0.2.1 - - [31/Oct/2026:10:00:00 +0900] "GET / HTTP/1.1',
        # ステータスが数字でない
        '192.0.2.1 - - [31/Oct/2026:10:00:00 +0900] "GET / HTTP/1.1" OK 1 "-" "-"',
        # 日時が壊れている
        '192.0.2.1 - - [32/Oct/2026:10:00:00 +0900] "GET / HTTP/1.1" 200 1 "-" "-"',
        '192.0.2.1 - - [31/Foo/2026:10:00:00 +0900] "GET / HTTP/1.1" 200 1 "-" "-"',
        '192.0.2.1 - - [31/Oct/2026:25:00:00 +0900] "GET / HTTP/1.1" 200 1 "-" "-"',
        '192.0.2.1 - - [2026-10-31T10:00:00+09:00] "GET / HTTP/1.1" 200 1 "-" "-"',
        # 末尾にゴミ
        '192.0.2.1 - - [31/Oct/2026:10:00:00 +0900] "GET / HTTP/1.1" 200 1 "-" "-" extra',
    ],
)
def test_malformed_lines_raise_parse_error(line):
    with pytest.raises(ParseError):
        parse_line(line)


def test_parse_time_keeps_timezone():
    t = parse_time("01/Jan/2026:00:00:00 -0530")
    assert t.utcoffset() == -timedelta(hours=5, minutes=30)


def test_parse_time_rejects_feb_30():
    with pytest.raises(ParseError):
        parse_time("30/Feb/2026:00:00:00 +0900")


@pytest.mark.parametrize(
    "request_line, expected",
    [
        ("GET / HTTP/1.1", ("GET", "/", "HTTP/1.1")),
        ("GET /old", ("GET", "/old", None)),
        ("-", (None, None, None)),
        ("", (None, None, None)),
        ("GET http://evil.example/ HTTP/1.1", (None, None, None)),  # プロキシ悪用の試行
    ],
)
def test_parse_request(request_line, expected):
    assert parse_request(request_line) == expected
