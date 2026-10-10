# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "sudachipy>=0.6.8",
#     "sudachidict-core>=20240409",
# ]
# ///
"""corpus/timeslice/features.py — 記事ごとの特徴量を計算して保存する。

ロードマップ S2(外部調査の再現)と S4(語彙の候補探し)の共通の下ごしらえ。
時系列コーパス(qiita-aug/data/{year}.jsonl.gz)と対コーパス(paired/<set>/)の
どちらにも同じ定義を当てる。定義を1か所にまとめ、層ごとに数え方がずれないようにする。

記事ごとに保存するもの(data/features-<name>.jsonl.gz、非コミット):
    prose_chars       地の文の文字数(空白を除く)
    bold              太字(**…**)の数。コードブロックと行内コードを除く
    list_lines        箇条書きの行数 / nonblank_lines 空でない行数(コードブロックの中を除く)
    dashes            ダッシュ(— ―)の数。地の文で数える
    summary_heading   「まとめ」を含む見出しがあるか
    desu_masu         です・ます調の文の割合
    lemmas            内容語(名詞・動詞・形容詞・形状詞・副詞)の基本形ごとの出現数(地の文)

使い方:
    uv run corpus/timeslice/features.py --timeslice 2019 2026
    uv run corpus/timeslice/features.py --paired tech-qiita-holdout
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "skills" / "natural-japanese" / "scripts"))
from textcore import mask_markdown_structure  # noqa: E402

DATA = HERE / "qiita-aug" / "data"
FM_RE = re.compile(r"\A---\n.*?\n---\n", re.S)
FENCE_RE = re.compile(r"^\s*(```|~~~).*?^\s*(```|~~~)[^\n]*$", re.M | re.S)
INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
BOLD_RE = re.compile(r"\*\*[^*\n]+\*\*|__[^_\n]+__")
LIST_RE = re.compile(r"^\s*([-*+]|\d+[.)])\s+")
HEADING_RE = re.compile(r"^\s*#{1,6}\s+(.*)$", re.M)
DASH_RE = re.compile(r"[—―]")
SENT_RE = re.compile(r"[^。！？!?\n]+[。！？!?]")
CONTENT_POS = {"名詞", "動詞", "形容詞", "形状詞", "副詞"}

_tok = None


def tokenizer():
    global _tok
    if _tok is None:
        from sudachipy import Dictionary, SplitMode

        _tok = (Dictionary(dict="core").create(), SplitMode.C)
    return _tok


def features(body: str) -> dict:
    no_code = FENCE_RE.sub("", body)
    no_code_inline = INLINE_CODE_RE.sub("", no_code)
    masked = mask_markdown_structure(body)
    prose = re.sub(r"\s+", "", masked)
    lines = [l for l in no_code.splitlines() if l.strip()]
    sents = SENT_RE.findall(masked)
    desu_masu = sum(1 for s in sents if re.search(r"(です|ます|でした|ました|ません|でしょう)[。！？!?]$", s))
    tok, mode = tokenizer()
    lemmas: Counter = Counter()
    # sudachi の入力長の上限を避けるため、行ごとに解析する
    for line in masked.splitlines():
        line = line.strip()
        if not line:
            continue
        for chunk in (line[i : i + 4000] for i in range(0, len(line), 4000)):
            for m in tok.tokenize(chunk, mode):
                pos = m.part_of_speech()
                if pos[0] in CONTENT_POS and pos[1] != "数詞":
                    lemmas[m.dictionary_form()] += 1
    return {
        "prose_chars": len(prose),
        "bold": len(BOLD_RE.findall(no_code_inline)),
        "list_lines": sum(1 for l in lines if LIST_RE.match(l)),
        "nonblank_lines": len(lines),
        "dashes": len(DASH_RE.findall(prose)),
        "summary_heading": any("まとめ" in h for h in HEADING_RE.findall(no_code)),
        "desu_masu": desu_masu / len(sents) if sents else 0.0,
        "lemmas": dict(lemmas),
    }


def _row(rec: dict) -> dict:
    f = features(rec["body"])
    meta = {k: v for k, v in rec.items() if k != "body"}
    return {**meta, **f}


def run(name: str, records: list[dict], workers: int) -> None:
    out = DATA / f"features-{name}.jsonl.gz"
    with ProcessPoolExecutor(workers) as ex, gzip.open(out, "wt", encoding="utf-8") as f:
        for i, row in enumerate(ex.map(_row, records, chunksize=20)):
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            if (i + 1) % 1000 == 0:
                print(f"  {name}: {i + 1}/{len(records)}", file=sys.stderr)
    print(f"-> {out} ({len(records)} docs)", file=sys.stderr)


def timeslice_records(year: int) -> list[dict]:
    with gzip.open(DATA / f"{year}.jsonl.gz", "rt", encoding="utf-8") as f:
        return [json.loads(l) for l in f]


def paired_records(set_name: str) -> dict[str, list[dict]]:
    set_dir = ROOT / "corpus" / "paired" / set_name
    groups = {"human": sorted((set_dir / "human").glob("*.md"))}
    # ai/ はタイトルだけの条件(グループ名はモデル名)、ai-<条件>/ はほかの生成条件
    # (グループ名は "<条件>/<モデル名>")
    for cond_dir in sorted(p for p in set_dir.glob("ai*") if p.is_dir()):
        prefix = "" if cond_dir.name == "ai" else cond_dir.name.removeprefix("ai-") + "/"
        for d in sorted(p for p in cond_dir.iterdir() if p.is_dir()):
            groups[prefix + d.name] = sorted(d.glob("*.md"))
    return {
        g: [{"id": p.stem, "group": g, "body": FM_RE.sub("", p.read_text(encoding="utf-8"), count=1)} for p in paths]
        for g, paths in groups.items()
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="記事ごとの特徴量を計算する")
    parser.add_argument("--timeslice", nargs="*", type=int, default=[])
    parser.add_argument("--paired", nargs="*", default=[])
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    DATA.mkdir(parents=True, exist_ok=True)
    for year in args.timeslice:
        run(str(year), timeslice_records(year), args.workers)
    for set_name in args.paired:
        records = [r for rs in paired_records(set_name).values() for r in rs]
        run(f"paired-{set_name}", records, args.workers)


if __name__ == "__main__":
    main()
