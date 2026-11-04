# /// script
# dependencies = ["markdown"]
# ///
"""v2.0.0 のビジュアルリリースノート(critical-thinking の初出)を release-notes/index.html に生成する。
素材は release-notes/data/v2.0.0/<文書>/(スキルなしの Claude Code に書かせた架空の稟議書・提案資料・制度企画・障害報告書と、
run-v2.0.0.py で現行のスキルをかけた結果)。上司や顧客の役の返事は dev/ct-eval/runs/o11-*、指摘と確認事項の突き合わせは ov5/ov6、
欠陥を仕込んだ素材での計測は r46 系から読む。
  uv run release-notes/build-v2.0.0.py
"""
import json, re, html, sys
from collections import Counter
from pathlib import Path
import markdown

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from rn_style import CSS, JS, FONT, DOC_CSS  # noqa: E402

DATA = HERE / "data" / "v2.0.0"
RUNS = HERE.parent / "dev" / "ct-eval" / "runs"
OUT = HERE / "index.html"
VER = "2.0.0"
PREV = ("v1.6.1", "https://tkewowm1d6.artifactshare.link/")
OLDER = [("v1.6.0", "https://6c8j7oke3x.artifactshare.link/"), ("v1.5.2", "https://7ttv0opj3s.artifactshare.link/"),
         ("v1.5.0", "https://x3a7rghxqv.artifactshare.link/"), ("v1.4.0", "https://2aretj5195.artifactshare.link/")]

# ---------- 文書の読み込み ----------
def E(t): return html.escape(re.sub(r"\*\*|`", "", str(t)))
def nonspace(t): return len(re.sub(r"\s", "", t))
def fmt(n): return f"{n:,}"
def sections(t):
    out, cur, buf = [], "", []
    for line in t.splitlines():
        if re.match(r"^##\s", line):
            out.append((cur, "\n".join(buf))); cur, buf = line, []
        else: buf.append(line)
    out.append((cur, "\n".join(buf)))
    return out
def kind(h):
    if re.match(r"^##\s*(\d+[.．]?\s*)?(確認事項)", h): return "kak"
    if re.match(r"^##\s*(付録|別紙|出典|参考)", h): return "app"
    return "body"
def parts(t):
    d = {"body": 0, "app": 0, "kak": 0}
    for h, b in sections(t): d[kind(h)] += nonspace(h) + nonspace(b)
    return d
def parse_qa(qmd, amd):
    qs = re.findall(r"^\s*(\d+)[.．]\s+(.+?)(?=^\s*\d+[.．]\s+|\Z)", qmd, re.M | re.S)
    qs = [(int(n), re.sub(r"\s+", "", t.strip().split("\n\n")[0]).strip()) for n, t in qs]
    ans = {}
    for m in re.finditer(r"^\s*(\d+)[.．]\s*問い[:：](.+?)^\s*答え[:：]\s*(.+?)(?=^\s*\d+[.．]\s*問い[:：]|\Z)", amd, re.M | re.S):
        ans[int(m.group(1))] = re.sub(r"\s+", "", m.group(3)).strip()
    return [(n, q, ans.get(n, "")) for n, q in qs]
def parse_kakfile(t):
    """確認事項のファイルを「頼む中身を小さくする案」「先に答える問い」「そのほか」に分ける。"""
    first, rest, cur, shrink = [], [], None, ""
    m = re.search(r"\*\*頼む中身を小さくする案\*\*\s*[:：]\s*(.+)", t)
    if m: shrink = m.group(1).strip()
    for l in t.splitlines():
        if re.match(r"^##\s*頼む中身を小さくする案", l): cur = "shrink"; continue
        if re.match(r"^##\s*先に答える", l): cur = first; continue
        if re.match(r"^##\s*そのほか", l): cur = rest; continue
        if cur == "shrink":
            if l.strip(): shrink += ("" if not shrink else "") + l.strip()
            continue
        m = re.match(r"^\s*(?:[-*]|\d+[.．])\s+(.+)", l)
        if m and isinstance(cur, list): cur.append(m.group(1).strip())
    return shrink, first, rest
def count_items(report):
    """検査の報告の指摘の数: 太字の L1・S1 のような項目と、「細かいもの n 件」の n。"""
    n = len(re.findall(r"^\*\*[LSP]\d+", report, re.M))
    m = re.search(r"細かいもの\s*(\d+)\s*件", report)
    return n + (int(m.group(1)) if m else 0)
def load(name):
    d = DATA / name
    t = {k: (d / f).read_text() for k, f in [("before", "doc.md"), ("after", "doc-review.md"), ("redesign", "doc-redesign.md"), ("concise", "doc-concise.md"),
                                             ("logic", "report-logic.md"), ("somo", "report-somosomo.md"), ("plans_md", "plans.md"),
                                             ("q_md", "questions.md"), ("a_md", "answers.md"), ("kak_md", "doc-review.確認事項.md"), ("kakr_md", "doc-redesign.確認事項.md")]}
    t["P0"], t["P1"], t["P2"], t["P3"] = parts(t["before"]), parts(t["after"]), parts(t["redesign"]), parts(t["concise"])
    t["qa"] = parse_qa(t["q_md"], t["a_md"])
    t["shrink"], t["kak_first"], t["kak_rest"] = parse_kakfile(t["kak_md"])
    t["kak"] = t["kak_first"] + t["kak_rest"]
    assert len(t["qa"]) == 3 and all(a for _, _, a in t["qa"]), (name, t["qa"])
    assert t["shrink"] and len(t["kak_first"]) == 3, (name, t["shrink"][:40], len(t["kak_first"]))
    for k in ("after", "redesign", "concise"):
        assert "要確認" not in t[k] and "確認事項" not in "".join(h for h, _ in sections(t[k])), (name, k)
    assert t["P1"]["kak"] == 0 and t["P2"]["kak"] == 0 and t["P3"]["kak"] == 0, name
    return t

DOCSETS = [
    ("ringi", "稟議書", "営業部の12名で、議事録を作る AI ツールを6か月、上限60万円で試験導入したいという社内の申請。読むのは経営会議。", "経営者", "exec"),
    ("kikaku", "社内の制度企画", "人事企画が、内勤180名を対象に週1日の在宅勤務制度を来年4月から始めたいという企画。昨年の離職率12%を業界平均の8%に近づけたい(全社250名で、およそ10名の差)。読むのは経営会議。", "経営者", "exec"),
    ("teian", "コンサルの提案資料", "コンサルティング会社が食品卸の北都フーズに、営業支援システム(SFA)の導入支援(3か月の診断と6か月の導入支援、2,700万円)を提案する資料。読むのは先方の営業本部長と経営会議。", "提案を受け取る会社の役員", "customer"),
    ("postmortem", "障害報告書", "情報システム部の運用チームが、受注管理システムが1時間半止まった障害を、情報システム部長と営業本部長に報告する文書。", "報告を受け取る上司", "boss"),
]
SETS = {n: load(n) for n, *_ in DOCSETS}
DOC_LABEL = {k: l for k, l, *_ in DOCSETS}
READER = {k: r for k, _, _, r, _ in DOCSETS}
R0 = SETS["ringi"]
assert R0["P0"]["body"] == 3299, R0["P0"]

