# /// script
# requires-python = ">=3.11"
# dependencies = ["torch", "transformers>=4.44", "fugashi", "unidic-lite", "huggingface_hub"]
# ///
"""steps.py — 旧版のスキルに変更を1つずつ足し、段階ごとに直前より良くなったかを確かめる。

段階には名前(label)をつけ、その段階のスキルのコミットを ref で指す。文書は versions.py と同じ47本
(corpus/private/versions/<doc>/before.md)。出力は <doc>/<label>.md。

    uv run corpus/bench/steps.py apply s0a --ref main      # その段階のスキルで47本を推敲する
    uv run corpus/bench/steps.py measure s0a               # 生成AI時代の語の密度・持ち込み・書き換えの割合
    uv run corpus/bench/steps.py judge s0a s0b             # sonnet で読みやすさの対比較と、中身の保持
    uv run corpus/bench/steps.py report s0a s0b "変更の説明"  # steps.md に1段落足す

判定は claude-sonnet-5-5(effort low)。読みやすさは左右を入れ替えて2回、中身の保持も2回。
依頼文は全段階で同じ(モードの指定をしない)。
"""
from __future__ import annotations

import argparse
import difflib
import json
import random
import re
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = ROOT / "corpus/private/versions"
ISO = Path("/tmp/corpus-gen-isolation")
NEUTRAL = ISO / "cwd"
sys.path.insert(0, str(HERE))
from versions import BUNDLE, JUDGE_CONTENT, JUDGE_READ, T  # noqa: E402

PROMPT = ("natural-japanese スキルで、input.md の文章を推敲してください。"
          "読み手と目的は文書の内容から判断してください。推敲した全文を output.md に書き出してください。"
          "input.md は変更しないでください。確認の質問はせず、最後まで自分の判断で進めてください。")
JUDGE_SYSTEM = "これは1往復のみの非対話バッチ呼び出しです。確認や質問をせず、指示された形式の出力だけを返してください。"
JUDGE_MODEL = "claude-sonnet-5-5"


def docs() -> list[Path]:
    return [d for d in sorted(OUT.iterdir()) if (d / "before.md").exists()]


def worktree(label: str, ref: str) -> Path:
    wt = ISO / f"wt-{label}"
    if not wt.exists():
        subprocess.run(["git", "-C", str(ROOT), "worktree", "add", "--detach", str(wt), ref], check=True)
    else:
        subprocess.run(["git", "-C", str(wt), "checkout", "-q", "--detach", ref], check=True)
    return wt


def apply_one(doc: Path, label: str, wt: Path) -> str:
    if (doc / f"{label}.md").exists():
        return f"skip {doc.name}"
    work = ISO / "steps" / f"{doc.name}-{label}"
    work.mkdir(parents=True, exist_ok=True)
    for f in work.iterdir():
        if f.is_file():
            f.unlink()
    (work / "input.md").write_text((doc / "before.md").read_text(encoding="utf-8"), encoding="utf-8")
    # 途中のツール呼び出しも残す(どの手順を実際に踏んだかを後から見るため)
    cmd = ["claude", "-p", PROMPT, "--model", "claude-opus-5-5", "--effort", "low", "--output-format", "stream-json", "--verbose",
           "--setting-sources", "project", "--plugin-dir", str(wt), "--add-dir", "/tmp",
           "--allowedTools", "Skill", "Read", "Write", "Edit", "Glob", "Grep",
           "Bash(uv run:*)", "Bash(python3:*)", "Bash(cat:*)", "Bash(wc:*)", "Bash(cp:*)", "Bash(mkdir:*)"]
    try:
        r = subprocess.run(cmd, cwd=work, capture_output=True, text=True, timeout=2400, stdin=subprocess.DEVNULL)
        log = r.stdout + "\n--- stderr ---\n" + r.stderr
    except subprocess.TimeoutExpired:
        log = "TIMEOUT"
    (doc / f"log-{label}.jsonl").write_text(log, encoding="utf-8")
    out = work / "output.md"
    if out.exists():
        (doc / f"{label}.md").write_text(out.read_text(encoding="utf-8"), encoding="utf-8")
        return f"ok {doc.name}"
    return f"FAIL {doc.name}"


def apply(label: str, ref: str, parallel: int) -> None:
    wt = worktree(label, ref)
    print(label, subprocess.run(["git", "-C", str(wt), "log", "-1", "--oneline"], capture_output=True, text=True).stdout.strip())
    jobs = docs()
    random.Random(1).shuffle(jobs)
    with ThreadPoolExecutor(parallel) as ex:
        for res in ex.map(lambda d: apply_one(d, label, wt), jobs):
            print(res, flush=True)


