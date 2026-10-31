"""集計結果を テキスト表 / JSON / CSV に整形するモジュール。"""

from __future__ import annotations

import csv
import io
import json
import unicodedata

from .aggregator import Report
from .reader import ReadStats


def _width(s: str) -> int:
    """全角文字を 2 として表示幅を数える。"""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def _table(title: str, header: tuple[str, str], rows: list[tuple[str, int]]) -> str:
    rows_s = [(k, f"{v:,}") for k, v in rows]
    kw = max([_width(header[0])] + [_width(k) for k, _ in rows_s])
    vw = max([_width(header[1])] + [len(v) for _, v in rows_s])

    def line(k: str, v: str) -> str:
        return f"  {k}{' ' * (kw - _width(k))}  {' ' * (vw - _width(v))}{v}"

    out = [f"■ {title}", line(*header), "  " + "-" * (kw + vw + 2)]
    out += [line(k, v) for k, v in rows_s] or ["  (データなし)"]
    return "\n".join(out)


def format_text(report: Report, stats: ReadStats, top: int | None) -> str:
    parts = [
        "■ 概要",
        f"  読み込んだファイル : {stats.files}",
        f"  総行数             : {stats.total_lines:,}",
        f"  解析成功           : {stats.parsed:,}",
        f"  スキップした不正行 : {stats.malformed:,}",
        f"  集計対象アクセス数 : {report.total:,}",
        "",
        _table("日別アクセス数", ("日付", "件数"),
               [(d.isoformat(), n) for d, n in report.daily_series()]),
        "",
        _table(f"アクセス元IP 上位{top or '全件'}", ("IP", "件数"), Report.top(report.ips, top)),
        "",
        _table(f"アクセスパス 上位{top or '全件'}", ("パス", "件数"), Report.top(report.paths, top)),
    ]
    if report.unknown_path:
        parts.append(f"  ※ リクエスト行が不正でパスを取得できなかったアクセス: {report.unknown_path:,} 件")
    return "\n".join(parts) + "\n"


def to_dict(report: Report, stats: ReadStats, top: int | None) -> dict:
    return {
        "summary": {
            "files": stats.files,
            "total_lines": stats.total_lines,
            "parsed": stats.parsed,
            "blank": stats.blank,
            "malformed": stats.malformed,
            "accesses": report.total,
            "unknown_path": report.unknown_path,
        },
        "daily": [{"date": d.isoformat(), "count": n} for d, n in report.daily_series()],
        "ips": [{"ip": k, "count": n} for k, n in Report.top(report.ips, top)],
        "paths": [{"path": k, "count": n} for k, n in Report.top(report.paths, top)],
        "malformed_samples": [
            {"file": m.file, "line": m.lineno, "reason": m.reason, "text": m.excerpt}
            for m in stats.samples
        ],
        "file_errors": [{"file": f, "error": e} for f, e in stats.file_errors],
    }


def format_json(report: Report, stats: ReadStats, top: int | None) -> str:
    return json.dumps(to_dict(report, stats, top), ensure_ascii=False, indent=2) + "\n"


def format_csv(report: Report, stats: ReadStats, top: int | None) -> str:
    """section,key,count の縦持ち形式。表計算ソフトでフィルタしやすい。"""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["section", "key", "count"])
    for d, n in report.daily_series():
        w.writerow(["daily", d.isoformat(), n])
    for k, n in Report.top(report.ips, top):
        w.writerow(["ip", k, n])
    for k, n in Report.top(report.paths, top):
        w.writerow(["path", k, n])
    return buf.getvalue()


FORMATTERS = {"text": format_text, "json": format_json, "csv": format_csv}
