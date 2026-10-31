import gzip
from pathlib import Path

import pytest

from ala.reader import MAX_SAMPLES, ReadStats, StrictModeError, collect_files, read_entries

FIXTURES = Path(__file__).parent / "fixtures"
VALID = '192.0.2.1 - - [31/Oct/2026:10:00:00 +0900] "GET / HTTP/1.1" 200 1 "-" "-"\n'


def test_collect_files_from_directory_includes_gz():
    files = collect_files([FIXTURES])
    assert [f.name for f in files] == ["access.log", "access.log.2.gz"]


def test_collect_files_glob_filters_other_logs(tmp_path):
    (tmp_path / "access.log").write_text(VALID)
    (tmp_path / "error.log").write_text("error\n")
    assert [f.name for f in collect_files([tmp_path])] == ["access.log"]


def test_collect_files_deduplicates(tmp_path):
    f = tmp_path / "access.log"
    f.write_text(VALID)
    assert len(collect_files([f, tmp_path, f])) == 1


def test_collect_files_missing_path(tmp_path):
    with pytest.raises(FileNotFoundError):
        collect_files([tmp_path / "nope.log"])


def test_read_fixture_continues_past_malformed_lines():
    stats = ReadStats()
    entries = list(read_entries(collect_files([FIXTURES]), stats))
    assert len(entries) == 8
    assert stats.files == 2
    assert stats.total_lines == 11
    assert stats.parsed == 8
    assert stats.blank == 1
    assert stats.malformed == 2
    assert [(m.lineno, m.excerpt) for m in stats.samples] == [
        (5, "this line is broken"),
        (6, '198.51.100.7 - - [32/Oct/2026:10:00:00 +0900] "GET /bad-date HTTP/1.1" 200 1 "-" "-"'),
    ]


def test_gzip_detected_by_content_not_extension(tmp_path):
    f = tmp_path / "access.log"  # 中身は gzip だが拡張子は .log
    f.write_bytes(gzip.compress(VALID.encode()))
    assert len(list(read_entries([f], ReadStats()))) == 1


def test_invalid_utf8_bytes_do_not_stop_reading(tmp_path):
    f = tmp_path / "access.log"
    f.write_bytes(b"\xff\xfe broken \x80\n" + VALID.encode())
    stats = ReadStats()
    assert len(list(read_entries([f], stats))) == 1
    assert stats.malformed == 1


def test_corrupted_gzip_keeps_other_files(tmp_path):
    bad = tmp_path / "access.log.1.gz"
    bad.write_bytes(gzip.compress((VALID * 3).encode())[:-10])  # 末尾を欠損させる
    good = tmp_path / "access.log"
    good.write_text(VALID)
    stats = ReadStats()
    entries = list(read_entries([bad, good], stats))
    assert len(stats.file_errors) == 1
    assert stats.file_errors[0][0] == str(bad)
    assert len(entries) >= 1  # good の 1 行は必ず読める


def test_samples_are_capped_but_count_is_exact(tmp_path):
    f = tmp_path / "access.log"
    f.write_text("broken\n" * (MAX_SAMPLES + 5))
    stats = ReadStats()
    list(read_entries([f], stats))
    assert stats.malformed == MAX_SAMPLES + 5
    assert len(stats.samples) == MAX_SAMPLES


def test_strict_mode_stops_on_first_malformed_line(tmp_path):
    f = tmp_path / "access.log"
    f.write_text(VALID + "broken\n" + VALID)
    with pytest.raises(StrictModeError, match=":2:"):
        list(read_entries([f], ReadStats(), strict=True))