# ---------- 上司や顧客の役の返事(o11)と、指摘と確認事項の突き合わせ(ov5・ov6) ----------
def load_outcome(label, group):
    rs = json.loads((RUNS / label / "results.json").read_text())
    out = {}
    for ver in ("元", "一括", "端的"):
        xs = [r for r in rs if r["name"] == f"{group}:{ver}" and "exec" in r]
        if not xs: continue
        verdicts = Counter(r["exec"].get("verdict") for r in xs)
        objs = [(q.get("q"), q.get("kind", "")) for r in xs for q in r["exec"].get("questions", [])] + \
               [(x.get("r"), x.get("kind", "")) for r in xs for x in r["exec"].get("reasons", [])]
        out[ver] = dict(verdict=verdicts.most_common(1)[0][0], verdicts=dict(verdicts), n=len(xs),
                        objs=objs, per_run=len(objs) / len(xs), in_doc=sum(1 for _, k in objs if "文書" in k) / len(xs),
                        read=sum(r["exec"].get("chars_read", 0) or 0 for r in xs) / len(xs),
                        reply=xs[0]["exec"].get("reply", ""))
    return out
OUTC = {"ringi": load_outcome("o11-exec", "ringi"), "kikaku": load_outcome("o11-exec", "kikaku"),
        "teian": load_outcome("o11-customer", "teian"), "postmortem": load_outcome("o11-postmortem", "postmortem")}
def load_overlap(label, name):
    rs = json.loads((RUNS / label / "results.json").read_text())
    r = next(x for x in rs if x["name"] == name)
    c = Counter(it.get("match", "none") for it in r["items"])
    return dict(n=len(r["items"]), first=c["first"], other=c["other"], none=c["none"], items=r["items"])
OV = {"ringi": load_overlap("ov6-page", "ringi"), "kikaku": load_overlap("ov6-page", "kikaku"),
      "teian": load_overlap("ov6-page", "teian"), "postmortem": load_overlap("ov5-postmortem", "postmortem")}
OV_TOTAL = sum(v["n"] for v in OV.values()); OV_NONE = sum(v["none"] for v in OV.values()); OV_FIRST = sum(v["first"] for v in OV.values())
assert OV_NONE == 0, OV

# ---------- 欠陥を仕込んだ素材での計測(r46 系) ----------
def summary(label):
    p = RUNS / label / "summary.md"
    return p.read_text() if p.exists() else ""
def detect_stats(label):
    """logic・somosomo の安定検出と持ち込み、欠陥なしの文書の読み違い。"""
    s = summary(label)
    found = partial = missed = 0
    rows = 0
    for m in re.finditer(r"^\| (?!id |run )[^|]+ \| [^|]* \| (\d+) \| (\d+) \| (\d+) \| [o\-]", s, re.M):
        found += int(m.group(1)); partial += int(m.group(2)); missed += int(m.group(3)); rows += 1
    stable = [(int(a), int(b)) for a, b in re.findall(r"安定検出率\(任意を除く\): (\d+)/(\d+)", s)]
    crossing = sum(int(x) for x in re.findall(r"持ち込み (\d+)", s))
    false_clean = [int(x) for x in re.findall(r"欠陥なしの文書\(3 回\): 妥当 \d+, 読み違い (\d+)", s)]
    return dict(found=found, partial=partial, missed=missed, rows=rows, stable=stable, crossing=crossing, false_clean=false_clean)
def table_rows(label):
    """summary.md の run の行(| 1 | 1136→1135/1135 | ... |)をセルの並びにする。"""
    s = summary(label); out = []
    for m in re.finditer(r"^\| (\d+) \| (\d+)→(\d+)/(\d+) \|(.*)\|\s*$", s, re.M):
        cells = [c.strip() for c in m.group(5).split("|")]
        out.append(dict(before=int(m.group(2)), after=int(m.group(3)), cells=cells))
    return out
def rewrite_stats(label):
    rows = table_rows(label)
    # cells: 印, 経緯, 新しい語, fixed, deferred, remains, 妥当, 持ち込み, (主結論, 決裁事項, 背骨, 案, 縮小案)
    return dict(n=len(rows), not_longer=sum(1 for r in rows if r["after"] <= r["before"]),
                fixed=sum(int(r["cells"][3]) for r in rows), deferred=sum(int(r["cells"][4]) for r in rows),
                remains=sum(int(r["cells"][5]) for r in rows), crossing=sum(int(r["cells"][7]) for r in rows),
                shrink=sum(1 for r in rows if len(r["cells"]) > 12 and r["cells"][12] == "○"),
                kept=sum(1 for r in rows if len(r["cells"]) > 9 and r["cells"][8] == "○" and r["cells"][9] == "○"))
DET = detect_stats("r46")
R46 = {k: summary(k) for k in ("r46b", "r46c", "r46d", "r46e", "r46f")}
HAVE_R46 = all(R46.values()) and bool(DET["stable"])

# ---------- 部品 ----------
def EM(t):
    return html.escape(t).replace("&lt;em&gt;", "<em>").replace("&lt;/em&gt;", "</em>")
def quote(ln, t, cls=""):
    c = f' class="{cls}"' if cls else ""
    l = f'<span class="ln">行{ln}</span> ' if ln else ""
    return f'<blockquote{c}><p>{l}{EM(t)}</p></blockquote>'
ICON = '<svg aria-hidden="true" width="24" height="24" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" fill="#fff"/><path d="M12 15.2 6.8 10l1.06-1.06L12 13.08l4.14-4.14L17.2 10 12 15.2Z" fill="currentColor"/><circle cx="12" cy="12" r="10.5" stroke="currentColor" fill="none"/></svg>'
def disclosure(label, body):
    return f'<details class="dsc"><summary>{ICON}<span>{E(label)}</span></summary><div class="dsc-body">{body}</div></details>'
def chip(t, color="gray", fill=False):
    return f'<span class="chip" data-color="{color}"{" data-fill" if fill else ""}>{E(t)}</span>'
def _norm(t): return re.sub(r"[\s|*]", "", re.sub(r"<[^>]+>", "", t))
def tabs(prefix, labels, aria):
    return f'<ul class="dads-tab__list" role="tablist" aria-label="{E(aria)}">' + "".join(
        f'<li><button type="button" class="dads-tab__tab" role="tab" id="{prefix}-tab-{i+1}" aria-selected="{"true" if i == 0 else "false"}" aria-controls="{prefix}-panel-{i+1}" tabindex="{0 if i == 0 else -1}"><span>{E(l)}</span></button></li>'
        for i, l in enumerate(labels)) + '</ul>'
def panel(prefix, i, body):
    return f'<div class="dads-tab__panel" id="{prefix}-panel-{i}" role="tabpanel" aria-labelledby="{prefix}-tab-{i}" tabindex="0"{"" if i == 1 else " hidden"}>{body}</div>'
def tabset(prefix, aria, bodies):
    return f'<div class="dads-tab">{tabs(prefix, [l for _, l, *_ in DOCSETS], aria)}<div class="dads-tab__panels">{"".join(panel(prefix, i + 1, b) for i, b in enumerate(bodies))}</div></div>'
def V(v): return v.replace("聞きたい", "判断の前に質問あり")

