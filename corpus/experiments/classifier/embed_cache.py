# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "sentence-transformers>=3.0",
#     "torch>=2.2",
#     "numpy",
# ]
# ///
"""embed_cache.py — corpus/ 全文書を文埋め込みモデルで文書ベクトル化してキャッシュする。

トラックC(教師あり分類器)専用。トラックBが並行で別キャッシュを作る可能性があるため、
このディレクトリ内 (corpus/experiments/classifier/cache/) に自前でキャッシュする。

モデル: cl-nagoya/ruri-v3-310m (embed-research.md 推奨の精度重視モデル)
文書埋め込み = 文分割 → 各文をモデルでエンコード → 平均(mean pooling)。
ruri-v3 は "検索: " 等のプレフィックス規約があるが、ここでは分類目的の生テキスト
表現が欲しいので接頭辞なし ("トピック: " なども付けない素の文エンコード) で統一する。

出力: cache/embeddings.npz (id, group, model_or_source, genre, vector)
       cache/meta.json (docごとのメタデータ一覧)
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent.parent
CORPUS_DIR = REPO_ROOT / "corpus"
CACHE_DIR = SCRIPT_DIR / "cache"
SCRIPTS_DIR = REPO_ROOT / "scripts"

sys.path.insert(0, str(SCRIPTS_DIR))

MODEL_NAME = "cl-nagoya/ruri-v3-310m"


def load_sources_map() -> dict:
    p = CORPUS_DIR / "sources.json"
    if not p.exists():
        return {}
    entries = json.loads(p.read_text(encoding="utf-8"))
    return {e["id"]: e for e in entries if "id" in e}


AI_GENRE_PREFIXES = ["blog", "business", "essay", "slide", "tech"]


def ai_genre_from_name(name: str) -> str:
    for pfx in AI_GENRE_PREFIXES:
        if name.startswith(pfx + "-"):
            return pfx
    return "unknown"


def collect_docs():
    """すべての対象文書を (doc_id, group, model_or_source, genre, quality, text) で列挙する。"""
    sources_map = load_sources_map()
    docs = []

    aozora_dir = CORPUS_DIR / "human" / "aozora"
    for p in sorted(aozora_dir.rglob("*.txt")) + sorted(aozora_dir.rglob("*.md")):
        text = p.read_text(encoding="utf-8", errors="ignore")
        if not text.strip():
            continue
        meta = sources_map.get(p.stem, {})
        docs.append(
            dict(
                doc_id=f"human_aozora/{p.stem}",
                group="human",
                model_or_source="aozora",
                genre=meta.get("genre", "essay"),
                quality="high" if meta.get("register") == "modern-colloquial-classic" else "other",
                path=str(p),
                text=text,
            )
        )

    web_dir = CORPUS_DIR / "human" / "web"
    for p in sorted(web_dir.rglob("*.md")) + sorted(web_dir.rglob("*.txt")):
        text = p.read_text(encoding="utf-8", errors="ignore")
        if not text.strip():
            continue
        meta = sources_map.get(p.stem, {})
        docs.append(
            dict(
                doc_id=f"human_web/{p.stem}",
                group="human",
                model_or_source="web",
                genre=meta.get("genre", "unknown"),
                quality=meta.get("quality", "unknown"),
                path=str(p),
                text=text,
            )
        )

    ai_dir = CORPUS_DIR / "ai"
    for model_dir in sorted(ai_dir.iterdir()):
        if not model_dir.is_dir():
            continue
        for p in sorted(model_dir.rglob("*.md")) + sorted(model_dir.rglob("*.txt")):
            text = p.read_text(encoding="utf-8", errors="ignore")
            if not text.strip():
                continue
            docs.append(
                dict(
                    doc_id=f"ai/{model_dir.name}/{p.stem}",
                    group="ai",
                    model_or_source=model_dir.name,
                    genre=ai_genre_from_name(p.stem),
                    quality="n/a",
                    path=str(p),
                    text=text,
                )
            )
    return docs


def embed_docs(docs: list[dict]) -> np.ndarray:
    import torch
    from sentence_transformers import SentenceTransformer

    import lint as lint_mod  # for mask_markdown_structure / split_sentences

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"[embed_cache] device={device}", file=sys.stderr)
    model = SentenceTransformer(MODEL_NAME, device=device)

    vectors = []
    t0 = time.time()
    for i, d in enumerate(docs):
        masked = lint_mod.mask_markdown_structure(d["text"])
        lines = lint_mod.iter_lines_with_no(masked)
        raw_lines_by_no = dict(lint_mod.iter_lines_with_no(d["text"]))
        sentences = lint_mod.split_sentences_with_lines(lines, raw_lines_by_no)
        # split_sentences_with_lines returns (line_no, masked_sentence, raw_sentence)
        sent_texts = [raw.strip() for (_no, _masked, raw) in sentences if raw.strip()]
        if not sent_texts:
            sent_texts = [d["text"][:500]]
        emb = model.encode(sent_texts, batch_size=32, show_progress_bar=False, convert_to_numpy=True)
        doc_vec = emb.mean(axis=0)
        vectors.append(doc_vec)
        if (i + 1) % 20 == 0 or (i + 1) == len(docs):
            elapsed = time.time() - t0
            print(f"[embed_cache] {i + 1}/{len(docs)} docs embedded ({elapsed:.1f}s elapsed)", file=sys.stderr)
    return np.vstack(vectors)


def main():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    docs = collect_docs()
    print(f"[embed_cache] collected {len(docs)} docs", file=sys.stderr)
    t0 = time.time()
    vectors = embed_docs(docs)
    elapsed = time.time() - t0
    print(f"[embed_cache] embedding took {elapsed:.1f}s total", file=sys.stderr)

    np.savez_compressed(CACHE_DIR / "embeddings.npz", vectors=vectors)
    meta = [{k: v for k, v in d.items() if k != "text"} for d in docs]
    (CACHE_DIR / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    (CACHE_DIR / "timing.json").write_text(
        json.dumps({"n_docs": len(docs), "embed_seconds": elapsed, "model": MODEL_NAME}, indent=2),
        encoding="utf-8",
    )
    print(f"[embed_cache] saved cache to {CACHE_DIR}", file=sys.stderr)


if __name__ == "__main__":
    main()
