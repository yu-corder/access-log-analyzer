"""Nginx アクセスログ 1 行を解析するモジュール。

対応形式は Nginx 標準の ``combined`` 形式:

    $remote_addr - $remote_user [$time_local] "$request" $status $body_bytes_sent
    "$http_referer" "$http_user_agent"

referer / user_agent が無い ``common`` 形式の行も受け付ける。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

def _quoted(name: str) -> str:
    """引用符で囲まれた項目。中身は「\\" 等のエスケープ」か「" と \\ 以外の文字」。"""
    return rf'"(?P<{name}>(?:[^"\\]|\\.)*)"'


_LINE_RE = re.compile(
    r"^(?P<ip>\S+) "
    r"\S+ "                                   # ident（通常は "-"）
    r"(?P<user>\S+) "
    r"\[(?P<time>[^\]]+)\] "
    + _quoted("request") + " "
    r"(?P<status>\d{3}) "
    r"(?P<size>\d+|-)"
    r"(?: " + _quoted("referer") + " " + _quoted("user_agent") + ")?"
    r"\s*$"
)

_TIME_RE = re.compile(
    r"^(?P<day>\d{2})/(?P<mon>[A-Za-z]{3})/(?P<year>\d{4})"
    r":(?P<h>\d{2}):(?P<m>\d{2}):(?P<s>\d{2}) (?P<tz>[+-]\d{4})$"
)

# %b はロケール依存なので月名は自前で変換する
_MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


class ParseError(ValueError):
    """ログ行が想定した形式でないときに送出される。"""


@dataclass(frozen=True)
class LogEntry:
    ip: str
    user: str | None
    time: datetime              # ログに書かれたタイムゾーン付き
    method: str | None          # リクエスト行が壊れている場合は None
    path: str | None
    protocol: str | None
    status: int
    size: int
    referer: str | None
    user_agent: str | None


def parse_time(value: str) -> datetime:
    """``31/Oct/2026:10:00:00 +0900`` 形式の文字列を datetime に変換する。"""
    m = _TIME_RE.match(value)
    if not m:
        raise ParseError(f"日時の形式が不正です: {value!r}")
    month = _MONTHS.get(m["mon"].capitalize())
    if month is None:
        raise ParseError(f"月名が不正です: {m['mon']!r}")
    tz = m["tz"]
    sign = 1 if tz[0] == "+" else -1
    offset = timedelta(hours=int(tz[1:3]), minutes=int(tz[3:5]))
    if offset >= timedelta(hours=24):
        raise ParseError(f"タイムゾーンが不正です: {tz!r}")
    try:
        return datetime(
            int(m["year"]), month, int(m["day"]),
            int(m["h"]), int(m["m"]), int(m["s"]),
            tzinfo=timezone(sign * offset),
        )
    except ValueError as e:  # 2月30日、25時など
        raise ParseError(f"日時の値が不正です: {value!r} ({e})") from None


def _dash_to_none(value: str | None) -> str | None:
    return None if value in (None, "-") else value


def parse_request(request: str) -> tuple[str | None, str | None, str | None]:
    """``GET /path HTTP/1.1`` を (method, path, protocol) に分解する。

    Nginx はスキャナ等の不正なリクエストもそのまま記録するため、
    3 要素に分解できない場合は (None, None, None) を返す（行自体は有効扱い）。
    """
    parts = request.split(" ")
    if len(parts) == 3 and parts[1].startswith("/"):
        return parts[0], parts[1], parts[2]
    if len(parts) == 2 and parts[1].startswith("/"):  # HTTP/0.9 形式
        return parts[0], parts[1], None
    return None, None, None


def parse_line(line: str) -> LogEntry:
    """ログ 1 行を解析して LogEntry を返す。不正な行は ParseError を送出する。"""
    line = line.rstrip("\r\n")
    if not line.strip():
        raise ParseError("空行です")
    m = _LINE_RE.match(line)
    if not m:
        raise ParseError("combined 形式に一致しません")

    method, path, protocol = parse_request(m["request"])
    size = m["size"]
    return LogEntry(
        ip=m["ip"],
        user=_dash_to_none(m["user"]),
        time=parse_time(m["time"]),
        method=method,
        path=path,
        protocol=protocol,
        status=int(m["status"]),
        size=0 if size == "-" else int(size),
        referer=_dash_to_none(m["referer"]),
        user_agent=_dash_to_none(m["user_agent"]),
    )