KAK_TOTAL = sum(len(SETS[k]["kak"]) for k in SETS)
# ---------- ファーストビュー: 稟議書の1行だけ ----------
SHORT = {"ringi": "議事録を作る AI ツール(架空の製品、ミナトノート)を、営業部の12名で6か月試験導入したいという稟議書"}
def _find_obj(key, needle):
    for q, k in OUTC[key]["元"]["objs"]:
        if needle in q: return q
    raise AssertionError((key, needle))
HERO = dict(key="ringi", obj=_find_obj("ringi", "時間単価が空欄"), q=2, after="時間単価は、経理部が社内の試算に使う標準単価の1時間3,500円である。", after2="費用に見合うのは、打ち合わせの全件で使い、1件あたり約39分以上減った場合で、今ある参考値の30分では届かない。")
def hero_row():
    t = SETS[HERO["key"]]; n, q, ans = t["qa"][HERO["q"] - 1]
    for x in (HERO["after"], HERO["after2"]): assert _norm(x) in _norm(t["after"]), x[:20]
    return f'''<div class="cmp">
  <div><h4>{chip("経営者役の指摘")}</h4><p>{E(SHORT["ringi"])}を読んで。4.2 と 8.3 は稟議書の節番号です。</p><blockquote><p>{E(HERO["obj"])}</p></blockquote></div>
  <div><h4>{chip("スキルの問い(提出前)", "blue", True)}</h4><blockquote class="key"><p>{E(q)}</p></blockquote><p class="ans">{chip("書き手の答え", "blue")} {E(ans.split("。")[0] + "。")}</p></div>
  <div><h4>{chip("答えを入れた文", "green", True)}</h4><blockquote><p>{E(HERO["after"])}</p></blockquote><blockquote><p>{E(HERO["after2"])}</p></blockquote></div>
</div>'''

# ---------- 流れ図 ----------
N_LOGIC = count_items(R0["logic"]); N_SOMO = count_items(R0["somo"])
NODES = {
    "src": ("文書", ["AI が書いたまま"], "src", "このページの例は、スキルなしの Claude Code(Opus 5.5)に短い依頼文から書かせた架空の稟議書・制度企画・提案資料・障害報告書です。わざと穴を作らせたのではなく、書かせたままです。"),
    "logic": ("筋を見る", ["文書の中だけで", "矛盾・根拠のない主張・食い違い"], "k", f"文書の中だけで読み、矛盾、根拠のない主張、事実と推論の混在、挙げた項目の抜けや食い違いを、行番号つきの問いにします。文書の論理構造(主結論、決裁事項、制約、論点ごとの根拠と、その根拠が決裁に要るかどうか)を別ファイルに書き出し、次の検査や直しはこれをもとに進めます。検査の結果は報告にまとめます。"),
    "somo": ("前提を疑う", ["決裁者の立場で", "前提・他の選択肢・覆る条件"], "o", f"決裁者の立場で読み、前提は妥当か、課題の立て方は合っているか、他の選択肢と比べたか、何が起きたら結論が覆るか、誰が実行するかを問います。決裁事項(読む人に決めてもらうこと)を覆しうる問いを報告の先頭に置きます。"),
    "ask": ("書き手に3つだけ聞く", ["書き手にしか答えられないこと", "文書の中で答えが出ることは聞かない"], "q", "文書の中で答えが出るもの(矛盾、計算、根拠に比べて強すぎる言い切り)は聞かずに直します。書き手に聞くのは、文書にない事実や、決裁者に何を決めてもらうつもりか、のように書き手にしか答えられないことだけで、3つまでです。関連する確認は1問にまとめます。「分からない」と答えてもかまいません。"),
    "fix": ("直した文書", ["答えを本文に入れる", "残りの問いは別ファイルの確認事項に"], "k", "書き手の答えを、強めず弱めず、出どころを添えて本文に入れます。「分からない」だった箇所は仮定の形にします。残りの問いは別のファイル(稟議書.確認事項.md)に、先に答えるべき3件と「そのほか」に分けて出します。答えで決裁事項の前提が崩れたときは、決裁事項を小さくする案(例: 12名の承認ではなく、まず2週間の測定だけを頼む)を確認事項の先頭に短く書きます。直した文書に、直した箇所の印や確認事項の節は入れません。ただし、文書の2か所の値が食い違っていて書き手にしか決められないときは、本文に両方の値を残して「確認中」と書きます。頼み方:「稟議書.md を決裁者の目で見て直して」"),
    "re": ("組み直す", ["頼んだときだけ", "事実と決裁事項は保ち、論の組み立てを替える"], "k", "事実・数値・主結論・決裁事項は保ったまま、論の組み立てだけを替えます。構成案を3つ出し、そのうち1つは必ず決裁事項を小さくする案です。書き手がその案を選んだときだけ、決裁事項も変わります。頼み方:「構成から組み直して」"),
    "cc": ("もっと端的に・丁寧に", ["頼んだときだけ", "本編に残す根拠の量を変えて書き直す"], "k", "文章を削るのではなく、どの根拠まで本編に残すかを決めて書き直します。端的にするときは、主結論、各論点の主張と決裁に要る根拠、決裁事項と制約だけを本編に残し、裏づけと補足は付録に移します。事実・数値・事例は消しません。頼み方:「もっと端的に」「もっと丁寧に」"),
}
def flow_svg():
    W, H = 1000, 420
    def box(key, x, y, w, h):
        title, sub, cls, _ = NODES[key]
        t = f'<g class="node {cls}" data-node="{key}" role="button" tabindex="0" aria-pressed="false" aria-label="{E(title)}の説明を見る"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" class="bx"/>'
        t += f'<text x="{x+w/2}" y="{y+34}" class="bt" text-anchor="middle">{E(title)}</text>'
        for i, s in enumerate(sub):
            t += f'<text x="{x+w/2}" y="{y+58+i*20}" class="bs" text-anchor="middle">{E(s)}</text>'
        return t + '</g>'
    def arrow(x1, y1, x2, y2, dashed=False):
        mx = (x1 + x2) / 2
        return f'<path d="M{x1},{y1} C{mx},{y1} {mx},{y2} {x2},{y2}" class="ar{" dashed" if dashed else ""}" marker-end="url(#ah)"/>'
    s = f'<svg viewBox="0 0 {W} {H}" class="fig flow" role="group" aria-label="流れ:文書を2つの見方で検査し、書き手に3つだけ聞いて、答えを入れた文書を返す。頼めば組み直す、端的にする">'
    s += '<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#4d4d4d"/></marker></defs>'
    s += arrow(130, 210, 170, 140) + arrow(130, 210, 170, 280) + arrow(390, 140, 430, 210) + arrow(390, 280, 430, 210) + arrow(690, 210, 730, 80)
    s += arrow(690, 210, 730, 210, True) + arrow(690, 210, 730, 340, True)
    s += box("src", 10, 160, 120, 100) + box("logic", 170, 90, 220, 100) + box("somo", 170, 230, 220, 100)
    s += box("ask", 430, 160, 260, 100) + box("fix", 730, 30, 260, 100) + box("re", 730, 160, 260, 100) + box("cc", 730, 290, 260, 100)
    return s + '</svg>'
