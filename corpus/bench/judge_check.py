# /// script
# requires-python = ">=3.11"
# dependencies = ["torch", "transformers>=4.44", "fugashi", "unidic-lite", "huggingface_hub"]
# ///
"""judge_check.py — 読みやすさの判定(sonnet)が、こちらの見たいものを見分けられるかを確かめる。

旧版の推敲結果(s0a.md)をもとに、2種類の「悪くした版」を作り、元と比べさせる。
    inj   5か所だけを生成AI時代の言い回し(効く、土台、落とし穴など)に置き換えた版(claude-opus-5-5 に置き換えさせ、
          style_check で語が増えたことと、ほかが変わっていないことを確かめる)
    long  段落の中の隣り合う文を、5か所だけ読点でつないで長くした版(機械的に作る。判定が読みにくさに反応するかの対照)
判定は2つの依頼文で行う。
    read  これまでの依頼文(AI らしさは判定しない)
    nat   AI らしさや不自然な言い回しも含めて、自然で読みやすい日本語かを見る依頼文

    uv run corpus/bench/judge_check.py make
    uv run corpus/bench/judge_check.py judge
    uv run corpus/bench/judge_check.py report
"""
from __future__ import annotations

import argparse
import difflib
import json
import random
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from steps import ISO, NEUTRAL, JUDGE_SYSTEM, docs, sign_p, sonnet  # noqa: E402
from versions import JUDGE_READ  # noqa: E402

INJECT = """次の文章のうち、ちょうど5か所だけを、意味を変えずに、生成AIがよく使う言い回しに置き換えてください。
使う言い回しの例: 効く、土台、落とし穴、境界、入口、拾う、刺さる、解像度、手触り、静かに(壊れる・効いてくる)、地に足のついた、肝、背骨、勘所、地味に効く。
置き換えるのは語句だけで、文の区切り・語順・ほかの語は一字も変えないでください。見出し・コード・表は変えないでください。
置き換えた全文だけを出力してください。説明は書かないでください。

{text}
"""
JUDGE_NAT = """同じ元の文書を2通りに推敲した文書X・Yがあります。日本語の書き手が書いた自然で読みやすい文章として、どちらがよいかを判定してください。
一文一義、語順、段落のまとまり、構成に加えて、言い回しの自然さも見てください。英語を直訳したような言い回しや、生成AIの文章によく出る言い回し(比喩的な「効く」「土台」「落とし穴」など)は、不自然なものとして扱います。
内容の正確さは判定しません。

次の JSON だけを出力してください: {{"better": "X" または "Y" または "同じ", "reason": "短く"}}

### 文書X
{x}

### 文書Y
{y}
"""
BASE = "s0a"


def opus(prompt: str) -> str | None:
    for _ in range(3):
        try:
            r = subprocess.run(["claude", "-p", prompt, "--model", "claude-opus-5-5", "--effort", "low",
                                "--setting-sources", "project", "--disallowed-tools", "*",
                                "--append-system-prompt", JUDGE_SYSTEM],
                               capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=900, check=True, cwd=NEUTRAL)
            return r.stdout.strip()
        except Exception as e:  # noqa: BLE001
            print(f"  ERR: {e}", file=sys.stderr)
    return None


def make_long(text: str, rng: random.Random) -> str:
    """段落(空行で区切られた地の文)の中の「。」を5か所だけ「、」にして、隣の文とつなぐ。"""
    lines = text.split("\n")
    cands = []
    fence = False
    for i, l in enumerate(lines):
        if l.lstrip().startswith("```"):
            fence = not fence
        if fence or re.match(r"\s*(#|\||>|[-*+] |\d+\. )", l) or not l.strip():
            continue
        for m in re.finditer(r"。(?=[^\s」』）)])", l):
            cands.append((i, m.start()))
    pick = sorted(rng.sample(cands, min(5, len(cands))), key=lambda x: (x[0], -x[1]))
    for i, pos in pick:
        lines[i] = lines[i][:pos] + "、" + lines[i][pos + 1:]
    return "\n".join(lines)


