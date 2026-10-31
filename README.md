# access-log-analyzer

Nginx のアクセスログ（combined 形式）を集計する CLI ツールです。

- 日別アクセス数（アクセス 0 件の日も表示）
- アクセス元 IP・アクセスパスの上位 N 件
- `.gz` に圧縮されたローテート済みログもそのまま読み込み
- 不正な形式の行はスキップして処理を継続し、件数と該当行を報告

外部ライブラリは使っていません（Python 3.10 以上の標準ライブラリのみ。テストには pytest を使います）。

## セットアップ

```bash
cd access-log-analyzer
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## 使い方

サーバから落としたログを `logs/` に置いて実行します。

```bash
ala report logs/                              # ディレクトリ内の *access*.log* を全て集計
ala report logs/access.log logs/access.log.2.gz
ala report logs/ --top 20                     # 上位 20 件（0 で全件）
ala report logs/ --since 2026-10-01 --until 2026-10-31
ala report logs/ --keep-query                 # /page?x=1 と /page を別々に数える
ala report logs/ --format json > report.json  # text / json / csv
ala report logs/ --strict                     # 不正な行があればエラー終了
```

インストールせずに `PYTHONPATH=src python3 -m ala report logs/` でも実行できます。

### 不正な行の扱い

| 状況 | 動作 |
|---|---|
| 形式が合わない行・日時が壊れた行 | スキップして件数を数え、標準エラー出力に先頭 5 件を表示（JSON 出力には最大 20 件） |
| 空行 | 不正行には数えずに読み飛ばす |
| UTF-8 として読めないバイト列 | 置換文字にして読み進める |
| 壊れた gzip・読み込み権限なし | そのファイルを警告付きで打ち切り、他のファイルの処理は続ける |
| リクエスト行が不正（スキャナ等） | アクセスとして日別・IP 別には数え、パス集計からは除外して件数を別に表示 |

集計結果は標準出力、警告は標準エラー出力に分けて出すので、`> report.json` でリダイレクトしても警告は混ざりません。

### 日付の扱い

日別集計はログに記録されたタイムゾーン（サーバのローカル時刻）の日付で行います。

## テスト

```bash
pytest
```

## 構成

```
src/ala/
├── parser.py      # 1 行を解析して LogEntry を返す（失敗時は ParseError）
├── reader.py      # ファイル・.gz の読み込み、不正行の記録
├── aggregator.py  # 日別・IP 別・パス別の集計
├── formatter.py   # text / json / csv 出力
└── cli.py         # コマンドラインの入口
```

`logs/` 内のファイルは IP アドレスを含むため `.gitignore` で管理対象外にしています。