flow_list = "".join(f'<li>{disclosure(v[0], f"<p>{E(v[3])}</p>")}</li>' for v in NODES.values())
node_desc = "".join(f'<div class="nd" data-for="{k}" hidden><b>{E(v[0])}</b><p>{E(v[3])}</p></div>' for k, v in NODES.items())

# ---------- 4つの文書(1本につき、返事1文・3問・直った文1つ・小さくする案1行) ----------
PICKS = {
 "ringi": dict(title="空欄だった時間単価が入り、損益の分かれ目が本文に出た", q=2,
        before=[(62, "当社の営業担当者の時間単価:<em>【 】円(人事・経理部門に確認して記入)</em>")],
        after=[(33, "時間単価は、<em>経理部が社内の試算に使う標準単価の1時間3,500円</em>である。"), (29, "費用に見合うのは、打ち合わせの全件で使い、<em>1件あたり約39分以上減った場合</em>で、今ある参考値の30分では届かない。")],
        note="書き手が答えた単価と元の月額からスキルが損益の分かれ目を計算し、元の試算の30分では費用に見合わないことを本文に書いた。"),
 "kikaku": dict(title="「退職理由の上位」が、人数の内訳になった", q=1,
        before=[(25, "| 退職者アンケート | 「働き方の柔軟性のなさ」が<em>退職理由の上位</em> | — |")],
        after=[(27, "| 退職者アンケート | <em>回答者は22名</em>。「働き方の柔軟性のなさ」が退職理由の上位で、<em>挙げたのは9名（うち内勤7名）</em>。自由記述で在宅勤務に触れたのは4名 | — |")],
        note="対象は内勤180名で、辞めた人が対象の中にいるかは書き手にしか分からない。答えの数字がそのまま入った。"),
 "teian": dict(title="「実際に失注が起きています」の出どころが、本文に入った", q=1,
        before=[(33, "御社ではこの引き継ぎの場面で<em>実際に失注が起きています</em>。")],
        after=[(33, "<em>営業本部長からは、引き継ぎで2社を失ったとうかがっています。資料では確かめておらず、その2社の時期や理由もうかがっていません。</em>")],
        note="答えは「聞いただけで、資料では確かめていない」。答えのまま書いたので、提案の前提が聞いた話だと読む人に分かる。"),
 "postmortem": dict(title="共有で終わる報告が、2つの判断を頼む報告になった", q=2,
        before=[(8, "10月21日(火)の午前中、受注管理システムの Web 画面が1時間半ほど応答しなくなりました。アプリケーションサーバー(受注管理システムの処理を動かすサーバー)のメモリが上限に達したためで、サーバーを再起動し、11:50 ごろに復旧しました。")],
        after=[(8, "<em>決めていただきたいことが2つあります。再発防止の3つの方向でよいかと、受注検索の改修が障害の原因かどうかの調査に1週間かけてよいかです。</em>")],
        note="元の報告には読んだ人に何をしてほしいかがなかった。「共有で終わる文書だと読んだが合っているか」と聞き、答えが冒頭に入った。"),
}
for _k, _p in PICKS.items():
    _t = SETS[_k]
    for _ln, _q in _p["before"]: assert _norm(_q) in _norm(_t["before"]), (_k, "before", _ln)
    for _ln, _q in _p["after"]: assert _norm(_q) in _norm(_t["after"]), (_k, "after", _ln)
def doc_body(key):
    t = SETS[key]; o = OUTC[key]; ov = OV[key]; p = PICKS[key]
    qs = "".join(f'<li>{E(q)}{disclosure("書き手の答え", f"<p>{E(a)}</p>")}</li>' for n, q, a in t["qa"])
    verdict = f'{E(READER[key])}役の返事は、元の文書で{E(V(o["元"]["verdict"]))}、直した後で{E(V(o["一括"]["verdict"]))}。元の文書への指摘 {ov["n"]} 件(同じ文書を3回読ませた合計)は、すべてスキルの確認事項にありました。'
    ex_before = o["元"]["objs"][0][0]; ex_after = o["一括"]["objs"][0][0]
    examples = f'<div class="ba"><div><h5>元の文書への指摘の例</h5><blockquote><p>{E(ex_before)}</p></blockquote></div><div><h5>直した後への指摘の例</h5><blockquote><p>{E(ex_after)}</p></blockquote></div></div>'
    kak = f'<p class="p">行番号は元の文書の行です。</p><p class="p"><b>決裁事項を小さくする案</b> {E(t["shrink"])}</p><h4>先に答えるべき問い</h4><ol class="list">{"".join(f"<li>{E(x)}</li>" for x in t["kak_first"])}</ol><h4>そのほか {len(t["kak_rest"])} 件</h4><ul class="list">{"".join(f"<li>{E(x)}</li>" for x in t["kak_rest"])}</ul>'
    desc = dict((k, d) for k, _, d, *_ in DOCSETS)[key]
    nf2 = "。答えから計算した約39分などの値を除く" if key == "ringi" else ""
    return f'''<p class="p prose-max">{E(desc)}</p>
  <p class="p prose-max">{verdict}</p>
  {examples}
  <h4>スキルが書き手に聞いた3つ</h4>
  <ol class="list prose-max">{qs}</ol>
  <h4>{E(p["title"])}</h4>
  <div class="ba"><div><h5>元の文書</h5>{"".join(quote(*x) for x in p["before"])}</div><div><h5>直した後</h5>{"".join(quote(*x) for x in p["after"])}</div></div>
  <p class="p prose-max">{E(p["note"])}</p>
  <p class="p prose-max">本編の字数 {fmt(t["P0"]["body"])} から {fmt(t["P1"]["body"])}(付録 {fmt(t["P1"]["app"])})。AI が勝手に足した数値・固有名詞は 0 件(スクリプトで確認{nf2})。</p>
  {disclosure(f"別ファイルに出した確認事項 {len(t['kak'])} 件と、先頭の「決裁事項を小さくする案」", kak)}'''
docs_html = tabset("doc", "4つの文書", [doc_body(k) for k, *_ in DOCSETS])

# ---------- もっと端的に ----------
def bars_svg(rows, aria):
    mx = max(sum(p.values()) for _, p in rows)
    W = 1000; LBL = 150; BAR = W - LBL - 110; ROW = 46; H = ROW * len(rows) + 40
    s = f'<svg viewBox="0 0 {W} {H}" class="fig bars" role="img" aria-label="{E(aria)}">'
    for i, (name, p) in enumerate(rows):
        y = 10 + i * ROW
        s += f'<text x="0" y="{y+22}" class="ml">{E(name)}</text>'
        x = LBL
        for k, cls in (("body", "s-body"), ("app", "s-app")):
            w = BAR * p[k] / mx
            if w <= 0: continue
            s += f'<rect x="{x}" y="{y}" width="{max(0,w-2)}" height="30" class="{cls}"/>'
            if w > 70: s += f'<text x="{x+8}" y="{y+20}" class="bl {"inv" if cls=="s-body" else ""}">{fmt(p[k])}</text>'
            x += w
        s += f'<text x="{x+8}" y="{y+20}" class="mn">計 {fmt(sum(p.values()))}</text>'
    y = 10 + len(rows) * ROW + 6
    for j, (lab, cls) in enumerate((("本編(決裁者が読む)", "s-body"), ("付録", "s-app"))):
        x = LBL + j * 230
        s += f'<rect x="{x}" y="{y}" width="14" height="14" class="{cls}"/><text x="{x+20}" y="{y+12}" class="mn">{E(lab)}</text>'
    return s + '</svg>'
