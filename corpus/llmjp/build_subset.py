# /// script
# requires-python = ">=3.11"
# ///
"""corpus/llmjp/build_subset.py — LLM-jp コーパス v4 から「生成AI以前の、説明的・実務的な Web 文章」を絞り込む。

日本語の文章を直すスキルや道具が「人間の普通の文章に誤って反応しないか」を測るための、
共通の基準データ(母集団)を作る。方針は調査メモ corpus/reports/research/llm-jp-corpus.md の10章。

ファイルは保存せず、取りながら gzip を展開して規則を当て、残った文書だけを手元に置く。
規則(RULE_VERSION で版を管理):
    1. 時期: meta.date が CUTOFF より前(そのページが生成AI以前に存在した)
    2. ドメイン: EC・通販・求人・不動産の一覧・Q&A・掲示板・スパムの多い TLD を除く
    3. 本文: PROSE_MIN 字以上、地の文の行(20字以上で句点などで終わる行)が文字数の PROSE_RATIO 以上、
       同じ行の繰り返しが少ない
    4. 種類: URL の規則で一次分類する(行政・企業の発信・報道・ブログ・コラム・その他)
lint.py の結果は絞り込みに使わない(誤検知を測る対象そのものなので)。

出力:
    corpus/private/llmjp/<level>-<file>.jsonl  本文つき(コミットしない)
    corpus/llmjp/manifest/<level>-<file>.jsonl 本文なしの一覧: source, docId, url, date, type, sha256, rule_version
                                              (公開できる形。利用者は抽出スクリプトで同じ文書を取り出せる)

使い方: uv run corpus/llmjp/build_subset.py --level level0 --files 0110 0001 0450
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.request
import zlib
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

BASE = "https://gitlab.llm-jp.nii.ac.jp/datasets/llm-jp-corpus-v4/-/raw/main/ja/ja_cc"
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RULE_VERSION = "2026-10-09.1"
CUTOFF = "2022-11-01"
PROSE_MIN = 800
PROSE_RATIO = 0.6
PROSE_LINE_RE = re.compile(r"^.{20,}[。！？」』）)]$")

EXCLUDE_HOST = re.compile(
    r"(amazon|rakuten|yahoo-shopping|shopping|store|shop|mercari|zozo|kakaku|monotaro|askul|lohaco|"
    r"/product/|/products/|/item/|/goods/|/cart|"
    r"indeed|townwork|baitoru|mynavi|rikunabi|doda|en-japan|"
    r"suumo|homes\.co\.jp|athome|chintai|"
    r"chiebukuro|oshiete|okwave|komachi|qa\.|2ch|5ch|bbspink|"
    r"fc2\.com/.*(video|adult)|dmm|av-|porn|xxx)", re.I)
EXCLUDE_TLD = re.compile(r"\.(xyz|top|club|online|site|work|info|biz|link|click|win|loan|bid|icu|buzz)$", re.I)
BLOG_HOST = re.compile(r"(ameblo|hatenablog|hatena\.ne\.jp|livedoor\.(blog|jp)|blog\.jp|fc2\.com|seesaa|jugem|exblog|goo\.ne\.jp/blog|note\.com|wordpress|blogspot|cocolog|muragon|naver)", re.I)
NEWS_HOST = re.compile(r"(nikkei|asahi|mainichi|yomiuri|sankei|jiji|kyodo|nhk|itmedia|impress|toyokeizai|president|diamond|newspicks|gendai|bunshun|j-cast|huffingtonpost|businessinsider|forbesjapan|news\.)", re.I)


def classify(url: str) -> str | None:
    """URL から種類を推定する。除外するものは None。"""
    u = urlparse(url.strip("<>"))
    host, path = u.netloc.lower(), u.path.lower()
    if not host or EXCLUDE_TLD.search(host) or EXCLUDE_HOST.search(host + path):
        return None
    if host.endswith((".go.jp", ".lg.jp")) or re.search(r"\.(pref|city|town|vill)\.[a-z]+\.jp$", host):
        return "行政"
    if NEWS_HOST.search(host):
        return "報道・ビジネス誌"
    if BLOG_HOST.search(host) or "/blog" in path:
        return "ブログ"
    if re.search(r"/(news|press|release|information|info|topics|notice)/", path) and host.endswith((".co.jp", ".or.jp", ".jp", ".com")):
        return "組織の発信"
    if re.search(r"/(column|columns|knowledge|magazine|media|guide|howto|tips)/", path):
        return "コラム・解説"
    if host.endswith(".ac.jp"):
        return "大学・研究機関"
    return "その他"


def prose_ok(text: str) -> bool:
    if len(text) < PROSE_MIN:
        return False
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if not lines:
        return False
    prose_chars = sum(len(l) for l in lines if PROSE_LINE_RE.match(l))
    if prose_chars / max(len(text), 1) < PROSE_RATIO:
        return False
    # 同じ行が何度も出る(テンプレートや自動生成)ものを除く
    c = Counter(lines)
    return c.most_common(1)[0][1] <= 3


def stream_lines(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "natural-japanese-corpus/1.0 (research)"})
    d = zlib.decompressobj(16 + zlib.MAX_WBITS)
    buf = ""
    with urllib.request.urlopen(req, timeout=120) as r:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            buf += d.decompress(chunk).decode("utf-8", "ignore")
            *lines, buf = buf.split("\n")
            yield from lines
    if buf:
        yield buf


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", default="level0")
    ap.add_argument("--files", nargs="+", required=True)
    a = ap.parse_args()
    priv = ROOT / "corpus/private/llmjp"
    man = HERE / "manifest"
    priv.mkdir(parents=True, exist_ok=True)
    man.mkdir(parents=True, exist_ok=True)
    for name in a.files:
        stats = Counter()
        types = Counter()
        tag = f"{a.level}-{name}"
        with open(priv / f"{tag}.jsonl", "w", encoding="utf-8") as fp, open(man / f"{tag}.jsonl", "w", encoding="utf-8") as fm:
            for line in stream_lines(f"{BASE}/{a.level}/{name}.jsonl.gz"):
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                stats["all"] += 1
                meta = rec.get("meta", {})
                date = (meta.get("date") or "")[:10]
                if not date or date >= CUTOFF:
                    stats["date"] += 1
                    continue
                t = classify(meta.get("url") or "")
                if t is None:
                    stats["domain"] += 1
                    continue
                text = rec.get("text") or ""
                if not prose_ok(text):
                    stats["prose"] += 1
                    continue
                stats["kept"] += 1
                types[t] += 1
                sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
                row = {"source": f"llm-jp-corpus-v4/ja/ja_cc/{a.level}/{name}.jsonl.gz", "docId": meta.get("docId"),
                       "url": (meta.get("url") or "").strip("<>"), "date": date, "type": t, "sha256": sha, "rule_version": RULE_VERSION}
                fm.write(json.dumps(row, ensure_ascii=False) + "\n")
                fp.write(json.dumps({**row, "text": text}, ensure_ascii=False) + "\n")
                if stats["all"] % 20000 == 0:
                    print(f"  {tag}: {dict(stats)}", flush=True)
        print(f"{tag}: {dict(stats)} types={dict(types)}", flush=True)


if __name__ == "__main__":
    main()
