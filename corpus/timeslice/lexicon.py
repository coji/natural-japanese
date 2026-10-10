# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""corpus/timeslice/lexicon.py — 語彙の候補を見つける(ロードマップ S4)。

features.py の出力から、内容語の基本形ごとに次の2つの比較を行う。
    W/H: 2026年の公開記事 vs AI以前(2019〜2022年)の公開記事
    G/H': 生成記事(対コーパスの AI 側) vs その対の human 記事
両方で増えた語を「AI 時代の語彙」の候補にする。

統計の規約(ROADMAP.md 5章):
    - 事前分布つきの対数オッズ比(Monroe et al. 2008)で z 値を出す。両群を合わせた
      頻度を事前分布にし、まれな語の偶然の差を抑える
    - 最低出現数: W/H では両群合わせて MIN_DOCS 記事以上に出た語だけを見る
    - 効果の大きさは 1,000字あたりの出現率の比で測り、その比で並べる(記事の長さの違いを打ち消す)。
      記事数が多いと z はありふれた語でも大きくなるため、z はふるい分けにだけ使う
    - 記事の割合(その語を含む記事の数 / 記事数)も参考に並べる
    - W と H の記事の割合には、著者単位のブートストラップで 95% 区間を付ける
    - W の話題の偏りを確かめるため、AI 関連タグの記事とそれ以外で W の割合を分けて出す

出力: qiita-aug/lexicon-candidates.md(数値のみ。コミットする)

使い方:
    uv run corpus/timeslice/lexicon.py --paired tech-qiita tech-qiita-s100
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "qiita-aug" / "data"
PRE = [2019, 2020, 2021, 2022]
POST = 2026
ALPHA0 = 1000.0
MIN_DOCS = 50
Z_MIN = 3.0
# 効果の大きさは 1,000字あたりの出現率の比で測る。記事の割合だと、長い記事(W は H の
# 約2倍、G も H' より長い)ほど、ありふれた語でも割合が上がってしまうため
RATE_RATIO_MIN = 3.0
BOOT = 200
AI_TAGS = {
    "AI", "生成AI", "ChatGPT", "OpenAI", "LLM", "Claude", "ClaudeCode", "Gemini", "Copilot",
    "GitHubCopilot", "Cursor", "MCP", "AIエージェント", "AIAgent", "RAG", "Codex", "プロンプトエンジニアリング",
    "LangChain", "Dify", "AzureOpenAIService", "Bedrock", "AmazonBedrock", "vibecoding", "バイブコーディング",
}


