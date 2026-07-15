# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "sudachipy>=0.6.8",
#     "sudachidict-core>=20240409",
#     "sentence-transformers>=3.0.0",
#     "torch>=2.2.0",
#     "numpy",
# ]
# ///
"""embed_corpus.py — 文単位に分割したコーパス全文書を文埋め込みモデルでベクトル化し、
npz にキャッシュする（トラックB: 文埋め込みによる意味的反復・結束性検出 実験の第1段階）。

設計:
    - corpus/experiments/readability-sweep.py の load_corpus() と同じ sources.json 対応付けロジックを
      その場で再実装する（同スクリプトを import すると重い14候補メトリクス計算まで
      引きずられるため、コーパス読み込み部分だけ複製する）。
    - 文分割は scripts/textcore.py の mask_markdown_structure + iter_lines_with_no +
      split_sentences_with_lines をそのまま流用（既存 lint と同じ文単位定義で公平に比較するため）。
    - 埋め込みモデルは既定で cl-nagoya/ruri-v3-310m。HF ページの規約に従い、文書検索用途では
      "" (無接頭辞) をクエリ/ドキュメント両方に使う運用もあるが、Ruri v3 は
      "検索クエリ: " / "" のような用途別接頭辞を推奨。本実験は「同一文書内の文同士の類似度」を
      見るだけで検索ではないため、接頭辞なし（生文）でエンコードする
      （Ruri v3 系は用途接頭辞なしでも意味表現として利用可能、と confirmed via HF model card の
      "Sentence Similarity" ウィジェット例が接頭辞なしであることから採用）。
    - MPS が使えれば使う。無ければ CPU（フォールバック時はログに明記）。
    - 487文書 × 平均数十文の埋め込みは1回だけ計算し、doc単位で
      corpus/experiments/embedding/cache/<model_slug>/<doc_id>.npz に保存する
      （文リストと埋め込み行列のペア）。2回目以降の実行はキャッシュを再利用しスキップする。

使い方:
    uv run corpus/experiments/embedding/embed_corpus.py [--model cl-nagoya/ruri-v3-310m] [--limit N]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent.parent
CORPUS_DIR = REPO_ROOT / "corpus"
SOURCES_JSON = CORPUS_DIR / "sources.json"
CACHE_DIR = SCRIPT_DIR / "cache"

DEFAULT_MODEL = "cl-nagoya/ruri-v3-310m"


def load_textcore():
    scripts_dir = REPO_ROOT / "skills" / "natural-japanese" / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    spec = importlib.util.spec_from_file_location("textcore", scripts_dir / "textcore.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["textcore"] = mod
    spec.loader.exec_module(mod)
    return mod


@dataclass
class CorpusDoc:
    doc_id: str
    group: str  # "human_fp_base" | "human_reference" | "ai"
    path: Path
    text: str
    genre: str | None = None
    quality: str | None = None
    register: str | None = None
    ai_model: str | None = None
    char_count: int = field(init=False)

    def __post_init__(self) -> None:
        self.char_count = len(self.text)


def load_sources() -> list[dict]:
    return json.loads(SOURCES_JSON.read_text(encoding="utf-8"))


def load_corpus() -> list[CorpusDoc]:
    sources = load_sources()
    docs: list[CorpusDoc] = []
    for src in sources:
        if src["type"] == "aozora":
            fname = src["id"].removeprefix("aozora-") + ".txt"
            fpath = CORPUS_DIR / "human" / "aozora" / fname
            if not fpath.exists():
                continue
            text = fpath.read_text(encoding="utf-8")
            is_fp_base = src.get("register") == "modern-colloquial-classic"
            docs.append(CorpusDoc(
                doc_id=src["id"], group="human_fp_base" if is_fp_base else "human_reference",
                path=fpath, text=text, genre=src.get("genre"), quality=src.get("quality"),
                register=src.get("register"),
            ))
        elif src["type"] == "web":
            fpath = None
            for ext in (".md", ".txt"):
                cand = CORPUS_DIR / "human" / "web" / f"{src['id']}{ext}"
                if cand.exists():
                    fpath = cand
                    break
            if fpath is None:
                continue
            text = fpath.read_text(encoding="utf-8")
            is_fp_base = src.get("quality") == "high"
            docs.append(CorpusDoc(
                doc_id=src["id"], group="human_fp_base" if is_fp_base else "human_reference",
                path=fpath, text=text, genre=src.get("genre"), quality=src.get("quality"),
                register=src.get("register"),
            ))

    ai_dir = CORPUS_DIR / "ai"
    if ai_dir.exists():
        for model_dir in sorted(p for p in ai_dir.iterdir() if p.is_dir()):
            for fpath in sorted(list(model_dir.glob("*.md")) + list(model_dir.glob("*.txt"))):
                text = fpath.read_text(encoding="utf-8")
                if not text.strip():
                    continue
                genre = None
                stem = fpath.stem
                for g in ("blog", "tech", "business", "essay", "note"):
                    if stem.startswith(g):
                        genre = g
                        break
                doc_id = f"{model_dir.name}/{fpath.stem}"
                docs.append(CorpusDoc(
                    doc_id=doc_id, group="ai", path=fpath, text=text, genre=genre,
                    ai_model=model_dir.name,
                ))
    return docs


def doc_sentences(tc, doc: CorpusDoc) -> list[str]:
    masked = tc.mask_markdown_structure(doc.text)
    lines = tc.iter_lines_with_no(masked)
    raw_lines_by_no = dict(tc.iter_lines_with_no(doc.text))
    sentences = tc.split_sentences_with_lines(lines, raw_lines_by_no)
    out = []
    for _, masked_s, raw_s in sentences:
        s = raw_s.strip() if raw_s.strip() else masked_s.strip()
        if s:
            out.append(s)
    return out


def model_slug(model_name: str) -> str:
    return model_name.replace("/", "__")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--limit", type=int, default=None, help="デバッグ用: 先頭N文書のみ処理")
    ap.add_argument("--batch-size", type=int, default=32)
    args = ap.parse_args()

    tc = load_textcore()

    print(f"[1/3] コーパス読み込み中...", file=sys.stderr)
    docs = load_corpus()
    if args.limit:
        docs = docs[: args.limit]
    print(f"  {len(docs)} 文書", file=sys.stderr)

    slug = model_slug(args.model)
    out_dir = CACHE_DIR / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[2/3] モデル読み込み中: {args.model} (初回はHFから自動DL、~1GB級の可能性あり)...", file=sys.stderr)
    t0 = time.time()
    import torch
    from sentence_transformers import SentenceTransformer

    device = "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")
    print(f"  device={device}", file=sys.stderr)
    model = SentenceTransformer(args.model, device=device, trust_remote_code=True)
    print(f"  モデル読み込み完了 ({time.time()-t0:.1f}s)", file=sys.stderr)

    print("[3/3] 文埋め込み計算中（キャッシュ済みはスキップ）...", file=sys.stderr)
    import numpy as np

    t_embed_total = 0.0
    n_done = 0
    n_skipped = 0
    n_sentences_total = 0
    for i, doc in enumerate(docs):
        safe_id = doc.doc_id.replace("/", "__")
        out_path = out_dir / f"{safe_id}.npz"
        if out_path.exists():
            n_skipped += 1
            continue
        sentences = doc_sentences(tc, doc)
        if not sentences:
            continue
        t0 = time.time()
        embeddings = model.encode(
            sentences, batch_size=args.batch_size, convert_to_numpy=True, show_progress_bar=False,
            normalize_embeddings=True,
        )
        t_embed_total += time.time() - t0
        n_sentences_total += len(sentences)
        np.savez_compressed(
            out_path,
            embeddings=embeddings.astype("float32"),
            sentences=np.array(sentences, dtype=object),
            doc_id=doc.doc_id, group=doc.group, genre=doc.genre or "",
            ai_model=doc.ai_model or "", quality=doc.quality or "", register=doc.register or "",
        )
        n_done += 1
        if i % 20 == 0:
            print(f"  {i}/{len(docs)}  (計算済み={n_done}, スキップ={n_skipped}, 総文数={n_sentences_total})", file=sys.stderr)

    print(
        f"完了: 新規計算={n_done}文書, 既存キャッシュ再利用={n_skipped}文書, "
        f"総文数={n_sentences_total}, 埋め込み計算時間={t_embed_total:.1f}s, device={device}",
        file=sys.stderr,
    )
    print(f"キャッシュ先: {out_dir}", file=sys.stderr)


if __name__ == "__main__":
    main()
