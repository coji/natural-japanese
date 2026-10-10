# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "sudachipy>=0.6.8",
#     "sudachidict-core>=20240409",
#     "trafilatura>=1.12",
# ]
# ///
"""corpus/selfcorpus/profile_self.py — 本人の文書(対象セット)の特徴を、H・G と並べて見る。

対象は3種類: Artifact Share の顧客向け文書(corpus/private/as/)、zenn-content の記事
(スキル作成 2026-07-12 の前と後)、本人の PR 説明文(corpus/private/prs/)。
比べる相手は Qiita の AI 以前の記事(H、無作為 600本)と、対コーパスの AI 記事(G、7モデル)。
長さの交絡を避けるため、指標は 1,000字あたりの率か、記事ごとの中央値で出す。

出力: corpus/private/self-profile.md(本人の文書の数値。タイトルは含めないがコミットしない)
"""
from __future__ import annotations
import gzip, json, random, re, statistics, subprocess, sys
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills/natural-japanese/scripts"))
sys.path.insert(0, str(ROOT / "corpus/timeslice"))
from features import features  # noqa: E402
from lint import run_lint  # noqa: E402
import trafilatura  # noqa: E402

SKILL_START = "2026-07-12"
WORDS = ["瞬間", "効く", "境界", "守る", "上限", "土台", "壊れる", "道具", "明示", "基準"]

def html_to_text(h: str) -> str:
    t = trafilatura.extract(h, include_tables=False, favor_precision=False, output_format="markdown")
    return t or ""

def load_groups() -> dict[str, list[str]]:
    g: dict[str, list[str]] = {}
    idx = json.loads((ROOT / "corpus/private/as/index.json").read_text())
    docs = []
    for x in idx:
        raw = (ROOT / "corpus/private/as" / x["path"]).read_text(encoding="utf-8")
        docs.append(html_to_text(raw) if x["kind"] == "html_page" else raw)
    g["as 顧客向け文書"] = docs
    zenn = Path.home() / "progs/zenn-content/articles"
    pre, post = [], []
    for f in sorted(zenn.glob("*.md")):
        txt = f.read_text(encoding="utf-8")
        if not re.search(r"^published:\s*true", txt, re.M):
            continue
        d = subprocess.run(["git", "-C", str(zenn.parent), "log", "--diff-filter=A", "--format=%ad", "--date=short", "--", str(f)], capture_output=True, text=True).stdout.split()
        body = re.sub(r"\A---\n.*?\n---\n", "", txt, flags=re.S)
        (post if d and d[-1] >= SKILL_START else pre).append(body)
    g["Zenn スキル前"] = pre
    g["Zenn スキル後"] = post
    prs = json.loads((ROOT / "corpus/private/prs/prs.json").read_text())
    g["PR 説明文"] = [x["body"] for x in prs if re.search(r"[ぁ-んァ-ヶ]", x.get("body") or "")]
    recs = []
    for y in (2019, 2020, 2021, 2022):
        with gzip.open(ROOT / f"corpus/timeslice/qiita-aug/data/{y}.jsonl.gz", "rt") as f:
            recs += [json.loads(l)["body"] for l in f]
    g["H: Qiita AI以前(無作為)"] = random.Random(0).sample(recs, 600)
    G = []
    for s in ("tech-qiita", "tech-qiita-s100"):
        for p in (ROOT / "corpus/paired" / s / "ai").glob("*/*.md"):
            G.append(re.sub(r"\A---\n.*?\n---\n", "", p.read_text(encoding="utf-8"), flags=re.S))
    g["G: AI 7モデル"] = G
    return g

def main() -> None:
    groups = load_groups()
    rows = []
    cats_all: set[str] = set()
    per_group = {}
    for name, docs in groups.items():
        docs = [d for d in docs if len(d) > 200]
        fs = [features(d) for d in docs]
        chars = sum(f["prose_chars"] for f in fs) / 1000 or 1
        lem = Counter()
        for f in fs: lem.update(f["lemmas"])
        cats = Counter()
        for d in docs:
            cats.update({x.category for x in run_lint(d, genre="tech")[0]})
        cats_all |= set(cats)
        per_group[name] = (len(docs), fs, chars, lem, cats)
    out = ["# 本人の文書の特徴(H・G との比較)", "",
           "語と構造は 1,000字あたり(地の文)。箇条書きは記事ごとの中央値。検出器は文書発火率(長さの交絡に注意)。", ""]
    head = ["群", "本数", "地の文 中央値", "太字", "箇条書き", "ダッシュ"] + WORDS
    out += ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for name, (n, fs, chars, lem, cats) in per_group.items():
        cells = [name, str(n), f"{statistics.median(f['prose_chars'] for f in fs):.0f}",
                 f"{sum(f['bold'] for f in fs)/chars:.2f}",
                 f"{statistics.median(f['list_lines']/max(f['nonblank_lines'],1) for f in fs):.2f}",
                 f"{sum(f['dashes'] for f in fs)/chars:.2f}"] + [f"{lem[w]/chars:.3f}" for w in WORDS]
        out.append("| " + " | ".join(cells) + " |")
    out += ["", "| 検出器 | " + " | ".join(per_group) + " |", "|---|" + "---|" * len(per_group)]
    for c in sorted(cats_all):
        out.append(f"| {c} | " + " | ".join(f"{v[4][c]/v[0]:.0%}" for v in per_group.values()) + " |")
    p = ROOT / "corpus/private/self-profile.md"
    p.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))

if __name__ == "__main__":
    main()
