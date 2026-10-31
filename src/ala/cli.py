"""コマンドラインの入口。

    ala report logs/ --top 20 --since 2026-10-01
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from typing import Sequence

from .aggregator import aggregate
from .formatter import FORMATTERS
from .reader import DEFAULT_GLOB, ReadStats, StrictModeError, collect_files, read_entries


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"日付は YYYY-MM-DD 形式で指定してください: {value}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ala", description="Nginx アクセスログ分析ツール")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("report", help="ログを集計して表示する")
    r.add_argument("paths", nargs="+", help="ログファイルまたはディレクトリ（.gz 可）")
    r.add_argument("--glob", default=DEFAULT_GLOB,
                   help=f"ディレクトリ指定時に読むファイル名パターン（既定: {DEFAULT_GLOB}）")
    r.add_argument("--top", type=int, default=10, help="IP・パスの表示件数（0 で全件、既定: 10）")
    r.add_argument("--since", type=_date, help="集計開始日 YYYY-MM-DD（この日を含む）")
    r.add_argument("--until", type=_date, help="集計終了日 YYYY-MM-DD（この日を含む）")
    r.add_argument("--keep-query", action="store_true", help="パスのクエリ文字列を残して集計する")
    r.add_argument("--format", choices=FORMATTERS, default="text", help="出力形式（既定: text）")
    r.add_argument("--strict", action="store_true", help="不正な行があれば即座にエラー終了する")
    return p


def _warn(msg: str) -> None:
    print(msg, file=sys.stderr)


def cmd_report(args: argparse.Namespace) -> int:
    if args.top < 0:
        _warn("エラー: --top は 0 以上を指定してください")
        return 2
    if args.since and args.until and args.since > args.until:
        _warn("エラー: --since は --until 以前の日付を指定してください")
        return 2

    try:
        files = collect_files(args.paths, args.glob)
    except FileNotFoundError as e:
        _warn(f"エラー: {e}")
        return 1
    if not files:
        _warn(f"エラー: 読み込むファイルがありません（パターン: {args.glob}）")
        return 1

    stats = ReadStats()
    try:
        report = aggregate(
            read_entries(files, stats, strict=args.strict),
            since=args.since, until=args.until, keep_query=args.keep_query,
        )
    except StrictModeError as e:
        _warn(f"エラー: {e}")
        return 1

    top = args.top or None
    sys.stdout.write(FORMATTERS[args.format](report, stats, top))

    # 警告は集計結果と混ざらないよう stderr に出す
    for f, err in stats.file_errors:
        _warn(f"警告: {f} の読み込みに失敗しました（読めた行までは集計済み）: {err}")
    if stats.malformed:
        _warn(f"警告: 不正な形式の行を {stats.malformed:,} 件スキップしました")
        for m in stats.samples[:5]:
            _warn(f"  {m.file}:{m.lineno}: {m.reason}: {m.excerpt[:120]}")
        if stats.malformed > 5:
            _warn(f"  …ほか {stats.malformed - 5:,} 件（--format json で最大 20 件まで確認できます）")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "report":
        return cmd_report(args)
    return 2  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
