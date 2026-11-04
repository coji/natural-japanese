# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""読む人の問い(outcome の run)と、スキルの「先に答える問い」(rewrite / review の run の確認事項)の重なりを数える(CT12)。

    uv run --with pyyaml dev/ct-eval/overlap.py --label ov1 \
        ringi=o6-exec/ringi_元:r43c/ringi-planted-rewrite \
        teian=o6-customer/teian_元:r43c/teian-planted-rewrite ...

name=<outcome の run>/<outcome の name(: は _)>:<eval の run>/<fixture-mode> の形。
outcome の各回の questions を reader.md に、eval の各回の source.確認事項.md を skill.md に並べ、判定者(Sonnet)に突き合わせさせる。
結果は runs/<label>/<name>/judge.json と runs/<label>/summary.md。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import eval as ev  # noqa: E402

HERE = Path(__file__).parent
PROMPT = (HERE / "prompts" / "judge-overlap.txt").read_text()


def gather(name: str, spec: str, label: str, judge_model: str) -> dict:
    ospec, espec = spec.split(":", 1)
    orun, oname = ospec.split("/", 1)
    erun, ename = espec.split("/", 1)
    w = ev.RUNS / label / name
    w.mkdir(parents=True, exist_ok=True)
    reader, n = [], 0
    for d in sorted((ev.RUNS / orun).glob(f"{oname}-*")):
        jp = d / "exec.json"
        if not jp.exists():
            continue
        for q in json.loads(jp.read_text()).get("questions", []):
            n += 1
            reader.append(f"{n}. {q.get('q')}(回 {d.name.rsplit('-', 1)[-1]}。{q.get('kind', '')})")
        src = d / "doc.md"
    (w / "reader.md").write_text("\n".join(reader) + "\n")
    skill = []
    for d in sorted((ev.RUNS / erun).glob(f"{ename}-*")):
        k = d / "source.確認事項.md"
        if k.exists():
            skill.append(f"# 実行 {d.name.rsplit('-', 1)[-1]}\n\n" + k.read_text())
    (w / "skill.md").write_text("\n\n".join(skill) + "\n")
    (w / "source.md").write_text(src.read_text())
    ev.claude(PROMPT.replace("{DIR}", str(w)), w, ["Read", "Write"], judge_model, "high", None, w / "log-judge.txt", timeout=900)
    jp = w / "judge.json"
    items = json.loads(jp.read_text()).get("items", []) if jp.exists() else []
    return {"name": name, "n_reader": n, "n_skill_runs": len(skill), "items": items}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pairs", nargs="+")
    ap.add_argument("--label", required=True)
    ap.add_argument("--judge-model", default="claude-sonnet-5-5")
    a = ap.parse_args()
    results = []
    for p in a.pairs:
        name, spec = p.split("=", 1)
        results.append(gather(name, spec, a.label, a.judge_model))
    lines = [f"# overlap: {a.label}", "", "| 素材 | 読む人の問い | 先に答える問いが覆う | そのほかにある | なし |", "|---|---|---|---|---|"]
    tf = tn = 0
    for r in results:
        c = {"first": 0, "other": 0, "none": 0}
        for it in r["items"]:
            c[it.get("match", "none")] = c.get(it.get("match", "none"), 0) + 1
        tf += c["first"]; tn += len(r["items"])
        lines.append(f"| {r['name']} | {len(r['items'])} | {c['first']} | {c['other']} | {c['none']} |")
    lines.append(f"\n合計: 先に答える問いが覆う {tf}/{tn} = {tf / tn:.0%}" if tn else "\n合計: 0")
    for r in results:
        lines.append(f"\n## {r['name']}")
        for it in r["items"]:
            lines.append(f"- [{it.get('match')}] {it.get('q')} ← {it.get('evidence', '')}")
    out = ev.RUNS / a.label
    (out / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