def measure(label: str) -> None:
    # 物差しは固定する(skill-v2 の style_check.py)。段階のブランチに style_check がなくても測れるように
    sys.path.insert(0, str(ISO / "wt-new/skills/natural-japanese/scripts"))
    from style_check import Pair, ok_word, sentences  # noqa: E402
    pair = Pair()
    for doc in docs():
        path = doc / "metrics.json"
        m = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        f = doc / f"{label}.md"
        if label in m or not f.exists():
            continue
        before = (doc / "before.md").read_text(encoding="utf-8")
        orig = pair.lemmas(before)
        text = f.read_text(encoding="utf-8")
        n, chars, lem = 0, 0, Counter()
        for _, s in sentences(text):
            chars += len(s)
            for w in pair.score(s):
                if ok_word(w) and w["d"] > T:
                    n += 1
                    lem[w["lemma"]] += 1
        m[label] = {"flags": n, "chars": chars, "density": round(n / max(chars, 1) * 1000, 2),
                    "introduced": sorted(k for k in lem if k not in orig),
                    "len_ratio": round(len(text) / max(len(before), 1), 3),
                    "edit": round(1 - difflib.SequenceMatcher(None, before, text, autojunk=False).ratio(), 3)}
        path.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
        print(doc.name, m[label]["density"], flush=True)


def sonnet(prompt: str) -> dict | None:
    for _ in range(3):
        try:
            r = subprocess.run(["claude", "-p", prompt, "--model", JUDGE_MODEL, "--effort", "low",
                                "--setting-sources", "project", "--disallowed-tools", "*",
                                "--append-system-prompt", JUDGE_SYSTEM],
                               capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=600, check=True, cwd=NEUTRAL)
            i = r.stdout.find("{")
            if i >= 0:
                return json.JSONDecoder().raw_decode(r.stdout[i:])[0]
        except Exception as e:  # noqa: BLE001
            print(f"  ERR: {e}", file=sys.stderr)
    return None


def judge(x: str, y: str, parallel: int) -> None:
    """読みやすさは read-sonnet-{x}-{y}-{r}(r=0 で X=x)、中身は content-sonnet-{label}-{r}。"""
    NEUTRAL.mkdir(parents=True, exist_ok=True)
    jobs = []
    for doc in docs():
        path = doc / "judge.json"
        j = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        before = (doc / "before.md").read_text(encoding="utf-8")
        if not ((doc / f"{x}.md").exists() and (doc / f"{y}.md").exists()):
            continue
        tx, ty = (doc / f"{x}.md").read_text(encoding="utf-8"), (doc / f"{y}.md").read_text(encoding="utf-8")
        for r, (a, b) in enumerate(((tx, ty), (ty, tx))):
            if f"read-sonnet-{x}-{y}-{r}" not in j:
                jobs.append((doc, f"read-sonnet-{x}-{y}-{r}", JUDGE_READ.format(x=a, y=b)))
        for lab, t in ((x, tx), (y, ty)):
            if lab == "before":
                continue
            for r in (0, 1):
                if f"content-sonnet-{lab}-{r}" not in j:
                    jobs.append((doc, f"content-sonnet-{lab}-{r}", JUDGE_CONTENT.format(a=before, b=t)))
    jobs = list({(d.name, k): (d, k, p) for d, k, p in jobs}.values())
    print(len(jobs), "jobs", flush=True)
    with ThreadPoolExecutor(parallel) as ex:
        for (doc, key, _), res in zip(jobs, ex.map(lambda jb: sonnet(jb[2]), jobs)):
            if res is None:
                print(f"FAIL {doc.name} {key}", flush=True)
                continue
            path = doc / "judge.json"
            j = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            j[key] = res
            path.write_text(json.dumps(j, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"ok {doc.name} {key}", flush=True)


def sign_p(a: int, b: int) -> float:
    """両側の符号検定。a 対 b(引き分けは除く)。"""
    from math import comb
    n = a + b
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(comb(n, i) for i in range(min(a, b) + 1)) / 2 ** n)


def paired(x: str, y: str) -> list[str]:
    """文書ごとに x と y を比べ、y のほうが少ない本数・多い本数と符号検定の p を出す(全47本)。"""
    def content(m, j, v):
        if v == "before":
            return 0.0
        xs = [sum(len(j[f"content-sonnet-{v}-{r}"].get(k) or []) for k in ("changed", "lost", "added"))
              for r in (0, 1) if f"content-sonnet-{v}-{r}" in j]
        return sum(xs) / len(xs) if xs else None

    def intro(m, j, v):
        return 0 if v == "before" else len(m[v]["introduced"])

    def density(m, j, v):
        return m[v]["density"]

    out = ["", "| 指標(文書ごとの対比較) | " + f"{y}が少ない | {y}が多い | 同じ | p(符号検定) |", "|---|---|---|---|---|"]
    for name, f in (("中身の変化", content), ("持ち込み", intro), ("密度", density)):
        lo = hi = eq = 0
        for doc in docs():
            if not (doc / "metrics.json").exists():
                continue
            m = json.loads((doc / "metrics.json").read_text(encoding="utf-8"))
            j = json.loads((doc / "judge.json").read_text(encoding="utf-8")) if (doc / "judge.json").exists() else {}
            if not ((x in m or x == "before") and y in m):
                continue
            a, b = f(m, j, x), f(m, j, y)
            if a is None or b is None:
                continue
            lo, hi, eq = lo + (b < a), hi + (b > a), eq + (b == a)
        out.append(f"| {name} | {lo} | {hi} | {eq} | {sign_p(lo, hi):.3f} |")
    return out


