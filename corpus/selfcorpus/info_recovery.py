# /// script
# requires-python = ">=3.11"
# dependencies = ["sudachipy", "sudachidict-core"]
# ///
"""corpus/selfcorpus/info_recovery.py — 比喩の語の直し方を「読み手が何を受け取れるか」で比べる。

読者実験の代わりに、別系統の2モデルを読み手にして、文から「何が起きるのか」を言い直させる。
比べる直し方:
    A 元の文
    B ふだんの言葉に戻す(同じ意味の幅で。事実は足さない)
    C 具体化する(文脈に書かれた事実だけを使う。なければ B と同じく戻す)
測るもの:
    - 具体: 読み手の言い直しに、具体的な出来事や動作が入っているか(具体 / 曖昧 / 不明)
    - 一致: 2つの読み手の言い直しが同じ内容か(一致 / 一部 / 不一致)。わかりやすい文ほど読み手の解釈がそろう
    - 足した: B・C が文脈にない事実を足したか、意味が保たれたか

文の出どころ:
    self  作者の文書16本(corpus/private/skill-apply/*/before.md)のうち、比喩の語を含む文
    qiita 2026年の Qiita 記事から無作為に選んだ、比喩の語を含む文

途中結果は corpus/private/info-recovery/ に置き、やり直すと済んだ段階は飛ばす(コミットしない)。
集計は corpus/private/info-recovery/summary.md。

使い方: uv run corpus/selfcorpus/info_recovery.py [--qiita 60] [--parallel 3]
"""
from __future__ import annotations

import argparse
import gzip
import json
import random
import re
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "corpus"))
sys.path.insert(0, str(ROOT / "skills/natural-japanese/scripts"))
import generate as g  # noqa: E402
import lint  # noqa: E402

OUT = ROOT / "corpus/private/info-recovery"
SELF_DIR = ROOT / "corpus/private/skill-apply"
QIITA = ROOT / "corpus/timeslice/qiita-aug/data/2026.jsonl.gz"
WRITER = ("claude", "opus")
READERS = {"gpt-6-luna": "codex", "gemini-3.8-flash": "agy"}
JUDGE = "gpt-6-luna"
BATCH = 10
VARIANTS = ["A", "B", "C"]

REWRITE_PROMPT = {
    "B": """次の各文には、比喩として使われているかもしれない語(【】で示す)が入っています。
それぞれの文を、ふだんの言葉で書き直してください。

規則:
- 【】の語が比喩なら、同じ意味の幅のふだんの言葉に置き換える。意味を狭めたり広げたりしない
- 具体的な事実(誰が、何を、数値、条件、原因)を新しく足さない。文脈にも書かれていないことは書かない
- 語が持っていた含み(目立たないが確かにある、後悔、など)は、ふだんの言葉で残す
- 【】の語が文字どおりの意味や定着した専門用語なら、その文は変えない
- 文の働き(主張・説明・推量など)と言い切りの強さは変えない

次の JSON 配列だけを出力してください: [{{"id": "...", "text": "書き直した文"}}, ...]

{items}
""",
    "C": """次の各文には、比喩として使われているかもしれない語(【】で示す)が入っています。
それぞれの文を、何が起きるのかが読み手にわかるように書き直してください。

規則:
- 【】の語が比喩なら、その語が指している具体的な出来事・動作・変化を書く。主語と述語がつながる形にする
- 使ってよい事実は、文と「文脈」に書かれていることだけ。書かれていない事実(人名、数値、日付、原因、条件)は作らない
- 文脈から具体的に書けないときは、同じ意味の幅のふだんの言葉に置き換えるだけにする
- 【】の語が文字どおりの意味や定着した専門用語なら、その文は変えない
- 文の働き(主張・説明・推量など)と言い切りの強さは変えない

次の JSON 配列だけを出力してください: [{{"id": "...", "text": "書き直した文", "concrete": true/false(文脈の事実で具体化できたら true)}}, ...]

{items}
""",
}

READER_PROMPT = """次の各文を読んで、その文が伝えている内容を、比喩を使わずに具体的に言い直してください。
「何が/誰が」「何を」「どうなる・どうする」を書きます。前の文は参考です。
文から確定できない部分は推測で埋めず、「不明」と書いてください。1件あたり1〜2文で。

次の JSON 配列だけを出力してください: [{{"id": "...", "reading": "言い直し"}}, ...]

{items}
"""

