# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "httpx>=0.27",
#     "pypdfium2>=4.30",
# ]
# ///
"""corpus/fetch.py — sources.json の type=web エントリを取得し、本文を
Markdown として corpus/human/web/{id}.md に保存する。

設計方針:
    - 著作権のある記事本文はコミットしない(.gitignore 済み)。ローカルの
      評価用コーパスとしてのみ使う。
    - note / Zenn 用の構造化抽出 + 汎用フォールバック(<article> / <main>
      からテキストを抜き出し、タグを除去する簡易実装)。
    - レートリミット: リクエスト間に1秒スリープ。
    - User-Agent を明示し、取得先に負荷をかけすぎない。

使い方:
    uv run corpus/fetch.py                 # sources.json の web エントリを全件取得
    uv run corpus/fetch.py --id note-essay-xxx  # 1件だけ取得(動作確認用)
    uv run corpus/fetch.py --limit 3        # 先頭3件だけ取得(試走用)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import httpx

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36 "
    "natural-japanese-corpus-fetch/0.1 (research/calibration use)"
)

CORPUS_DIR = Path(__file__).parent
SOURCES_PATH = CORPUS_DIR / "sources.json"
OUT_DIR = CORPUS_DIR / "human" / "web"

RATE_LIMIT_SECONDS = 1.0


def load_sources() -> list[dict]:
    data = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    return [s for s in data if s.get("type") == "web"]


def unescape_entities(text: str) -> str:
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    text = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), text)
    text = re.sub(r"&#x([0-9a-fA-F]+);", lambda m: chr(int(m.group(1), 16)), text)
    return text


def convert_headings(html: str) -> str:
    """本文 HTML 中の <h1>〜<h6> を Markdown 見出し(`#`〜`######`)に変換する。

    strip_tags でタグを剥がす前に呼ぶこと。見出しタグ内部にインライン
    タグ(<span>/<a> 等)が含まれる場合もテキストのみを取り出す。
    """

    def repl(m: re.Match[str]) -> str:
        level = int(m.group(1))
        inner = re.sub(r"<[^>]+>", "", m.group(2))
        inner = unescape_entities(inner)
        text = " ".join(inner.split()).strip()
        if not text:
            return ""
        return "\n\n" + ("#" * level) + " " + text + "\n\n"

    return re.sub(r"<h([1-6])[^>]*>(.*?)</h\1>", repl, html, flags=re.S | re.I)


def strip_tags(html: str) -> str:
    html = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", "", html, flags=re.S | re.I)
    html = convert_headings(html)
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    html = re.sub(r"</p>", "\n\n", html, flags=re.I)
    html = re.sub(r"<[^>]+>", "", html)
    html = unescape_entities(html)
    lines = [ln.strip() for ln in html.splitlines()]
    lines = [ln for ln in lines if ln]
    return "\n\n".join(lines)


def extract_note(html: str) -> str | None:
    # note.com: 本文は <div class="note-common-styles__textnote-body"> 配下
    m = re.search(
        r'<div class="note-common-styles__textnote-body"[^>]*>(.*?)</div>\s*</div>\s*</div>',
        html,
        re.S,
    )
    if not m:
        # フォールバック: <article> タグ
        m = re.search(r"<article[^>]*>(.*?)</article>", html, re.S)
    if not m:
        return None
    return strip_tags(m.group(1))


def extract_zenn(html: str) -> str | None:
    # Zenn: 本文は <div class="znc"> (Zenn Notation Compiled) 配下
    m = re.search(r'<div class="znc"[^>]*>(.*?)</div>\s*</div>\s*</div>', html, re.S)
    if not m:
        m = re.search(r"<article[^>]*>(.*?)</article>", html, re.S)
    if not m:
        return None
    return strip_tags(m.group(1))


def extract_generic(html: str) -> str:
    m = re.search(r"<article[^>]*>(.*?)</article>", html, re.S)
    if not m:
        m = re.search(r"<main[^>]*>(.*?)</main>", html, re.S)
    body = m.group(1) if m else html
    return strip_tags(body)


def extract_title(html: str) -> str:
    m = re.search(r"<title>(.*?)</title>", html, re.S)
    return m.group(1).strip() if m else ""


def extract_pdf(content: bytes) -> str:
    """PDF バイト列からページ単位でテキストを抽出し、明らかなゴミ行
    (単独のページ番号、ヘッダ/フッタの繰り返し行)を除去して結合する。"""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(content)
    page_texts = []
    for page in pdf:
        textpage = page.get_textpage()
        page_texts.append(textpage.get_text_range())

    # 繰り返し出現する短い行 (ヘッダ/フッタ) を検出して除去する
    from collections import Counter

    line_counts: Counter[str] = Counter()
    for pt in page_texts:
        for ln in {ln.strip() for ln in pt.splitlines() if ln.strip()}:
            if len(ln) <= 40:
                line_counts[ln] += 1
    n_pages = max(len(page_texts), 1)
    repeated = {
        ln for ln, c in line_counts.items() if c >= max(3, n_pages // 2) and n_pages > 2
    }

    out_lines: list[str] = []
    for pt in page_texts:
        for ln in pt.splitlines():
            s = ln.strip()
            if not s:
                continue
            if s in repeated:
                continue
            if re.fullmatch(r"[-‐―ー0-9０-９ページPage/\s.]{1,10}", s):
                continue
            out_lines.append(s)
    return "\n".join(out_lines)


def extract_body(url: str, html: str) -> tuple[str, str]:
    """(抽出方式, 本文テキスト) を返す。"""
    if "note.com" in url:
        text = extract_note(html)
        if text and len(text) > 200:
            return "note", text
    if "zenn.dev" in url:
        text = extract_zenn(html)
        if text and len(text) > 200:
            return "zenn", text
    return "generic", extract_generic(html)


def decode_html(resp: httpx.Response) -> str:
    """レスポンス本文をデコードする。

    HTTP ヘッダに charset が無い場合、httpx は utf-8 と誤検出することがある
    (例: 総務省白書ページは Shift_JIS を meta/XML 宣言でのみ示す)。
    HTTP ヘッダに charset が明示されていなければ、生バイト列から
    <meta charset> / XML encoding 宣言を読み取ってデコードし直す。
    """
    content_type_header = resp.headers.get("content-type", "")
    if "charset=" in content_type_header.lower():
        return resp.text

    raw = resp.content
    head = raw[:2048].decode("ascii", errors="ignore")
    m = re.search(r'charset=["\']?([\w-]+)', head, re.I) or re.search(
        r'encoding=["\']([\w-]+)["\']', head, re.I
    )
    if m:
        declared = m.group(1).strip().lower()
        try:
            return raw.decode(declared)
        except (LookupError, UnicodeDecodeError):
            pass
    return resp.text


def fetch_one(source: dict, client: httpx.Client) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{source['id']}.md"
    url = source["url"]
    print(f"fetch: {source['id']} <- {url}", file=sys.stderr)
    resp = client.get(url, headers={"User-Agent": USER_AGENT}, timeout=60, follow_redirects=True)
    resp.raise_for_status()

    content_type = resp.headers.get("content-type", "").lower()
    is_pdf = "application/pdf" in content_type or url.lower().split("?")[0].endswith(".pdf")
    if is_pdf:
        method = "pdf"
        body = extract_pdf(resp.content)
        title = source.get("title") or ""
    else:
        html = decode_html(resp)
        method, body = extract_body(url, html)
        title = source.get("title") or extract_title(html)

    frontmatter = (
        "---\n"
        f"id: {source['id']}\n"
        f"source_url: {url}\n"
        f"title: {json.dumps(title, ensure_ascii=False)}\n"
        f"author: {json.dumps(source.get('author') or '', ensure_ascii=False)}\n"
        f"genre: {source.get('genre', '')}\n"
        f"extract_method: {method}\n"
        f"chars: {len(body)}\n"
        "---\n\n"
    )
    out_path.write_text(frontmatter + body + "\n", encoding="utf-8")
    print(f"  -> {out_path} ({method}, {len(body)} chars)", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="corpus/sources.json の web エントリを取得する")
    parser.add_argument("--id", help="この id のエントリだけ取得する")
    parser.add_argument("--limit", type=int, help="先頭 N 件だけ取得する(試走用)")
    args = parser.parse_args()

    sources = load_sources()
    if args.id:
        sources = [s for s in sources if s["id"] == args.id]
        if not sources:
            print(f"id not found: {args.id}", file=sys.stderr)
            sys.exit(1)
    elif args.limit:
        sources = sources[: args.limit]

    failed = 0
    with httpx.Client() as client:
        for i, source in enumerate(sources):
            try:
                fetch_one(source, client)
            except Exception as e:  # noqa: BLE001 — 1件失敗しても続行する
                failed += 1
                print(f"  ERROR: {source['id']}: {e}", file=sys.stderr)
            if i < len(sources) - 1:
                time.sleep(RATE_LIMIT_SECONDS)

    succeeded = len(sources) - failed
    print(f"summary: {succeeded} succeeded, {failed} failed (total {len(sources)})", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
