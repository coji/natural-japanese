# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "sentence-transformers>=3.0.0",
#     "numpy",
#     "sudachipy>=0.6.8",
#     "sudachidict-core>=20240409",
# ]
# ///
"""corpus/timeslice/embed_eval.py — 埋め込みの「話題の平板さ」を新しいコーパスで測り直す(ロードマップ S7)。

skills/natural-japanese/scripts/semantic.py と同じ文分割・同じ指標
(coherence_flatness_range: 隣接文類似度の最大値 - 最小値。狭いほど話題の起伏がない)を、
対コーパス(human と各モデル)と時系列コーパス(H と W から無作為に N 本)に当てる。
2026-07 の校正は AI 側が汚染コーパスだった(D4)。閾値は semantic.py の既定値と tech 用を使う。

出力: qiita-aug/embed-eval.md(数値のみ)

使い方:
    uv run corpus/timeslice/embed_eval.py --paired tech-qiita tech-qiita-s100 --sample 300
"""

from __future__ import annotations

import argparse
import gzip
import json
import random
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "skills" / "natural-japanese" / "scripts"))
import semantic as sem  # noqa: E402

DATA = HERE / "qiita-aug" / "data"
FM_RE = re.compile(r"\A---\n.*?\n---\n", re.S)
THRESHOLDS = {"既定": sem.DEFAULT_FLATNESS_THRESHOLD, "tech": sem.GENRE_PROFILES["tech"]["flatness_threshold"]}


def flatness(model, text: str) -> float | None:
    sents = [s for _, s in sem.doc_sentences_with_lines(text)]
    if len(sents) < sem.MIN_SENTENCES_FOR_STATS:
        return None
    emb = model.encode(sents, normalize_embeddings=True, batch_size=64, show_progress_bar=False)
    return sem.compute_metrics(emb)["coherence_flatness_range"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--paired", nargs="*", default=["tech-qiita", "tech-qiita-s100"])
    parser.add_argument("--sample", type=int, default=300)
    args = parser.parse_args()

    groups: dict[str, list[str]] = defaultdict(list)
    for s in args.paired:
        d = ROOT / "corpus" / "paired" / s
        for p in sorted((d / "human").glob("*.md")):
            groups["H'"].append(FM_RE.sub("", p.read_text(encoding="utf-8"), count=1))
        for m in sorted(x for x in (d / "ai").iterdir() if x.is_dir()):
            for p in sorted(m.glob("*.md")):
                groups[m.name].append(FM_RE.sub("", p.read_text(encoding="utf-8"), count=1))
    rng = random.Random(0)
    for name, years in {"H(2019-22)": [2019, 2020, 2021, 2022], "W(2026)": [2026]}.items():
        bodies = []
        for y in years:
            with gzip.open(DATA / f"{y}.jsonl.gz", "rt", encoding="utf-8") as f:
                bodies += [json.loads(l)["body"] for l in f]
        groups[name] = rng.sample(bodies, min(args.sample, len(bodies)))

    model = sem.load_model(sem.DEFAULT_MODEL)
    out = ["# 埋め込みの「話題の平板さ」の再測定(S7)", ""]
    out.append("coherence_flatness_range(隣接文類似度の最大 - 最小)。値が閾値以下を「平板」として検出する。10文未満の記事は除く。")
    out += ["", "| 層 | 測れた記事 | 中央値 | " + " | ".join(f"検出率({k} {v:.3f})" for k, v in THRESHOLDS.items()) + " |"]
    out.append("|---|---|---|" + "---|" * len(THRESHOLDS))
    for name, texts in groups.items():
        vals = [v for v in (flatness(model, t) for t in texts) if v is not None]
        cells = [f"{sum(v <= th for v in vals) / len(vals):.0%}" for th in THRESHOLDS.values()] if vals else ["-"] * len(THRESHOLDS)
        med = f"{statistics.median(vals):.3f}" if vals else "-"
        out.append(f"| {name} | {len(vals)} / {len(texts)} | {med} | " + " | ".join(cells) + " |")
        print(out[-1], file=sys.stderr)
    (HERE / "qiita-aug" / "embed-eval.md").write_text("\n".join(out) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