def summary(x: str, y: str) -> list[str]:
    def avg(xs):
        xs = [v for v in xs if v is not None]
        return sum(xs) / len(xs) if xs else float("nan")

    out = [f"| 束 | 本数 | 密度 {x} | {y} | 持ち込み(語/本) {x} | {y} | 書き換え {x} | {y} | 中身の変化(件/本) {x} | {y} | "
           f"読みやすさ {x}が2回とも上 | {y}が2回とも上 | 割れた・同じ |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    tot = Counter()
    for b, lab in BUNDLE.items():
        rows = []
        for doc in OUT.glob(f"{b}-*"):
            if not (doc / "metrics.json").exists():
                continue
            m = json.loads((doc / "metrics.json").read_text(encoding="utf-8"))
            j = json.loads((doc / "judge.json").read_text(encoding="utf-8")) if (doc / "judge.json").exists() else {}
            if (x in m or x == "before") and y in m:
                rows.append((m, j))
        if not rows:
            continue

        def met(v, k):
            if v == "before":
                return avg([m["before"].get(k) for m, _ in rows]) if k == "density" else 0.0
            return avg([m[v].get(k) for m, _ in rows])

        def intro(v):
            return 0.0 if v == "before" else avg([len(m[v]["introduced"]) for m, _ in rows])

        def content(v):
            if v == "before":
                return 0.0
            return avg([avg([sum(len(j[f"content-sonnet-{v}-{r}"].get(k) or []) for k in ("changed", "lost", "added"))
                             for r in (0, 1) if f"content-sonnet-{v}-{r}" in j]) for _, j in rows])

        res = []
        for _, j in rows:
            k0, k1 = f"read-sonnet-{x}-{y}-0", f"read-sonnet-{x}-{y}-1"
            if k0 in j and k1 in j:
                w0 = {"X": x, "Y": y}.get(j[k0].get("better"), "tie")
                w1 = {"X": y, "Y": x}.get(j[k1].get("better"), "tie")
                res.append(w0 if w0 == w1 else "tie")
        nx, ny = res.count(x), res.count(y)
        tot.update({x: nx, y: ny, "n": len(res)})
        out.append(f"| {lab} | {len(rows)} | {met(x, 'density'):.2f} | {met(y, 'density'):.2f} | {intro(x):.1f} | {intro(y):.1f} | "
                   f"{met(x, 'edit'):.0%} | {met(y, 'edit'):.0%} | {content(x):.1f} | {content(y):.1f} | {nx} | {ny} | {len(res) - nx - ny} |")
    out.append(f"\n読みやすさの合計: {x} {tot[x]}・{y} {tot[y]}・割れた・同じ {tot['n'] - tot[x] - tot[y]}(計 {tot['n']} 本、p = {sign_p(tot[x], tot[y]):.3f})")
    return out + paired(x, y)


def report(x: str, y: str, note: str) -> None:
    path = HERE / "steps.md"
    head = "# スキルの段階ごとの比較\n\n旧版に変更を1つずつ足し、直前の段階と比べる。判定は claude-sonnet-5-5。\n"
    text = path.read_text(encoding="utf-8") if path.exists() else head
    sec = "\n".join([f"\n## {y}(比較の相手: {x})", "", note, "", *summary(x, y), ""])
    path.write_text(text + sec, encoding="utf-8")
    print(sec)


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("apply")
    p.add_argument("label")
    p.add_argument("--ref", required=True)
    p.add_argument("--parallel", type=int, default=3)
    p = sub.add_parser("measure")
    p.add_argument("label")
    p = sub.add_parser("judge")
    p.add_argument("x")
    p.add_argument("y")
    p.add_argument("--parallel", type=int, default=4)
    p = sub.add_parser("report")
    p.add_argument("x")
    p.add_argument("y")
    p.add_argument("note")
    a = ap.parse_args()
    if a.cmd == "apply":
        apply(a.label, a.ref, a.parallel)
    elif a.cmd == "measure":
        measure(a.label)
    elif a.cmd == "judge":
        judge(a.x, a.y, a.parallel)
    else:
        report(a.x, a.y, a.note)


if __name__ == "__main__":
    main()