def _hname(h): return re.sub(r"^##\s*(?:\d+[.．]\s*)?", "", h).strip()
def heading_cols(t):
    before = [(_hname(h), nonspace(h) + nonspace(b)) for h, b in sections(t["before"]) if h]
    after = [(_hname(h), nonspace(h) + nonspace(b), kind(h)) for h, b in sections(t["concise"]) if h]
    def li(h, n): return f'<li>{E(h)} <span class="ln">{fmt(n)}字</span></li>'
    nb = sum(1 for *_, k in after if k == "body"); na = sum(1 for *_, k in after if k == "app")
    return f'<div class="keep"><div><h4>元の本編 {len(before)}節</h4><ol>{"".join(li(h, n) for h, n in before)}</ol></div><div><h4>端的にした本編 {nb}節</h4><ol>{"".join(li(h, n) for h, n, k in after if k == "body")}</ol><h4>付録 {na}節</h4><ul style="list-style:none;padding-left:0">{"".join(li(h, n) for h, n, k in after if k == "app")}</ul></div></div>'
def concise_body(key):
    t = SETS[key]
    return f'''<p class="p prose-max">本編は {fmt(t["P0"]["body"])} 字から {fmt(t["P3"]["body"])} 字(元の {t["P3"]["body"] / t["P0"]["body"]:.0%})になり、付録が {fmt(t["P3"]["app"])} 字付きました。</p>
  <div class="bars-wrap">{bars_svg([("元の文書", t["P0"]), ("端的にした後", t["P3"])], "元の文書と端的にした後の字数を、本編と付録に分けた棒")}</div>
  {disclosure("見出しは、こう分かれた", heading_cols(t))}'''
concise_html = tabset("cc", "端的にした4つの文書", [concise_body(k) for k, *_ in DOCSETS])

# ---------- 組み直す ----------
def _field(body, names):
    for n in names:
        m = re.search(r"^\s*-?\s*\*{0,2}" + n + r"\*{0,2}\s*[:：](.+)$", body, re.M)
        if m: return m.group(1).strip()
    return ""
def parse_plans(md):
    plans = []
    for m in re.finditer(r"^## (案[A-Z0-9０-９])\s*[:：]?\s*(.+?)$([\s\S]*?)(?=^## |\Z)", md, re.M):
        key, title, body = m.group(1), m.group(2).strip(), m.group(3)
        if re.match(r"^を?選んだ", title): continue
        shrink = "小さくする" in title or "縮め" in title[:12]
        chosen = bool(re.search(r"[(（](?:選んだ案|採用)[)）]", title))
        title = re.sub(r"\s*[(（](?:採用|選んだ案|書き手が選ぶ案)[)）]\s*", "", title).strip()
        title = re.sub(r"^頼む中身を(?:小さくする|保つ)案?\s*[:：]?\s*[(（]?", "", title).rstrip("）)")
        plans.append(dict(key=key, title=title.replace("背骨にする", "中心に置く").replace("背骨", "中心"), shrink=shrink, chosen=chosen, claim=_field(body, ["主張"])))
    tail = md[md.rindex("## 選んだ案"):] if "## 選んだ案" in md else md[md.rindex("を選んだ理由"):] if "を選んだ理由" in md else ""
    mm = re.search(r"(案[A-Z0-9０-９])", tail)
    chosen = mm.group(1) if mm else next((p["key"] for p in plans if p["chosen"]), None)
    return plans, chosen
def _clean(t):
    t = re.sub(r"[(（](?:[SLRP]S?\d[\d\-・/、SLRP\s]*|somosomo\s*[^)）]*|logic\s*[^)）]*)[)）]", "", t)
    return re.sub(r"\s{2,}", " ", t).replace("背骨", "中心").strip("、 ")
for _k, _t in SETS.items():
    _t["PLANS"], _t["CHOSEN"] = parse_plans(_t["plans_md"])
    assert len(_t["PLANS"]) == 3 and _t["CHOSEN"] and any(p["shrink"] for p in _t["PLANS"]), (_k, [p["key"] for p in _t["PLANS"]], _t["CHOSEN"])
def compute_moves(before_t, redesign_t, min_hits=2):
    new = [(_hname(h), b) for h, b in sections(redesign_t) if h and kind(h) != "kak"]
    out = {}
    for h, body in sections(before_t):
        if not h: continue
        text = re.sub(r"[|*\s]", "", "".join(l for l in body.splitlines() if l and not l.startswith("#")))
        hits = {}
        for i in range(0, max(1, len(text) - 14), 10):
            ch = text[i:i + 14]
            if len(ch) < 14: continue
            for nh, nb in new:
                if ch in re.sub(r"[|*\s]", "", nb): hits[nh] = hits.get(nh, 0) + 1
        out[_hname(h)] = [nh for nh, n in sorted(hits.items(), key=lambda x: -x[1]) if n >= min_hits]
    return out
def mapping_svg(t, moves):
    L = [(_hname(h), nonspace(h) + nonspace(b)) for h, b in sections(t["before"]) if h]
    R = [(_hname(h), nonspace(h) + nonspace(b), kind(h)) for h, b in sections(t["redesign"]) if h and kind(h) != "kak"]
    before_names = {h for h, _ in L}
    ROW = 34; TOP = 44; W = 1000; bw = 330; lx = 10; rx = W - bw - 10
    H = TOP + max(len(L), len(R)) * ROW + 20
    s = f'<svg viewBox="0 0 {W} {H}" class="fig map" role="img" aria-label="元の{len(L)}節が、組み直した後の本編と付録のどこへ移ったか">'
    nb_ = sum(1 for _, _, k in R if k == "body"); na_ = sum(1 for _, _, k in R if k == "app")
    s += f'<text x="{lx}" y="24" class="mh">元の本編 {len(L)}節 {fmt(t["P0"]["body"])}字</text>'
    s += f'<text x="{rx}" y="24" class="mh">組み直した後 本編{nb_}節 {fmt(t["P2"]["body"])}字 + 付録{na_}節 {fmt(t["P2"]["app"])}字</text>'
    ly = {}; ry = {}
    for i, (h, n) in enumerate(L):
        y = TOP + i * ROW; ly[h] = y + ROW / 2
        s += f'<g class="src" data-src="{i}" tabindex="0" role="img" aria-label="{E(h)}の行き先を強調"><rect x="{lx}" y="{y+3}" width="{bw}" height="{ROW-6}" rx="4" class="mr"/>'
        s += f'<text x="{lx+10}" y="{y+ROW/2+5}" class="ml">{E(h)}</text><text x="{lx+bw-10}" y="{y+ROW/2+5}" class="mn" text-anchor="end">{fmt(n)}</text></g>'
    for i, (h, n, k) in enumerate(R):
        y = TOP + i * ROW; ry[h] = (y + ROW / 2, i)
        new = k == "body" and not any(h in b or b in h for b in before_names)
        s += f'<g class="dst" data-dst="{i}"><rect x="{rx}" y="{y+3}" width="{bw}" height="{ROW-6}" rx="4" class="mr {k}{" new" if new else ""}"/>'
        s += f'<text x="{rx+10}" y="{y+ROW/2+5}" class="ml">{E(h)}{"(新しい節)" if new else ""}</text><text x="{rx+bw-10}" y="{y+ROW/2+5}" class="mn" text-anchor="end">{fmt(n)}</text></g>'
    x1, x2 = lx + bw, rx
    for i, (h, _) in enumerate(L):
        for d in moves.get(h, []):
            if d not in ry: continue
            y1 = ly[h]; y2, j = ry[d]; mx = (x1 + x2) / 2
            s += f'<path d="M{x1},{y1} C{mx},{y1} {mx},{y2} {x2},{y2}" class="mv" data-src="{i}" data-dst="{j}"/>'
    return s + '</svg>'
