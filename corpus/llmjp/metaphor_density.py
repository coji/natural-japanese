# /// script
# requires-python = ">=3.11"
# dependencies = ["sudachipy>=0.6.8", "sudachidict-core>=20240409", "trafilatura>=1.12"]
# ///
"""corpus/llmjp/metaphor_density.py — 比喩の語彙の密度(地の文1,000字あたり)を、人間・AI・作者の文書で比べる。

比喩になりやすい語(何が起きるのかをぼかす語)を基本形で数える。文字どおりの意味で普通に使う語
(検証・履歴・応答・基準など)は除いた。指摘の閾値を、人間の文書での誤検知が5%未満になるように決める材料。

出力: corpus/llmjp/metaphor-density.md(数値のみ)
"""
from __future__ import annotations
import gzip, json, random, re, statistics, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "corpus/timeslice"))
sys.path.insert(0, str(HERE))
from features import features  # noqa: E402
from label_sample import trim  # noqa: E402

WORDS = ["効く", "壊れる", "土台", "境界", "入口", "道具", "守る", "届く", "残る", "任せる", "繋がる", "つながる",
         "瞬間", "落とし穴", "踏み込む", "切り分ける", "潰す", "静か"]

def density(text: str) -> tuple[float, int]:
    f = features(text)
    n = sum(f["lemmas"].get(w, 0) for w in WORDS)
    return n / max(f["prose_chars"], 1) * 1000, f["prose_chars"]

def main() -> None:
    rng = random.Random(0)
    groups: dict[str, list[str]] = {}
    llm = [json.loads(l) for f in sorted((ROOT / "corpus/private/llmjp").glob("*.scored.jsonl")) for l in open(f, encoding="utf-8")]
    groups["人間: LLM-jp 説明的な Web(スコア0.7以上)"] = [trim(r["text"]) for r in rng.sample([r for r in llm if r["score"] >= 0.7], 600)]
    h = []
    for y in (2019, 2020, 2021, 2022):
        with gzip.open(ROOT / f"corpus/timeslice/qiita-aug/data/{y}.jsonl.gz", "rt", encoding="utf-8") as f:
            h += [json.loads(l)["body"] for l in f]
    groups["人間: Qiita AI以前(無作為)"] = rng.sample(h, 600)
    w = []
    with gzip.open(ROOT / "corpus/timeslice/qiita-aug/data/2026.jsonl.gz", "rt", encoding="utf-8") as f:
        w = [json.loads(l)["body"] for l in f]
    groups["W: Qiita 2026"] = rng.sample(w, 600)
    for m in ("claude-opus-5-5@low", "gpt-6-luna@low", "gemini-3.8-flash@low"):
        groups[f"AI ベンチ: {m}"] = [p.read_text(encoding="utf-8") for p in (ROOT / "corpus/private/bench/out" / m).glob("*.md")]
    import trafilatura
    idx = json.loads((ROOT / "corpus/private/as/index.json").read_text())
    docs = []
    for x in idx:
        raw = (ROOT / "corpus/private/as" / x["path"]).read_text(encoding="utf-8")
        docs.append((trafilatura.extract(raw, output_format="markdown") or "") if x["kind"] == "html_page" else raw)
    groups["作者: 顧客向け文書"] = docs
    groups["スキルの文書(SKILL.md・references)"] = [p.read_text(encoding="utf-8") for p in (ROOT / "skills/natural-japanese").rglob("*.md")]
    out = ["# 比喩の語彙の密度(地の文1,000字あたり)", "", "語: " + "・".join(WORDS), "",
           "| 群 | n | 中央値 | 90パーセンタイル | 0.5超 | 1.0超 | 1.5超 |", "|---|---|---|---|---|---|---|"]
    for g, texts in groups.items():
        ds = [d for d, pc in (density(t) for t in texts) if pc >= 500]
        ds.sort()
        p90 = ds[int(len(ds) * 0.9)] if ds else 0
        out.append(f"| {g} | {len(ds)} | {statistics.median(ds):.2f} | {p90:.2f} | "
                   + " | ".join(f"{sum(d > t for d in ds) / len(ds):.0%}" for t in (0.5, 1.0, 1.5)) + " |")
    (HERE / "metaphor-density.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))

if __name__ == "__main__":
    main()
