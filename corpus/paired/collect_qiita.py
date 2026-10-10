# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""corpus/paired/collect_qiita.py — 対コーパスの human 側を Qiita API から集める。

生成AI以前(ChatGPT 公開の 2022-11-30 より前)に書かれ、その後も更新されていない
技術記事を、Qiita の検索 API で集める。本文は著作権があるためコミットしない
(corpus/paired/<set>/human/ は非コミット)。コミットするのは記事 ID と条件を書いた
manifest.json だけで、このスクリプトで誰でも同じ集合を取り直せる。

収集条件(manifest.json の criteria にも記録する):
    - created_at と updated_at がどちらも CUTOFF より前(後からの AI 加筆を除く)
    - ストック数 MIN_STOCKS 以上(品質の代わり。手作業の品質ラベルはやめる)
    - タイトルに「翻訳」「訳」を含まない(翻訳調が human 側に混ざると
      translationese 系検出器の FP 基盤が壊れる)
    - 地の文(コード・見出し・リスト・表を除いた本文)が MIN_PROSE_CHARS 〜 MAX_PROSE_CHARS 字
    - 1著者 MAX_PER_AUTHOR 本まで(FP 率は文書単位で数えるので、同じ著者の文体が
      偏って多いと独立性が崩れる)
    - 話題の偏りを避けるため、TAGS を順に回して1タグあたり最大 PER_TAG 本

使い方:
    uv run corpus/paired/collect_qiita.py --set tech-qiita --limit 50
    uv run corpus/paired/collect_qiita.py --set tech-qiita-s100 --min-stocks 100 --exclude-set tech-qiita
    QIITA_TOKEN=... で認証付き(レート上限 1000/時。なしだと 60/時)
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "skills" / "natural-japanese" / "scripts"))
from textcore import mask_markdown_structure  # noqa: E402

API = "https://qiita.com/api/v2/items"
CUTOFF = "2022-11-30"
MIN_STOCKS = 30
MIN_PROSE_CHARS = 1500
# AI に同じ長さで書かせるのが現実的な範囲に収める(極端に長い記事は対にならない)
MAX_PROSE_CHARS = 8000
MAX_PER_AUTHOR = 1
PER_TAG = 4
TAGS = [
    "JavaScript", "TypeScript", "Python", "Go", "Rust", "Ruby", "Java", "PHP",
    "React", "Vue.js", "AWS", "Docker", "Kubernetes", "Linux", "Git", "SQL",
    "PostgreSQL", "MySQL", "設計", "テスト", "機械学習", "セキュリティ",
    "初心者", "ポエム", "新人プログラマ応援", "チーム開発", "アジャイル",
    "CI", "Terraform", "Swift", "Android", "Flutter", "C", "C++", "Haskell",
]
TRANSLATION_RE = re.compile(r"翻訳|訳")
FENCE_RE = re.compile(r"^\s*(```|~~~).*?^\s*(```|~~~)\s*$", re.M | re.S)


def prose_chars(body: str) -> int:
    return len(re.sub(r"\s+", "", mask_markdown_structure(body)))


def chars_without_code(body: str) -> int:
    return len(re.sub(r"\s+", "", FENCE_RE.sub("", body)))