def redesign_body(key):
    t = SETS[key]
    shrink = next(p for p in t["PLANS"] if p["shrink"]); chosen = next(p for p in t["PLANS"] if p["key"] == t["CHOSEN"])
    mapnote = '<p>節を押すと、移った先の節が強く表示されます。線は元の節の文の移り先です。</p>'
    return f'''<p class="p prose-max">{chip("決裁事項を小さくする案", "blue", True)} <b>{E(shrink["title"])}</b></p><blockquote class="key"><p>{E(_clean(shrink["claim"]))}</p></blockquote>
  <p class="p prose-max">{chip("この案で書いた", "gray")} <b>{E(chosen["title"])}</b></p><blockquote><p>{E(_clean(chosen["claim"]))}</p></blockquote>
  <p class="p prose-max">本編は {fmt(t["P0"]["body"])} 字から {fmt(t["P2"]["body"])} 字になり、付録が {fmt(t["P2"]["app"])} 字付きました。</p>
  {disclosure("元の節は、どこへ移ったか", mapnote + f'<div class="map-wrap">{mapping_svg(t, compute_moves(t["before"], t["redesign"]))}</div>')}'''
redesign_html = tabset("rd", "組み直した4つの文書", [redesign_body(k) for k, *_ in DOCSETS])

# ---------- 確かめたこと ----------
def checked_html():
    rows = "".join(f'<tr><th scope="row">{E(DOC_LABEL[k])}</th><td>{E(READER[k])}</td><td>{E(V(OUTC[k]["元"]["verdict"]))}</td><td>{E(V(OUTC[k]["一括"]["verdict"]))}</td><td>{OV[k]["n"]} 件のうち {OV[k]["n"] - OV[k]["none"]} 件</td></tr>' for k, *_ in DOCSETS)
    assert HAVE_R46, "r46 系の summary がない"
    rw = rewrite_stats("r46b"); rd = rewrite_stats("r46d")
    cc = summary("r46e"); cl = summary("r46f")
    rv_rows = table_rows("r46c")
    rv_q = sum(int(r["cells"][0]) for r in rv_rows); rv_q_doc = sum(int(r["cells"][1]) for r in rv_rows)
    uudd = [tuple(int(x) for x in r["cells"][2].split("/")) for r in rv_rows]
    rv_used = sum(u[0] for u in uudd); rv_dfd = sum(u[2] for u in uudd); rv_drop = sum(u[3] for u in uudd)
    cc_ok = [(int(a), int(b)) for a, b in re.findall(r"満たした run: (\d+)/(\d+)", cc + cl)]
    method = f'''<p>上司や顧客の役は別のセッションの Claude Opus 5.5 で、文書ごとに経営者、提案を受け取る会社の役員、報告を受け取る上司です。元の文書と直した後を、どちらが直した後かを知らせずに別々に渡し、返事(OK、条件つきOK、判断の前に質問あり、却下)と指摘を3回ずつ返させました。指摘と確認事項の照合は Claude Sonnet 5.5 が行い、判定が甘くないかは、テスト用の文書で、ある文書への指摘を無関係な別の文書の確認事項と照合した 42 組がすべて「ない」と判定されることで確認しました。</p>
<p>テスト用の文書は、スキルの作者が欠陥(表と本文で食い違う数字、根拠のない見込み、診断の後で決めるはずなのにもう書いてある製品名、報告日より後の「実施済み」など)を仕込んだ架空の文書5本と、ない欠陥を指摘しないかを見る欠陥のない4本です。問いが欠陥を捉えたか、直しが欠陥を解いたか、書き手の答えを改変せずに入れたかは Claude Sonnet 5.5 が判定しました。書かせたのも直したのも Claude Opus 5.5 で、人による確認はしていません。「構成から組み直して」は、4本を3回ずつの {rd['n']} 本すべてで決裁事項を小さくする案が出て、主結論と決裁事項は {rd['kept']} 本で元のままでした。組み直した本編が元より長くなった回が制度企画で2本(いずれも元の 2% 以内)ありました。「もっと端的に」「もっと丁寧に」は、主結論・決裁事項・数値が保たれ本編の各文が元の文書に対応することを条件に、{sum(a for a, _ in cc_ok)}/{sum(b for _, b in cc_ok)} 回で満たしました(満たさなかった1回は、丁寧にした本編が元の 110% を超えたもの)。回ごとの結果は <a href="https://github.com/coji/natural-japanese/blob/main/dev/ct-eval/RESULTS.md">dev/ct-eval/RESULTS.md</a> にあります。</p>'''
    return f'''<h3>上の4本で</h3>
  <div class="tbl-wrap"><table class="tbl"><thead><tr><th>文書</th><th>読む役</th><th>元の文書への返事</th><th>直した後への返事</th><th>元の文書への指摘のうち、確認事項にあったもの</th></tr></thead><tbody>{rows}</tbody></table></div>
  <p class="p prose-max">指摘 {OV_TOTAL} 件のうち、確認事項になかったものは {OV_NONE} 件。各文書の「先に答えるべき3件」(4本で12件)に入っていたのは {OV_FIRST} 件で、残りは「そのほか」にありました。</p>
  <h3>テスト用の文書で</h3>
  <p class="p prose-max">スキルの作者が欠陥を仕込んだ架空の文書5本と、欠陥のない4本に、このバージョンのスキルを3回ずつかけました。</p>
  <div class="stats">
    <div class="stat"><b>仕込んだ欠陥{DET["rows"]}か所を3回ずつ検査した計{DET["found"] + DET["partial"] + DET["missed"]}回のうち、問いにできた</b><div class="n">{DET["found"]}<small>回(見落とし {DET["missed"]})</small></div></div>
    <div class="stat"><b>検査が元にない事実を持ち込んだ</b><div class="n">{DET["crossing"]}<small>件。欠陥のない4本で、ない欠陥を指摘したのは {sum(DET["false_clean"])} 件</small></div></div>
    <div class="stat"><b>「決裁者の目で見て直す」が書き手に聞いた問い</b><div class="n">{rv_q}<small>件のうち、文書の中で答えが出るもの {rv_q_doc}。答えは改変せずに本文に入れ、落としたのは {rv_drop} 件</small></div></div>
    <div class="stat"><b>「指摘を反映して直して」が仕込んだ欠陥を直すか確認事項に回した</b><div class="n">{rw["fixed"] + rw["deferred"]}<small>回のうち {rw["fixed"] + rw["deferred"]}(残った {rw["remains"]})。本編が元より長くならなかったのは5本を3回ずつの {rw["n"]} 本中 {rw["not_longer"]} 本、元にない事実の持ち込みは {rw["crossing"]} 件</small></div></div>
  </div>
  {disclosure("測り方と注", method)}'''

