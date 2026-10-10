# /// script
# requires-python = ">=3.11"
# dependencies = ["trafilatura>=1.12"]
# ///
"""corpus/bench/build_tasks.py — モデル評価ベンチの課題を作る(ロードマップ S40)。

作者の文書から材料を抜き出し、「材料から書く」課題と「推敲する」課題を作る。
課題の一覧(どの文書を使うか)は corpus/private/bench/tasks.json に置く(顧客のリポジトリ名や文書 ID を含むのでコミットしない)。
材料と作者の版は作者の文書を含むので corpus/private/bench/tasks/<task-id>/ に置き、コミットしない。

課題の種類:
    report   顧客向け文書 → 事実・数値・判断のメモ → 「この材料から〇〇を書いて」
    article  Zenn 記事 → コードブロック+作業メモ → 「Zenn の技術記事を書いて」
    pr       PR → 差分(gh pr diff) → 「PR の説明文を書いて」
    skilldoc スキルの references の文書 → 内容のメモ → 「スキルの解説文書を書いて」
    polish   作者の文書をそのまま → 「読みやすく推敲して」

メモの抜き出しは AI に任せる。抜き出したモデルの文体が材料を通じて評価に混ざらないよう、
メモは体言止めの短い箇条書きに限り、文章にしないよう指示する。抜き出しモデルは EXTRACTOR。

使い方:
    uv run corpus/bench/build_tasks.py [--only <task-id>...]
"""
from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import subprocess
import sys
from pathlib import Path

import trafilatura

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "corpus"))
import generate as g  # noqa: E402

OUT = ROOT / "corpus/private/bench/tasks"
TASKS = json.loads((ROOT / "corpus/private/bench/tasks.json").read_text(encoding="utf-8"))
EXTRACTOR = ("gpt-6-luna", g.run_codex)
FENCE_RE = re.compile(r"^\s*(```|~~~)[^\n]*\n.*?^\s*\1\s*$", re.M | re.S)

NOTE_PROMPT = """次の文書から、書き直しの材料になるメモを作ってください。
- 文書に書かれている事実・数値・固有名詞・決定事項・判断・理由・今後の予定を、漏れなく拾う
- 1行1項目の箇条書き。体言止めか、ごく短い句で書く。文章にしない。言い換えや要約の装飾をしない
- 見出しは付けない。文書にない情報は足さない
メモだけを出力してください。

{doc}
"""

REQUEST = {
    "report": "以下の材料から、{audience}向けの{doctype}を書いて。\n\n{materials}",
    "article": "以下のコードと作業メモから、Zenn に載せる技術記事を書いて。\n\n{materials}",
    "pr": "以下の差分から、この PR の説明文を書いて。\n\n{materials}",
    "polish": "次の文章を読みやすく推敲して。推敲した全文だけを出力して。\n\n{materials}",
    "skilldoc": (
        "以下のメモをもとに、日本語の文章術スキル(natural-japanese)の解説文書を Markdown で書いて。"
        "読み手は、このスキルを使って仕事の文書を書く人と、このスキルを読み込んで文章を直す AI。\n\n{materials}"
    ),
}


def html_to_text(raw: str) -> str:
    text = trafilatura.extract(raw, output_format="markdown", include_tables=True) or ""
    if len(text) < 200:
        body = re.sub(r"(?is)<(script|style|svg|head)\b.*?</\1>", "", raw)
        body = re.sub(r"(?i)<br\s*/?>|</(p|div|li|h[1-6]|tr|section)>", "\n", body)
        text = html_lib.unescape(re.sub(r"<[^>]+>", "", body))
        text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    return text


def as_doc(as_id: str) -> tuple[str, dict]:
    idx = {x["id"]: x for x in json.loads((ROOT / "corpus/private/as/index.json").read_text())}
    x = idx[as_id]
    raw = (ROOT / "corpus/private/as" / x["path"]).read_text(encoding="utf-8")
    return (html_to_text(raw) if x["kind"] == "html_page" else raw), x


def notes(doc: str) -> str:
    return EXTRACTOR[1](NOTE_PROMPT.format(doc=doc), EXTRACTOR[0], "low")


def build(t: dict) -> None:
    d = OUT / t["id"]
    if (d / "task.json").exists():
        print(f"skip {t['id']}")
        return
    d.mkdir(parents=True, exist_ok=True)
    kind = t["kind"]
    if kind == "report":
        doc, meta = as_doc(t["source"])
        materials = notes(doc)
        reference = doc
    elif kind == "article":
        txt = (Path.home() / "progs/zenn-content/articles" / f"{t['source']}.md").read_text(encoding="utf-8")
        body = re.sub(r"\A---\n.*?\n---\n", "", txt, flags=re.S)
        code = "\n\n".join(m.group(0).strip() for m in FENCE_RE.finditer(body))
        memo = notes(FENCE_RE.sub("", body))
        materials = f"## 作業メモ\n{memo}\n\n## コードと実行結果\n{code}"
        reference = body
    elif kind == "pr":
        diff = subprocess.run(["gh", "pr", "diff", t["source"]], capture_output=True, text=True, check=True).stdout
        materials = diff[:40000]
        prs = {x["url"]: x for x in json.loads((ROOT / "corpus/private/prs/prs.json").read_text())}
        reference = prs[t["source"]]["body"]
    elif kind == "skilldoc":
        # スキルの references の文書から、内容のメモを抜き出して書き直させる
        doc = (ROOT / "skills/natural-japanese/references" / t["source"]).read_text(encoding="utf-8")
        materials = notes(doc)
        reference = doc
    elif kind == "polish":
        doc, _ = as_doc(t["source"]) if not t["source"].endswith(".md") else (
            re.sub(r"\A---\n.*?\n---\n", "", (Path.home() / "progs/zenn-content/articles" / t["source"]).read_text(encoding="utf-8"), flags=re.S), None)
        materials = doc
        reference = doc
    else:
        raise ValueError(kind)
    prompt = REQUEST[kind].format(materials=materials, audience=t.get("audience", ""), doctype=t.get("doctype", ""))
    (d / "materials.md").write_text(materials, encoding="utf-8")
    (d / "reference.md").write_text(reference, encoding="utf-8")
    (d / "task.json").write_text(json.dumps({**t, "prompt": prompt, "extractor": EXTRACTOR[0]}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"ok {t['id']} materials={len(materials)} reference={len(reference)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    g.prepare_isolation()
    for t in TASKS:
        if a.only and t["id"] not in a.only:
            continue
        build(t)


if __name__ == "__main__":
    main()