JUDGE_PROMPT = """同じ文を2人の読み手が読み、それぞれ内容を言い直しました。各件について判定してください。

- r1, r2: それぞれの言い直しが、具体的な出来事・動作・変化を述べているか
  - 具体: 何が・誰が、どうなる・どうする、が特定できる
  - 曖昧: 言い換えただけで、何が起きるのかは特定できない
  - 不明: 読み取れないと答えている
- agree: 2人の言い直しが同じ内容を指しているか(一致 / 一部 / 不一致)

次の JSON 配列だけを出力してください: [{{"id": "...", "r1": "具体", "r2": "曖昧", "agree": "一致"}}, ...]

{items}
"""

FAITH_PROMPT = """元の文を書き直した版が、元の文と文脈に書かれていない事実を足していないか、意味を保っているかを判定してください。

- added: 元の文と文脈のどちらにも書かれていない事実(人名、数値、日付、原因、条件、動作の主体など)を足したか(true/false)
- added_what: 足したものがあれば短く(なければ空文字)
- meaning: 元の文の主張と言い切りの強さを保っているか(保っている / 一部変わった / 変わった)

次の JSON 配列だけを出力してください: [{{"id": "...", "added": false, "added_what": "", "meaning": "保っている"}}, ...]

{items}
"""


# ---------- 段階0: 文を集める ----------

def tokenize(raw: str):
    text = lint.mask_markdown_structure(raw)
    return lint.tokenize_sentences(
        lint.split_sentences_with_lines(lint.iter_lines_with_no(text), dict(lint.iter_lines_with_no(raw))))


def items_from(doc_id: str, raw: str, source: str, limit: int | None = None) -> list[dict]:
    toks = tokenize(raw)
    hits = lint._metaphor_hits(toks)
    out, seen = [], set()
    for ts, w in hits:
        if ts.line in seen:
            continue
        seen.add(ts.line)
        i = toks.index(ts)
        ctx = [t.raw_text.strip() for t in toks[max(0, i - 3):i]]
        s = ts.raw_text.strip()
        if not (15 <= len(s) <= 160):
            continue
        out.append({"id": f"{source}:{doc_id}:{ts.line}", "source": source, "word": w,
                    "sentence": s, "context": ctx})
    if limit is not None and len(out) > limit:
        out = random.Random(doc_id).sample(out, limit)
    return out


def collect(n_qiita: int) -> list[dict]:
    path = OUT / "items.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    items = []
    for d in sorted(SELF_DIR.iterdir()):
        if (d / "before.md").exists():
            items += items_from(d.name, (d / "before.md").read_text(encoding="utf-8"), "self")
    docs = [json.loads(l) for l in gzip.open(QIITA, "rt", encoding="utf-8")]
    rng = random.Random(1)
    rng.shuffle(docs)
    q = []
    for doc in docs:
        got = items_from(str(doc["id"]), doc["body"], "qiita", limit=1)
        q += got
        if len(q) >= n_qiita:
            break
    items += q
    OUT.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    return items


# ---------- 呼び出しの共通部分 ----------

def parse_array(out: str) -> list[dict]:
    m = re.search(r"\[.*\]", out, re.S)
    if not m:
        return []
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return []


def call(kind: str, model: str, prompt: str, worker: int) -> str:
    if kind == "claude":
        return g.run_claude(prompt, model, "low")
    if kind == "codex":
        home = g.ISOLATION_DIR / f"codex-home-ir-{worker}"
        home.mkdir(parents=True, exist_ok=True)
        (home / "auth.json").write_bytes((g.CODEX_HOME / "auth.json").read_bytes())
        return g.run_codex(prompt, model, "low", codex_home=home)
    return g.run_agy(prompt, model, "low")


