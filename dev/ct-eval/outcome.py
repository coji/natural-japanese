# /// script
# requires-python = ">=3.11"
# ///
"""成果物の評価(outcome)。経営者役の AI に文書を1本だけ渡し、返事(OK / 条件つきOK / 聞きたい / 却下)と聞きたいことを返させる。

    uv run dev/ct-eval/outcome.py --label o1 --repeat 3 \\
        ringi-planted=fixtures/ringi-planted.md \\
        ringi-review=dev/ct-eval/runs/r27j/ringi-planted-review-1/source-after.md ...

name=path を並べる。各文書を repeat 回、別々に(並べずに)渡す。結果は runs/<label>/<name>-<i>/exec.json と runs/<label>/summary.md。

経営者役は同じ文面・同じ文書でも日によって返事が揺れる(o1 と o3c で元の稟議書が 1.0 → 3.0)ので、
別の回どうしは比べない。比べたいもの(元・旧・新)は必ず同じ回に入れ、name を「組:版」の形にする。

    uv run --with pyyaml dev/ct-eval/outcome.py --label o4 --repeat 3 \
        ringi:元=dev/ct-eval/fixtures/ringi-planted.md \
        ringi:旧=dev/ct-eval/runs/r32/ringi-planted-rewrite-1/source-after.md \
        ringi:新=dev/ct-eval/runs/r33e/ringi-planted-rewrite-1/source-after.md

summary.md の先頭に、組ごとに版を横に並べた表が出る(返事 / 聞きたい(うち文書の中で答えが出る))。
"""
from __future__ import annotations

import argparse, json, re, shutil, sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import eval as ev  # noqa: E402

HERE = Path(__file__).parent
PROMPT = (HERE / "prompts" / "exec.txt").read_text()


def one(label: str, name: str, src: Path, i: int, model: str) -> dict:
    w = ev.RUNS / label / f"{name.replace(':', '_')}-{i}"
    w.mkdir(parents=True, exist_ok=True)
    doc = w / "doc.md"
    text = src.read_text()
    # 付録と確認事項は経営者も読めるので残す。改訂の印などはない前提
    doc.write_text(text)
    ev.claude(PROMPT.replace("{FILE}", str(doc)), w, ["Read", "Write"], model, "medium", None, w / "log.txt", timeout=900)
    out = {"name": name, "i": i, "chars": ev._nonspace(text)}
    jp = w / "exec.json"
    if jp.exists():
        try:
            out["exec"] = json.loads(jp.read_text())
        except json.JSONDecodeError:
            out["error"] = "parse"
    return out


def _stats(rs: list[dict]) -> dict:
    verdicts = Counter(r["exec"].get("verdict", "?") for r in rs)
    top = verdicts.most_common(1)[0]
    qs = [q for r in rs for q in r["exec"].get("questions", [])]
    return {"verdict": top[0] + ("" if top[1] == len(rs) else f"({dict(verdicts)})"),
            "n_q": len(qs) / len(rs),
            "in_doc": sum(1 for q in qs if "文書" in q.get("kind", "")) / len(rs),
            "ext": sum(1 for q in qs if "起案者" in q.get("kind", "")) / len(rs),
            "read": sum(r["exec"].get("chars_read", 0) or 0 for r in rs) / len(rs)}


def summarize(results: list[dict], repeat: int) -> str:
    names = list(dict.fromkeys(r["name"] for r in results))
    lines = ["# outcome: 経営者役の返事", ""]
    # 「組:版」の名前があれば、組ごとに版を横に並べる(同じ回の中でだけ比べる)
    groups: dict[str, list[str]] = {}
    for n in names:
        if ":" in n:
            g, v = n.split(":", 1)
            groups.setdefault(g, []).append(v)
    if groups:
        variants = list(dict.fromkeys(v for vs in groups.values() for v in vs))
        lines += ["## 同じ回での比較(返事 / 聞きたい(うち文書の中で答えが出る) / 読んだ字数)", "",
                  "| 組 | " + " | ".join(variants) + " |", "|---|" + "---|" * len(variants)]
        for g, vs in groups.items():
            cells = []
            for v in variants:
                rs = [r for r in results if r["name"] == f"{g}:{v}" and "exec" in r]
                if not rs:
                    cells.append("-"); continue
                st = _stats(rs)
                cells.append(f"{st['verdict']} / {st['n_q']:.1f}({st['in_doc']:.1f}) / {st['read']:.0f}")
            if "元" not in vs:
                cells.append("(元がない。元と同じ回で比べること)")
            lines.append(f"| {g} | " + " | ".join(cells) + " |")
        lines.append("")
    lines += ["| 文書 | 字数 | 返事(多数決) | 聞きたい(平均) | うち文書の中で答えが出る | 起案者にしか答えられない | 読んだ字数(平均) | 一言(1回目) |", "|---|---|---|---|---|---|---|---|"]
    for n in names:
        rs = [r for r in results if r["name"] == n and "exec" in r]
        if not rs:
            lines.append(f"| {n} | - | 失敗 | | | | | |"); continue
        st = _stats(rs)
        reply = rs[0]["exec"].get("reply", "").replace("|", "/")[:60]
        lines.append(f"| {n} | {rs[0]['chars']} | {st['verdict']} | {st['n_q']:.1f} | {st['in_doc']:.1f} | {st['ext']:.1f} | {st['read']:.0f} | {reply} |")
    lines += ["", "聞きたいことの一覧:"]
    for n in names:
        for r in [r for r in results if r["name"] == n and "exec" in r]:
            for q in r["exec"].get("questions", []):
                lines.append(f"- {n} #{r['i']} [{q.get('kind','?')}] {q.get('q','')}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("docs", nargs="+", help="name=path")
    ap.add_argument("--label", required=True)
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--model", default="claude-opus-5-5")
    a = ap.parse_args()
    pairs = []
    for d in a.docs:
        n, p = d.split("=", 1)
        p = Path(p).resolve()  # 相対パスは cwd から(リポジトリの根から uv run する前提)
        pairs.append((n, p))
    jobs = [(n, p, i) for n, p in pairs for i in range(1, a.repeat + 1)]
    results = []
    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        for r in ex.map(lambda j: one(a.label, j[0], j[1], j[2], a.model), jobs):
            print(f"done {r['name']}-{r['i']} {r.get('exec', {}).get('verdict')}", file=sys.stderr)
            results.append(r)
    out = ev.RUNS / a.label
    (out / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
    s = summarize(results, a.repeat)
    (out / "summary.md").write_text(s)
    print(s)


if __name__ == "__main__":
    main()
