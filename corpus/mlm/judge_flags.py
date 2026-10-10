# /// script
# requires-python = ">=3.11"
# ///
"""corpus/mlm/judge_flags.py — 差が大きい語が、読んで本当に不自然かを、別系統の2モデルに判定させる。

比べる群(どの群の語かは判定モデルに伏せ、混ぜて並べる):
    flag_ai   AI 時代の文章(Qiita 2026年・生成記事・作者の文書)で差 > 4 の語
    rand_ai   同じ文章で差 < 1 の語(無作為)
    flag_pre  AI 以前の文章(Qiita 2022年・仕事の文章)で差 > 4 の語(誤検知の中身を見る)
どれもカタカナ語と英字の語は除く。

判定: その語の使い方が日本語として自然か(自然 / やや不自然 / 不自然)と、不自然なら理由の種類
      (英語の直訳のよう / 比喩でぼかしている / 硬い・大げさ / その他)。
判定モデル: gpt-6-luna(codex)と gemini-3.8-flash(agy)。どちらも effort low。

出力: corpus/private/mlm/judge-flags.jsonl と、corpus/mlm/judge-flags.md(数値のみ。コミットする)

使い方: uv run corpus/mlm/judge_flags.py [--n 120]
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PRIV = ROOT / "corpus/private/mlm"
sys.path.insert(0, str(ROOT / "corpus"))
import generate as g  # noqa: E402

JUDGES = {"gpt-6-luna": "codex", "gemini-3.8-flash": "agy"}
BATCH = 12
PROMPT = """次の各文で【】に入った語の使い方が、日本語として自然かを判定してください。
文の内容や専門用語の難しさではなく、その語の選び方・使い方だけを見ます。

- verdict: 自然 / やや不自然 / 不自然
  - 自然: 日本語を書き慣れた人がふつうに選ぶ使い方
  - やや不自然: 意味は通じるが、ふつうは別の言い方をする
  - 不自然: 日本語としておかしい、または何を言いたいのかがぼやける
- kind(自然でないときだけ): 英語の直訳 / 比喩でぼかす / 硬い・大げさ / その他
- better(自然でないときだけ): その語の代わりに、ふつうはどう言うか(短く)

次の JSON 配列だけを出力してください: [{{"id": "...", "verdict": "自然", "kind": "", "better": ""}}, ...]

