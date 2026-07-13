# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "torch",
#     "transformers",
#     "sentencepiece",
#     "protobuf",
#     "sudachipy>=0.6.8",
#     "sudachidict-core>=20240409",
# ]
# ///
"""perplexity_sweep.py — トラックD「perplexity系AI検出」の実測実験。

背景:
    corpus/reports/research/embed-research.md §3 の事前調査では「見送りが妥当」と
    結論済み（最新LLM・パラフレーズへの精度崩壊が学術的に報告されており、
    natural-japanese の「FP厳格排除」方針と相性が悪い）。本スクリプトは
    自前コーパスでの実測値を残し、その判断を確定させる（反証が出れば歓迎）ことが目的。

手法:
    rinna/japanese-gpt2-medium（小型日本語GPT-2、3.36億パラメータ）で文書ごとの
    perplexity を計測する。文書は Markdown 構造をマスクし（scripts/textcore.py の
    mask_markdown_structure を流用）、先頭2000字に切って計算する
    （ブリーフの許可に基づくサンプリング。理由: GPT-2クラスでも長文の文単位
    perplexity 計算は文書によっては数秒〜十数秒かかるため、コーパス全体
    （human quality:high 69本 + AI 406本）を高速に走査する）。

    生の perplexity に加えて、文単位 perplexity の分散（burstiness的指標。
    人間文はAI文よりも文単位のperplexityのばらつきが大きいという仮説がある）も
    参考として計測する。

FP基準（このプロジェクトの確立ルール）:
    human quality:high の誤検知率 <5% を保ちつつ、AI側の検出率が意味のある水準
    （目安10%以上）になる閾値が存在するかを閾値スイープで探す。

使い方:
    uv run corpus/experiments/perplexity/perplexity_sweep.py
    （初回はrinna/japanese-gpt2-mediumのダウンロードで1GB弱のネットワークI/Oが発生）

出力:
    corpus/experiments/perplexity/ 配下に JSON（生データ）と Markdown（報告）を書く。
    このディレクトリは gitignore 済みでコミットしない。
"""

from __future__ import annotations

import importlib.util
import json
import math
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent.parent
CORPUS_DIR = REPO_ROOT / "corpus"
SCRIPTS_DIR = REPO_ROOT / "scripts"
SOURCES_JSON = CORPUS_DIR / "sources.json"
OUT_DIR = SCRIPT_DIR

MODEL_NAME = "rinna/japanese-gpt2-medium"
MAX_CHARS = 2000  # ブリーフの許可に基づく先頭切り出し

sys.path.insert(0, str(SCRIPTS_DIR))