def run_batches(name: str, kind: str, model: str, batches: list[tuple[str, list[str]]], parallel: int) -> dict[str, dict]:
    """batches: (プロンプト, そのバッチの id の一覧)。結果は id → 応答の辞書。ファイルに貯めて再開できる。"""
    path = OUT / f"{name}.jsonl"
    done: dict[str, dict] = {}
    if path.exists():
        for l in open(path, encoding="utf-8"):
            r = json.loads(l)
            done[r["id"]] = r
    todo = [(i, p, ids) for i, (p, ids) in enumerate(batches) if not all(x in done for x in ids)]

    def work(args):
        i, prompt, ids = args
        for _ in range(3):
            try:
                rows = parse_array(call(kind, model, prompt, i % parallel))
            except Exception as e:  # noqa: BLE001
                print(f"  ERR {name} batch {i}: {e}", file=sys.stderr)
                rows = []
            rows = [r for r in rows if isinstance(r, dict) and str(r.get("id")) in ids]
            if len(rows) >= len(ids) * 0.8:
                return rows
        return rows

    with open(path, "a", encoding="utf-8") as fp, ThreadPoolExecutor(parallel) as ex:
        for rows in ex.map(work, todo):
            for r in rows:
                r["id"] = str(r["id"])
                done[r["id"]] = r
                fp.write(json.dumps(r, ensure_ascii=False) + "\n")
            fp.flush()
            print(f"{name}: {len(done)} 件", flush=True)
    return done


def chunks(xs: list, n: int) -> list[list]:
    return [xs[i:i + n] for i in range(0, len(xs), n)]


def mark(sentence: str, word: str) -> str:
    """比喩の語(基本形)の最初の出現を【】で囲む。活用形は語幹の一致で探す。"""
    stem = word[:-1] if len(word) >= 2 and word[-1] in "うくぐすつぬぶむる" else word
    i = sentence.find(stem)
    if i < 0:
        return sentence
    j = i + len(stem)
    while j < len(sentence) and j - i < len(word) + 3 and re.match(r"[ぁ-ん]", sentence[j]) and sentence[j] not in "をがはにでとのもへやか":
        j += 1
    return sentence[:i] + "【" + sentence[i:j] + "】" + sentence[j:]


# ---------- 本体 ----------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--qiita", type=int, default=60)
    ap.add_argument("--parallel", type=int, default=3)
    a = ap.parse_args()
    g.prepare_isolation()
    items = collect(a.qiita)
    by_id = {it["id"]: it for it in items}
    print(f"文: {len(items)} 件({Counter(it['source'] for it in items)})", flush=True)

    # 段階1: 書き直し(B, C)
    texts: dict[str, dict[str, str]] = {v: {} for v in VARIANTS}
    texts["A"] = {it["id"]: it["sentence"] for it in items}
    concrete_flag: dict[str, bool] = {}
    for v in ("B", "C"):
        batches = []
        for ch in chunks(items, BATCH):
            body = "\n\n".join(
                f"### id: {it['id']}\n文脈: {' '.join(it['context']) or '(なし)'}\n文: {mark(it['sentence'], it['word'])}"
                for it in ch)
            batches.append((REWRITE_PROMPT[v].format(items=body), [it["id"] for it in ch]))
        res = run_batches(f"rewrite-{v}", WRITER[0], WRITER[1], batches, a.parallel)
        for i, r in res.items():
            if i in by_id and r.get("text"):
                texts[v][i] = r["text"].replace("【", "").replace("】", "")
                if v == "C":
                    concrete_flag[i] = bool(r.get("concrete"))

    # 段階2: 読み手(版ごとに別のバッチにして、同じ文の別の版が並ばないようにする)
    readings: dict[str, dict[str, dict[str, str]]] = {m: {} for m in READERS}
    for m, kind in READERS.items():
        for v in VARIANTS:
            ids = [i for i in by_id if i in texts[v]]
            batches = []
            for ch in chunks(ids, BATCH):
                body = "\n\n".join(
                    f"### id: {i}\n前の文: {(by_id[i]['context'] or ['(なし)'])[-1]}\n文: {texts[v][i]}" for i in ch)
                batches.append((READER_PROMPT.format(items=body), ch))
            res = run_batches(f"read-{m}-{v}", kind, m, batches, a.parallel)
            for i, r in res.items():
                readings[m].setdefault(v, {})[i] = r.get("reading", "")

    # 段階3: 判定(具体・一致)。版は伏せる
    m1, m2 = list(READERS)
    judged: dict[str, dict[str, dict]] = {}
    for v in VARIANTS:
        ids = [i for i in by_id if i in readings[m1].get(v, {}) and i in readings[m2].get(v, {})]
        batches = []
        for ch in chunks(ids, BATCH):
            body = "\n\n".join(
                f"### id: {i}\n文: {texts[v][i]}\n読み手1: {readings[m1][v][i]}\n読み手2: {readings[m2][v][i]}" for i in ch)
            batches.append((JUDGE_PROMPT.format(items=body), ch))
        judged[v] = run_batches(f"judge-{v}", "codex", JUDGE, batches, a.parallel)

    # 段階4: 足したか・意味を保ったか(B, C)
    faith: dict[str, dict[str, dict]] = {}
    for v in ("B", "C"):
        ids = [i for i in by_id if i in texts[v]]
        batches = []
        for ch in chunks(ids, BATCH):
            body = "\n\n".join(
                f"### id: {i}\n文脈: {' '.join(by_id[i]['context']) or '(なし)'}\n元の文: {by_id[i]['sentence']}\n書き直した版: {texts[v][i]}"
                for i in ch)
            batches.append((FAITH_PROMPT.format(items=body), ch))
        faith[v] = run_batches(f"faith-{v}", "codex", JUDGE, batches, a.parallel)

    summarize(items, texts, judged, faith, concrete_flag)


