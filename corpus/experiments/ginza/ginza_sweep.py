# /// script
# requires-python = ">=3.10,<3.12"
# dependencies = [
#     "ginza>=5.2.0,<5.3.0",
#     "ja-ginza-electra>=5.2.0,<5.3.0",
#     "sudachipy>=0.6.8,<0.7.0",
#     "sudachidict-core>=20210802",
#     "click>=7.1.1,<9.0.0",
#     "typer>=0.3.0,<1.0.0",
#     "spacy>=3.4.4,<3.5.0",
#     "confection<0.1.1",
#     "numpy<2.0.0",
#     "thinc>=8.1.0,<8.2.0",
#     "setuptools<81",
# ]
# ///
"""ginza_sweep.py — GiNZA係り受け解析による2検出器候補をコーパスで検証する。

トラックA（nn-experiments-brief.md）: 主語述語距離（文節単位、GiNZAの本物の係り受けで
厳密に測る） と 修飾語順（長→短原則違反率）。

背景:
    corpus/reports/readability-sweep.md の候補2「主語述語距離」は sudachipy の
    形態素位置による近似（は/がの助詞位置 → 文末の実質述語形態素、の形態素数）で
    NO-GO（FP 3.6%, AI検出11.2%、ジャンルessayでFP超過）だった。本スクリプトは
    GiNZAのbunsetu API（文節認識）を使い、「主語文節」から「述語文節（文の係り受け
    ルート）」までの文節数距離を厳密に測って同じ判定規律で再検証する。

判定規律（プロジェクト共通、readability-sweep.py を踏襲）:
    FP基準集合 = human quality:high (web) + register:modern-colloquial-classic (aozora)。
    この集合でのFP率<5%を保ちつつAI検出率が意味のある水準(目安10%以上)の閾値を探す。
    なければ「検出器化不可」と結論する。

技術メモ:
    - ja_ginza_electra は spacy>=3.6 / confection>=0.1.1 の環境では
      `compound_splitter` の config validation (`split_mode: None` が `str` 型に
      合わずエラー) で動かない。ginza 5.2.0 が要求する `spacy<4.0,>=3.4.4` の
      下限に合わせて `spacy>=3.4.4,<3.5.0` + `confection<0.1.1` に明示的に
      ピン留めすることで解決する（本ディレクトリの smoke_electra.py で検証済み）。
    - Python 3.12+ では `tokenizers==0.13.3`（sudachitra の依存）にプリビルドwheelが
      無くRustビルドが必要になるため `requires-python = ">=3.10,<3.12"` で回避する。
    - sudachipy は ginza の要求範囲 `<0.7.0,>=0.6.2` 内で 0.6.11 に解決され、
      既存 lint.py の `sudachipy>=0.6.8` と衝突しない（同一仮想環境で共存可能、
      ただし本プロジェクトは lint.py とは別プロセス・別 uv 環境で実行するため
      実運用でも衝突リスクはない）。
    - 実行コスト: モデルロード(electra) 約2.7秒/プロセス起動、文書1本のparseは
      数十msオーダー。全コーパス(human_fp_base+ai 計150件強)を1プロセス内で
      逐次処理すればモデルロードは1回で済む。

使い方:
    uv run corpus/experiments/ginza/ginza_sweep.py
"""

from __future__ import annotations

import importlib.util
import json
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent.parent
CORPUS_DIR = REPO_ROOT / "corpus"
SOURCES_JSON = CORPUS_DIR / "sources.json"