def search(tag: str, page: int, token: str | None, min_stocks: int) -> list[dict]:
    query = f"tag:{tag} created:<{CUTOFF} stocks:>={min_stocks}"
    url = f"{API}?{urllib.parse.urlencode({'query': query, 'per_page': 100, 'page': page})}"
    req = urllib.request.Request(url, headers={"User-Agent": "natural-japanese-corpus/1.0"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=60) as res:
        remaining = res.headers.get("Rate-Remaining")
        if remaining is not None and int(remaining) < 3:
            print(f"rate limit almost exhausted (remaining={remaining})", file=sys.stderr)
        return json.loads(res.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="対コーパスの human 側を Qiita から集める")
    parser.add_argument("--set", default="tech-qiita", help="corpus/paired/<set>/ に保存する")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--min-stocks", type=int, default=MIN_STOCKS)
    parser.add_argument("--tags", nargs="*", help="検索するタグ(省略時は TAGS)")
    parser.add_argument("--per-tag", type=int, default=PER_TAG)
    parser.add_argument(
        "--exclude-set",
        nargs="*",
        default=[],
        help="既存セットの記事と著者を除く(独立した集合にして、検証用にも使えるようにする)",
    )
    args = parser.parse_args()

    token = os.environ.get("QIITA_TOKEN")
    set_dir = HERE / args.set
    human_dir = set_dir / "human"
    human_dir.mkdir(parents=True, exist_ok=True)

    picked: list[dict] = []
    authors: dict[str, int] = {}
    seen: set[str] = set()
    excluded_authors: set[str] = set()
    for name in args.exclude_set:
        for it in json.loads((HERE / name / "manifest.json").read_text(encoding="utf-8"))["items"]:
            seen.add(it["qiita_id"])
            excluded_authors.add(it["author"])
    tags = args.tags or TAGS
    for tag in tags:
        if len(picked) >= args.limit:
            break
        n_tag = 0
        try:
            items = search(tag, 1, token, args.min_stocks)
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR tag={tag}: {e}", file=sys.stderr)
            continue
        # ストック数の多い順に見る(検索結果は新しい順で返るため)
        items.sort(key=lambda x: x.get("stocks_count", 0), reverse=True)
        for it in items:
            if n_tag >= args.per_tag or len(picked) >= args.limit:
                break
            if it["id"] in seen:
                continue
            seen.add(it["id"])
            author = it["user"]["id"]
            if it["updated_at"][:10] >= CUTOFF or it["created_at"][:10] >= CUTOFF:
                continue
            if TRANSLATION_RE.search(it["title"]):
                continue
            if author in excluded_authors or authors.get(author, 0) >= MAX_PER_AUTHOR:
                continue
            body = it["body"]
            pc = prose_chars(body)
            if pc < MIN_PROSE_CHARS or pc > MAX_PROSE_CHARS:
                continue
            authors[author] = authors.get(author, 0) + 1
            n_tag += 1
            rec = {
                "id": f"qiita-{it['id']}",
                "source": "qiita",
                "qiita_id": it["id"],
                "url": it["url"],
                "title": it["title"],
                "author": author,
                "tag": tag,
                "tags": [t["name"] for t in it["tags"]],
                "created_at": it["created_at"],
                "updated_at": it["updated_at"],
                "stocks": it.get("stocks_count"),
                "likes": it.get("likes_count"),
                "prose_chars": pc,
                "chars_without_code": chars_without_code(body),
                "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            }
            fm = "---\n" + "".join(
                f"{k}: {json.dumps(v, ensure_ascii=False)}\n"
                for k, v in rec.items() if k != "body_sha256"
            ) + "genre: tech\n---\n\n"
            (human_dir / f"{rec['id']}.md").write_text(fm + body + "\n", encoding="utf-8")
            picked.append(rec)
            print(f"  + {rec['id']} [{tag}] {rec['title'][:40]} ({pc} prose chars)", file=sys.stderr)
        time.sleep(1)

    manifest = {
        "set": args.set,
        "collected_at": dt.datetime.now().isoformat(timespec="seconds"),
        "criteria": {
            "cutoff": CUTOFF,
            "min_stocks": args.min_stocks,
            "exclude_sets": args.exclude_set,
            "min_prose_chars": MIN_PROSE_CHARS,
            "max_prose_chars": MAX_PROSE_CHARS,
            "max_per_author": MAX_PER_AUTHOR,
            "per_tag": args.per_tag,
            "tags": tags,
            "exclude_title": TRANSLATION_RE.pattern,
        },
        "items": picked,
    }
    (set_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"collected {len(picked)} items -> {set_dir / 'manifest.json'}", file=sys.stderr)


if __name__ == "__main__":
    main()
