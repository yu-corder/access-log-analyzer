import csv
import io
import json
from pathlib import Path

import pytest

from ala.cli import main

FIXTURES = Path(__file__).parent / "fixtures"


def run(capsys, *args):
    code = main(["report", *map(str, args)])
    out, err = capsys.readouterr()
    return code, out, err


def test_json_report_on_fixtures(capsys):
    code, out, err = run(capsys, FIXTURES, "--format", "json")
    assert code == 0
    data = json.loads(out)
    assert data["summary"] == {
        "files": 2, "total_lines": 11, "parsed": 8, "blank": 1,
        "malformed": 2, "accesses": 8, "unknown_path": 1,
    }
    assert data["daily"] == [
        {"date": "2026-10-29", "count": 2},
        {"date": "2026-10-30", "count": 1},
        {"date": "2026-10-31", "count": 3},
        {"date": "2026-11-01", "count": 0},
        {"date": "2026-11-02", "count": 2},
    ]
    assert data["ips"][0] == {"ip": "192.0.2.1", "count": 3}
    assert data["ips"][1] == {"ip": "203.0.113.9", "count": 2}
    assert {p["path"]: p["count"] for p in data["paths"]} == {
        "/": 2, "/posts/hello": 2, "/about": 1, "/api/like": 1, "/search": 1,
    }
    assert len(data["malformed_samples"]) == 2
    assert "不正な形式の行を 2 件スキップしました" in err


def test_text_report(capsys):
    code, out, _ = run(capsys, FIXTURES)
    assert code == 0
    assert "■ 日別アクセス数" in out
    assert "2026-10-31" in out
    assert "192.0.2.1" in out
    assert "パスを取得できなかったアクセス: 1 件" in out


def test_csv_report_with_top_and_since(capsys):
    code, out, _ = run(capsys, FIXTURES, "--format", "csv", "--top", "1", "--since", "2026-10-31")
    assert code == 0
    rows = list(csv.reader(io.StringIO(out)))
    assert rows[0] == ["section", "key", "count"]
    assert ["daily", "2026-10-31", "3"] in rows
    assert not any(r[0] == "daily" and r[1] < "2026-10-31" for r in rows[1:])
    assert sum(1 for r in rows if r[0] == "ip") == 1


def test_strict_mode_fails(capsys):
    code, out, err = run(capsys, FIXTURES, "--strict")
    assert code == 1
    assert out == ""
    assert "access.log:5" in err


def test_missing_path(capsys, tmp_path):
    code, _, err = run(capsys, tmp_path / "nope.log")
    assert code == 1
    assert "見つかりません" in err


def test_empty_directory(capsys, tmp_path):
    code, _, err = run(capsys, tmp_path)
    assert code == 1
    assert "読み込むファイルがありません" in err


def test_since_after_until_is_rejected(capsys):
    code, _, err = run(capsys, FIXTURES, "--since", "2026-11-01", "--until", "2026-10-01")
    assert code == 2


def test_invalid_date_argument(capsys):
    with pytest.raises(SystemExit) as e:
        main(["report", str(FIXTURES), "--since", "2026/10/01"])
    assert e.value.code == 2
