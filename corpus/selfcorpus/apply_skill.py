# /// script
# requires-python = ">=3.11"
# dependencies = ["trafilatura>=1.12"]
# ///
"""corpus/selfcorpus/apply_skill.py — 今のスキルを作者の文書に当てる(ロードマップ S30)。

claude -p に、このリポジトリのスキル(--plugin-dir)を読み込ませ、個人設定は外して
(--setting-sources project)、クイックモードで推敲させる。作業ディレクトリは文書ごとの
一時ディレクトリで、許可するのはファイルの読み書きと uv run(スキルの lint 実行)だけ。

入力: 顧客向け文書(corpus/private/as/)から選んだ本数と、スキル前の Zenn 記事
出力: corpus/private/skill-apply/<id>/before.md, after.md, log.txt(コミットしない)

使い方:
    uv run corpus/selfcorpus/apply_skill.py --ids <as-id>... --zenn <slug>... [--parallel 3]
"""
from __future__ import annotations
import argparse, json, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import html as html_lib
import trafilatura

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "corpus/private/skill-apply"
PROMPT = (
    "natural-japanese スキルのクイックモードで、input.md の文章を推敲してください。"
    "読み手と目的は文書の内容から判断してください。"
    "推敲した全文を output.md に書き出してください。input.md は変更しないでください。"
    "確認の質問はせず、最後まで自分の判断で進めてください。"
)

def html_to_text(raw: str) -> str:
    """trafilatura で取り出せない HTML(アプリ風のページなど)は、タグを外したテキストで代用する。"""
    text = trafilatura.extract(raw, output_format="markdown", include_tables=True) or ""
    if len(text) < 200:
        body = re.sub(r"(?is)<(script|style|svg|head)\b.*?</\1>", "", raw)
        body = re.sub(r"(?i)<br\s*/?>|</(p|div|li|h[1-6]|tr|section)>", "\n", body)
        text = html_lib.unescape(re.sub(r"<[^>]+>", "", body))
        text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    return text


def prepare(item_id: str, text: str) -> Path:
    d = OUT / item_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "before.md").write_text(text, encoding="utf-8")
    work = Path("/tmp/corpus-gen-isolation/skill-apply") / item_id
    work.mkdir(parents=True, exist_ok=True)
    (work / "input.md").write_text(text, encoding="utf-8")
    return work

def run(item_id: str, work: Path, tag: str = "") -> str:
    d = OUT / item_id
    after_name = f"after-{tag}.md" if tag else "after.md"
    if (d / after_name).exists():
        return f"skip {item_id}"
    cmd = [
        "claude", "-p", PROMPT,
        "--model", "claude-opus-5-5", "--effort", "low",
        "--setting-sources", "project",
        "--plugin-dir", str(ROOT),
        "--allowedTools", "Skill", "Read", "Write", "Edit", "Glob", "Grep",
        "Bash(uv run:*)", "Bash(python3:*)", "Bash(cat:*)", "Bash(wc:*)",
    ]
    r = subprocess.run(cmd, cwd=work, capture_output=True, text=True, timeout=1200, stdin=subprocess.DEVNULL)
    (d / f"log{('-' + tag) if tag else ''}.txt").write_text(r.stdout + "\n--- stderr ---\n" + r.stderr, encoding="utf-8")
    out = work / "output.md"
    if out.exists():
        text = out.read_text(encoding="utf-8")
        (d / after_name).write_text(text, encoding="utf-8")
        out.unlink()
        return f"ok {item_id} {len(text)} chars"
    return f"FAIL {item_id}: no output.md"

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", nargs="*", default=[])
    ap.add_argument("--zenn", nargs="*", default=[])
    ap.add_argument("--parallel", type=int, default=3)
    ap.add_argument("--tag", default="", help="出力を after-<tag>.md として保存する(スキルの版ごとに比べるため)")
    ap.add_argument("--all-existing", action="store_true", help="skill-apply/ にある対すべてに当て直す")
    a = ap.parse_args()
    idx = {x["id"]: x for x in json.loads((ROOT / "corpus/private/as/index.json").read_text())}
    jobs = []
    for i in a.ids:
        x = idx[i]
        raw = (ROOT / "corpus/private/as" / x["path"]).read_text(encoding="utf-8")
        text = html_to_text(raw) if x["kind"] == "html_page" else raw
        jobs.append((f"as-{i}", prepare(f"as-{i}", text or "")))
    for slug in a.zenn:
        txt = (Path.home() / "progs/zenn-content/articles" / f"{slug}.md").read_text(encoding="utf-8")
        jobs.append((f"zenn-{slug}", prepare(f"zenn-{slug}", txt)))
    if a.all_existing:
        for d in sorted(p for p in OUT.iterdir() if (p / "before.md").exists()):
            work = Path("/tmp/corpus-gen-isolation/skill-apply") / d.name
            work.mkdir(parents=True, exist_ok=True)
            (work / "input.md").write_text((d / "before.md").read_text(encoding="utf-8"), encoding="utf-8")
            jobs.append((d.name, work))
    with ThreadPoolExecutor(a.parallel) as ex:
        for res in ex.map(lambda j: run(*j, a.tag), jobs):
            print(res, flush=True)

if __name__ == "__main__":
    main()
