# /// script
# requires-python = ">=3.11"
# ///
"""corpus/mlm/gen_matched.py — AI 時代のモデル(B)の学習用に、A と話題・分野をそろえた AI の文章を作る。

F43: A と B の学習データの分野と話題がずれていると、差に「最近の業務・話題の語」が混ざる。
そこで B を、A と同じ話題で AI に書かせた文章だけで学習し直す。

プロンプト(どちらも「書く」条件。推敲させると AI 時代の語彙が入らない(F18 付近の S6 の結果)):
    qiita  AI 以前(2019〜2021年)の Qiita 記事のタイトル
           「「{title}」というタイトルで技術ブログの記事を書いて。本文は{chars}字程度で。」(S6 の title 条件と同じ)
    biz    LLM-jp 由来の AI 以前の業務寄りの文章(組織の発信・報道・行政・コラム・大学)の冒頭の数文を材料にする
           「次の内容を伝える{kind}を書いて。本文は{chars}字程度で。\\n\\n内容: {lead}」
書き手:
    claude  claude -p(claude-opus-5-5、effort low、個人設定を外す)
    codex   codex exec(gpt-6.1-sol、effort low、個人設定を外す)
    gemini  Gemini API の Batch モード(gemini-3.8-flash、thinking low)。システムプロンプトなし

段階:
    build   プロンプトを作る(corpus/private/mlm/gen/prompts-<tag>.json)
    run     書かせる(corpus/private/mlm/gen/<tag>/<engine>/<id>.md)。済んだものは飛ばす
    report  文字数と Gemini のトークン数(料金の見積り)を出す

使い方:
    uv run corpus/mlm/gen_matched.py build --tag trial --qiita 15 --biz 15
    uv run corpus/mlm/gen_matched.py run --tag trial [--engines claude codex gemini] [--all-engines]
    uv run corpus/mlm/gen_matched.py report --tag trial
"""
from __future__ import annotations

import argparse
import gzip
import json
import random
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "corpus"))
import generate as g  # noqa: E402

DATA = ROOT / "corpus/timeslice/qiita-aug/data"
GEN = ROOT / "corpus/private/mlm/gen"
QIITA_PROMPT = "「{title}」というタイトルで技術ブログの記事を書いて。本文は{chars}字程度で。"
BIZ_PROMPT = "次の内容を伝える{kind}を書いて。本文は{chars}字程度で。\n\n内容: {lead}"
KIND = {"組織の発信": "会社や団体のお知らせ", "報道・ビジネス誌": "記事", "行政": "自治体や官公庁のお知らせ",
        "コラム・解説": "解説記事", "大学・研究機関": "大学や研究機関のお知らせ"}
MODELS = {"claude": "opus", "codex": "gpt-6.1-sol", "gemini": "gemini-3.8-flash"}
API = "https://generativelanguage.googleapis.com/v1beta"
# 文書ごとの出どころ。ベンダー名だけでなく、モデル・effort・ハーネス(または API)と、その設定を残す
PROVENANCE = {
    "claude": {"vendor": "Anthropic", "model": "claude-opus-5-5", "model_arg": "opus", "effort": "low",
               "harness": "Claude Code (claude -p)",
               "settings": "--setting-sources project(ユーザー設定・ルール・プラグイン・hook を読まない)、"
                           "--disallowed-tools *、作業ディレクトリは空、"
                           "--append-system-prompt で「1往復のみの非対話バッチ。確認を求めず本文だけを出力」と追記。"
                           "それ以外は Claude Code 標準のシステムプロンプトのまま"},
    "codex": {"vendor": "OpenAI", "model": "gpt-6.1-sol", "model_arg": "gpt-6.1-sol", "effort": "low",
              "harness": "Codex CLI (codex exec)",
              "settings": "-c model_reasoning_effort=low、-c web_search=\"disabled\"、--sandbox read-only、"
                          "空の CODEX_HOME と HOME(個人設定・AGENTS.md を読まない)、"
                          "プロンプトの先頭に「1往復のみの非対話バッチ。確認を求めず本文だけを出力」を付ける。"
                          "それ以外は Codex 標準のシステムプロンプトのまま"},
    "gemini": {"vendor": "Google", "model": "gemini-3.8-flash", "model_arg": "gemini-3.8-flash", "effort": "low",
               "harness": "Gemini API v1beta Batch (models/gemini-3.8-flash:batchGenerateContent)",
               "settings": "generation_config.thinkingConfig.thinkingLevel=low、システムプロンプトなし、"
                           "非対話の指示も付けない(そのため冒頭に「承知いたしました」などの返事が付くことがある)"},
}


