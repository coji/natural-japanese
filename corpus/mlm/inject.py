"""inject.py — 生成AI以前の人間の文書に、生成AIらしさを入れた版を作る(物差しの検査用)。

2種類を作る。どちらも claude-opus-5-5(effort low)に書き換えさせる。
    word  5か所だけ、語句を生成AI時代の比喩的な言い回し(効く・土台・落とし穴など)に置き換える。文の運びは変えない
    rhet  語彙は変えずに、文の運びだけを生成AIらしくする(短い言い切りの決め文、「〜ではなく〜」、体言止め、
          「〜。それが〜だ。」、問いかけの見出しなど)を5か所。比喩的な言い回しの一覧の語は使わない
入力は doc_meter.py の dev の人間の文書(qiita2022・llmjp)の先頭 2,500 字ほど(段落の切れ目で切る)。

    uv run corpus/mlm/inject.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "corpus/mlm"))
from doc_meter import load  # noqa: E402

OUT = ROOT / "corpus/private/mlm/inject"
NEUTRAL = Path("/tmp/corpus-gen-isolation/cwd")
SYSTEM = "これは1往復のみの非対話バッチ呼び出しです。確認や質問をせず、指示された出力だけを返してください。"
METAPHOR = "効く、土台、落とし穴、境界、入口、拾う、刺さる、解像度、手触り、静かに、地に足のついた、肝、背骨、勘所"
PROMPT = {
    "word": f"""次の文章のうち、ちょうど5か所だけ、語句を意味を変えずに生成AIがよく使う比喩的な言い回しに置き換えてください。
使う言い回しの例: {METAPHOR}。
置き換えるのは語句だけで、文の区切り・語順・ほかの語は変えないでください。
置き換えた全文だけを出力してください。説明は書かないでください。

{{text}}
""",
    "rhet": f"""次の文章のうち、ちょうど5か所だけ、文の運びを生成AIの文章によくある形に書き換えてください。意味と語彙はできるだけ変えません。
使う形の例: 短い言い切りの決め文で段落を締める(「〜。それが〜だ。」)、「AではなくBだ」という対比、体言止めの連続、
「結論から言うと、」「ポイントは〜だ。」のような前置き、3つ並べてリズムをつける列挙。
次の語は使わないでください: {METAPHOR}。新しい事実は足さないでください。
書き換えた全文だけを出力してください。説明は書かないでください。

{{text}}
""",
}


def excerpt(text: str, n: int = 2500) -> str:
    out, total = [], 0
    for para in text.split("\n\n"):
        if total >= n:
            break
        out.append(para)
        total += len(para)
    return "\n\n".join(out)


def opus(prompt: str) -> str | None:
    for _ in range(3):
        try:
            r = subprocess.run(["claude", "-p", prompt, "--model", "claude-opus-5-5", "--effort", "low",
                                "--setting-sources", "project", "--disallowed-tools", "*", "--append-system-prompt", SYSTEM],
                               capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=900, check=True, cwd=NEUTRAL)
            return r.stdout.strip()
        except Exception as e:  # noqa: BLE001
            print(f"  ERR: {e}", file=sys.stderr)
    return None


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    NEUTRAL.mkdir(parents=True, exist_ok=True)
    rows = [r for r in load() if r["split"] == "dev" and r["set"] in ("qiita2022", "llmjp")]
    jobs = []
    for r in rows:
        orig = OUT / f"{r['id']}-orig.md"
        if not orig.exists():
            orig.write_text(excerpt(r["text"]), encoding="utf-8")
        for kind in PROMPT:
            if not (OUT / f"{r['id']}-{kind}.md").exists():
                jobs.append((r["id"], kind, PROMPT[kind].format(text=orig.read_text(encoding="utf-8"))))
    print(len(jobs), "jobs", flush=True)
    with ThreadPoolExecutor(4) as ex:
        for (rid, kind, _), out in zip(jobs, ex.map(lambda j: opus(j[2]), jobs)):
            if out:
                (OUT / f"{rid}-{kind}.md").write_text(out + "\n", encoding="utf-8")
                print("ok", rid, kind, flush=True)


if __name__ == "__main__":
    main()
