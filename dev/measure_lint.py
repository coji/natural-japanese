# /// script
# requires-python = ">=3.10"
# dependencies = ["sudachipy>=0.6.8", "sudachidict-core>=20240409"]
# ///
"""lint の検出器ごとに、生成AI以前の人間の文書と生成AIの文書で1本あたりの指摘数を比べる(手元の点検用)。

人間の文書で出る指摘はすべて誤検出とみなす。直すたびに、人間での指摘が減り、生成AIでの指摘が保たれるかを見る。
文書の本文は公開できないため、このリポジトリには入れていない。tests.json の形({"束の名前": ["本文", ...]})の
ファイルを手元で用意して渡す。

    uv run dev/measure_lint.py path/to/tests.json [--save out.json] [--compare base.json]
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/natural-japanese/scripts"))
from lint import run_lint, run_reading_load  # noqa: E402

SETS = {"人間 Qiita 2022": ("qiita2022", 200), "人間 llm-jp": ("llmjp", 200), "生成AI": ("generated_holdout", 100)}


def body(t: str) -> str:
    return t.split("\n---\n", 1)[1] if t.startswith("---\n") and "\n---\n" in t else t


def measure(path: Path) -> dict:
    tests = json.loads(path.read_text(encoding="utf-8"))
    rng = random.Random(0)
    out = {}
    for name, (key, n) in SETS.items():
        docs = tests[key] if len(tests[key]) <= n else rng.sample(tests[key], n)
        c = Counter()
        for t in docs:
            t = body(t)
            f, _ = run_lint(t)
            rl, _ = run_reading_load(t)
            c.update(x.category for x in f)
            c.update(f"(読解負荷) {x.category}" for x in rl)
            c["合計"] += len(f)
        out[name] = {k: v / len(docs) for k, v in c.items()}
    return out


def show(res: dict, base: dict | None) -> None:
    cats = sorted({k for v in res.values() for k in v}, key=lambda k: (k != "合計", k.startswith("("), k))
    names = list(SETS)
    print("| 検出器 | " + " | ".join(names) + " |")
    print("|---|" + "---|" * len(names))
    for k in cats:
        cells = []
        for n in names:
            v = res[n].get(k, 0.0)
            if base is not None:
                b = base[n].get(k, 0.0)
                cells.append(f"{v:.2f}" + (f"({v - b:+.2f})" if abs(v - b) >= 0.005 else ""))
            else:
                cells.append(f"{v:.2f}")
        print(f"| {k} | " + " | ".join(cells) + " |")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("tests", type=Path)
    ap.add_argument("--save", type=Path)
    ap.add_argument("--compare", type=Path)
    a = ap.parse_args()
    res = measure(a.tests)
    base = json.loads(a.compare.read_text(encoding="utf-8")) if a.compare else None
    show(res, base)
    if a.save:
        a.save.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