def load_textcore():
    spec = importlib.util.spec_from_file_location("textcore", SCRIPTS_DIR / "textcore.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["textcore"] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# コーパス読み込み（scripts/calibrate.py の load_corpus() を踏襲した簡略版）
# ---------------------------------------------------------------------------


@dataclass
class Doc:
    bucket: str  # human_high / human_ordinary / human_aozora / ai:<model>
    genre: str
    model: str | None
    path: Path
    text: str


def _load_sources() -> list[dict]:
    if not SOURCES_JSON.exists():
        return []
    return json.loads(SOURCES_JSON.read_text(encoding="utf-8"))


def _genre_from_ai_filename(name: str) -> str:
    # corpus/ai/<model>/<genre>-....md
    for g in ("blog", "business", "essay", "slide", "tech"):
        if name.startswith(g + "-"):
            return g
    return "unknown"


def load_corpus() -> list[Doc]:
    docs: list[Doc] = []
    sources = _load_sources()
    by_id = {s["id"]: s for s in sources if isinstance(s, dict) and s.get("id")}

    # human/web
    web_dir = CORPUS_DIR / "human" / "web"
    for p in sorted(web_dir.rglob("*.md")) if web_dir.exists() else []:
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if not text.strip():
            continue
        meta = by_id.get(p.stem, {})
        quality = meta.get("quality")
        genre = meta.get("genre", "unknown")
        bucket = "human_high" if quality == "high" else "human_ordinary"
        docs.append(Doc(bucket=bucket, genre=genre, model=None, path=p, text=text))

    # human/aozora（quality フィールドが無いので register で high 相当を判定）
    aozora_dir = CORPUS_DIR / "human" / "aozora"
    for p in sorted(aozora_dir.rglob("*.txt")) if aozora_dir.exists() else []:
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if not text.strip():
            continue
        meta = by_id.get(p.stem, {})
        register = meta.get("register")
        bucket = "human_high" if register == "modern-colloquial-classic" else "human_ordinary"
        docs.append(Doc(bucket=bucket, genre="essay", model=None, path=p, text=text))

    # ai/<model>/*.md
    ai_dir = CORPUS_DIR / "ai"
    if ai_dir.exists():
        for model_dir in sorted(ai_dir.iterdir()):
            if not model_dir.is_dir():
                continue
            for p in sorted(model_dir.glob("*.md")):
                try:
                    text = p.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                if not text.strip():
                    continue
                genre = _genre_from_ai_filename(p.name)
                docs.append(Doc(bucket=f"ai:{model_dir.name}", genre=genre, model=model_dir.name, path=p, text=text))

    return docs


# ---------------------------------------------------------------------------
# perplexity 計算
# ---------------------------------------------------------------------------


def clean_text(tc_mod, raw_text: str) -> str:
    """Markdown構造をマスクし、空行を除去して先頭MAX_CHARSに切る。"""
    masked = tc_mod.mask_markdown_structure(raw_text)
    lines = [ln for ln in masked.split("\n") if ln.strip()]
    joined = "\n".join(lines)
    return joined[:MAX_CHARS]


@dataclass
class PplResult:
    doc: Doc
    char_count: int
    doc_ppl: float  # 文書全体を1系列として計算したperplexity
    sentence_ppls: list[float]  # 文単位（改行区切り近似）のperplexity
    sentence_ppl_std: float  # 文単位perplexityの標準偏差（burstiness的指標）
    elapsed_sec: float


def compute_perplexity(model, tok, device, text: str) -> tuple[float, list[float]]:
    """textのdoc-level perplexityと、行単位(改行区切り)perplexityのリストを返す。"""
    import torch

    def _ppl_of(s: str) -> float | None:
        s = s.strip()
        if not s:
            return None
        enc = tok(s, return_tensors="pt", truncation=True, max_length=1024).to(device)
        if enc["input_ids"].shape[1] < 2:
            return None
        with torch.no_grad():
            out = model(**enc, labels=enc["input_ids"])
        loss = out.loss.item()
        if math.isnan(loss) or math.isinf(loss):
            return None
        return math.exp(loss)

    doc_ppl = _ppl_of(text)
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    line_ppls = []
    for ln in lines:
        p = _ppl_of(ln)
        if p is not None and p < 1e6:
            line_ppls.append(p)
    return (doc_ppl if doc_ppl is not None else float("nan")), line_ppls


def main() -> None:
    import statistics

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tc_mod = load_textcore()

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"[perplexity_sweep] device = {device}")

    t_load0 = time.time()
    tok = AutoTokenizer.from_pretrained(MODEL_NAME, use_fast=False)
    model = AutoModelForCausalLM.from_pretrained(MODEL_NAME)
    model = model.to(device).eval()
    load_sec = time.time() - t_load0
    print(f"[perplexity_sweep] model load: {load_sec:.1f}s, params={sum(p.numel() for p in model.parameters()):,}")

    docs = load_corpus()
    print(f"[perplexity_sweep] corpus loaded: {len(docs)} docs")
    for bucket in sorted({d.bucket for d in docs}):
        n = sum(1 for d in docs if d.bucket == bucket)
        print(f"  {bucket}: {n}")

    results: list[PplResult] = []
    t_all0 = time.time()
    for i, d in enumerate(docs):
        t0 = time.time()
        text = clean_text(tc_mod, d.text)
        doc_ppl, line_ppls = compute_perplexity(model, tok, device, text)
        elapsed = time.time() - t0
        std = statistics.pstdev(line_ppls) if len(line_ppls) >= 2 else 0.0
        results.append(
            PplResult(
                doc=d,
                char_count=len(text),
                doc_ppl=doc_ppl,
                sentence_ppls=line_ppls,
                sentence_ppl_std=std,
                elapsed_sec=elapsed,
            )
        )
        if (i + 1) % 25 == 0 or (i + 1) == len(docs):
            print(f"  [{i + 1}/{len(docs)}] {d.bucket}/{d.path.name} ppl={doc_ppl:.1f} ({elapsed:.2f}s)")

    total_sec = time.time() - t_all0
    print(f"[perplexity_sweep] total compute: {total_sec:.1f}s ({total_sec / max(1, len(docs)):.2f}s/doc avg)")

    # ---- 保存: 生データ ----
    raw_path = OUT_DIR / "raw_results.json"
    raw_path.write_text(
        json.dumps(
            [
                {
                    "bucket": r.doc.bucket,
                    "genre": r.doc.genre,
                    "model": r.doc.model,
                    "path": str(r.doc.path.relative_to(REPO_ROOT)),
                    "char_count": r.char_count,
                    "doc_ppl": r.doc_ppl,
                    "sentence_ppl_std": r.sentence_ppl_std,
                    "n_sentences": len(r.sentence_ppls),
                    "elapsed_sec": r.elapsed_sec,
                }
                for r in results
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"[perplexity_sweep] raw results -> {raw_path}")

    meta = {
        "model_name": MODEL_NAME,
        "device": device,
        "load_sec": load_sec,
        "total_compute_sec": total_sec,
        "n_docs": len(docs),
        "max_chars": MAX_CHARS,
    }
    (OUT_DIR / "run_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
