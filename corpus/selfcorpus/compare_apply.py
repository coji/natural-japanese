# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "sudachipy>=0.6.8",
#     "sudachidict-core>=20240409",
# ]
# ///
"""corpus/selfcorpus/compare_apply.py — スキルを当てる前と後を比べる(ロードマップ S30)。

corpus/private/skill-apply/<id>/before.md と after.md の対ごとに:
    - 現行モデルの癖: 検証用セットまで残った語彙(F18 の21語)・ダッシュ・太字・箇条書き(1,000字あたり)
    - lint の検出器: 前だけ反応(直った)・両方(残った)・後だけ(新しく入った)
    - 文字数の比、数値の保持(前の文書にあった数値が後にも残っているか)
を出す。

出力: corpus/private/skill-apply/compare.md(本文は含めないが、作者の文書の数値なのでコミットしない)
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills/natural-japanese/scripts"))
sys.path.insert(0, str(ROOT / "corpus/timeslice"))
from features import features  # noqa: E402
from lint import run_lint  # noqa: E402

DIR = ROOT / "corpus/private/skill-apply"
WORDS = ["瞬間", "境界", "守る", "任せる", "上限", "本番", "土台", "道具", "届く", "自然", "セッション",
         "たび", "検証", "明示", "基準", "残る", "明確", "つながる", "応答", "履歴", "習慣", "効く", "壊れる"]
NUM_RE = re.compile(r"\d[\d,.]*")


def strip_fm(t: str) -> str:
    return re.sub(r"\A---\n.*?\n---\n", "", t, flags=re.S)


def cats(t: str) -> set[str]:
    return {f.category for f in run_lint(t, genre="tech")[0]}


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--after", default="after.md", help="比べる後の版のファイル名(例: after-v2.md)")
    args = ap.parse_args()
    pairs = sorted(p for p in DIR.iterdir() if (p / args.after).exists())
    fixed, kept, added = Counter(), Counter(), Counter()
    word_before = Counter(); word_after = Counter()
    chars_b = chars_a = 0.0
    struct = Counter()
    rows = []
    for p in pairs:
        b = strip_fm((p / "before.md").read_text(encoding="utf-8"))
        a = strip_fm((p / args.after).read_text(encoding="utf-8"))
        fb, fa = features(b), features(a)
        cb, ca = cats(b), cats(a)
        for c in cb - ca: fixed[c] += 1
        for c in cb & ca: kept[c] += 1
        for c in ca - cb: added[c] += 1
        chars_b += fb["prose_chars"] / 1000; chars_a += fa["prose_chars"] / 1000
        for w in WORDS:
            word_before[w] += fb["lemmas"].get(w, 0); word_after[w] += fa["lemmas"].get(w, 0)
        for k in ("bold", "dashes", "list_lines", "nonblank_lines"):
            struct[("b", k)] += fb[k]; struct[("a", k)] += fa[k]
        nb = set(NUM_RE.findall(b)); na = set(NUM_RE.findall(a))
        keep = len(nb & na) / len(nb) if nb else 1.0
        # 文字数の比は本文全体で見る(箇条書き中心の文書は地の文が小さく、比が大きく振れるため)
        rows.append((p.name.split("-")[0], len(a) / max(len(b), 1), keep, len(cb), len(ca)))

    out = [f"# スキルを当てる前と後(S30): {args.after}", "", f"対の数: {len(pairs)}", ""]
    out += ["## 対ごと", "", "| 種類 | 文字数の比(後/前) | 数値の保持 | 検出器の数(前→後) |", "|---|---|---|---|"]
    for kind, ratio, keep, nb, na in rows:
        out.append(f"| {kind} | {ratio:.2f} | {keep:.0%} | {nb} → {na} |")
    out += ["", "## 現行モデルの癖(1,000字あたり、全対の合計)", "", "| 項目 | 前 | 後 |", "|---|---|---|"]
    out.append(f"| 太字 | {struct[('b','bold')]/chars_b:.2f} | {struct[('a','bold')]/chars_a:.2f} |")
    out.append(f"| ダッシュ | {struct[('b','dashes')]/chars_b:.2f} | {struct[('a','dashes')]/chars_a:.2f} |")
    out.append(f"| 箇条書きの行の割合 | {struct[('b','list_lines')]/max(struct[('b','nonblank_lines')],1):.2f} | {struct[('a','list_lines')]/max(struct[('a','nonblank_lines')],1):.2f} |")
    total_b = sum(word_before.values()) / chars_b; total_a = sum(word_after.values()) / chars_a
    out.append(f"| 語彙候補の合計 | {total_b:.2f} | {total_a:.2f} |")
    for w in WORDS:
        if word_before[w] or word_after[w]:
            out.append(f"| {w} | {word_before[w]/chars_b:.3f} | {word_after[w]/chars_a:.3f} |")
    out += ["", "## lint の検出器", "", "| 検出器 | 直った | 残った | 新しく入った |", "|---|---|---|---|"]
    for c in sorted(set(fixed) | set(kept) | set(added)):
        out.append(f"| {c} | {fixed[c]} | {kept[c]} | {added[c]} |")
    (DIR / f"compare-{args.after.removesuffix('.md')}.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