def load(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return [json.loads(l) for l in f]


def log_odds_z(c1: Counter, c2: Counter) -> dict[str, float]:
    n1, n2 = sum(c1.values()), sum(c2.values())
    bg = c1 + c2
    nb = sum(bg.values())
    z = {}
    for w, b in bg.items():
        a = ALPHA0 * b / nb
        y1, y2 = c1.get(w, 0), c2.get(w, 0)
        d = math.log((y1 + a) / (n1 + ALPHA0 - y1 - a)) - math.log((y2 + a) / (n2 + ALPHA0 - y2 - a))
        z[w] = d / math.sqrt(1 / (y1 + a) + 1 / (y2 + a))
    return z


def doc_share(docs: list[dict]) -> Counter:
    return Counter(w for d in docs for w in d["lemmas"])


def token_counts(docs: list[dict]) -> Counter:
    c: Counter = Counter()
    for d in docs:
        c.update(d["lemmas"])
    return c


def author_bootstrap(docs: list[dict], words: list[str], seed: int = 0) -> dict[str, tuple[float, float]]:
    by_author: dict[str, list[dict]] = defaultdict(list)
    for d in docs:
        by_author[d.get("author", d.get("id"))].append(d)
    authors = list(by_author)
    rng = random.Random(seed)
    samples: dict[str, list[float]] = {w: [] for w in words}
    for _ in range(BOOT):
        picked = [d for a in (rng.choice(authors) for _ in authors) for d in by_author[a]]
        n = len(picked)
        share = Counter(w for d in picked for w in d["lemmas"] if w in samples)
        for w in words:
            samples[w].append(share[w] / n)
    out = {}
    for w, s in samples.items():
        s.sort()
        out[w] = (s[int(0.025 * BOOT)], s[int(0.975 * BOOT) - 1])
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="語彙の候補を見つける")
    parser.add_argument("--paired", nargs="*", default=["tech-qiita", "tech-qiita-s100"])
    parser.add_argument("--top", type=int, default=80)
    args = parser.parse_args()

    H = [d for y in PRE for d in load(DATA / f"features-{y}.jsonl.gz")]
    W = load(DATA / f"features-{POST}.jsonl.gz")
    G: list[dict] = []
    Hp: list[dict] = []
    for s in args.paired:
        rows = load(DATA / f"features-paired-{s}.jsonl.gz")
        Hp += [r for r in rows if r["group"] == "human"]
        # G はタイトルだけの条件(グループ名に "/" を含まない)に限る
        G += [r for r in rows if r["group"] != "human" and "/" not in r["group"]]

    z_wh = log_odds_z(token_counts(W), token_counts(H))
    z_gh = log_odds_z(token_counts(G), token_counts(Hp))
    sh_h, sh_w, sh_g, sh_hp = doc_share(H), doc_share(W), doc_share(G), doc_share(Hp)
    W_ai = [d for d in W if AI_TAGS & set(d.get("tags", []))]
    W_other = [d for d in W if not (AI_TAGS & set(d.get("tags", [])))]
    sh_w_ai, sh_w_other = doc_share(W_ai), doc_share(W_other)

    def rate(c: Counter, n: int, w: str) -> float:
        return c[w] / n if n else 0.0

    tc_h, tc_w, tc_g, tc_hp = token_counts(H), token_counts(W), token_counts(G), token_counts(Hp)
    chars = {k: sum(d["prose_chars"] for d in v) / 1000 for k, v in {"H": H, "W": W, "G": G, "Hp": Hp}.items()}

    def per_k(c: Counter, key: str, w: str) -> float:
        # 0件の語で比が無限大にならないよう、0.5件を足す
        return (c[w] + 0.5) / chars[key]

    cands = []
    for w in z_wh:
        if sh_h[w] + sh_w[w] < MIN_DOCS:
            continue
        rr_wh = per_k(tc_w, "W", w) / per_k(tc_h, "H", w)
        rr_gh = per_k(tc_g, "G", w) / per_k(tc_hp, "Hp", w)
        if z_wh[w] >= Z_MIN and z_gh.get(w, 0) >= Z_MIN and rr_wh >= RATE_RATIO_MIN and rr_gh >= RATE_RATIO_MIN:
            cands.append((w, rr_wh, rr_gh))
    cands.sort(key=lambda x: -min(x[1], x[2]))
    cands = cands[: args.top]
    ci_h = author_bootstrap(H, [c[0] for c in cands])
    ci_w = author_bootstrap(W, [c[0] for c in cands], seed=1)

    out = ["# 語彙の候補(S4)", ""]
    out.append(
        f"H: AI以前の Qiita {len(H):,} 記事(2019〜2022年8月) / W: 2026年8月 {len(W):,} 記事"
        f"(うち AI 関連タグ {len(W_ai):,}) / G: 対コーパスの AI 側 {len(G)} 記事 / H': その対の human {len(Hp)} 記事"
    )
    out.append(
        f"条件: W/H と G/H' の両方で、事前分布つき対数オッズ比の z ≥ {Z_MIN}、かつ 1,000字あたりの出現率が {RATE_RATIO_MIN} 倍以上。"
        f"H と W を合わせて {MIN_DOCS} 記事以上に出た語。比の小さいほうで並べた。"
        f"記事の割合の区間は著者単位のブートストラップ({BOOT} 回)の 95% 区間。"
    )
    out.append("G/H' の対コーパスは開発用セット(ROADMAP.md 5章)。ここでの候補は S5 で検証用セットを使って確かめる。")
    out += ["", f"候補 {len(cands)} 語", ""]
    out += [
        "| 語 | 率の比 W/H | 率の比 G/H' | 記事の割合 H | W | W(AIタグ外) | W(AIタグ) | H' | G |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for w, rr_wh, rr_gh in cands:
        lo_h, hi_h = ci_h[w]
        lo_w, hi_w = ci_w[w]
        out.append(
            f"| {w} | {rr_wh:.1f} | {rr_gh:.1f} | {rate(sh_h, len(H), w):.1%} [{lo_h:.1%}, {hi_h:.1%}] "
            f"| {rate(sh_w, len(W), w):.1%} [{lo_w:.1%}, {hi_w:.1%}] "
            f"| {rate(sh_w_other, len(W_other), w):.1%} | {rate(sh_w_ai, len(W_ai), w):.1%} "
            f"| {rate(sh_hp, len(Hp), w):.0%} | {rate(sh_g, len(G), w):.0%} |"
        )
    report = HERE / "qiita-aug" / "lexicon-candidates.md"
    report.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out[:12 + 30]))


if __name__ == "__main__":
    main()
