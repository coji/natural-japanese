# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""ページの例の文書(release-notes/data/v2.0.0/<文書>/doc.md)に、いまの作業ツリーの critical-thinking を `full` で2回かける。
  uv run --with pyyaml release-notes/run-v2.0.0.py ringi teian kikaku postmortem
1回目(pass1/)は writer.json の事実しか知らない書き手の答えで回り、返答は差し戻しと宿題になる。
2回目(pass2/)は writer2.json(宿題を済ませて分かったことを足した事実)で回る。
各 pass の中身: doc.md のコピー、writer.json、questions.md、answers.md、doc.review.md、doc.確認事項.md、doc.review.short.md、
doc.review.plans.md、doc.review.rebuild.md、それぞれの確認事項、report-logic.md、report-somosomo.md、YAML、reply.md(最後の返答)。
実行ログ log-*.txt は残るが git には入れない(.gitignore)。
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "dev" / "ct-eval"))
import eval as ev  # noqa: E402

DATA = Path(__file__).resolve().parent / "data" / "v2.0.0"
TOOLS = ev.REWRITE_TOOLS + ["Skill"]
MODEL, EFFORT = "claude-opus-5-5", "high"
FULL = "/critical-thinking full doc.md"


def full(d: Path, plugin: Path, log: str) -> None:
    lp = d / f"log-{log}.txt"
    ev.claude(FULL, d, TOOLS, MODEL, EFFORT, plugin, lp)
    # 最後の返答は stream-json の result イベントにある
    for line in reversed(lp.read_text().splitlines()):
        if line.startswith("{") and '"type":"result"' in line.replace(" ", ""):
            try:
                (d / "reply.md").write_text(json.loads(line).get("result", ""))
            except json.JSONDecodeError:
                pass
            break


def homework_questions(kak: Path) -> list[str]:
    """1回目の確認事項ファイルの「出す前にやること」を、書き手への問いの形にする。"""
    out, cur, inside = [], None, False
    for line in kak.read_text().splitlines():
        if line.startswith("## "):
            inside = line.startswith("## 出す前にやること")
            continue
        if not inside:
            continue
        m = re.match(r"^(\d+)\.\s*\**(.+?)\**\s*$", line)
        if m:
            cur = m.group(2).strip("*:： "); out.append(cur); continue
        m = re.match(r"^\s*-\s*\**調べること\**[:：]\s*(.+)$", line)
        if m and out:
            out[-1] = out[-1] + "。" + m.group(1).strip()
    return out


def one_pass(src: Path, w: Path, writer: str, plugin: Path, prev: Path | None = None) -> None:
    if w.exists():
        shutil.rmtree(w)
    w.mkdir()
    shutil.copy(src / "doc.md", w / "doc.md")
    shutil.copy(src / writer, w / "writer.json")
    if prev is not None:
        # 2回目: 1回目の問いと宿題を、宿題を済ませた書き手に答えさせてから回す(問いの工程は飛ばす)
        qs = [l for l in (prev / "questions.md").read_text().splitlines() if re.match(r"^\d+\.", l)]
        hw = homework_questions(prev / "doc.確認事項.md")
        n = len(qs)
        qs += [f"{n + i + 1}. 宿題:{h}。調べた結果を教えてください" for i, h in enumerate(hw)]
        (w / "questions.md").write_text("\n".join(qs) + "\n")
    else:
        full(w, plugin, "full1")  # answers.md がないので questions.md を書いて止まる
    if (w / "questions.md").exists():
        ev.claude(ev.WRITER_PROMPT.format(file="doc.md"), w, ev.WRITER_TOOLS, MODEL, "medium", None, w / "log-writer.txt")
        if (w / "answers.md").exists():
            full(w, plugin, "full2")


def run(d: Path, plugin: Path) -> str:
    if not PASS2_ONLY:
        one_pass(d, d / "pass1", "writer.json", plugin)
    one_pass(d, d / "pass2", "writer2.json", plugin, prev=d / "pass1")
    return f"done {d.name}: " + ", ".join(sorted(p.name for p in (d / "pass2").iterdir() if not p.name.startswith("log-")))


PASS2_ONLY = False


def main() -> None:
    global PASS2_ONLY
    names = [a for a in sys.argv[1:] if not a.startswith("--")]
    PASS2_ONLY = "--pass2-only" in sys.argv  # 1回目の出力を残し、2回目だけ回す
    plugin = ev.make_plugin_dir()
    with ThreadPoolExecutor(max_workers=4) as ex:
        for r in ex.map(lambda n: run(DATA / n, plugin), names):
            print(r, flush=True)
    shutil.rmtree(plugin, ignore_errors=True)


if __name__ == "__main__":
    main()