# ---------- ページ ----------
DOCS = {k: markdown.markdown(v, extensions=["tables"]) for k, v in
        [("before", R0["before"]), ("after", R0["after"]), ("concise", R0["concise"]), ("redesign", R0["redesign"]), ("kak", R0["kak_md"]), ("logic", R0["logic"]), ("somosomo", R0["somo"])]}
TEMPLATES = "".join(f'<template id="t-{k}"><article>{v}</article></template>' for k, v in DOCS.items())
OLDER_LINKS = "".join(f'・<a href="{u}">{v}</a>' for v, u in OLDER)
page = f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>natural-japanese v{VER}:上司や顧客が聞いてくることを提出前に洗い出す critical-thinking を追加</title>
<meta name="description" content="稟議書・提案資料・企画・障害報告書を、出す前に読む人の目で検査し、書き手にしか答えられないことを3つだけ聞いて、答えを入れた文書を返す Agent Skill、critical-thinking を追加しました。">
{FONT}
<style>{CSS}</style>
</head>
<body>
<nav class="toc" aria-label="目次">
  <div class="toc-inner">
    <p class="toc-h">natural-japanese</p>
    <ol class="toc-list">
      <li><a href="#top">v{VER}</a></li>
      <li><a href="#how">何をするか</a></li>
      <li><a href="#examples">4つの文書の例</a></li>
      <li><a href="#concise">もっと端的に</a></li>
      <li><a href="#redesign">組み直す</a></li>
      <li><a href="#checked">確かめたこと</a></li>
      <li><a href="#limits">苦手なこと</a></li>
      <li><a href="#install">インストール</a></li>
      <li><a href="#read">文書を読む</a></li>
    </ol>
  </div>
</nav>

<header class="hero" id="top"><div class="wrap">
  <p class="ver"><small>v</small>{VER}</p>
  <p class="meta">natural-japanese 2026年11月</p>
  <h1>上司や顧客が聞いてくることを提出前に洗い出すスキル critical-thinking を追加しました</h1>
  <p class="p lead">AI に稟議書や提案資料を書かせると、丁寧で穴のなさそうな文書ができます。それでも上司や顧客は「<mark>この数字は誰の分か</mark>」「<mark>空欄のままで判断できない</mark>」と聞いてきます。critical-thinking(Claude Code や ChatGPT に入れて使う指示書)に「決裁者の目で見て直して」と頼むと、文書の中で答えが出ることは黙って直し、書き手にしか答えられないことを3つ聞いて答えを本文に入れ、残りの問いを別ファイルの確認事項に残します。</p>
  <p class="p lead">架空の文書4本を上司や顧客の役の AI に読ませて出た指摘 {OV_TOTAL} 件は、4本で計 {KAK_TOTAL} 件の確認事項の中にすべてありました。各文書の「先に答えるべき3件」(4本で12件)に入っていたのは {OV_FIRST} 件です。</p>
  {hero_row()}
</div></header>

<main>
<section class="block" id="how"><div class="wrap">
  <h2 data-chip>何をするか</h2>
  <p class="p prose-max">対象は、稟議書、企画書、提案資料、障害報告書のような、読んだ人に判断を求める文書です。同じリポジトリの natural-japanese は日本語の言い回しを直すスキルで、今回追加した critical-thinking は論の筋を見ます。箱を押すと説明が出ます。</p>
  <div class="flow-wrap">{flow_svg()}</div>
  <div class="nd-wrap">{node_desc}</div>
  <ol class="flow-list">{flow_list}</ol>
</div></section>

<section class="block" id="examples"><div class="wrap">
  <h2 data-chip>4つの文書で、どう変わったか</h2>
  <p class="p prose-max">どれもスキルなしの Claude Code(Opus 5.5)に書かせた架空の文書で、書かせたままです。「決裁者の目で見て直して」と頼み、スキルが聞いた3つに書き手が答えると、こう変わりました。書き手の答えは AI が返しました(スキルの作者が事実の一覧を先に書き、AI はそれだけを見て答え、一覧にないことは「分からない」と答えます)。上司や顧客の役の AI の返事(OK、条件つきOK、判断の前に質問あり、却下)は、4本とも元の時点で丁寧なのでほとんど変わりません。変わるのは指摘の中身で、元の文書への指摘は「空欄を埋めてから」「出どころを示して」が中心、直した後は「他の案と比べたか」のように書き手の判断を求めるものになります。文書ごとに1つずつ例を載せています。</p>
  {docs_html}
</div></section>

<section class="block" id="concise"><div class="wrap">
  <h2 data-chip>もっと端的に</h2>
  <p class="p prose-max">「もっと端的に」と頼むと、決裁者が読む本編に主結論・決裁に要る根拠・費用・決裁事項だけを残し、裏づけと補足を付録に移します。事実・数値・事例は消さないので、「もっと丁寧に」と頼めば戻せます。</p>
  {concise_html}
</div></section>

<section class="block" id="redesign"><div class="wrap">
  <h2 data-chip>構成から組み直す</h2>
  <p class="p prose-max">構成案を3つ出し、そのうち1つは必ず「決裁事項を小さくする案」です。選べるのは書き手だけです。この例ではスキルの作者は案を選ばず、スキルに任せたので、組み直した文書は決裁事項を変えない案で書いてあります。スキルには元の文書、検査の報告、書き手の答えを渡しました。3案のうち、小さくする案と書いた案の2つを載せています。</p>
  <div class="keep">
    <div><h4>保つ</h4><ul><li>事実と数値、出典</li><li>主結論と決裁事項</li><li>書き手の制約(開始時期、評価の時期、上限の額)</li></ul></div>
    <div><h4>替えてよい</h4><ul><li>先頭に何を置くか</li><li>本編と付録の切り分け</li><li>申請の立て方(効果を言い切るか、確かめる試験にするか、判断を何回に分けるか)</li></ul></div>
  </div>
  {redesign_html}
</div></section>

<section class="block" id="checked"><div class="wrap">
  <h2 data-chip>確かめたこと</h2>
  {checked_html()}
</div></section>

<section class="block" id="limits"><div class="wrap">
  <h2 data-chip>苦手なこと</h2>
  <ul class="list prose-max">
    <li>文書の外の事実は調べに行きません。他社の事例が本当かは、問いにして返すだけです。</li>
    <li>書き手に聞くのは3つまでなので、聞かなかった問いは確認事項に残ります。稟議書の例では{len(R0["kak"])}件で、直した後も経営者役は「何もしない案や、人数を絞る案と比べたか」と聞いてきました。</li>
    <li>書き手の答えが本文に入ると、申請の弱さがそのまま見えます。欠陥を仕込んだ稟議書では、答えを入れた文書を経営者役が「最良の前提でも効果が費用を下回る」と戻しました。スキルはそのとき、確認事項の先頭に決裁事項を小さくする案を書いています。</li>
    <li>検査は LLM の読みに頼るので、同じ文書をもう一度検査すると、指摘の数や言い方は揺れます。</li>
    <li>本物の上司や顧客では試していません。書き手の答え、直す側、読む役はすべて AI で、直す側と読む役は同じモデル(Claude Opus 5.5)です。</li>
  </ul>
