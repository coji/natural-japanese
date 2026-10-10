# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""corpus/timeslice/collect_qiita_timeslice.py — Qiita の時系列コーパス(H と W)を集める。

ロードマップ S1。外部調査(逆瀬川「Qiita 7万記事で見る生成AI以前・以後の文章の変化」)と
同じく、各年の8月に投稿された記事を Qiita API v2 で集める。1回の検索は1万件までなので、
1日単位に分けて取る。

除外基準(外部調査に合わせる):
    - スライドモードの記事
    - AI以前(2019〜2022年)の記事で、2022-11-30 以降に更新されたもの
    - 地の文(見出し・リスト・コード・引用・表を除いた本文)が300字未満
    - 日本語以外(地の文に占めるひらがな・カタカナが10%未満)

保存(本文は著作権があるため非コミット):
    data/{year}.jsonl.gz   1行1記事。本文、著者 ID、タグ、日時、ストック数など
    manifest-{year}.json   取得条件と件数(除外理由ごと)。コミットする

使い方:
    uv run corpus/timeslice/collect_qiita_timeslice.py --years 2026 --days 1-3   # 試走
    uv run corpus/timeslice/collect_qiita_timeslice.py --years 2019 2020 2021 2022 2023 2024 2025 2026
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "skills" / "natural-japanese" / "scripts"))
from textcore import mask_markdown_structure  # noqa: E402

API = "https://qiita.com/api/v2/items"
CUTOFF = "2022-11-30"
MIN_PROSE_CHARS = 300
MIN_KANA_RATIO = 0.10
OUT_DIR = HERE / "qiita-aug"
KANA_RE = re.compile(r"[ぁ-んァ-ヶー]")


def load_token() -> str:
    for line in (ROOT / "corpus" / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("QIITA_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("QIITA_TOKEN が corpus/.env にない")


def fetch(query: str, page: int, token: str) -> tuple[list[dict], int]:
    url = f"{API}?{urllib.parse.urlencode({'query': query, 'per_page': 100, 'page': page})}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "natural-japanese-corpus/1.0",
        "Authorization": f"Bearer {token}",
    })
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as res:
                remaining = int(res.headers.get("Rate-Remaining", "1000"))
                reset = int(res.headers.get("Rate-Reset", "0"))
                total = int(res.headers.get("Total-Count", "0"))
                items = json.loads(res.read().decode("utf-8"))
            if remaining < 5:
                wait = max(0, reset - int(time.time())) + 5
                print(f"  rate limit: {wait}s 待つ", file=sys.stderr)
                time.sleep(wait)
            return items, total
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                print("  rate limited; 10分待つ", file=sys.stderr)
                time.sleep(600)
                continue
            if e.code >= 500:
                time.sleep(10 * (attempt + 1))
                continue
            raise
        except urllib.error.URLError:
            time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"fetch failed: {query} page={page}")


def classify(it: dict, year: int) -> tuple[str | None, dict | None]:
    """除外理由(なければ None)と、保存するレコードを返す。"""
    if it.get("slide"):
        return "slide", None
    if year <= 2022 and it["updated_at"][:10] >= CUTOFF:
        return "updated_after_cutoff", None
    prose = re.sub(r"\s+", "", mask_markdown_structure(it["body"]))
    if len(prose) < MIN_PROSE_CHARS:
        return "short_prose", None
    if len(KANA_RE.findall(prose)) / len(prose) < MIN_KANA_RATIO:
        return "non_japanese", None
    return None, {
        "id": it["id"],
        "year": year,
        "title": it["title"],
        "author": it["user"]["id"],
        "tags": [t["name"] for t in it["tags"]],
        "created_at": it["created_at"],
        "updated_at": it["updated_at"],
        "likes": it.get("likes_count"),
        "stocks": it.get("stocks_count"),
        "prose_chars": len(prose),
        "body": it["body"],
    }


def parse_days(spec: str) -> list[int]:
    a, _, b = spec.partition("-")
    return list(range(int(a), int(b or a) + 1))


def collect_year(year: int, days: list[int], token: str) -> dict:
    OUT_DIR.joinpath("data").mkdir(parents=True, exist_ok=True)
    reasons: Counter = Counter()
    fetched = 0
    kept = 0
    seen: set[str] = set()
    out_path = OUT_DIR / "data" / f"{year}.jsonl.gz"
    with gzip.open(out_path, "wt", encoding="utf-8") as out:
        for day in days:
            start = dt.date(year, 8, day)
            end = start + dt.timedelta(days=1)
            query = f"created:>={start.isoformat()} created:<{end.isoformat()}"
            page = 1
            while True:
                items, total = fetch(query, page, token)
                for it in items:
                    if it["id"] in seen:
                        continue
                    seen.add(it["id"])
                    fetched += 1
                    reason, rec = classify(it, year)
                    if reason:
                        reasons[reason] += 1
                    else:
                        kept += 1
                        out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                if len(items) < 100 or page * 100 >= total:
                    break
                page += 1
            print(f"  {year}-08-{day:02d}: total={total} kept(累計)={kept}", file=sys.stderr)
    manifest = {
        "year": year,
        "month": 8,
        "days": [days[0], days[-1]],
        "collected_at": dt.datetime.now().isoformat(timespec="seconds"),
        "criteria": {
            "cutoff_for_pre_ai_updates": CUTOFF,
            "min_prose_chars": MIN_PROSE_CHARS,
            "min_kana_ratio": MIN_KANA_RATIO,
        },
        "fetched": fetched,
        "kept": kept,
        "excluded": dict(reasons),
    }
    (OUT_DIR / f"manifest-{year}.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Qiita の8月の記事を年ごとに集める")
    parser.add_argument("--years", nargs="+", type=int, required=True)
    parser.add_argument("--days", default="1-31", help="8月の日の範囲(例: 1-3)")
    args = parser.parse_args()
    token = load_token()
    for year in args.years:
        m = collect_year(year, parse_days(args.days), token)
        print(f"{year}: fetched={m['fetched']} kept={m['kept']} excluded={m['excluded']}", file=sys.stderr)


if __name__ == "__main__":
    main()
