# /// script
# requires-python = ">=3.11"
# ///
"""corpus/llmjp/label_sample.py — 絞り込んだ文書の一部に、LLM で種類と使いやすさのラベルを付ける。

URL の規則だけでは「説明的・実務的な文章か」を判断できなかった(その他が75%、メニューの残骸も多い)。
FineWeb-Edu と同じく、少数に LLM でラベルを付け、あとで軽い分類器に学習させて全件に広げる。
判定は codex の gpt-6-luna(個人設定を外した corpus/generate.py の run_codex)で、10件ずつまとめて行う。
本文は先頭と末尾のメニューなど短い行を切り落とし、先頭 MAX_CHARS 字だけを見せる。

出力: corpus/private/llmjp/labels.jsonl(本文つきの抜粋を含むのでコミットしない)。
      判定のプロンプトとモデルは corpus/llmjp/label_prompt.md に記録する(コミットする)

使い方: uv run corpus/llmjp/label_sample.py --n 30 --seed 1
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "corpus"))
import generate as g  # noqa: E402

PRIV = ROOT / "corpus/private/llmjp"
MODEL = "gpt-6-luna"
MAX_CHARS = 1500
BATCH = 10
GENRES = ["お知らせ", "報道記事", "報告・レポート", "解説・ハウツー", "手順・マニュアル", "意見・コラム",
          "体験談・日記", "レビュー・紹介", "広告・宣伝", "求人", "一覧・目次", "創作", "Q&A", "その他"]
PROMPT_VERSION = "v2"
PROMPT = """次の {n} 件の日本語の Web 文書を、1件ずつ判定してください。文書は先頭の一部だけです。

判定項目:
- genre: 次から1つ。{genres}
- usable: 「仕事や組織の立場で、読み手に何かを伝えるために書かれた、説明的・実務的な日本語の文章」の例として使えるか
  - 0: 使えない。日記・創作・広告・通販の商品ページ・一覧・目次・スパム・翻訳記事
  - 1: 一部なら使える。個人の趣味や感想のブログ、娯楽の紹介、宣伝色が強い記事、アフィリエイト目的の解説
  - 2: 使える。組織のお知らせや報告、仕事の内容を説明する記事、報道記事、専門家の解説
  - 3: 良い例。上の 2 のうち、構成と説明がよく整っていて、仕事の文書の手本になりうるもの
  - 個人の趣味・日記・感想は、文章が上手でも最大 1 にする
- translated: 外国語の記事を日本語に訳したもの(新聞の日本語版、海外記事の翻訳、機械翻訳など)なら true
- boilerplate: メニュー・パンくず・ボタン名などの残骸の多さ。0=ほぼない、1=少しある、2=多い
- spam: 検索エンジン向けの自動生成や、意味の通らない文の並びなら true

次の JSON 配列だけを出力してください(id は文書の番号)。
[{{"id": 1, "genre": "…", "usable": 0, "translated": false, "boilerplate": 0, "spam": false}}, ...]

{docs}
"""


def trim(text: str) -> str:
    """先頭と末尾の、メニューやパンくずなどの短い行を切り落とす。"""
    lines = text.split("\n")
    def is_prose(l: str) -> bool:
        return len(l.strip()) >= 20 and not re.fullmatch(r"[#>\s]*[\w\s/|>»・-]{0,40}", l.strip())
    start = next((i for i, l in enumerate(lines) if is_prose(l)), 0)
    end = len(lines) - next((i for i, l in enumerate(reversed(lines)) if is_prose(l)), 0)
    # 見出しは残す(直前の # 行)
    while start > 0 and lines[start - 1].lstrip().startswith("#"):
        start -= 1
    return "\n".join(lines[start:end]).strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--parallel", type=int, default=3)
    ap.add_argument("--out", default="labels.jsonl")
    a = ap.parse_args()
    rows = [json.loads(l) for f in sorted(PRIV.glob("level0-*.jsonl")) for l in open(f, encoding="utf-8")]
    rng = random.Random(a.seed)
    sample = rng.sample(rows, a.n)
    for i, r in enumerate(sample):
        r["trimmed"] = trim(r["text"])[:MAX_CHARS]
    batches = [sample[i:i + BATCH] for i in range(0, len(sample), BATCH)]
    g.prepare_isolation()

    def run(bi_batch):
        bi, batch = bi_batch
        docs = "\n\n".join(f"### 文書 {j + 1}\n{r['trimmed']}" for j, r in enumerate(batch))
        prompt = PROMPT.format(n=len(batch), genres="、".join(GENRES), docs=docs)
        home = g.ISOLATION_DIR / f"codex-home-label-{bi % a.parallel}"
        home.mkdir(parents=True, exist_ok=True)
        (home / "auth.json").write_bytes((g.CODEX_HOME / "auth.json").read_bytes())
        for _ in range(2):
            try:
                out = g.run_codex(prompt, MODEL, "low", codex_home=home)
                m = re.search(r"\[.*\]", out, re.S)
                labels = json.loads(m.group(0)) if m else []
                if len(labels) == len(batch):
                    return batch, labels
            except Exception as e:  # noqa: BLE001
                print(f"  ERR batch {bi}: {e}", file=sys.stderr)
        return batch, []

    PRIV.mkdir(parents=True, exist_ok=True)
    with open(PRIV / a.out, "a", encoding="utf-8") as fp, ThreadPoolExecutor(a.parallel) as ex:
        for batch, labels in ex.map(run, list(enumerate(batches))):
            for r, lab in zip(batch, labels):
                fp.write(json.dumps({"docId": r["docId"], "url": r["url"], "type_by_url": r["type"],
                                     "label": lab, "model": MODEL, "prompt_version": PROMPT_VERSION, "excerpt": r["trimmed"]}, ensure_ascii=False) + "\n")
            print(f"batch ok={bool(labels)} n={len(batch)}", flush=True)
    (HERE / "label_prompt.md").write_text(
        f"# ラベル付けのプロンプト({PROMPT_VERSION})\n\nモデル: {MODEL}(codex exec、effort low、個人設定を外す)\n"
        f"1回に {BATCH} 件、各文書は先頭と末尾の短い行を切り落とした先頭 {MAX_CHARS} 字。\n\n```\n{PROMPT}\n```\n",
        encoding="utf-8")


if __name__ == "__main__":
    main()
