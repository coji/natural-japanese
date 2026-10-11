# /// script
# requires-python = ">=3.11"
# dependencies = ["torch", "transformers>=4.44", "fugashi", "unidic-lite", "huggingface_hub"]
# ///
"""corpus/bench/versions.py — スキルの旧版と新版を同じ文書に当て、作者が文章を読まずに数値で比べる(ロードマップ S50)。

文書の束:
    A  作者の文書16本(corpus/private/skill-apply/*/before.md。顧客向け文書と Zenn 記事)
    B  学習外の生成記事21本(3社×7本: claude-opus-5-5・gpt-6.1-sol・gemini-3.8-flash。corpus/private/mlm/tests.json)
    C  生成AI以前の人間の文書10本(Qiita 2022年5本・LLM-jp 由来の仕事の文章5本。同上。直さないのが正解に近い)
スキルの版: old = main の worktree、new = skill-v2 の worktree(どちらも claude -p --plugin-dir で読み込む)
書き手: claude-opus-5-5(effort low)。個人設定は外す(--setting-sources project)

測るもの:
    m1 生成AI時代の語の密度   style_check.py の差 > 3 の語が、本文1,000字あたり何語か(before・old・new)
    m2 持ち込み               直した文書にあって、原文にない見出し語で、差 > 3 のもの
    m3 中身の保持             gpt-6-luna(effort low)が原文と直した文書を比べ、変わった・消えた・足された点を数える。2回回して一致を見る
    m4 読みやすさ             gpt-6-luna が old と new の直した文書を対で比べる(左右を入れ替えて2回)
    m5 変えすぎ               字数の比と、文字単位の書き換えの割合
m1 は、新版が直すのに使ったのと同じモデルで測るので、新版に甘く出る。

出力: corpus/private/versions/<束>-<id>/{before,old,new}.md・log-*.txt・metrics.json、corpus/bench/versions.md(数値のみ)

使い方:
    uv run corpus/bench/versions.py prepare
    uv run corpus/bench/versions.py apply [--versions old new] [--parallel 3]
    uv run corpus/bench/versions.py measure
    uv run corpus/bench/versions.py judge
    uv run corpus/bench/versions.py report
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

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = ROOT / "corpus/private/versions"
ISO = Path("/tmp/corpus-gen-isolation")
WT = {"old": ISO / "wt-old", "new": ISO / "wt-new"}
sys.path.insert(0, str(ROOT / "corpus"))
import generate as g  # noqa: E402

PROMPT = {
    "old": ("natural-japanese スキルのクイックモードで、input.md の文章を推敲してください。"
            "読み手と目的は文書の内容から判断してください。推敲した全文を output.md に書き出してください。"
            "input.md は変更しないでください。確認の質問はせず、最後まで自分の判断で進めてください。"),
    "new": ("natural-japanese スキルで、input.md の文章を推敲してください。"
            "読み手と目的は文書の内容から判断してください。推敲した全文を output.md に書き出してください。"
            "input.md は変更しないでください。確認の質問はせず、最後まで自分の判断で進めてください。"),
}
BUNDLE = {"A": "作者の文書", "B": "生成記事(学習外)", "C": "AI 以前の人間の文書"}
T = 3.0

JUDGE_CONTENT = """文書A(元の文書)と文書B(推敲した文書)を比べ、伝えている内容の違いを挙げてください。
言い回し・語順・文の区切り・見出しの書き方の違いは数えません。内容の違いだけを数えます。

- changed: A の事実・数値・条件・確信の度合い(断定/推定/未定)が、B で別のものになった
- lost: A にある事実・条件・注意が、B で消えた
- added: A にない事実・数値・条件・人名・日付が、B に足された

次の JSON だけを出力してください:
{{"changed": ["短い説明", ...], "lost": [...], "added": [...]}}

### 文書A
{a}

### 文書B
{b}
"""
JUDGE_READ = """同じ元の文書を2通りに推敲した文書X・Yがあります。想定する読み手にとって、どちらが読みやすいかを判定してください。
見るのは、一文一義、語順、段落のまとまり、構成(結論が先にあるか、見出しで内容がわかるか)です。
内容の正確さや、AI らしさは判定しません。