{items}
"""


def ok(w) -> bool:
    return not re.fullmatch(r"[ァ-ヶー・]+", w["w"]) and "-" not in w["lemma"] and not re.search(r"[A-Za-z]", w["w"])


def mark(s: str, w: str) -> str | None:
    i = s.find(w)
    return None if i < 0 else s[:i] + "【" + w + "】" + s[i + len(w):]


def collect(n: int) -> list[dict]:
    rng = random.Random(0)
    pools = {"flag_ai": [], "rand_ai": [], "flag_pre": []}
    for name in ("qiita2026", "generated_holdout", "self", "qiita2022", "llmjp"):
        for l in open(PRIV / f"scores-{name}.jsonl", encoding="utf-8"):
            r = json.loads(l)
            for w in r["words"]:
                if not ok(w):
                    continue
                m = mark(r["s"], w["w"])
                if not m:
                    continue
                item = {"set": name, "w": w["w"], "lemma": w["lemma"], "d": w["d"], "text": m}
                if name in ("qiita2022", "llmjp"):
                    if w["d"] > 4:
                        pools["flag_pre"].append(item)
                elif w["d"] > 4:
                    pools["flag_ai"].append(item)
                elif w["d"] < 1:
                    pools["rand_ai"].append(item)
    items = []
    for grp, k in (("flag_ai", n), ("rand_ai", n), ("flag_pre", n // 2)):
        # 同じ語が並びすぎないよう、語ごとに3件まで
        pool = pools[grp]
        rng.shuffle(pool)
        seen = Counter()
        picked = []
        for it in pool:
            if seen[it["lemma"]] >= 3:
                continue
            seen[it["lemma"]] += 1
            picked.append({**it, "group": grp})
            if len(picked) >= k:
                break
        items += picked
    rng.shuffle(items)
    for i, it in enumerate(items):
        it["id"] = f"j{i}"
    return items


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=120)
    ap.add_argument("--parallel", type=int, default=3)
    a = ap.parse_args()
    g.prepare_isolation()
    path = PRIV / "judge-flags-items.json"
    if path.exists():
        items = json.loads(path.read_text(encoding="utf-8"))
    else:
        items = collect(a.n)
        path.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    by_id = {it["id"]: it for it in items}
    print(Counter(it["group"] for it in items), flush=True)

    out_path = PRIV / "judge-flags.jsonl"
    done = {}
    if out_path.exists():
        for l in open(out_path, encoding="utf-8"):
            r = json.loads(l)
            done[(r["judge"], r["id"])] = r
    jobs = []
    for m, kind in JUDGES.items():
        todo = [it for it in items if (m, it["id"]) not in done]
        for k in range(0, len(todo), BATCH):
            jobs.append((m, kind, todo[k:k + BATCH], len(jobs)))

    def work(job):
        m, kind, batch, i = job
        body = "\n\n".join(f"### id: {it['id']}\n{it['text']}" for it in batch)
        prompt = PROMPT.format(items=body)
        for _ in range(3):
            try:
                if kind == "codex":
                    home = g.ISOLATION_DIR / f"codex-home-jf-{i % a.parallel}"
                    home.mkdir(parents=True, exist_ok=True)
                    (home / "auth.json").write_bytes((g.CODEX_HOME / "auth.json").read_bytes())
                    res = g.run_codex(prompt, m, "low", codex_home=home)
                else:
                    res = g.run_agy(prompt, m, "low")
                mm = re.search(r"\[.*\]", res, re.S)
                rows = json.loads(mm.group(0)) if mm else []
                rows = [r for r in rows if isinstance(r, dict) and r.get("id") in {b["id"] for b in batch}]
                if len(rows) >= len(batch) * 0.8:
                    return m, rows
            except Exception as e:  # noqa: BLE001
                print(f"  ERR {m}: {e}", file=sys.stderr)
        return m, []

    with open(out_path, "a", encoding="utf-8") as f, ThreadPoolExecutor(a.parallel) as ex:
        for m, rows in ex.map(work, jobs):
            for r in rows:
                r["judge"] = m
                done[(m, r["id"])] = r
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
            print(f"{m}: {sum(1 for k in done if k[0] == m)} 件", flush=True)

    # 集計
    label = {"flag_ai": "AI 時代の文章で差 > 4", "rand_ai": "AI 時代の文章で差 < 1(対照)", "flag_pre": "AI 以前の文章で差 > 4"}
    out = ["# 差が大きい語は、読んで不自然か", "",
           "判定モデル gpt-6-luna と gemini-3.8-flash に、【】の語の使い方が自然かを判定させた。どの群の語かは伏せ、混ぜて並べた。", "",
           "| 群 | 語 | " + " | ".join(f"{m}: 不自然+やや不自然" for m in JUDGES) + " | 2モデルとも自然でない |", "|---|---|" + "---|" * (len(JUDGES) + 1)]
    for grp in label:
        ids = [it["id"] for it in items if it["group"] == grp]
        cells = []
        for m in JUDGES:
            vs = [done[(m, i)].get("verdict") for i in ids if (m, i) in done]
            cells.append(f"{sum(v in ('不自然', 'やや不自然') for v in vs) / max(len(vs), 1):.0%}({len(vs)})")
        both = [i for i in ids if all((m, i) in done for m in JUDGES)]
        nb = sum(all(done[(m, i)].get("verdict") in ("不自然", "やや不自然") for m in JUDGES) for i in both)
        out.append(f"| {label[grp]} | {len(ids)} | " + " | ".join(cells) + f" | {nb / max(len(both), 1):.0%} |")
    kinds = Counter(done[(m, it["id"])].get("kind") for it in items if it["group"] == "flag_ai" for m in JUDGES
                    if (m, it["id"]) in done and done[(m, it["id"])].get("verdict") in ("不自然", "やや不自然"))
    out += ["", "自然でないと判定された理由(AI 時代の文章で差 > 4、2モデル合計): " + "、".join(f"{k} {v}" for k, v in kinds.most_common())]
    (HERE / "judge-flags.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
