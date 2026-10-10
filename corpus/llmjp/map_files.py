# /// script
# requires-python = ">=3.11"
# ///
"""corpus/llmjp/map_files.py — LLM-jp コーパス v4 の ja_cc のファイルと収集時期の対応表を作る。

各ファイルの先頭 HEAD_BYTES だけを範囲指定で取り、gzip を途中まで展開して、
完全に読めた行の meta.date から主な年月を数える。ja_cc は1ファイルがほぼ1回のクロールに
当たる(調査メモ corpus/reports/research/llm-jp-corpus.md 4.2)ので、ファイル単位で時期を選べる。
サーバは同一アドレスからの同時接続を制限しているため、1本ずつ順に取る。

出力: corpus/llmjp/file-map-<level>.json(コミットする。本文は含まない)
使い方: uv run corpus/llmjp/map_files.py --level level0
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
import zlib
from collections import Counter
from pathlib import Path

BASE = "https://gitlab.llm-jp.nii.ac.jp/datasets/llm-jp-corpus-v4/-/raw/main/ja/ja_cc"
HEAD_BYTES = 200_000
HERE = Path(__file__).resolve().parent


def head_records(url: str) -> list[dict]:
    req = urllib.request.Request(url, headers={"Range": f"bytes=0-{HEAD_BYTES - 1}", "User-Agent": "natural-japanese-corpus/1.0 (research)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    d = zlib.decompressobj(16 + zlib.MAX_WBITS)
    text = d.decompress(data).decode("utf-8", "ignore")
    lines = text.split("\n")[:-1]  # 最後の行は途中で切れている
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", default="level0")
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--end", type=int, default=1000)
    a = ap.parse_args()
    path = HERE / f"file-map-{a.level}.json"
    table = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    for i in range(a.start, a.end):
        name = f"{i:04d}"
        if name in table:
            continue
        try:
            recs = head_records(f"{BASE}/{a.level}/{name}.jsonl.gz")
        except Exception as e:  # noqa: BLE001
            print(f"{name} ERR {e}", flush=True)
            if "404" in str(e):
                break
            time.sleep(10)
            continue
        months = Counter((r.get("meta", {}).get("date") or "")[:7] for r in recs)
        top, n = months.most_common(1)[0] if months else ("", 0)
        table[name] = {"n": len(recs), "top_month": top, "top_share": round(n / max(len(recs), 1), 2),
                       "months": dict(months.most_common(5))}
        print(f"{name} {top} {table[name]['top_share']} n={len(recs)}", flush=True)
        if i % 20 == 0:
            path.write_text(json.dumps(table, ensure_ascii=False, indent=1), encoding="utf-8")
        time.sleep(1)
    path.write_text(json.dumps(table, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