def make() -> None:
    NEUTRAL.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ISO / "wt-new/skills/natural-japanese/scripts"))
    from style_check import Pair  # noqa: E402
    pair = Pair()
    rng = random.Random(0)
    targets = [d for d in docs() if (d / f"{BASE}.md").exists()]
    for d in targets:
        if not (d / "jc-long.md").exists():
            (d / "jc-long.md").write_text(make_long((d / f"{BASE}.md").read_text(encoding="utf-8"), rng), encoding="utf-8")
    todo = [d for d in targets if not (d / "jc-inj.md").exists()]
    with ThreadPoolExecutor(4) as ex:
        for d, out in zip(todo, ex.map(lambda d: opus(INJECT.format(text=(d / f"{BASE}.md").read_text(encoding="utf-8"))), todo)):
            if out:
                (d / "jc-inj.md").write_text(out + "\n", encoding="utf-8")
    stats = {}
    for d in targets:
        if not (d / "jc-inj.md").exists():
            continue
        a, b = (d / f"{BASE}.md").read_text(encoding="utf-8"), (d / "jc-inj.md").read_text(encoding="utf-8")
        fa, _ = pair.flagged(a, 3.0)
        fb, _ = pair.flagged(b, 3.0)
        stats[d.name] = {"flags_base": sum(len(r["words"]) for r in fa), "flags_inj": sum(len(r["words"]) for r in fb),
                         "edit": round(1 - difflib.SequenceMatcher(None, a, b, autojunk=False).ratio(), 4)}
        print(d.name, stats[d.name], flush=True)
    (HERE.parent / "private/judge-check.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")


def judge() -> None:
    stats = json.loads((HERE.parent / "private/judge-check.json").read_text(encoding="utf-8"))
    ok = {k for k, v in stats.items() if v["flags_inj"] > v["flags_base"] and v["edit"] < 0.03}
    jobs = []
    for d in docs():
        path = d / "judge.json"
        j = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        base = (d / f"{BASE}.md").read_text(encoding="utf-8") if (d / f"{BASE}.md").exists() else None
        for kind in ("inj", "long"):
            if base is None or not (d / f"jc-{kind}.md").exists() or (kind == "inj" and d.name not in ok):
                continue
            bad = (d / f"jc-{kind}.md").read_text(encoding="utf-8")
            for pname, tmpl in (("read", JUDGE_READ), ("nat", JUDGE_NAT)):
                if kind == "long" and pname == "nat":
                    continue
                for r, (x, y) in enumerate(((base, bad), (bad, base))):  # r=0 で X=元
                    key = f"jc-{pname}-{kind}-{r}"
                    if key not in j:
                        jobs.append((d, key, tmpl.format(x=x, y=y)))
    print(len(jobs), "jobs", flush=True)
    with ThreadPoolExecutor(4) as ex:
        for (d, key, _), res in zip(jobs, ex.map(lambda jb: sonnet(jb[2]), jobs)):
            if res is None:
                print(f"FAIL {d.name} {key}", flush=True)
                continue
            path = d / "judge.json"
            j = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            j[key] = res
            path.write_text(json.dumps(j, ensure_ascii=False, indent=1), encoding="utf-8")


def report() -> None:
    stats = json.loads((HERE.parent / "private/judge-check.json").read_text(encoding="utf-8"))
    vals = list(stats.values())
    out = ["# 読みやすさの判定は、悪くした版を見分けられるか", "",
           f"旧版の推敲結果(s0a)をもとに悪くした版を作り、元と比べさせた(claude-sonnet-5-5、左右を入れ替えて2回)。",
           f"生成AI時代の語を入れた版(inj)は {len(vals)} 本作り、差 > 3 の語が元より増え、書き換えが3%未満のものだけを使った"
           f"(1本あたりの語の数: 元 {sum(v['flags_base'] for v in vals) / len(vals):.1f} → {sum(v['flags_inj'] for v in vals) / len(vals):.1f})。", "",
           "| 悪くした版 | 依頼文 | 本数 | 元が2回とも上 | 悪くした版が2回とも上 | 割れた・同じ | p |", "|---|---|---|---|---|---|---|"]
    for kind, pname, label in (("long", "read", "文を5か所つないで長くした"), ("inj", "read", "生成AI時代の語を5か所入れた"),
                               ("inj", "nat", "生成AI時代の語を5か所入れた")):
        a = b = n = 0
        for d in docs():
            if not (d / "judge.json").exists():
                continue
            j = json.loads((d / "judge.json").read_text(encoding="utf-8"))
            k0, k1 = f"jc-{pname}-{kind}-0", f"jc-{pname}-{kind}-1"
            if k0 in j and k1 in j:
                n += 1
                w0 = {"X": "base", "Y": "bad"}.get(j[k0].get("better"), "tie")
                w1 = {"X": "bad", "Y": "base"}.get(j[k1].get("better"), "tie")
                a += w0 == w1 == "base"
                b += w0 == w1 == "bad"
        pl = {"read": "これまでの依頼文", "nat": "言い回しの自然さも見る依頼文"}[pname]
        out.append(f"| {label} | {pl} | {n} | {a} | {b} | {n - a - b} | {sign_p(a, b):.3f} |")
    (HERE / "judge-check.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["make", "judge", "report"])
    a = ap.parse_args()
    {"make": make, "judge": judge, "report": report}[a.cmd]()


if __name__ == "__main__":
    main()