def summarize(items, texts, judged, faith, concrete_flag) -> None:
    out = ["# 情報回復テスト(比喩の語の直し方)", "",
           "A=元の文 / B=ふだんの言葉に戻す / C=文脈の事実で具体化(なければ戻す)。",
           f"読み手 {', '.join(READERS)}、判定 {JUDGE}。書き直し {WRITER[1]}。", ""]
    for src in ("self", "qiita", None):
        ids = [it["id"] for it in items if src is None or it["source"] == src]
        label = {"self": "作者の文書", "qiita": "Qiita 2026", None: "全体"}[src]
        out += [f"## {label}({len(ids)} 文)", "",
                "| 版 | 読み手の言い直しが具体(2人分の割合) | 2人の解釈が一致 | 一部一致 | 不一致 | 足した | 意味が変わった(一部含む) | 変えなかった文 |",
                "|---|---|---|---|---|---|---|---|"]
        for v in VARIANTS:
            js = [judged[v][i] for i in ids if i in judged[v]]
            conc = sum((j.get("r1") == "具体") + (j.get("r2") == "具体") for j in js) / max(2 * len(js), 1)
            ag = Counter(j.get("agree") for j in js)
            n = max(len(js), 1)
            if v == "A":
                add = mean = same = "—"
            else:
                fs = [faith[v][i] for i in ids if i in faith[v]]
                add = f"{sum(bool(f.get('added')) for f in fs) / max(len(fs), 1):.0%}"
                mean = f"{sum(f.get('meaning') in ('一部変わった', '変わった') for f in fs) / max(len(fs), 1):.0%}"
                same = f"{sum(texts[v].get(i) == texts['A'][i] for i in ids) / max(len(ids), 1):.0%}"
            out.append(f"| {v} | {conc:.0%} | {ag['一致'] / n:.0%} | {ag['一部'] / n:.0%} | {ag['不一致'] / n:.0%} | {add} | {mean} | {same} |")
        if src is not None:
            cf = [concrete_flag[i] for i in ids if i in concrete_flag]
            out += ["", f"C で文脈の事実から具体化できたと書き手が答えた割合: {sum(cf) / max(len(cf), 1):.0%}", ""]
    # 語ごと(A と B と C の「具体」の割合)
    out += ["## 語ごと(読み手の言い直しが具体の割合、A → B → C、全体)", "", "| 語 | 文 | A | B | C |", "|---|---|---|---|---|"]
    per = defaultdict(list)
    for it in items:
        per[it["word"]].append(it["id"])
    for w, ids in sorted(per.items(), key=lambda kv: -len(kv[1])):
        cells = []
        for v in VARIANTS:
            js = [judged[v][i] for i in ids if i in judged[v]]
            cells.append(f"{sum((j.get('r1') == '具体') + (j.get('r2') == '具体') for j in js) / max(2 * len(js), 1):.0%}")
        out.append(f"| {w} | {len(ids)} | " + " | ".join(cells) + " |")
    (OUT / "summary.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
