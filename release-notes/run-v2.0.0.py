# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""ページの例の文書(release-notes/data/v2.0.0/<文書>/doc.md)に、いまの作業ツリーの critical-thinking を一通りかける。
  uv run --with pyyaml release-notes/run-v2.0.0.py ringi teian kikaku postmortem
doc.md・brief.txt・writer.json は残し、それ以外の出力を作り直す。頼み方の文は dev/ct-eval/eval.py の PROMPTS と同じ。
出力: report-logic.md, report-somosomo.md, doc.md.logic.yaml, questions.md, answers.md, doc-review.md, doc-review.確認事項.md,
      plans.md, doc-redesign.md, doc-redesign.確認事項.md, doc-concise.md, doc-concise.確認事項.md, log-*.txt
"""
from __future__ import annotations

import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "dev" / "ct-eval"))
import eval as ev  # noqa: E402

DATA = Path(__file__).resolve().parent / "data" / "v2.0.0"
KEEP = {"doc.md", "brief.txt", "writer.json"}
TOOLS = ev.REWRITE_TOOLS
MODEL, EFFORT = "claude-opus-5-5", "high"


def run(d: Path, plugin: Path) -> str:
    for p in d.iterdir():
        if p.name not in KEEP:
            p.unlink()
    f = "doc.md"
    def go(name: str, prompt: str) -> None:
        ev.claude(prompt, d, TOOLS, MODEL, EFFORT, plugin, d / f"log-{name}.txt")
    go("logic", ev.PROMPTS["logic"].format(file=f).replace("report.md", "report-logic.md"))
    go("somosomo", ev.PROMPTS["somosomo"].format(file=f).replace("report.md", "report-somosomo.md"))
    rv = ev.PROMPTS["review"].format(file=f).replace("source-after.md", "doc-review.md").replace("source.確認事項.md", "doc-review.確認事項.md")
    go("review1", rv)
    if (d / "questions.md").exists():
        ev.claude(ev.WRITER_PROMPT.format(file=f), d, ev.WRITER_TOOLS, MODEL, "medium", None, d / "log-writer.txt")
        if (d / "answers.md").exists():
            go("review2", rv)
    go("redesign", ev.PROMPTS["redesign"].format(file=f).replace("source-after.md", "doc-redesign.md").replace("source.確認事項.md", "doc-redesign.確認事項.md"))
    go("concise", ev.PROMPTS["concise"].format(file=f).replace("source-after.md", "doc-concise.md").replace("source.確認事項.md", "doc-concise.確認事項.md"))
    return f"done {d.name}: " + ", ".join(sorted(p.name for p in d.iterdir() if p.name not in KEEP and not p.name.startswith("log-")))


def main() -> None:
    names = sys.argv[1:]
    plugin = ev.make_plugin_dir()
    with ThreadPoolExecutor(max_workers=4) as ex:
        for r in ex.map(lambda n: run(DATA / n, plugin), names):
            print(r, flush=True)
    shutil.rmtree(plugin, ignore_errors=True)


if __name__ == "__main__":
    main()
