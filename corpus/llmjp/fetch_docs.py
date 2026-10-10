# /// script
# requires-python = ">=3.11"
# ///
"""corpus/llmjp/fetch_docs.py — 一覧(manifest)に載った文書の本文を、LLM-jp コーパス v4 から取り出す。

一覧には本文を含めていない(各文書の著作権は書いた人にある)。この抽出スクリプトで、
利用者自身が LLM-jp コーパスの配布元から同じ文書を取り出す。本文の SHA-256 が一覧と一致するものだけを書き出す。
配布元から文書が削除されていれば、その文書は取り出せない(飛ばして件数を報告する)。

使い方:
    uv run corpus/llmjp/fetch_docs.py --manifest corpus/llmjp/manifest/explanatory-pre2022-v1.jsonl \
        --out docs.jsonl [--min-score 0.7] [--limit 1000]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_subset import stream_lines  # noqa: E402

BASE = "https://gitlab.llm-jp.nii.ac.jp/datasets/llm-jp-corpus-v4/-/raw/main/"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--min-score", type=float, default=0.0)
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    want = [json.loads(l) for l in open(a.manifest, encoding="utf-8")]
    want = [w for w in want if w.get("score", 1) >= a.min_score][: a.limit]
    by_source = defaultdict(dict)
    for w in want:
        by_source[w["source"].removeprefix("llm-jp-corpus-v4/")][w["docId"]] = w
    found = mismatch = 0
    with open(a.out, "w", encoding="utf-8") as fp:
        for src, docs in by_source.items():
            for line in stream_lines(BASE + src):
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                w = docs.get(rec.get("meta", {}).get("docId"))
                if not w:
                    continue
                text = rec.get("text") or ""
                if hashlib.sha256(text.encode("utf-8")).hexdigest() != w["sha256"]:
                    mismatch += 1
                    continue
                fp.write(json.dumps({**w, "text": text}, ensure_ascii=False) + "\n")
                found += 1
            print(f"{src}: {found} found so far", file=sys.stderr)
    print(f"requested {len(want)}, found {found}, hash mismatch {mismatch}, missing {len(want) - found - mismatch}")


if __name__ == "__main__":
    main()