</div></section>

<section class="block" id="install"><div class="wrap">
  <h2 data-chip>インストールと頼み方</h2>
  <p class="p prose-max">文書は Markdown かテキストのファイルで渡し、「稟議書.md を決裁者の目で見て直して」と頼みます。工程を分けるときは「筋が通っているか検査して」「前提から疑って」「指摘を反映して直して」「構成から組み直して」「もっと端的に」。</p>
  <div class="dads-tab">
    <ul class="dads-tab__list" role="tablist" aria-label="使う環境">
      <li><button type="button" class="dads-tab__tab" role="tab" id="env-tab-1" aria-selected="true" aria-controls="env-panel-1" tabindex="0"><span>Claude Code など</span></button></li>
      <li><button type="button" class="dads-tab__tab" role="tab" id="env-tab-2" aria-selected="false" aria-controls="env-panel-2" tabindex="-1"><span>claude.ai</span></button></li>
      <li><button type="button" class="dads-tab__tab" role="tab" id="env-tab-3" aria-selected="false" aria-controls="env-panel-3" tabindex="-1"><span>ChatGPT</span></button></li>
      <li><button type="button" class="dads-tab__tab" role="tab" id="env-tab-4" aria-selected="false" aria-controls="env-panel-4" tabindex="-1"><span>Gemini</span></button></li>
      <li><button type="button" class="dads-tab__tab" role="tab" id="env-tab-5" aria-selected="false" aria-controls="env-panel-5" tabindex="-1"><span>Microsoft 365 Copilot</span></button></li>
    </ul>
    <div class="dads-tab__panels">
      <div class="dads-tab__panel" id="env-panel-1" role="tabpanel" aria-labelledby="env-tab-1" tabindex="0">
        <p class="p">Claude Code、Codex、Cursor、Gemini CLI、GitHub Copilot など、Agent Skills に対応したコーディングエージェント。</p>
        <div class="cmd"><code id="cmd">npx skills add coji/natural-japanese</code><button type="button" data-copy="cmd">コピー</button></div>
        <p class="p">このコマンドで natural-japanese と critical-thinking の両方が入ります。critical-thinking は uv と Python がなくても動きます。</p>
      </div>
      <div class="dads-tab__panel" id="env-panel-2" role="tabpanel" aria-labelledby="env-tab-2" tabindex="0" hidden>
        <ol class="steps">
          <li><a href="https://github.com/coji/natural-japanese/releases/latest/download/critical-thinking.zip">critical-thinking.zip</a> をダウンロードする</li>
          <li>「カスタマイズ」→「スキル」→「+」→「スキルをアップロード」で zip を選ぶ</li>
          <li>文書を貼るか添付して、「この稟議書を決裁者の目で見て直して」と頼む</li>
        </ol>
      </div>
      <div class="dads-tab__panel" id="env-panel-3" role="tabpanel" aria-labelledby="env-tab-3" tabindex="0" hidden>
        <p class="p">ChatGPT Business、Enterprise、Edu。管理者がスキルのアップロードを許可している必要があります。</p>
        <ol class="steps"><li><a href="https://github.com/coji/natural-japanese/releases/latest/download/critical-thinking.zip">critical-thinking.zip</a> をダウンロードする</li><li>「スキル」→「作成」→「コンピューターからアップロード」で zip を選ぶ</li><li>文書を添付して頼む</li></ol>
      </div>
      <div class="dads-tab__panel" id="env-panel-4" role="tabpanel" aria-labelledby="env-tab-4" tabindex="0" hidden>
        <p class="p">Gemini アプリ。2026年11月の時点で個人アカウントで使えます。</p>
        <ol class="steps"><li><a href="https://github.com/coji/natural-japanese/releases/latest/download/critical-thinking.zip">critical-thinking.zip</a> をダウンロードして展開する</li><li>「カスタマイズ」→「スキル」→「作成」から、SKILL.md を含むフォルダをアップロードする</li><li>文書を添付して頼む</li></ol>
      </div>
      <div class="dads-tab__panel" id="env-panel-5" role="tabpanel" aria-labelledby="env-tab-5" tabindex="0" hidden>
        <p class="p">Microsoft 365 Copilot の宣言型エージェントにスキルを足す機能は、2026年11月の時点でプレビューです。</p>
        <ol class="steps"><li>Agent Builder でエージェントを作り、スキルとして <a href="https://github.com/coji/natural-japanese/releases/latest/download/critical-thinking.zip">critical-thinking.zip</a> を追加する</li><li>そのエージェントに文書を渡して頼む</li></ol>
      </div>
    </div>
  </div>
</div></section>

<section class="block" id="read"><div class="wrap">
  <h2 data-chip>文書を読む</h2>
  <p class="p prose-max">架空の稟議書です。社名・人名・製品名は実在しません。4本の文書の全文は <a href="https://github.com/coji/natural-japanese/tree/main/release-notes/data/v2.0.0">リポジトリの release-notes/data/v2.0.0</a> にあります。</p>
  <div class="seg" role="group" aria-label="表示">
    <button type="button" data-m="side" aria-pressed="true">元 | 直した後</button>
    <button type="button" data-m="side3">元 | 端的にした後</button>
    <button type="button" data-m="side2">元 | 組み直した後</button>
    <button type="button" data-m="kak">別ファイルの確認事項</button>
    <button type="button" data-m="logic">筋を見る</button>
    <button type="button" data-m="somosomo">前提を疑う</button>
  </div>
  <label class="sync" id="syncbox"><input type="checkbox" id="sync" checked> スクロールを同期</label>
  <div class="viewer" id="viewer">
    <div class="pane" id="paneL"><p class="cap">元の稟議書</p><div class="doc" tabindex="0"></div></div>
    <div class="pane" id="paneR"><p class="cap">直した後</p><div class="doc" tabindex="0"></div></div>
  </div>
  {TEMPLATES}
</div></section>
</main>

<footer><div class="wrap">
  <p>これまでのリリースノート <a href="{PREV[1]}">{PREV[0]}</a>{OLDER_LINKS}</p>
  <p>見た目は、デジタル庁デザインシステムの <a href="https://github.com/digital-go-jp/design-system-example-components-html">HTML 実装例</a>(MIT)に基づきます。</p>
  <p><a href="https://github.com/coji/natural-japanese">github.com/coji/natural-japanese</a></p>
</div></footer>
<script>{JS}</script>
</body>
</html>"""
page = page.replace("(doc.md 行", "(行").replace("doc.md 行", "行").replace("doc-review.md", "直した後の文書").replace("doc.md", "元の文書").replace("直した後の文書 は", "直した後の文書は").replace("元の文書 の", "元の文書の")
OUT.write_text(page)
_txt = re.sub(r"<template[\s\S]*?</template>|<details[\s\S]*?</details>|<style[\s\S]*?</style>|<script[\s\S]*?</script>", "", page)
_visible = nonspace(re.sub(r"<[^>]+>", "", _txt))
print("ok", OUT, "visible chars", _visible, "ov", OV_TOTAL, OV_NONE, OV_FIRST)
