# /// script
# requires-python = ">=3.11"
# dependencies = ["markdown>=3.6"]
# ///
"""corpus/selfcorpus/build_review.py — 前後の対を左右に並べたレビュー用 HTML を作る(ロードマップ S30)。

対ごとに、評価軸の判定(2モデル × 2つの並び順)と内容の保持の指摘を上に置き、
直す前と後の本文を左右に並べる。Artifact Share のローカルプレビューで開いて、作者がコメントを付ける。

出力: corpus/private/review/review.html(コミットしない)
使い方: uv run corpus/selfcorpus/build_review.py <pair-id>...
"""
from __future__ import annotations
import html, json, re, sys
from pathlib import Path
import markdown

ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT / "corpus/private/skill-apply"
AXES = ["A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9", "A10"]
RUBRIC = (ROOT / "corpus/selfcorpus/rubric.md").read_text(encoding="utf-8")
NAMES = {ax: re.search(rf"\| {ax} ([^|]+) \|", RUBRIC).group(1).strip() for ax in AXES}

def md(t: str) -> str:
    t = re.sub(r"\A---\n.*?\n---\n", "", t, flags=re.S)
    return markdown.markdown(t, extensions=["tables", "fenced_code"])

def verdicts(pair: Path) -> tuple[str, str]:
    rows, notes = [], []
    js = {}
    for f in sorted(pair.glob("judge-*.json")):
        js[f.stem.replace("judge-", "")] = json.loads(f.read_text(encoding="utf-8"))
    for ax in AXES:
        cells = []
        for key, d in js.items():
            order = key.rsplit("-", 1)[1]
            b = d.get("axes", {}).get(ax, {}).get("better", "tie")
            after_label = "B" if order == "ba" else "A"
            v = "後" if b == after_label else ("前" if b in ("A", "B") else "＝")
            cells.append(v)
        rows.append(f"<tr><td>{html.escape(NAMES[ax])}</td>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
    head = "<tr><th>軸</th>" + "".join(f"<th>{html.escape(k)}</th>" for k in js) + "</tr>"
    for key, d in js.items():
        a = d.get("A11", {})
        if a.get("preservation") and a.get("preservation") != "保っている":
            notes.append(f"<li><b>{html.escape(key)}</b>: {html.escape(a.get('preservation',''))} — {html.escape(a.get('reason',''))}</li>")
    return f"<table class='v'>{head}{''.join(rows)}</table>", f"<ul>{''.join(notes)}</ul>" if notes else "<p>指摘なし</p>"

def main() -> None:
    parts = []
    for i, pid in enumerate(sys.argv[1:], 1):
        p = DIR / pid
        table, notes = verdicts(p)
        kind = "顧客向け文書" if pid.startswith("as-") else "Zenn 記事"
        parts.append(f"""
<section>
<h2>{i}. {kind}({html.escape(pid)})</h2>
<details open><summary>評価軸の判定(後=直した後がよい、前=直す前がよい、＝=差がない)</summary>{table}</details>
<h3>内容の保持についての指摘</h3>{notes}
<div class="cols">
<div class="col"><h3>直す前</h3>{md((p/'before.md').read_text(encoding='utf-8'))}</div>
<div class="col"><h3>直した後</h3>{md((p/'after.md').read_text(encoding='utf-8'))}</div>
</div>
</section>""")
    page = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>スキル適用の前後レビュー</title>
<style>
:root{{--bg:#fff;--fg:#1d1d1f;--muted:#666;--line:#ddd;--card:#fafafa}}
@media (prefers-color-scheme:dark){{:root{{--bg:#151515;--fg:#eee;--muted:#aaa;--line:#333;--card:#1e1e1e}}}}
body{{background:var(--bg);color:var(--fg);font-family:system-ui,-apple-system,"Hiragino Sans",sans-serif;line-height:1.8;margin:0;padding:16px}}
section{{border-top:3px solid var(--line);padding-top:12px;margin-top:32px}}
.cols{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
@media (max-width:800px){{.cols{{grid-template-columns:1fr}}}}
.col{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px;overflow-x:auto;font-size:15px}}
table{{border-collapse:collapse;font-size:13px}} td,th{{border:1px solid var(--line);padding:2px 8px}}
table.v td:not(:first-child){{text-align:center}}
pre{{white-space:pre-wrap;word-break:break-all}}
h2{{font-size:20px}} h3{{font-size:16px;color:var(--muted)}}
</style></head><body>
<h1>スキル適用の前後レビュー</h1>
<p>今のスキル(クイックモード)で直した前後の対です。評価軸の判定は GPT・Gemini が並び順を入れ替えて2回ずつ行ったもの。読みやすくなったか、内容が変わっていないか、まだ足りない点はどこかを、気になった箇所にコメントしてください。</p>
{''.join(parts)}
</body></html>"""
    out = ROOT / "corpus/private/review/review.html"
    out.write_text(page, encoding="utf-8")
    print(out)

if __name__ == "__main__":
    main()