def load_textcore():
    scripts_dir = REPO_ROOT / "skills" / "natural-japanese" / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    path = scripts_dir / "textcore.py"
    spec = importlib.util.spec_from_file_location("textcore", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"textcore.py をロードできません: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["textcore"] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# コーパス読み込み（readability-sweep.py の実装を流用）
# ---------------------------------------------------------------------------


@dataclass
class CorpusDoc:
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
            docs.append(
                CorpusDoc(
                    group="human_fp_base" if is_fp_base else "human_reference",
                    path=fpath,
                    text=text,
                    genre=src.get("genre"),
                    quality=src.get("quality"),
                    register=src.get("register"),
                )
            )
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
            docs.append(
                CorpusDoc(
                    group="human_fp_base" if is_fp_base else "human_reference",
                    path=fpath,
                    text=text,
                    genre=src.get("genre"),
                    quality=src.get("quality"),
                    register=src.get("register"),
                )
            )

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
                docs.append(
                    CorpusDoc(group="ai", path=fpath, text=text, genre=genre, ai_model=model_dir.name)
                )

    return docs


# ---------------------------------------------------------------------------
# GiNZA 解析
# ---------------------------------------------------------------------------


def get_nlp():
    import spacy

    return spacy.load("ja_ginza_electra")


def clean_sentences(tc, doc: CorpusDoc) -> list[str]:
    """textcore で Markdown 構造をマスクし、文分割した「本文」文のみを返す
    （見出し・リスト記号・コードブロック等のノイズを GiNZA に渡さないため）。
    生文（raw）を優先し、無ければマスク済みテキストにフォールバックする
    （readability-sweep.py の sentence_texts と同じ方針）。
    """
    masked = tc.mask_markdown_structure(doc.text)
    lines = tc.iter_lines_with_no(masked)
    raw_lines_by_no = dict(tc.iter_lines_with_no(doc.text))
    sentences = tc.split_sentences_with_lines(lines, raw_lines_by_no)
    out = []
    for _, masked_text, raw_text in sentences:
        t = raw_text if raw_text.strip() else masked_text
        t = t.strip()
        if t:
            out.append(t)
    return out


def bunsetu_head_token_indices(sent, bunsetu_head_list_fn) -> list[int]:
    return list(bunsetu_head_list_fn(sent))


def analyze_sentence(sent, ginza_mod) -> dict | None:
    """1文について GiNZA の bunsetu API から:
    - 主語文節→述語文節（sent.root）の文節距離
    - 修飾語順違反（同一被修飾文節に係る複数の前置修飾文節のうち、短い方が先に来る）
    を計算する。
    """
    bunsetu_spans_fn = ginza_mod.bunsetu_spans
    bunsetu_head_list_fn = ginza_mod.bunsetu_head_list

    spans = list(bunsetu_spans_fn(sent))
    if len(spans) < 2:
        return None
    head_token_idx = sorted(bunsetu_head_list_fn(sent))  # token index -> bunsetu head token index list, ascending
    # トークンindex -> 文節index の対応表
    tok_to_bunsetu = {}
    for bi, hti in enumerate(head_token_idx):
        span = None
        for s in spans:
            if s.root.i == hti:
                span = s
                break
        if span is None:
            continue
        for tok in span:
            tok_to_bunsetu[tok.i] = bi

    n_bunsetu = len(spans)

    # --- 主語述語距離 ---
    subj_distance = None
    root_bunsetu_idx = tok_to_bunsetu.get(sent.root.i)
    subj_candidates = [t for t in sent if t.dep_ in ("nsubj", "iobj") and t.i in tok_to_bunsetu]
    if subj_candidates and root_bunsetu_idx is not None:
        subj_tok = subj_candidates[0]
        subj_bunsetu_idx = tok_to_bunsetu[subj_tok.i]
        subj_distance = abs(root_bunsetu_idx - subj_bunsetu_idx)

    # --- 修飾語順違反 ---
    # 文節ごとに、それを直接修飾する「前方の」子文節（複数）を集め、
    # 文字長の昇順(短→長)で並んでいる箇所が「短→長」の禁止パターンに一致する数を数える。
    violations = 0
    modifier_groups = 0
    children_by_bunsetu: dict[int, list[tuple[int, int]]] = {}  # head_bunsetu_idx -> [(bunsetu_idx, char_len)]
    for bi, hti in enumerate(head_token_idx):
        head_tok = sent.doc[hti]
        for child in head_tok.children:
            if child.dep_ not in ("acl", "amod", "nmod", "advcl", "compound"):
                continue
            if child.i not in tok_to_bunsetu:
                continue
            child_bi = tok_to_bunsetu[child.i]
            if child_bi >= bi:
                continue  # 前方修飾のみ対象（日本語は基本左修飾）
            child_span = spans[child_bi]
            children_by_bunsetu.setdefault(bi, []).append((child_bi, len(child_span.text)))

    for bi, kids in children_by_bunsetu.items():
        if len(kids) < 2:
            continue
        kids_sorted_by_pos = sorted(kids, key=lambda x: x[0])
        modifier_groups += 1
        for (bi1, len1), (bi2, len2) in zip(kids_sorted_by_pos, kids_sorted_by_pos[1:]):
            # bi1 は bi2 より前に出現。「短→長」原則違反 = 前の方が短いのに後ろの方が長い
            if len1 < len2:
                violations += 1

    return {
        "n_bunsetu": n_bunsetu,
        "subj_distance": subj_distance,
        "modifier_groups": modifier_groups,
        "modifier_violations": violations,
    }


def analyze_doc(nlp, ginza_mod, sentences: list[str]) -> dict:
    subj_distances: list[int] = []
    total_modifier_groups = 0
    total_modifier_violations = 0
    n_sent_with_2plus_bunsetu = 0
    long_distance_count = 0  # 距離 >= 6 の文数（閾値スイープの一候補として粗く数える）

    # GiNZA自身の文分割ではなく、textcoreの文をそのまま1文書として渡すと
    # 文境界を誤認する恐れがあるため、1文ずつ nlp() する。
    for s in sentences:
        if not s:
            continue
        doc = nlp(s)
        for sent in doc.sents:
            result = analyze_sentence(sent, ginza_mod)
            if result is None:
                continue
            n_sent_with_2plus_bunsetu += 1
            if result["subj_distance"] is not None:
                subj_distances.append(result["subj_distance"])
                if result["subj_distance"] >= 6:
                    long_distance_count += 1
            total_modifier_groups += result["modifier_groups"]
            total_modifier_violations += result["modifier_violations"]

    mean_subj_distance = statistics.mean(subj_distances) if subj_distances else None
    p90_subj_distance = None
    if len(subj_distances) >= 5:
        p90_subj_distance = statistics.quantiles(subj_distances, n=10)[8]
    rate_long_distance = (
        long_distance_count / len(subj_distances) if subj_distances else None
    )
    modifier_violation_rate = (
        total_modifier_violations / total_modifier_groups if total_modifier_groups else None
    )

    return {
        "n_sentences_analyzed": n_sent_with_2plus_bunsetu,
        "n_subj_pred_pairs": len(subj_distances),
        "mean_subj_distance": mean_subj_distance,
        "p90_subj_distance": p90_subj_distance,
        "rate_long_distance_ge6": rate_long_distance,
        "n_modifier_groups": total_modifier_groups,
        "n_modifier_violations": total_modifier_violations,
        "modifier_violation_rate": modifier_violation_rate,
    }


# ---------------------------------------------------------------------------
# 閾値スイープ（readability-sweep.py と同じロジック）
# ---------------------------------------------------------------------------


def collect_values(results: list[tuple[CorpusDoc, dict]], group: str, key: str) -> list[float]:
    vals = []
    for doc, r in results:
        if doc.group != group:
            continue
        v = r.get(key)
        if v is not None:
            vals.append(v)
    return vals


def sweep_threshold(fp_vals: list[float], ai_vals: list[float], direction: str) -> dict:
    """direction: "high" (value>=threshold が検出) or "low" (value<=threshold が検出)"""
    candidates = sorted(set(fp_vals) | set(ai_vals))
    if not candidates:
        return {"best": None}
    best = None
    for th in candidates:
        if direction == "high":
            fp_rate = sum(1 for v in fp_vals if v >= th) / len(fp_vals) if fp_vals else 0.0
            ai_rate = sum(1 for v in ai_vals if v >= th) / len(ai_vals) if ai_vals else 0.0
        else:
            fp_rate = sum(1 for v in fp_vals if v <= th) / len(fp_vals) if fp_vals else 0.0
            ai_rate = sum(1 for v in ai_vals if v <= th) / len(ai_vals) if ai_vals else 0.0
        if fp_rate < 0.05:
            if best is None or ai_rate > best["ai_rate"]:
                best = {"threshold": th, "fp_rate": fp_rate, "ai_rate": ai_rate, "direction": direction}
    return {"best": best, "n_fp": len(fp_vals), "n_ai": len(ai_vals)}


def genre_breakdown(results: list[tuple[CorpusDoc, dict]], group: str, key: str, threshold: float | None, direction: str) -> dict:
    by_genre: dict[str, list[float]] = {}
    for doc, r in results:
        if doc.group != group:
            continue
        v = r.get(key)
        if v is None:
            continue
        by_genre.setdefault(doc.genre or "unknown", []).append(v)
    out = {}
    for g, vals in by_genre.items():
        entry = {"n": len(vals), "mean": statistics.mean(vals)}
        if threshold is not None:
            if direction == "high":
                entry["fp_rate_at_threshold"] = sum(1 for v in vals if v >= threshold) / len(vals)
            else:
                entry["fp_rate_at_threshold"] = sum(1 for v in vals if v <= threshold) / len(vals)
        out[g] = entry
    return out


def model_breakdown(results: list[tuple[CorpusDoc, dict]], key: str, threshold: float | None, direction: str) -> dict:
    by_model: dict[str, list[float]] = {}
    for doc, r in results:
        if doc.group != "ai":
            continue
        v = r.get(key)
        if v is None:
            continue
        by_model.setdefault(doc.ai_model or "unknown", []).append(v)
    out = {}
    for m, vals in by_model.items():
        entry = {"n": len(vals), "mean": statistics.mean(vals)}
        if threshold is not None:
            if direction == "high":
                entry["detect_rate"] = sum(1 for v in vals if v >= threshold) / len(vals)
            else:
                entry["detect_rate"] = sum(1 for v in vals if v <= threshold) / len(vals)
        out[m] = entry
    return out


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main():
    tc = load_textcore()
    import ginza as ginza_mod  # noqa

    t0 = time.time()
    docs = load_corpus()
    print(f"[load_corpus] {len(docs)} docs ({time.time()-t0:.1f}s)", file=sys.stderr)

    fp_docs = [d for d in docs if d.group == "human_fp_base"]
    ref_docs = [d for d in docs if d.group == "human_reference"]
    ai_docs = [d for d in docs if d.group == "ai"]
    print(
        f"human_fp_base={len(fp_docs)} human_reference={len(ref_docs)} ai={len(ai_docs)}",
        file=sys.stderr,
    )

    t0 = time.time()
    nlp = get_nlp()
    print(f"[model load] {time.time()-t0:.1f}s", file=sys.stderr)

    results: list[tuple[CorpusDoc, dict]] = []
    target_docs = fp_docs + ref_docs + ai_docs
    t_start = time.time()
    for i, doc in enumerate(target_docs):
        sentences = clean_sentences(tc, doc)
        r = analyze_doc(nlp, ginza_mod, sentences)
        results.append((doc, r))
        if (i + 1) % 20 == 0:
            elapsed = time.time() - t_start
            print(f"  ...{i+1}/{len(target_docs)} docs ({elapsed:.1f}s elapsed)", file=sys.stderr)
    total_elapsed = time.time() - t_start
    print(f"[analyze all docs] {total_elapsed:.1f}s ({total_elapsed/len(target_docs):.2f}s/doc)", file=sys.stderr)

    # --- 生データをキャッシュ（再解析なしで方向違いのスイープ再検討ができるように） ---
    raw_cache = [
        {
            "group": doc.group,
            "genre": doc.genre,
            "ai_model": doc.ai_model,
            "path": str(doc.path.relative_to(REPO_ROOT)),
            **r,
        }
        for doc, r in results
    ]
    (SCRIPT_DIR / "ginza_raw_cache.json").write_text(
        json.dumps(raw_cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # --- スイープ対象指標 ---
    # 方向は事前に固定せず両方向(high/low)を試して良い方を採用する
    # （precedent: readability-sweep.py の候補2/3は "high" 仮説で設計したが、
    # 実際には human_fp_base の方が値が高く "low" 方向でしか弁別できなかった。
    # 本トラックでも同じ反転が起きうるため、決め打ちしない）。
    metrics = [
        ("mean_subj_distance", "auto", "主語述語距離(平均, 文節数)"),
        ("p90_subj_distance", "auto", "主語述語距離(p90, 文節数)"),
        ("rate_long_distance_ge6", "auto", "主語述語距離>=6の文の比率"),
        ("modifier_violation_rate", "auto", "修飾語順違反率(短→長禁止)"),
    ]

    report = {
        "corpus_sizes": {
            "human_fp_base": len(fp_docs),
            "human_reference": len(ref_docs),
            "ai": len(ai_docs),
        },
        "timing": {
            "model_load_s": None,
            "analyze_total_s": total_elapsed,
            "analyze_per_doc_s": total_elapsed / len(target_docs),
        },
        "metrics": {},
    }

    for key, direction, label in metrics:
        fp_vals = collect_values(results, "human_fp_base", key)
        ai_vals = collect_values(results, "ai", key)
        if direction == "auto":
            sweep_high = sweep_threshold(fp_vals, ai_vals, "high")
            sweep_low = sweep_threshold(fp_vals, ai_vals, "low")
            best_high = sweep_high.get("best")
            best_low = sweep_low.get("best")
            rate_high = best_high["ai_rate"] if best_high else -1
            rate_low = best_low["ai_rate"] if best_low else -1
            if rate_low > rate_high:
                sweep, direction = sweep_low, "low"
            else:
                sweep, direction = sweep_high, "high"
        else:
            sweep = sweep_threshold(fp_vals, ai_vals, direction)
        best = sweep.get("best")
        th = best["threshold"] if best else None
        genre_fp = genre_breakdown(results, "human_fp_base", key, th, direction)
        model_ai = model_breakdown(results, key, th, direction)
        report["metrics"][key] = {
            "label": label,
            "direction": direction,
            "n_fp": len(fp_vals),
            "n_ai": len(ai_vals),
            "fp_dist": {
                "mean": statistics.mean(fp_vals) if fp_vals else None,
                "median": statistics.median(fp_vals) if fp_vals else None,
                "min": min(fp_vals) if fp_vals else None,
                "max": max(fp_vals) if fp_vals else None,
            },
            "ai_dist": {
                "mean": statistics.mean(ai_vals) if ai_vals else None,
                "median": statistics.median(ai_vals) if ai_vals else None,
                "min": min(ai_vals) if ai_vals else None,
                "max": max(ai_vals) if ai_vals else None,
            },
            "best_threshold": best,
            "genre_breakdown_fp": genre_fp,
            "model_breakdown_ai": model_ai,
        }

    out_path = SCRIPT_DIR / "ginza_sweep_result.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[written] {out_path}", file=sys.stderr)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