def harness_version(engine: str) -> str:
    import subprocess
    cmd = {"claude": ["claude", "--version"], "codex": ["codex", "--version"]}.get(engine)
    if not cmd:
        return "v1beta"
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def write_meta(tag: str, rows: list[dict]) -> None:
    import threading
    global _META_LOCK
    try:
        _META_LOCK
    except NameError:
        _META_LOCK = threading.Lock()
    with _META_LOCK, open(GEN / tag / "meta.jsonl", "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def meta_row(engine: str, p: dict, version: str, **extra) -> dict:
    pv = PROVENANCE[engine]
    return {"id": p["id"], "engine": engine, "src": p["src"], "type": p.get("type"), "vendor": pv["vendor"],
            "model": pv["model"], "effort": pv["effort"], "harness": pv["harness"], "harness_version": version,
            "settings": pv["settings"], "prompt": p["prompt"],
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **extra}
# 料金(Batch、2026年12月31日までの導入価格、100万トークンあたりドル)
PRICE_IN, PRICE_OUT = 0.375, 1.875


def clamp_chars(n: int) -> int:
    return max(1500, min(5000, round(n / 500) * 500))


def build(tag: str, n_qiita: int, n_biz: int, seed: int) -> None:
    rng = random.Random(seed)
    q = [json.loads(l) for y in (2019, 2020, 2021) for l in gzip.open(DATA / f"{y}.jsonl.gz", "rt", encoding="utf-8")]
    q = [d for d in q if d.get("prose_chars", 0) >= 1000 and d.get("title")]
    biz = [json.loads(l) for f in sorted((ROOT / "corpus/private/llmjp").glob("level0-*.scored.jsonl"))
           for l in open(f, encoding="utf-8")]
    biz = [d for d in biz if d["score"] >= 0.5 and d["type"] in KIND and len(d["text"]) >= 1000]
    # 既に使ったプロンプトの元と、検査用の文書(mlm_contrast.py prepare の tests.json)を除く
    used = {x["id"] for f in GEN.glob("prompts-*.json") if f.name != f"prompts-{tag}.json"
            for x in json.loads(f.read_text(encoding="utf-8"))}
    tests_path = ROOT / "corpus/private/mlm/tests.json"
    test_texts = {t for v in json.loads(tests_path.read_text(encoding="utf-8")).values() for t in v} if tests_path.exists() else set()
    q = [d for d in q if f"q-{d['id']}" not in used and d["body"] not in test_texts]
    biz = [d for d in biz if f"b-{d['docId']}" not in used and d["text"] not in test_texts]
    n_qiita, n_biz = min(n_qiita, len(q)), min(n_biz, len(biz))
    prompts = []
    for d in rng.sample(q, n_qiita):
        prompts.append({"id": f"q-{d['id']}", "src": "qiita",
                        "prompt": QIITA_PROMPT.format(title=d["title"], chars=clamp_chars(d["prose_chars"]))})
    for d in rng.sample(biz, n_biz):
        # メニューや見出しの残骸を避け、句点で終わる20字以上の行(地の文)から冒頭の3文を取る
        prose = [l.strip() for l in d["text"].split("\n") if re.fullmatch(r"[^#|/>＞]{20,}[。！？]", l.strip())]
        sents = [s for s in re.split(r"(?<=[。！？])", "".join(prose)) if len(s) >= 15]
        lead = "".join(sents[:3])[:300]
        if len(lead) < 60:
            continue
        prompts.append({"id": f"b-{d['docId']}", "src": "biz", "type": d["type"],
                        "prompt": BIZ_PROMPT.format(kind=KIND[d["type"]], chars=clamp_chars(len(d["text"])), lead=lead)})
    GEN.mkdir(parents=True, exist_ok=True)
    (GEN / f"prompts-{tag}.json").write_text(json.dumps(prompts, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(prompts)} 件のプロンプト")


def assign(prompts: list[dict], engines: list[str], all_engines: bool) -> list[tuple[str, dict]]:
    if all_engines:
        return [(e, p) for p in prompts for e in engines]
    return [(engines[i % len(engines)], p) for i, p in enumerate(prompts)]


def run_cli(jobs: list[tuple[str, dict]], tag: str, parallel: int) -> None:
    g.prepare_isolation()
    versions = {e: harness_version(e) for e in ("claude", "codex")}

    def work(job):
        i, (engine, p) = job
        out = GEN / tag / engine / f"{p['id']}.md"
        if out.exists():
            return
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            if engine == "claude":
                text = g.run_claude(p["prompt"], PROVENANCE["claude"]["model_arg"], PROVENANCE["claude"]["effort"])
            else:
                home = g.ISOLATION_DIR / f"codex-home-gen-{i % parallel}"
                home.mkdir(parents=True, exist_ok=True)
                (home / "auth.json").write_bytes((g.CODEX_HOME / "auth.json").read_bytes())
                text = g.run_codex(p["prompt"], PROVENANCE["codex"]["model_arg"], PROVENANCE["codex"]["effort"], codex_home=home)
            if len(text) > 300:
                out.write_text(text, encoding="utf-8")
                write_meta(tag, [meta_row(engine, p, versions[engine], chars=len(text))])
            print(f"  {engine} {p['id']} {len(text)} 字", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"  ERR {engine} {p['id']}: {e}", file=sys.stderr, flush=True)

    with ThreadPoolExecutor(parallel) as ex:
        list(ex.map(work, enumerate(jobs)))


def api(method: str, path: str, body: dict | None = None) -> dict:
    key = g.load_env_value("GEMINI_API_KEY")
    req = urllib.request.Request(f"{API}/{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"x-goog-api-key": key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def run_gemini_batch(prompts: list[dict], tag: str) -> None:
    out_dir = GEN / tag / "gemini"
    out_dir.mkdir(parents=True, exist_ok=True)
    state_path = GEN / tag / "gemini-batch.json"
    todo = [p for p in prompts if not (out_dir / f"{p['id']}.md").exists()]
    if state_path.exists():
        state = json.loads(state_path.read_text())
    elif todo:
        reqs = [{"request": {"contents": [{"role": "user", "parts": [{"text": p["prompt"]}]}],
                             "generation_config": {"thinkingConfig": {"thinkingLevel": PROVENANCE["gemini"]["effort"]}}},
                 "metadata": {"key": p["id"]}} for p in todo]
        res = api("POST", f"models/{PROVENANCE['gemini']['model_arg']}:batchGenerateContent",
                  {"batch": {"display_name": f"natural-japanese-{tag}", "input_config": {"requests": {"requests": reqs}}}})
        state = {"name": res["name"], "n": len(reqs)}
        state_path.write_text(json.dumps(state))
        print(f"Gemini バッチを作成: {state['name']}({len(reqs)} 件)", flush=True)
    else:
        return
    while True:
        st = api("GET", state["name"])
        s = st.get("metadata", {}).get("state", "")
        if st.get("done"):
            break
        print(f"  Gemini バッチ: {s}", flush=True)
        time.sleep(60)
    if s not in ("JOB_STATE_SUCCEEDED", "BATCH_STATE_SUCCEEDED"):
        print(f"Gemini バッチが失敗: {s} {st.get('error')}", file=sys.stderr)
        return
    usage = {"in": 0, "out": 0, "think": 0}
    inl = st.get("response", {}).get("inlinedResponses", [])
    if isinstance(inl, dict):  # {"inlinedResponses": [...]} の形で返ることがある
        inl = inl.get("inlinedResponses", [])
    (GEN / tag / "gemini-raw.json").write_text(json.dumps(st, ensure_ascii=False))
    for r in inl:
        key = r.get("metadata", {}).get("key")
        resp = r.get("response")
        if not key or not resp:
            continue
        parts = resp.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        text = "".join(pt.get("text", "") for pt in parts if not pt.get("thought"))
        um = resp.get("usageMetadata", {})
        usage["in"] += um.get("promptTokenCount", 0)
        usage["out"] += um.get("candidatesTokenCount", 0)
        usage["think"] += um.get("thoughtsTokenCount", 0)
        if len(text) > 300:
            (out_dir / f"{key}.md").write_text(text, encoding="utf-8")
            p = next((x for x in prompts if x["id"] == key), {"id": key, "src": key[0], "prompt": ""})
            write_meta(tag, [meta_row("gemini", p, "v1beta", chars=len(text), model_version=resp.get("modelVersion"),
                                      response_id=resp.get("responseId"), batch=state["name"],
                                      usage=um)])
    (GEN / tag / "gemini-usage.json").write_text(json.dumps(usage))
    state_path.unlink()
    print(f"Gemini 完了: {usage}", flush=True)


def report(tag: str) -> None:
    prompts = json.loads((GEN / f"prompts-{tag}.json").read_text(encoding="utf-8"))
    print(f"プロンプト {len(prompts)} 件(qiita {sum(p['src'] == 'qiita' for p in prompts)} / biz {sum(p['src'] == 'biz' for p in prompts)})")
    for e in MODELS:
        files = list((GEN / tag / e).glob("*.md")) if (GEN / tag / e).exists() else []
        chars = [len(f.read_text(encoding="utf-8")) for f in files]
        if chars:
            print(f"{e}: {len(files)} 本、平均 {sum(chars) // len(chars):,} 字、合計 {sum(chars):,} 字")
    up = GEN / tag / "gemini-usage.json"
    if up.exists():
        u = json.loads(up.read_text())
        files = list((GEN / tag / "gemini").glob("*.md"))
        chars = sum(len(f.read_text(encoding="utf-8")) for f in files)
        cost = u["in"] / 1e6 * PRICE_IN + (u["out"] + u["think"]) / 1e6 * PRICE_OUT
        print(f"Gemini トークン: 入力 {u['in']:,} / 出力 {u['out']:,} / 思考 {u['think']:,}、料金 ${cost:.3f}(Batch)")
        print(f"  1字あたりの出力トークン {u['out'] / max(chars, 1):.2f}、思考は出力の {u['think'] / max(u['out'], 1):.0%}")
        if chars:
            per_char = cost / chars
            for total in (3_300_000, 10_000_000):
                print(f"  Gemini で {total:,} 字書かせたときの見積り: ${per_char * total:.1f}")


def backfill(tag: str) -> None:
    """出どころの記録を付ける前に作った分(trial・prod)に、同じ設定で書いた記録を後から付ける。
    ハーネスのバージョンは記録時点(2026-10-10)のもの。Gemini は保存した応答から modelVersion を取る。"""
    prompts = {p["id"]: p for p in json.loads((GEN / f"prompts-{tag}.json").read_text(encoding="utf-8"))}
    meta_path = GEN / tag / "meta.jsonl"
    if meta_path.exists():
        meta_path.unlink()
    raw = {}
    rp = GEN / tag / "gemini-raw.json"
    if rp.exists():
        st = json.loads(rp.read_text(encoding="utf-8"))
        inl = st.get("response", {}).get("inlinedResponses", [])
        inl = inl.get("inlinedResponses", []) if isinstance(inl, dict) else inl
        raw = {r.get("metadata", {}).get("key"): (r.get("response") or {}) for r in inl}
        batch = st.get("name")
    rows = []
    for e in PROVENANCE:
        ver = harness_version(e) + "(2026-10-10 に確認)" if e != "gemini" else "v1beta"
        for f in sorted((GEN / tag / e).glob("*.md")):
            p = prompts.get(f.stem, {"id": f.stem, "src": "?", "prompt": ""})
            extra = {"chars": len(f.read_text(encoding="utf-8")), "backfilled": True}
            if e == "gemini" and f.stem in raw:
                extra.update(model_version=raw[f.stem].get("modelVersion"), response_id=raw[f.stem].get("responseId"),
                             batch=batch, usage=raw[f.stem].get("usageMetadata"))
            row = meta_row(e, p, ver, **extra)
            row["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(f.stat().st_mtime))
            rows.append(row)
    write_meta(tag, rows)
    print(f"{tag}: {len(rows)} 件の出どころを記録")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--tag", required=True)
    b.add_argument("--qiita", type=int, default=15)
    b.add_argument("--biz", type=int, default=15)
    b.add_argument("--seed", type=int, default=0)
    r = sub.add_parser("run")
    r.add_argument("--tag", required=True)
    r.add_argument("--engines", nargs="+", default=list(MODELS))
    r.add_argument("--all-engines", action="store_true", help="各プロンプトを全員に書かせる(既定は順番に割り当てる)")
    r.add_argument("--parallel", type=int, default=3)
    bf = sub.add_parser("backfill")
    bf.add_argument("--tag", required=True)
    rp = sub.add_parser("report")
    rp.add_argument("--tag", required=True)
    a = ap.parse_args()
    if a.cmd == "build":
        build(a.tag, a.qiita, a.biz, a.seed)
    elif a.cmd == "run":
        prompts = json.loads((GEN / f"prompts-{a.tag}.json").read_text(encoding="utf-8"))
        jobs = assign(prompts, a.engines, a.all_engines)
        gem = [p for e, p in jobs if e == "gemini"]
        cli = [(e, p) for e, p in jobs if e != "gemini"]
        with ThreadPoolExecutor(2) as ex:
            f1 = ex.submit(run_gemini_batch, gem, a.tag) if gem else None
            f2 = ex.submit(run_cli, cli, a.tag, a.parallel) if cli else None
            for f in (f1, f2):
                if f:
                    f.result()
        report(a.tag)
    elif a.cmd == "backfill":
        backfill(a.tag)
    else:
        report(a.tag)


if __name__ == "__main__":
    main()