次の JSON だけを出力してください: {{"better": "X" または "Y" または "同じ", "reason": "短く"}}

### 文書X
{x}

### 文書Y
{y}
"""


def prepare() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(0)
    docs = {}
    for d in sorted((ROOT / "corpus/private/skill-apply").iterdir()):
        if (d / "before.md").exists():
            docs[f"A-{d.name}"] = (d / "before.md").read_text(encoding="utf-8")
    tests = json.loads((ROOT / "corpus/private/mlm/tests.json").read_text(encoding="utf-8"))
    by_model: dict[str, list[str]] = {}
    for t in tests["generated_holdout"]:
        m = re.search(r'^model: "?([^"\n]+)', t, re.M)
        body = t.split("\n---\n", 1)[1].strip() if t.startswith("---\n") else t
        by_model.setdefault(m.group(1) if m else "", []).append(body)
    for model in ("claude-opus-5-5", "gpt-6.1-sol", "gemini-3.8-flash"):
        xs = by_model[model][:]
        rng.shuffle(xs)
        for i, body in enumerate(xs[:7]):
            docs[f"B-{model}-{i}"] = body
    for name in ("qiita2022", "llmjp"):
        xs = [x for x in tests[name] if 1500 <= len(x) <= 5000]
        rng.shuffle(xs)
        for i, body in enumerate(xs[:5]):
            docs[f"C-{name}-{i}"] = body
    for k, text in docs.items():
        (OUT / k).mkdir(exist_ok=True)
        (OUT / k / "before.md").write_text(text, encoding="utf-8")
    print(Counter(k[0] for k in docs))


def apply_one(doc: Path, ver: str) -> str:
    if (doc / f"{ver}.md").exists():
        return f"skip {doc.name} {ver}"
    work = ISO / "versions" / f"{doc.name}-{ver}"
    work.mkdir(parents=True, exist_ok=True)
    for f in work.iterdir():
        if f.is_file():
            f.unlink()
    (work / "input.md").write_text((doc / "before.md").read_text(encoding="utf-8"), encoding="utf-8")
    cmd = ["claude", "-p", PROMPT[ver], "--model", "claude-opus-5-5", "--effort", "low",
           "--setting-sources", "project", "--plugin-dir", str(WT[ver]), "--add-dir", "/tmp",
           "--allowedTools", "Skill", "Read", "Write", "Edit", "Glob", "Grep",
           "Bash(uv run:*)", "Bash(python3:*)", "Bash(cat:*)", "Bash(wc:*)", "Bash(cp:*)", "Bash(mkdir:*)"]
    try:
        r = subprocess.run(cmd, cwd=work, capture_output=True, text=True, timeout=2400, stdin=subprocess.DEVNULL)
        log = r.stdout + "\n--- stderr ---\n" + r.stderr
    except subprocess.TimeoutExpired:
        log = "TIMEOUT"
    (doc / f"log-{ver}.txt").write_text(log, encoding="utf-8")
    out = work / "output.md"
    if out.exists():
        (doc / f"{ver}.md").write_text(out.read_text(encoding="utf-8"), encoding="utf-8")
        return f"ok {doc.name} {ver}"
    return f"FAIL {doc.name} {ver}"


def apply(versions: list[str], parallel: int) -> None:
    jobs = [(d, v) for d in sorted(OUT.iterdir()) if (d / "before.md").exists() for v in versions]
    random.Random(1).shuffle(jobs)
    with ThreadPoolExecutor(parallel) as ex:
        for res in ex.map(lambda j: apply_one(*j), jobs):
            print(res, flush=True)


def measure() -> None:
    sys.path.insert(0, str(WT["new"] / "skills/natural-japanese/scripts"))
    from style_check import Pair, ok_word, sentences  # noqa: E402
    pair = Pair()

    def flagged(text):
        n, chars, lem = 0, 0, Counter()
        for _, s in sentences(text):
            chars += len(s)
            for w in pair.score(s):
                if ok_word(w) and w["d"] > T:
                    n += 1
                    lem[w["lemma"]] += 1
        return n, chars, lem

    for doc in sorted(OUT.iterdir()):
        if not (doc / "before.md").exists():
            continue
        path = doc / "metrics.json"
        m = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        before = (doc / "before.md").read_text(encoding="utf-8")
        orig_lemmas = pair.lemmas(before)
        for ver in ("before", "old", "new"):
            f = doc / f"{ver}.md"
            if ver in m or not f.exists():
                continue
            text = f.read_text(encoding="utf-8")
            n, chars, lem = flagged(text)
            row = {"flags": n, "chars": chars, "density": round(n / max(chars, 1) * 1000, 2)}
            if ver != "before":
                row["introduced"] = sorted(k for k in lem if k not in orig_lemmas)
                row["len_ratio"] = round(len(text) / max(len(before), 1), 3)
                row["edit"] = round(1 - difflib.SequenceMatcher(None, before, text, autojunk=False).ratio(), 3)
            m[ver] = row
        path.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
        print(doc.name, {k: v.get("density") for k, v in m.items() if isinstance(v, dict)}, flush=True)


def luna(prompt: str, slot: int) -> dict | None:
    for _ in range(3):
        try:
            home = g.ISOLATION_DIR / f"codex-home-ver-{slot % 3}"
            home.mkdir(parents=True, exist_ok=True)
            (home / "auth.json").write_bytes((g.CODEX_HOME / "auth.json").read_bytes())
            res = g.run_codex(prompt, "gpt-6-luna", "low", codex_home=home)
            mm = re.search(r"\{.*\}", res, re.S)
            if mm:
                return json.loads(mm.group(0))
        except Exception as e:  # noqa: BLE001
            print(f"  ERR: {e}", file=sys.stderr)
    return None


def judge() -> None:
    g.prepare_isolation()
    jobs = []
    for doc in sorted(OUT.iterdir()):
        if not (doc / "before.md").exists():
            continue
        path = doc / "judge.json"
        j = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        before = (doc / "before.md").read_text(encoding="utf-8")
        for ver in ("old", "new"):
            if not (doc / f"{ver}.md").exists():
                continue
            for run in (0, 1):
                key = f"content-{ver}-{run}"
                if key not in j:
                    jobs.append((doc, key, JUDGE_CONTENT.format(a=before, b=(doc / f"{ver}.md").read_text(encoding="utf-8"))))
        if (doc / "old.md").exists() and (doc / "new.md").exists():
            o, n = (doc / "old.md").read_text(encoding="utf-8"), (doc / "new.md").read_text(encoding="utf-8")
            if "read-0" not in j:
                jobs.append((doc, "read-0", JUDGE_READ.format(x=o, y=n)))  # X = old
            if "read-1" not in j:
                jobs.append((doc, "read-1", JUDGE_READ.format(x=n, y=o)))  # X = new

    def work(job):
        i, (doc, key, prompt) = job
        return doc, key, luna(prompt, i)

    with ThreadPoolExecutor(3) as ex:
        for doc, key, res in ex.map(work, enumerate(jobs)):
            if res is None:
                print(f"FAIL {doc.name} {key}", flush=True)
                continue
            path = doc / "judge.json"
            j = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            j[key] = res
            path.write_text(json.dumps(j, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"ok {doc.name} {key}", flush=True)


def report() -> None:
    rows = []
    for doc in sorted(OUT.iterdir()):
        if (doc / "metrics.json").exists():
            rows.append((doc.name[0], json.loads((doc / "metrics.json").read_text(encoding="utf-8")),
                         json.loads((doc / "judge.json").read_text(encoding="utf-8")) if (doc / "judge.json").exists() else {}))

    def avg(xs):
        xs = [x for x in xs if x is not None]
        return sum(xs) / len(xs) if xs else float("nan")

    out = ["# スキルの旧版と新版の比較", "",
           "同じ文書を claude-opus-5-5(effort low)が旧版(main)と新版(skill-v2)のスキルで推敲した。文書は作者が読んでいない。新版は構成と文の見直しの手順を足した2つめの草稿。最初の草稿の結果は versions-f51.md にある(そこでの new は、ここでの new1)。", "",
           "## m1 生成AI時代の語の密度(差 > 3、本文1,000字あたり)と m2 持ち込み・m5 変えすぎ", "",
           "| 束 | 本数 | 元 | 旧版 | 新版 | 持ち込み 旧版(語/本) | 持ち込み 新版 | 持ち込み0の割合 旧版 | 新版 | 字数の比 旧版 | 新版 | 書き換え 旧版 | 新版 |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for b, lab in BUNDLE.items():
        xs = [m for bb, m, _ in rows if bb == b and "old" in m and "new" in m]
        if not xs:
            continue
        cell = lambda v, k: avg([m[v].get(k) for m in xs])  # noqa: E731
        intro = lambda v: avg([len(m[v]["introduced"]) for m in xs])  # noqa: E731
        zero = lambda v: sum(not m[v]["introduced"] for m in xs) / len(xs)  # noqa: E731
        out.append(f"| {lab} | {len(xs)} | {cell('before', 'density'):.2f} | {cell('old', 'density'):.2f} | {cell('new', 'density'):.2f} | "
                   f"{intro('old'):.1f} | {intro('new'):.1f} | {zero('old'):.0%} | {zero('new'):.0%} | "
                   f"{cell('old', 'len_ratio'):.2f} | {cell('new', 'len_ratio'):.2f} | {cell('old', 'edit'):.0%} | {cell('new', 'edit'):.0%} |")
    out += ["", "## m3 中身の保持(gpt-6-luna、1本あたりの件数。2回の平均)", "",
            "| 束 | 変わった 旧版 | 新版 | 消えた 旧版 | 新版 | 足された 旧版 | 新版 | 2回の件数の一致(差が1以内) |", "|---|---|---|---|---|---|---|---|"]
    for b, lab in BUNDLE.items():
        js = [j for bb, _, j in rows if bb == b and j]
        if not js:
            continue
        def cnt(ver, kind):
            return avg([avg([len(j.get(f"content-{ver}-{r}", {}).get(kind, []) or []) for r in (0, 1) if f"content-{ver}-{r}" in j]) for j in js])
        agree = [abs(sum(len(j[f"content-{v}-0"].get(k, []) or []) for k in ("changed", "lost", "added"))
                     - sum(len(j[f"content-{v}-1"].get(k, []) or []) for k in ("changed", "lost", "added"))) <= 1
                 for j in js for v in ("old", "new") if f"content-{v}-0" in j and f"content-{v}-1" in j]
        out.append(f"| {BUNDLE[b]} | {cnt('old', 'changed'):.1f} | {cnt('new', 'changed'):.1f} | {cnt('old', 'lost'):.1f} | {cnt('new', 'lost'):.1f} | "
                   f"{cnt('old', 'added'):.1f} | {cnt('new', 'added'):.1f} | {sum(agree) / max(len(agree), 1):.0%} |")
    out += ["", "## m4 読みやすさ(gpt-6-luna、旧版と新版の対比較。左右を入れ替えて2回)", "",
            "| 束 | 本数 | 新版が2回とも上 | 旧版が2回とも上 | 割れた・同じ |", "|---|---|---|---|---|"]
    for b, lab in BUNDLE.items():
        js = [j for bb, _, j in rows if bb == b and "read-0" in j and "read-1" in j]
        if not js:
            continue
        def winner(j, r):
            v = j[f"read-{r}"].get("better")
            return {"X": "old" if r == 0 else "new", "Y": "new" if r == 0 else "old"}.get(v, "tie")
        res = [(winner(j, 0), winner(j, 1)) for j in js]
        nw = sum(a == b2 == "new" for a, b2 in res)
        ow = sum(a == b2 == "old" for a, b2 in res)
        out.append(f"| {lab} | {len(js)} | {nw} | {ow} | {len(js) - nw - ow} |")
    (HERE / "versions.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["prepare", "apply", "measure", "judge", "report"])
    ap.add_argument("--versions", nargs="+", default=["old", "new"])
    ap.add_argument("--parallel", type=int, default=3)
    a = ap.parse_args()
    {"prepare": prepare, "apply": lambda: apply(a.versions, a.parallel), "measure": measure,
     "judge": judge, "report": report}[a.cmd]()


if __name__ == "__main__":
    main()
