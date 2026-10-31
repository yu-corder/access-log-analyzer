"""ログファイルを読み込み、解析済みエントリを順に返すモジュール。

不正な行やファイルがあっても例外で止めず、件数と内容を ReadStats に記録して処理を続ける。
"""

from __future__ import annotations

import gzip
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

from .parser import LogEntry, ParseError, parse_line

DEFAULT_GLOB = "*access*.log*"
MAX_SAMPLES = 20  # 記録しておく不正行サンプルの最大数


@dataclass
class MalformedLine:
    file: str
    lineno: int
    reason: str
    excerpt: str


@dataclass
class ReadStats:
    files: int = 0
    total_lines: int = 0
    parsed: int = 0
    blank: int = 0
    malformed: int = 0
    samples: list[MalformedLine] = field(default_factory=list)
    file_errors: list[tuple[str, str]] = field(default_factory=list)

    def add_malformed(self, item: MalformedLine) -> None:
        self.malformed += 1
        if len(self.samples) < MAX_SAMPLES:
            self.samples.append(item)


class StrictModeError(Exception):
    """strict モードで不正な行・ファイルを検出したときに送出される。"""


def collect_files(paths: Iterable[str | Path], pattern: str = DEFAULT_GLOB) -> list[Path]:
    """ファイル・ディレクトリの指定から、読み込むファイルの一覧を作る。

    ディレクトリは直下の ``pattern`` に一致するファイルを対象にする。
    存在しないパスは FileNotFoundError。
    """
    files: list[Path] = []
    for p in map(Path, paths):
        if p.is_dir():
            files.extend(sorted(f for f in p.glob(pattern) if f.is_file()))
        elif p.is_file():
            files.append(p)
        else:
            raise FileNotFoundError(f"ファイルまたはディレクトリが見つかりません: {p}")
    # 同じファイルが重複指定されても 1 回だけ読む
    seen: set[Path] = set()
    unique = []
    for f in files:
        key = f.resolve()
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique


def _open_text(path: Path):
    # gzip はマジックナンバーで判定する（拡張子が無い・間違っている場合に備える）
    with open(path, "rb") as fh:
        is_gzip = fh.read(2) == b"\x1f\x8b"
    # 不正なバイト列は置換文字にして読み進める
    if is_gzip:
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return open(path, "r", encoding="utf-8", errors="replace")


def read_entries(
    files: Iterable[Path], stats: ReadStats, strict: bool = False
) -> Iterator[LogEntry]:
    """ファイル群を 1 行ずつ解析して LogEntry を返すジェネレータ。"""
    for path in files:
        stats.files += 1
        try:
            with _open_text(path) as fh:
                for lineno, line in enumerate(fh, start=1):
                    stats.total_lines += 1
                    if not line.strip():
                        stats.blank += 1
                        continue
                    try:
                        entry = parse_line(line)
                    except ParseError as e:
                        item = MalformedLine(str(path), lineno, str(e), line.rstrip("\r\n")[:200])
                        if strict:
                            raise StrictModeError(
                                f"{item.file}:{item.lineno}: {item.reason}: {item.excerpt}"
                            ) from None
                        stats.add_malformed(item)
                        continue
                    stats.parsed += 1
                    yield entry
        except (OSError, EOFError, gzip.BadGzipFile) as e:
            # 壊れた gzip や読み込み権限なし。読めた行までは集計に含める
            if strict:
                raise StrictModeError(f"{path}: 読み込みに失敗しました: {e}") from None
            stats.file_errors.append((str(path), str(e)))
