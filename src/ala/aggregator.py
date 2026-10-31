"""解析済みエントリを日別・IP 別・パス別に集計するモジュール。"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable

from .parser import LogEntry


@dataclass
class Report:
    total: int = 0
    daily: Counter[date] = field(default_factory=Counter)
    ips: Counter[str] = field(default_factory=Counter)
    paths: Counter[str] = field(default_factory=Counter)
    unknown_path: int = 0  # リクエスト行が壊れていてパスが取れなかった件数

    def daily_series(self) -> list[tuple[date, int]]:
        """最初の日から最後の日まで、アクセス 0 件の日も含めて日付順に返す。"""
        if not self.daily:
            return []
        start, end = min(self.daily), max(self.daily)
        days = (end - start).days
        return [(d, self.daily[d]) for d in (start + timedelta(n) for n in range(days + 1))]

    @staticmethod
    def top(counter: Counter[str], n: int | None) -> list[tuple[str, int]]:
        """件数の多い順。同数ならキーの昇順にして結果を安定させる。"""
        items = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
        return items if n is None else items[:n]


def normalize_path(path: str, keep_query: bool = False) -> str:
    if keep_query:
        return path
    return path.split("?", 1)[0].split("#", 1)[0]


def aggregate(
    entries: Iterable[LogEntry],
    since: date | None = None,
    until: date | None = None,
    keep_query: bool = False,
) -> Report:
    """エントリを集計する。since / until は両端を含む（ログのローカル日付で判定）。"""
    report = Report()
    for e in entries:
        day = e.time.date()
        if since and day < since:
            continue
        if until and day > until:
            continue
        report.total += 1
        report.daily[day] += 1
        report.ips[e.ip] += 1
        if e.path is None:
            report.unknown_path += 1
        else:
            report.paths[normalize_path(e.path, keep_query)] += 1
    return report
