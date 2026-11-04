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
    ("kikaku", "社内の制度企画", "人事企画が、内勤180名を対象に週1日の在宅勤務制度を来年4月から始めたいという企画。昨年の離職率12%を業界平均の8%に近づけたい(差はおよそ10名)。読むのは経営会議。", "経営者", "exec"),
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
    t = html.escape(t).replace("&lt;em&gt;", "<em>").replace("&lt;/em&gt;", "</em>")
    return t
def quote(ln, t):
    if ln is None: return f'<p class="gone">{EM(t)}</p>'
    return f'<blockquote><span class="ln">行{ln}</span><p>{EM(t)}</p></blockquote>'
ICON = '<svg aria-hidden="true" width="24" height="24" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" fill="#fff"/><path d="M12 15.2 6.8 10l1.06-1.06L12 13.08l4.14-4.14L17.2 10 12 15.2Z" fill="currentColor"/><circle cx="12" cy="12" r="10.5" stroke="currentColor" fill="none"/></svg>'
def disclosure(label, body, cls=""):
    return f'<details class="dsc {cls}"><summary>{ICON}<span>{E(label)}</span></summary><div class="dsc-body">{body}</div></details>'
def _norm(t): return re.sub(r"[\s|*]", "", re.sub(r"<[^>]+>", "", t))
def tabs(prefix, labels, aria):
    return f'<ul class="dads-tab__list" role="tablist" aria-label="{E(aria)}">' + "".join(
        f'<li><button type="button" class="dads-tab__tab" role="tab" id="{prefix}-tab-{i+1}" aria-selected="{"true" if i == 0 else "false"}" aria-controls="{prefix}-panel-{i+1}" tabindex="{0 if i == 0 else -1}"><span>{E(l)}</span></button></li>'
        for i, l in enumerate(labels)) + '</ul>'
def panel(prefix, i, body, cls="pick"):
    return f'<div class="dads-tab__panel {cls}" id="{prefix}-panel-{i}" role="tabpanel" aria-labelledby="{prefix}-tab-{i}" tabindex="0"{"" if i == 1 else " hidden"}>{body}</div>'

# ---------- ファーストビュー:上司や顧客の指摘 → スキルが先に聞いた問い → 答えを入れた文 ----------
# 指摘は o11 の役の出力から、問いは questions.md から、文は doc-review.md から。文は文書の文そのまま。
SHORT = {"ringi": "議事録を作る AI ツール(ミナトノート)を、営業部の12名で6か月試験導入したいという稟議書", "kikaku": "内勤180名に週1日の在宅勤務制度を作りたいという企画。退職理由の上位が「働き方の柔軟性のなさ」で、離職率12%を業界平均の8%に近づけたい", "postmortem": "受注管理システムが1時間半止まった障害の報告書。前日に反映した受注検索の改修が疑われている", "teian": "コンサルが食品卸に、営業支援システム(SFA)の導入支援を提案する資料"}
HERO_ROWS = [
    dict(key="ringi", obj="時間単価が空欄のままで、回収の判断も本導入・中止の基準も判定できない。", q=2,
         after=(33, "時間単価は、経理部が社内の試算に使う標準単価の1時間3,500円である。"),
         after2=(29, "費用に見合うのは、打ち合わせの全件で使い、1件あたり約39分以上減った場合で、今ある参考値の30分では届かない。")),
    dict(key="kikaku", obj="柔軟性を理由に辞めた人が年30名のうち何名かが書かれていない。", q=1,
         after=(27, "回答者は22名。「働き方の柔軟性のなさ」が退職理由の上位で、挙げたのは9名（うち内勤7名）。自由記述で在宅勤務に触れたのは4名")),
    dict(key="postmortem", obj="疑っている受注検索の改修は今も本番で動いているか。切り戻さないなら、再発したときの手当は何か。", q=1,
         after=(14, "改修は切り戻しておらず、本番に残っています。再起動後はメモリ使用量を1時間ごとに見ていて、10月28日の時点で再発はありません。")),
]
def _find_obj(key, needle):
    """役の指摘の中から、needle を含むものを1つ返す(文は役の出力そのまま)。"""
    for q, k in OUTC[key]["元"]["objs"]:
        if needle in q: return q
    raise AssertionError((key, needle))
HERO_OBJ = {"ringi": _find_obj("ringi", "時間単価が空欄"), "kikaku": _find_obj("kikaku", "何名"), "postmortem": _find_obj("postmortem", "本番")}
def hero_rows():
    out = []
    for r in HERO_ROWS:
        t = SETS[r["key"]]; n, q, ans = t["qa"][r["q"] - 1]
        for ln, txt in [r["after"]] + ([r["after2"]] if r.get("after2") else []):
            assert _norm(txt) in _norm(t["after"]), (r["key"], ln)
        after = f'<blockquote><p>{EM(r["after"][1])}</p></blockquote>' + (f'<blockquote><p><b>答えから計算した文</b> {EM(r["after2"][1])}</p></blockquote>' if r.get("after2") else "")
        out.append(f'''<div class="hero3">
  <div><h4>{E(READER[r["key"]])}役の指摘 <span class="tag tag-somo">{E(DOC_LABEL[r["key"]])}を読んで</span></h4><p class="legend" style="margin:0 0 8px">{E(SHORT[r["key"]])}</p><blockquote class="q-somo"><p>{E(HERO_OBJ[r["key"]])}</p></blockquote></div>
  <div class="arrow" aria-hidden="true"></div>
  <div><h4>スキルが書き手に聞いた問い <span class="tag tag-ask">提出前</span></h4><blockquote class="q-ask"><p>{E(q)}</p></blockquote><blockquote class="q-ans"><p><b>書き手の答え</b> {E(ans.split("。")[0] + "。")}{"" if ans.count("。") <= 1 else "(答えの続きは下の例に)"}</p></blockquote></div>
  <div class="arrow" aria-hidden="true"></div>
  <div><h4>答えを入れた文</h4>{after}</div>
</div>''')
    return "".join(out)

# ---------- 図:流れ(押すと説明が出る) ----------
N_LOGIC = count_items(R0["logic"]); N_SOMO = count_items(R0["somo"])
NODES = {
    "src": ("文書", ["AI が書いたまま"], "src", "このページの例は、スキルなしの Claude Code(Opus 5.5)に短い依頼文から書かせた架空の稟議書・制度企画・提案資料・障害報告書です。わざと穴を作らせたのではなく、書かせたままの文書です。どれも丁寧に書かれていて、障害報告書は原因が確定していないことを自分から書いています。"),
    "logic": ("筋を見る", ["文書の中だけで", "矛盾・根拠のない主張・食い違い"], "k", f"文書の中だけで読み、矛盾、根拠のない主張、事実と推論の混在、挙げた項目の抜けや食い違いを、行番号つきの問いにします。文書の論理構造(主結論、決裁事項、書き手が置いた制約、論点ごとの根拠と、その根拠が決裁に要るかどうか)を別ファイルに書き出し、次の検査や直しはこの書き出しをもとに進めます。稟議書の例では{N_LOGIC}件でした。"),
    "somo": ("前提を疑う", ["決裁者の立場で", "前提・他の選択肢・覆る条件"], "o", f"決裁者の立場で読み、決裁者が何を決める文書かを押さえたうえで、前提は妥当か、解こうとしている課題の立て方は合っているか、他の選択肢と比べたか、何が起きたら結論が覆るか、誰が実行するかを問います。決裁事項を覆しうる問いを報告の先頭に置きます。稟議書の例では{N_SOMO}件でした。"),
    "ask": ("書き手に3つだけ聞く", ["書き手にしか答えられないこと", "文書の中で答えが出ることは聞かない"], "q", "2つの検査の問いのうち、文書の中で答えが出るもの(矛盾、計算、言い切りの強さ、並べて挙げた項目どうしの食い違い)は聞かずに直します。書き手に聞くのは、文書にない事実、決裁者に何を決めてもらうつもりか、どこまで頼むか、のように書き手にしか答えられないことだけで、3つまでです。関連する確認は1問にまとめます。「分からない」という答えも答えです。"),
    "fix": ("直した文書", ["答えを本文に入れる", "残りの問いは別ファイルの確認事項に"], "k", "書き手の答えを、強めず弱めず、出どころを添えて本文に入れます。「分からない」だった箇所は仮定の形にします。文書の中で直せる指摘はすべて直し、裏づけの試算や体制は付録に移します。文書の2か所で値が食い違っていて、どちらが正しいか書き手にしか分からないときだけ、本文に両方の値を残して「確認中」と書きます。残りの問いは文書の中には書かず、別のファイル(稟議書.確認事項.md)に、先に答えるべき3件(聞いた3つとは別で、答えを受けて残った問いの上位3件)と「そのほか」に分けて出します。書き手の答えで決裁事項の前提が崩れたときは、決裁事項を小さくする案(例: 12名の承認ではなく、まず2週間の測定だけを頼む)を確認事項の先頭に1行で書きます。直した文書には、「確認中」を除いて、直した箇所の印も確認事項の節も残りません。頼み方:「稟議書.md を決裁者の目で見て直して」"),
    "re": ("組み直す", ["頼んだときだけ", "事実と決裁事項は保ち、論の組み立てを替える"], "k", "検査のあとに別に頼みます。事実・数値・主結論・決裁事項は保ったまま、論の組み立てだけを替えます。構成案を3つ出し、そのうち1つは必ず決裁事項を小さくする案です。書き手がその案を選んだときだけ、決裁事項も変わります。頼み方:「構成から組み直して」"),
    "cc": ("もっと端的に・丁寧に", ["頼んだときだけ", "本編に残す根拠の量を変えて書き直す"], "k", "文章を削るのではなく、どの根拠まで本編に残すかを決めて書き直します。端的にするときは、主結論、各論点の主張と決裁に要る根拠、決裁をお願いする事項と制約だけを本編に残し、裏づけと補足は付録に移します。事実・数値・事例は消しません。丁寧にするときは、裏づけを本編に戻し、根拠と主張をつなぐ考えを論点ごとに一文で書きます。頼み方:「もっと端的に」「もっと丁寧に」"),
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
flow_list = "".join(f'<li><details class="dsc"><summary>{ICON}<span>{E(v[0])}</span></summary><div class="dsc-body"><p>{E("、".join(v[1]))}。</p><p>{E(v[3])}</p></div></details></li>' for v in NODES.values())
node_desc = "".join(f'<div class="nd" data-for="{k}" hidden><b>{E(v[0])}</b><p>{E(v[3])}</p></div>' for k, v in NODES.items())

# ---------- 4つの文書(タブ) ----------
# <em> は直す前後で変わった語。引用は文書の文そのまま(作者がスクリプトで突き合わせて確かめる)。
PICKS_BY = {
 "ringi": [
    dict(title="「週に平均8件」は部全体か、1人あたりか", src=("ask", 1),
        before=[(20, "<em>営業部では</em>、顧客打ち合わせが週に平均8件(月に約35件)ある。")],
        after=[(22, "顧客打ち合わせは<em>営業部全体で</em>週に平均8件(月に約35件)ある。<em>1人あたりの件数ではなく、営業支援システムの訪問記録の直近6か月から出した</em>。")],
        note="元の文書だけでは、部全体か1人あたりか決まらない。1人あたりなら試算は12倍ずれる。書き手の答えで決まり、出どころが本文に入った。「部全体の作成時間は測っていない」という答えは、本文を仮定の形にし、確認事項の先頭の問い(承認の前に2週間で測るか)になった。"),
    dict(title="空欄だった時間単価が入り、損益の分かれ目が本文に出た", src=("ask", 2),
        before=[(62, "当社の営業担当者の時間単価:<em>【 】円(人事・経理部門に確認して記入)</em>")],
        after=[(33, "時間単価は、<em>経理部が社内の試算に使う標準単価の1時間3,500円</em>である。"),
               (29, "費用に見合うのは、打ち合わせの全件で使い、<em>1件あたり約39分以上減った場合</em>で、今ある参考値の30分では届かない。")],
        note="書き手が答えた標準単価と、元の文書にある月額79,200円から、損益の分かれ目(月約22.6時間、1件あたり約39分)を計算して本文に書いた。元の試算の30分では費用に見合わない、と本文が言うようになった。この計算の結果、12名・6か月の申請の前提が崩れたので、確認事項の先頭に「頼む中身を小さくする案」が付いた。"),
 ],
 "kikaku": [
    dict(title="「退職理由の上位」が、人数の内訳になった", src=("ask", 1),
        before=[(25, "| 退職者アンケート | 「働き方の柔軟性のなさ」が<em>退職理由の上位</em> | — |")],
        after=[(27, "| 退職者アンケート | <em>回答者は22名</em>。「働き方の柔軟性のなさ」が退職理由の上位で、<em>挙げたのは9名（うち内勤7名）</em>。自由記述で在宅勤務に触れたのは4名 | — |")],
        note="離職率は250名全体の数字で、対象は内勤180名。辞めた人が対象の中にいるのかは、書き手に聞かないと分からない。答えの数字がそのまま入った。「その人たちが求めていた柔軟性に今回の制度で応えられるか」は分からない、という答えだったので、本文は仮定の形になり、確認事項の先頭の問いになった。"),
    dict(title="本日決めるのは「4月開始」か、「方針と準備の着手」か", src=("ask", 3),
        before=[(10, "内勤の従業員180名を対象に、週1日の在宅勤務制度を <em>2027年4月から</em> 始めること")],
        after=[(10, "内勤の従業員180名を対象に、週1日の在宅勤務制度を<em>作る方針を承認いただくこと</em>（開始は 2027年4月 を<em>目標</em>とします）")],
        note="書き手の答えは「方針の承認と準備の着手で、開始日は2月の最終案で改めて決めてもらう形でもよい」。決裁をお願いする事項の文がそれに合わせて変わった。"),
 ],
 "teian": [
    dict(title="「実際に失注が起きています」の出どころが、本文に入った", src=("ask", 1),
        before=[(33, "御社ではこの引き継ぎの場面で<em>実際に失注が起きています</em>。")],
        after=[(33, "<em>営業本部長からは、引き継ぎで2社を失ったとうかがっています。資料では確かめておらず、その2社の時期や理由もうかがっていません。</em>")],
        note="書き手の答えは「営業本部長が『引き継ぎで2社失った』と話したのを聞いただけ。資料では確かめていない。件数と金額は分からない」。本文はその答えを、強めも弱めもせずに書いた。提案の前提が「聞いた話」であることが、読む人に分かるようになった。"),
 ],
 "postmortem": [
    dict(title="共有で終わる報告が、2つの判断を頼む報告になった", src=("ask", 2),
        before=[(8, "10月21日(火)の午前中、受注管理システムの Web 画面が1時間半ほど応答しなくなりました。アプリケーションサーバー(受注管理システムの処理を動かすサーバー)のメモリが上限に達したためで、サーバーを再起動し、11:50 ごろに復旧しました。")],
        after=[(8, "<em>決めていただきたいことが2つあります。再発防止の3つの方向でよいかと、受注検索の改修が障害の原因かどうかの調査に1週間かけてよいかです。</em>")],
        note="元の報告書には、読んだ人に何をしてほしいかが書かれていなかった。スキルは「共有で終わる文書だと読んだが、合っているか」と聞き、書き手の答え(2つ決めてほしい)が冒頭に入った。どちらの部長に求めるかは答えがなく、確認事項の先頭の問いになった。"),
    dict(title="改修を疑う根拠の弱さが、半年前の通知と並んで本文に出た", src=("ask", 3),
        before=[(29, "メモリが上限に達した理由は確定していません。<em>疑っているのは前日の夕方に反映した受注検索の改修ですが、</em>根拠は反映と障害の時期が近いことだけで、改修がメモリの使用量を増やしたことはまだ確かめていません。")],
        after=[(31, "メモリが上限に達した理由は確定していません。改修を疑う根拠は反映と障害の時期が近いことだけで、改修がメモリの使用量を増やしたことはまだ確かめていません。<em>半年前に1度、同じサーバーのメモリで通知が出たことがあります。そのときは再起動で収まり、原因は調べていません。</em>")],
        note="書き手の答え「半年前にも同じサーバーで通知が出た。原因は調べていない」がそのまま入り、改修だけを疑う根拠が弱いことが読む人に分かるようになった。この答えで再発防止の3つの方向の前提が揺らぐので、確認事項の先頭に「調査の1週間だけを先に決めてもらう案」が付いた。"),
 ],
}
for _key, _picks in PICKS_BY.items():
    _t = SETS[_key]
    for _p in _picks:
        for _ln, _q in _p["before"]: assert _norm(_q) in _norm(_t["before"]), (_key, "before", _ln)
        for _ln, _q in _p["after"]: assert _norm(_q) in _norm(_t["after"]), (_key, "after", _ln)
def pick_html(p, key, qa):
    n, q, ans = qa[p["src"][1] - 1]
    qs = f'<div class="q q-ask"><span class="tag">スキルの問い {n}</span><p>{E(q)}</p></div><div class="q q-ans"><span class="tag">書き手の答え</span><p>{E(ans)}</p></div>'
    return f'''<div class="ex">
  <h4 class="ex-t">{E(p["title"])} <span class="st st-ask">書き手の答えで直った</span></h4>
  <div class="ba"><div><h5>元の文書</h5>{"".join(quote(*x) for x in p["before"])}</div><div><h5>直した後</h5>{"".join(quote(*x) for x in p["after"])}</div></div>
  <p class="note">{E(p["note"])}</p>
  {disclosure(f"問い {n} と書き手の答え", qs)}
</div>'''
def verdict_html(key):
    o = OUTC[key]; ov = OV[key]
    def cell(v):
        x = o[v]; vs = x["verdicts"]
        v = x["verdict"].replace("聞きたい", "判断の前に質問あり")
        return f'{E(v)}' + ("" if len(vs) == 1 else f'<small>(3回のうち{vs[x["verdict"]]}回)</small>') + f'<br><small>指摘 {x["per_run"]:.1f} 件/回(うち文書を読み直せば答えが出るもの {x["in_doc"]:.1f})</small>'
    return f'''<table class="tbl"><thead><tr><th>{E(READER[key])}役が読んだ文書</th><th>元の文書</th><th>直した後</th><th>端的にした後</th></tr></thead>
<tbody><tr><th>返事(3回の多数決)</th><td>{cell("元")}</td><td>{cell("一括")}</td><td>{cell("端的")}</td></tr></tbody></table>
<p class="note">元の文書への指摘 {ov["n"]} 件(3回の延べ)のうち、スキルの確認事項にあったのは {ov["n"] - ov["none"]} 件(先に答えるべき3件の中に {ov["first"]} 件、そのほかに {ov["other"]} 件)。元の文書への1回目の返事の一言:「{E(o["元"]["reply"])}」</p>'''
def doc_panel_body(key):
    t = SETS[key]
    qa = "".join(f'<li><p class="qq">{E(q)}</p><p class="qa"><span class="tag">書き手の答え</span>{E(a)}</p></li>' for n, q, a in t["qa"])
    kak_body = f'<p class="cap">決裁事項を小さくする案</p><p>{E(t["shrink"])}</p><p class="cap">先に答えるべき問い</p><ol class="kak">{"".join(f"<li>{E(x)}</li>" for x in t["kak_first"])}</ol><p class="cap">そのほか</p><ul class="kak kak-rest">{"".join(f"<li>{E(x)}</li>" for x in t["kak_rest"])}</ul>'
    nums = f'本編の字数 {fmt(t["P0"]["body"])} → {fmt(t["P1"]["body"])}(付録 {fmt(t["P1"]["app"])})。別ファイルの確認事項 {len(t["kak"])} 件(先に答えるべき問い 3 件)。元の文書にも書き手の答えにもない数値・固有名詞は、スクリプトで調べて 0 件{"(答えから計算した約39分などの値を除く)" if key == "ringi" else ""}。'
    return f'''<p class="desc">{E(dict((k, d) for k, _, d, *_ in DOCSETS)[key])}</p>
  <h4 class="ex-t">{E(READER[key])}役の返事は、どう変わったか</h4>
  {verdict_html(key)}
  <h4 class="ex-t">スキルが書き手に聞いた3つ</h4>
  <ol class="qa-list">{qa}</ol>
  {"".join(pick_html(p, key, t["qa"]) for p in PICKS_BY[key])}
  <h4 class="ex-t">確認事項の先頭に付いた、決裁事項を小さくする案 <span class="st st-shrink">選ぶのは書き手</span></h4>
  <blockquote class="q-shrink"><p>{E(t["shrink"])}</p></blockquote>
  <p class="nums">{E(nums)}</p>
  {disclosure(f"別ファイルに出した確認事項 {len(t['kak'])} 件", kak_body)}'''
docs_html = f'<div class="dads-tab" data-position="top">{tabs("doc", [l for _, l, *_ in DOCSETS], "4つの文書")}<div class="dads-tab__panels">{"".join(panel("doc", i + 1, doc_panel_body(k)) for i, (k, *_) in enumerate(DOCSETS))}</div></div>'

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
    def li(h, n): return f'<li>{E(h)}<span class="ln" style="margin-left:.5em">{fmt(n)}字</span></li>'
    L = "".join(li(h, n) for h, n in before)
    body = "".join(li(h, n) for h, n, k in after if k == "body")
    app = "".join(li(h, n) for h, n, k in after if k == "app")
    return f'<div class="keep"><div class="k"><h4>元の本編 {len(before)}節</h4><ol>{L}</ol></div><div class="mid" aria-hidden="true"></div><div class="k"><h4>端的にした本編 {sum(1 for *_, k in after if k == "body")}節</h4><ol>{body}</ol><h4 style="margin-top:12px">付録 {sum(1 for *_, k in after if k == "app")}節</h4><ul style="list-style:none;padding-left:0">{app}</ul></div></div>'
concise_rows = [(DOC_LABEL[k], SETS[k]["P0"]) for k, *_ in DOCSETS]
def concise_panel_body(key):
    t = SETS[key]; o = OUTC[key]
    bars = bars_svg([("元の文書", t["P0"]), ("端的にした後", t["P3"])], "元の文書と端的にした後の字数を、本編と付録に分けた棒")
    ratio = t["P3"]["body"] / t["P0"]["body"]
    return f'''<p class="desc">本編は {fmt(t["P0"]["body"])} 字から {fmt(t["P3"]["body"])} 字(元の {ratio:.0%})になり、付録が {fmt(t["P3"]["app"])} 字付きました。{E(READER[key])}役の返事は、元の文書と端的にした後で同じ({E(o["元"]["verdict"].replace("聞きたい", "判断の前に質問あり"))} → {E(o["端的"]["verdict"].replace("聞きたい", "判断の前に質問あり"))})でした。</p>
  <div class="bars-wrap">{bars}</div>
  {disclosure("見出しは、こう分かれた", heading_cols(t))}'''
concise_html = f'<div class="dads-tab" data-position="top">{tabs("cc", [l for _, l, *_ in DOCSETS], "端的にした4つの文書")}<div class="dads-tab__panels">{"".join(panel("cc", i + 1, concise_panel_body(k)) for i, (k, *_) in enumerate(DOCSETS))}</div></div>'

# ---------- 組み直す ----------
def _field(body, names):
    for n in names:
        m = re.search(r"^\s*-?\s*\*{0,2}" + n + r"\*{0,2}\s*[:：](.+)$", body, re.M)
        if m: return m.group(1).strip()
    return ""
def _block(body, names):
    for n in names:
        m = re.search(r"^\s*-?\s*\*{0,2}" + n + r"[^\n]*\n((?:\s*(?:[-*]|\d+\.)\s+.+\n?)+)", body, re.M)
        if m:
            out = []
            for l in m.group(1).splitlines():
                t = re.sub(r"^\s*(?:[-*]|\d+\.)\s+", "", l).strip()
                if not t: continue
                if re.match(r"\*\*", t) or re.match(r"(答える問い|答える検査の問い|弱点|この案)", t) or re.search(r"[SL]\d", t): break
                out.append(t)
            return out
    return []
def parse_plans(md):
    plans = []
    for m in re.finditer(r"^## (案[A-Z0-9０-９])\s*[:：]?\s*(.+?)$([\s\S]*?)(?=^## |\Z)", md, re.M):
        key, title, body = m.group(1), m.group(2).strip(), m.group(3)
        if re.match(r"^を?選んだ", title): continue
        shrink = "小さくする" in title or "縮め" in title[:12]
        outline = _block(body, ["本編の骨組み", "骨組み"])
        if not outline:
            outline = [x.strip() for x in re.split(r"[／/]", _field(body, ["本編の骨組み", "骨組み"])) if x.strip()]
        chosen = bool(re.search(r"[(（](?:選んだ案|採用)[)）]", title))
        title = re.sub(r"\s*[(（](?:採用|選んだ案|書き手が選ぶ案)[)）]\s*", "", title).strip()
        plans.append(dict(key=key, title=title, shrink=shrink, chosen=chosen, claim=_field(body, ["主張"]), weak=_field(body, ["弱点"]), outline=outline))
    tail = md[md.rindex("## 選んだ案"):] if "## 選んだ案" in md else md[md.rindex("を選んだ理由"):] if "を選んだ理由" in md else ""
    mm = re.search(r"(案[A-Z0-9０-９])", tail)
    chosen = mm.group(1) if mm else next((p["key"] for p in plans if p["chosen"]), None)
    return plans, chosen
def _clean(t):
    t = re.sub(r"[(（](?:[SLRP]S?\d[\d\-・/、SLRP\s]*|somosomo\s*[^)）]*|logic\s*[^)）]*)[)）]", "", t)
    t = re.sub(r"(?:[SLRP]S?\d[\d\-]*)(?:\s*[・/、]\s*[SLRP]S?\d[\d\-]*)*\s*(?:のとおり|の読みが立つ|の)?", lambda m: "" if re.match(r"^[SLRP]", m.group(0)) else m.group(0), t)
    return re.sub(r"\s{2,}", " ", t).replace("(、", "(").replace("()", "").strip("、 ")
for _k, _t in SETS.items():
    _t["PLANS"], _t["CHOSEN"] = parse_plans(_t["plans_md"])
    assert len(_t["PLANS"]) == 3 and _t["CHOSEN"] and any(p["shrink"] for p in _t["PLANS"]), (_k, [p["key"] for p in _t["PLANS"]], _t["CHOSEN"])
def plan_block(p, chosen, label):
    title = re.sub(r"^頼む中身を(?:小さくする|保つ)案?\s*[:：]?\s*[(（]?", "", p["title"]).rstrip("）)")
    ol = "".join(f"<li>{E(x)}</li>" for x in p["outline"][:8])
    body = f'<p class="claim">{E(_clean(p["claim"]).replace("背骨", "中心"))}</p>' + (f'<ol>{ol}</ol>' if ol else '')
    title = title.replace("背骨にする", "中心に置く").replace("背骨", "中心")
    if p["shrink"]:
        return f'<div class="plan shrink"><h4>{E(label)} {E(title)} <span class="st st-shrink">決裁事項を小さくする案</span></h4>{body}</div>'
    if p["key"] == chosen:
        return f'<div class="plan sel"><h4>{E(label)} {E(title)} <span class="st st-fixed">この案で書いた</span></h4>{body}</div>'
    return disclosure(f'{label} {title}', body, "plan-alt")
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
    s = f'<svg viewBox="0 0 {W} {H}" class="fig map" role="img" aria-label="元の{len(L)}節が、組み直した後の本編と付録のどこへ移ったか。左の節にポインタを置くと、その節の行き先だけが濃くなる">'
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
def redesign_panel_body(key):
    t = SETS[key]
    ordered = sorted(t["PLANS"], key=lambda p: 0 if p["shrink"] else 1)
    plans = "".join(plan_block(p, t["CHOSEN"], f"案{i + 1}") for i, p in enumerate(ordered))
    return f'''<h3 class="sec" style="margin-top:8px">構成案を3つ出し、書き手が1つ選ぶ</h3>
  <p class="sub">この例ではスキルの作者が選ばずにスキルに任せたので、組み直した文書は決裁事項を変えない案で書いてあります。決裁事項を小さくする案を選べるのは書き手だけです。</p>
  {plans}
  <h3 class="sec">元の{len([h for h, _ in sections(t["before"]) if h])}節は、どこへ移ったか</h3>
  <p class="sub">左の節にポインタを重ねるか押すと、移った先の節が強く表示されます。線は、元の節の文がどの節に移ったかをスキルの作者がスクリプトで探して引いたものです。</p>
  <div class="map-wrap">{mapping_svg(t, compute_moves(t["before"], t["redesign"]))}</div>
  <p class="sub">決裁者が読む本編は {fmt(t["P0"]["body"])} 字から {fmt(t["P2"]["body"])} 字になりました。付録を足すと全体は {fmt(sum(t["P2"].values()))} 字です。</p>'''
redesign_html = f'<div class="dads-tab" data-position="top">{tabs("rd", [l for _, l, *_ in DOCSETS], "組み直した4つの文書")}<div class="dads-tab__panels">{"".join(panel("rd", i + 1, redesign_panel_body(k)) for i, (k, *_) in enumerate(DOCSETS))}</div></div>'

# ---------- 確かめたこと ----------
def checked_html():
    verdict_rows = "".join(
        f'<tr><th>{E(DOC_LABEL[k])}</th><td>{E(READER[k])}</td><td>{E(OUTC[k]["元"]["verdict"].replace("聞きたい", "判断の前に質問あり"))}</td><td>{E(OUTC[k]["一括"]["verdict"].replace("聞きたい", "判断の前に質問あり"))}</td><td>{OV[k]["n"]} 件のうち {OV[k]["n"] - OV[k]["none"]} 件</td></tr>'
        for k, *_ in DOCSETS)
    page_part = f'''<h3 class="sec" style="margin-top:0">上の4本で</h3>
  <p class="sub">上司や顧客の役の AI(別のセッションの Claude Opus 5.5。役は文書ごとに、経営者、提案を受け取る会社の役員、報告を受け取る上司)に、元の文書と直した後の文書を、どちらが直した後かを知らせずに別々に渡し、返事と指摘を3回ずつ返させました。役は、文書を読み直せば答えが出ること(矛盾、計算、空欄があること)と、書き手にしか答えられないことを分けて指摘します。</p>
  <table class="tbl"><thead><tr><th>文書</th><th>読む役</th><th>元の文書への返事</th><th>直した後への返事</th><th>元の文書への指摘のうち、スキルの確認事項にあったもの</th></tr></thead><tbody>{verdict_rows}</tbody></table>
  <p class="note">指摘 {OV_TOTAL} 件のうち、確認事項になかったものは {OV_NONE} 件。先に答えるべき3件の中にあったのは {OV_FIRST} 件で、残りは「そのほか」にありました。突き合わせは別のセッションの Claude Sonnet 5.5 が行いました。判定が甘くないかは、下の欠陥を仕込んだ素材で、指摘と別の文書の確認事項の組(稟議書への指摘に提案資料の確認事項など)42 件を突き合わせて確かめ、すべて「ない」と判定されました。</p>'''
    assert HAVE_R46, "r46 系の summary がない"
    rw = rewrite_stats("r46b"); rd = rewrite_stats("r46d")
    rv = summary("r46c"); cc = summary("r46e"); cl = summary("r46f")
    rv_rows = table_rows("r46c")
    # review の cells: 問い, 文書内で答えが出る問い, used/unchanged/deferred/dropped, 確認事項 先に答える/全体(消せたはず), fixed, deferred, remains, 持ち込み
    rv_q = sum(int(r["cells"][0]) for r in rv_rows); rv_q_doc = sum(int(r["cells"][1]) for r in rv_rows)
    uudd = [tuple(int(x) for x in r["cells"][2].split("/")) for r in rv_rows]
    rv_used = sum(u[0] for u in uudd); rv_unch = sum(u[1] for u in uudd); rv_dfd = sum(u[2] for u in uudd); rv_drop = sum(u[3] for u in uudd)
    rv_ok = sum(int(a) for a, _ in re.findall(r"満たした run: (\d+)/(\d+)", rv)); rv_n = sum(int(b) for _, b in re.findall(r"満たした run: (\d+)/(\d+)", rv))
    cc_ok = [(int(a), int(b)) for a, b in re.findall(r"満たした run: (\d+)/(\d+)", cc + cl)]
    st = DET["stable"]; stable_ok = sum(a for a, _ in st); stable_n = sum(b for _, b in st)
    return page_part + f'''
  <h3 class="sec">欠陥を仕込んだ素材で</h3>
  <p class="sub">上の4本は例です。欠陥をどれだけ見つけられるか、書き手の答えを改変せずに入れるか、回ごとにどれだけ結果が変わるかを見るために、スキルの作者が欠陥を仕込んだ架空の文書5本(稟議書、長い稟議書、社内の制度企画、コンサルの提案資料、障害報告書)と、ない欠陥を指摘しないかを見るための欠陥のない4本に、このバージョンのスキルを3回ずつかけて測りました。</p>
  <div class="stats four">
    <div class="stat"><b>仕込んだ欠陥{DET["rows"]}か所を3回ずつ検査して、問いにした</b><div class="n">{DET["found"]}<small>回のうち {DET["found"]}(延べ {DET["found"] + DET["partial"] + DET["missed"]} 回。部分的 {DET["partial"]} 回、見落とし {DET["missed"]} 回)</small></div></div>
    <div class="stat"><b>検査が元にない事実を持ち込んだ</b><div class="n">{DET["crossing"]}<small>件。欠陥のない4本で、ない欠陥を指摘したのは {sum(DET["false_clean"])} 件</small></div></div>
    <div class="stat"><b>「決裁者の目で見て直す」が書き手に聞いた問い</b><div class="n">{rv_q}<small>件のうち、文書の中で答えが出るもの {rv_q_doc}。答え {rv_used} 件を改変せずに本文に入れ、「分からない」の {rv_dfd} 件は本文を仮定の形にし、落としたのは {rv_drop} 件</small></div></div>
    <div class="stat"><b>「直す」が仕込んだ欠陥を直すか確認事項に回した</b><div class="n">{rw["fixed"] + rw["deferred"]}<small>回のうち {rw["fixed"] + rw["deferred"]}(残った {rw["remains"]})。本編が元以下 {rw["not_longer"]}/{rw["n"]} 本、持ち込み {rw["crossing"]}</small></div></div>
  </div>
  {disclosure("測り方と注", f"<p>欠陥は、表と本文で食い違う数字、根拠のない見込み、診断の後で決めるはずなのにもう書いてある製品名、報告日より後の「実施済み」などです。問いが欠陥を捉えたか、直しが欠陥を解いたか、書き手の答えを改変せずに入れたかは、別のセッションの Claude Sonnet 5.5 が判定しました。書かせたのも直したのも Claude Opus 5.5 で、人による確認はしていません。</p><p>「組み直す」は {rd['n']} 本すべてで決裁事項を小さくする案が出て、主結論と決裁事項は {rd['kept']} 本で元のままでした。本編が元より長くなった回が制度企画で2本(いずれも元の 2% 以内)ありました。「もっと端的に」「もっと丁寧に」は、主結論・決裁事項・数値が保たれ、本編の各文が元の文書に対応することを条件に、{sum(a for a, _ in cc_ok)}/{sum(b for _, b in cc_ok)} 回で条件を満たしました。測り方と回ごとの結果は <a href=\"https://github.com/coji/natural-japanese/blob/main/dev/ct-eval/RESULTS.md\">dev/ct-eval/RESULTS.md</a> にあります。</p>")}'''

# ---------- ページ ----------
DOCS = {k: markdown.markdown(v, extensions=["tables"]) for k, v in
        [("before", R0["before"]), ("after", R0["after"]), ("concise", R0["concise"]), ("redesign", R0["redesign"]), ("kak", R0["kak_md"]), ("logic", R0["logic"]), ("somosomo", R0["somo"])]}
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
<div class="band"><div class="wrap"><span><b>natural-japanese</b> 仕事の日本語を書く・直す Agent Skill</span><a href="https://github.com/coji/natural-japanese">github.com/coji/natural-japanese</a></div></div>
<nav class="toc" aria-label="目次">
  <div class="toc-inner">
    <p class="toc-h">目次</p>
    <ol class="toc-list">
      <li><a href="#top">はじめに</a></li>
      <li><a href="#how">何をするか</a></li>
      <li><a href="#examples">4つの文書で、どう変わったか</a></li>
      <li><a href="#concise">もっと端的に</a></li>
      <li><a href="#redesign">構成から組み直す</a></li>
      <li><a href="#checked">確かめたこと</a></li>
      <li><a href="#limits">苦手なこと</a></li>
      <li><a href="#install">インストールと頼み方</a></li>
      <li><a href="#read">文書を読む</a></li>
    </ol>
  </div>
</nav>

<header class="hero" id="top"><div class="wrap">
  <p class="ver"><small>v</small>{VER}</p>
  <p class="meta">2026年11月。ひとつ前のリリースノートは <a href="{PREV[1]}">{PREV[0]}</a></p>
  <h1>上司や顧客が聞いてくることを提出前に洗い出すスキル critical-thinking を追加しました</h1>
  <p class="lead">AI に稟議書や提案資料、障害報告書を書かせると、丁寧で穴のなさそうな文書ができます。それでも上司や顧客は「<mark>この数字は誰の分か</mark>」「<mark>空欄のままで判断できない</mark>」「<mark>他の案と比べたか</mark>」と聞いてきます。考えの穴なので、日本語を直しても埋まりません。</p>
  <p class="lead">critical-thinking は、Claude Code や ChatGPT などの AI に入れて使う指示書のセットです。「<mark class="key">決裁者の目で見て直して</mark>」と頼むと、文書の中で答えが出ることは黙って直し、書き手にしか答えられないことを<mark class="key">3つ</mark>聞いて、答えを本文に入れます。答えが出なかった問いと聞かなかった問いは、別のファイルの確認事項に残します。架空の文書4本を上司や顧客の役の AI に3回ずつ読ませて出た指摘 {OV_TOTAL} 件は、すべて1本あたり30件前後のこの確認事項の中にありました(確認事項の中でも先に答えるべき3件に入っていたのは {OV_FIRST} 件)。</p>
  <p class="cap">例: 上司や顧客の役が元の文書に出した指摘と、スキルが提出前に書き手へ聞いていた問い、答えを入れた文。書き手の答えは AI が返しました。スキルの作者が事実の一覧を先に書き、AI はそれだけを見て答え、一覧にないことは「分からない」と答えます。</p>
  {hero_rows()}
</div></header>

<main>
<section class="block" id="how"><div class="wrap">
  <h2>何をするか</h2>
  <p class="sub">対象は、稟議書、企画書、提案資料、障害報告書のような、読んだ人に判断を求める文書です。natural-japanese が言い回しを直すのに対し、critical-thinking は論の筋を見ます。各項目を押すと説明が出ます。</p>
  <div class="flow-wrap">{flow_svg()}</div>
  <div class="nd-wrap">{node_desc}</div>
  <ol class="flow-list">{flow_list}</ol>
</div></section>

<section class="block" id="examples"><div class="wrap">
  <h2>4つの文書で、どう変わったか</h2>
  <p class="sub">どれもスキルなしの Claude Code(Opus 5.5)に書かせた架空の文書で、わざと穴を作らせたのではなく、書かせたままです。それぞれに「決裁者の目で見て直して」と頼み、スキルが聞いた3つに書き手が答えると、こう変わりました。書き手の答えは AI が返しました(スキルの作者が事実の一覧を先に書き、AI はそれだけを見て答え、一覧にないことは「分からない」と答えます)。</p>
  <p class="sub">上司や顧客の役の返事は、同じ役に元の文書と直した後を、どちらが直した後かを知らせずに別々に渡して3回ずつ集めました。返事は OK、条件つきOK、判断の前に質問あり、却下の4つから選びます。4本とも元の文書の時点で丁寧に書かれているので、返事が変わったのは障害報告書の1本(質問あり → 条件つきOK)だけで、指摘の数も減りません。変わるのは指摘の中身です。元の文書への指摘は「空欄を埋めてから」「出どころを示して」が中心で、直した後は「他の案と比べたか」のように書き手の判断を求めるものと、入れた答えが別の節と合っているかの指摘(稟議書と障害報告書で増えた分)になります。</p>
  <p class="legend" style="margin:-8px 0 16px">色の意味<i style="background:var(--ok-50);box-shadow:inset 0 -2px 0 var(--ok)"></i>直す前後で変わった言い方<i style="background:var(--key-50);border:1px solid var(--key-200)"></i>スキルの問い<i style="background:var(--warn-50);border:1px solid var(--warn)"></i>書き手の答え</p>
  {docs_html}
</div></section>

<section class="block" id="concise"><div class="wrap">
  <h2>もっと端的に</h2>
  <p class="sub">「もっと端的に」と頼むと、文章を削るのではなく、決裁者が読む本編に主結論・決裁に要る根拠・費用・決裁事項だけを残し、裏づけと補足を付録に移します。事実・数値・事例は消さないので、あとで「もっと丁寧に」と頼めば戻せます。根拠が決裁に要るかどうかは、検査のときに論点ごとに書き出してあります。</p>
  {concise_html}
</div></section>

<section class="block" id="redesign"><div class="wrap">
  <h2>構成から組み直す</h2>
  <p class="sub">構成案は3つ出し、そのうち1つは必ず「決裁事項を小さくする案」です。検査の問いが決裁事項の前提を疑っているとき、決裁事項を保ったまま段取りを替えるだけでは答えになりません。この案は決裁事項を縮める・分ける・先に確かめる・取り下げるのどれかで、選べるのは書き手だけです。書き手がこの案を選んだときだけ、決裁事項も変わります。下の例は、検査の報告と書き手の答えも読める状態で、元の文書から作りました。障害報告書の案に「調査に1週間」が入っているのは、書き手の答えから来ています。</p>
  <div class="keep">
    <div class="k"><h4>保つ</h4><ul><li>事実と数値、出典</li><li>主結論と決裁事項</li><li>書き手の制約(開始時期、評価の時期、上限の額)</li></ul></div>
    <div class="mid" aria-hidden="true"></div>
    <div class="c"><h4>替えてよい</h4><ul><li>先頭に何を置くか</li><li>本編と付録の切り分け</li><li>申請の立て方(効果を言い切るか、確かめる試験にするか、判断を何回に分けるか)</li></ul></div>
  </div>
  {redesign_html}
</div></section>

<section class="block" id="checked"><div class="wrap">
  <h2>確かめたこと</h2>
  {checked_html()}
</div></section>

<section class="block" id="limits"><div class="wrap">
  <h2>苦手なこと</h2>
  <ul class="limits">
    <li>文書の外の事実は調べに行きません。稟議書が挙げる他社の事例が本当かは、問いにして返すだけです。</li>
    <li>書き手に聞くのは3つまでなので、聞かなかった問いは別ファイルの確認事項に残ります。稟議書の例では{len(R0["kak"])}件でした。3つに答えただけでは、文書は出せる形に近づきますが、上司や顧客の指摘が消えるわけではありません。上の4本でも、直した後の文書に経営者役は「何もしない案や、人数を絞る案と比べたか」と聞いてきました。この問いは確認事項にありますが、答えられるのは書き手だけです。</li>
    <li>書き手の答えが本文に入ると、申請の弱さがそのまま見えます。欠陥を仕込んだ稟議書では、答えを入れた文書を経営者役が「最良の前提でも効果が費用を下回る」と戻しました。スキルはそのとき、確認事項の先頭に「決裁事項を小さくする案」を書いています。</li>
    <li>文書の2か所で値が食い違い、どちらが正しいか書き手にしか分からないときは、本文に両方を残して「確認中」と書きます。書き手が決めるまで提出できない箇所がそのまま残るので、上司役は障害報告書で「確認中と書きながら別の節では言い切っている」と指摘しました。</li>
    <li>検査は LLM の読みに頼るので、同じ文書をもう一度検査すると、指摘の数や言い方は揺れます。上司や顧客の役の返事も、同じ文書で回によって揺れます。</li>
  </ul>
</div></section>

<section class="block" id="install"><div class="wrap">
  <h2>インストールと頼み方</h2>
  <p class="sub">使う環境を選んでください。頼み方はどの環境でも同じで、文書のファイルを示して「稟議書.md を決裁者の目で見て直して」と頼みます。スキルが3つまで質問するので、答えると直した文書が返ります。工程を分けて使いたいときの頼み方は、次の4つです。</p>
  <ul class="limits" style="margin-top:-8px">
    <li>検査だけ:「稟議書.md の筋が通っているか検査して」「稟議書.md を決裁者目線で、前提から疑って」</li>
    <li>検査のあとで、聞かずに直す:「指摘を反映して直して」</li>
    <li>論の組み立てから替える:「構成から組み直して」</li>
    <li>長さを変える:「もっと端的に」「もっと丁寧に」</li>
  </ul>
  <div class="dads-tab" data-position="top">
    <ul class="dads-tab__list" role="tablist" aria-label="使う環境">
      <li><button type="button" class="dads-tab__tab" role="tab" id="env-tab-1" aria-selected="true" aria-controls="env-panel-1" tabindex="0"><span>Claude Code など</span></button></li>
      <li><button type="button" class="dads-tab__tab" role="tab" id="env-tab-2" aria-selected="false" aria-controls="env-panel-2" tabindex="-1"><span>claude.ai</span></button></li>
      <li><button type="button" class="dads-tab__tab" role="tab" id="env-tab-3" aria-selected="false" aria-controls="env-panel-3" tabindex="-1"><span>ChatGPT</span></button></li>
      <li><button type="button" class="dads-tab__tab" role="tab" id="env-tab-4" aria-selected="false" aria-controls="env-panel-4" tabindex="-1"><span>Gemini</span></button></li>
      <li><button type="button" class="dads-tab__tab" role="tab" id="env-tab-5" aria-selected="false" aria-controls="env-panel-5" tabindex="-1"><span>Microsoft 365 Copilot</span></button></li>
    </ul>
    <div class="dads-tab__panels">
      <div class="dads-tab__panel env" id="env-panel-1" role="tabpanel" aria-labelledby="env-tab-1" tabindex="0">
        <p class="desc">Claude Code、Codex、Cursor、Gemini CLI、GitHub Copilot など、Agent Skills に対応したコーディングエージェント。</p>
        <div class="cmd"><code id="cmd">npx skills add coji/natural-japanese</code><button type="button" data-copy="cmd">コピー</button></div>
        <p class="desc">このコマンドで natural-japanese と critical-thinking の両方が入ります。critical-thinking は uv と Python がなくても動きます。あれば、検査で書き出した論理構造に文書の行の漏れがないかを小さなスクリプトで確かめ、なければエージェントが自分で突き合わせます。natural-japanese の機械検査スクリプトには uv と Python が要ります。</p>
      </div>
      <div class="dads-tab__panel env" id="env-panel-2" role="tabpanel" aria-labelledby="env-tab-2" tabindex="0" hidden>
        <p class="desc">Web とデスクトップアプリの Claude。Free から Enterprise まで、コード実行を有効にしていれば使えます。</p>
        <ol class="steps">
          <li><a href="https://github.com/coji/natural-japanese/releases/latest/download/critical-thinking.zip">critical-thinking.zip</a> をダウンロードする(日本語を直す方も使うなら <a href="https://github.com/coji/natural-japanese/releases/latest/download/natural-japanese.zip">natural-japanese.zip</a> も)</li>
          <li>左のメニューの「カスタマイズ」から「スキル」を開き、「+」→「スキルを作成」→「スキルをアップロード」で zip を選ぶ</li>
          <li>チャットで文書を貼るか添付して、「この稟議書を決裁者の目で見て直して」のように頼む</li>
        </ol>
        <p class="desc">Team と Enterprise では、組織のオーナーが全員にまとめて配れます。スキルは環境をまたいで同期しないので、使う場所ごとに入れます。natural-japanese の機械検査(日本語の形態素解析)はこの環境では動かず、スキルが手動のチェックリストに切り替えます。</p>
      </div>
      <div class="dads-tab__panel env" id="env-panel-3" role="tabpanel" aria-labelledby="env-tab-3" tabindex="0" hidden>
        <p class="desc">ChatGPT Business、Enterprise、Edu。ワークスペースの管理者がスキルの作成とアップロードを許可している必要があります。</p>
        <ol class="steps">
          <li><a href="https://github.com/coji/natural-japanese/releases/latest/download/critical-thinking.zip">critical-thinking.zip</a> をダウンロードする</li>
          <li>「スキル」を開き、「作成」→「コンピューターからアップロード」で zip を選ぶ。アップロード後にスキャンが走り、終わると使える</li>
          <li>チャットで文書を添付して頼む</li>
        </ol>
        <p class="desc">管理者は、管理画面の「スキル」からワークスペース全体にアップロードできます。</p>
      </div>
      <div class="dads-tab__panel env" id="env-panel-4" role="tabpanel" aria-labelledby="env-tab-4" tabindex="0" hidden>
        <p class="desc">Gemini アプリ(gemini.google.com と Mac アプリ)。2026年11月の時点で、個人アカウントで使えます。Google Workspace の仕事用アカウントは、Google が「まもなく」としています。</p>
        <ol class="steps">
          <li><a href="https://github.com/coji/natural-japanese/releases/latest/download/critical-thinking.zip">critical-thinking.zip</a> をダウンロードして展開する</li>
          <li>「カスタマイズ」→「スキル」→「作成」から、SKILL.md を含むフォルダをアップロードする</li>
          <li>チャットで / に続けてスキル名を打つか、文書を添付して頼む</li>
        </ol>
        <p class="desc">スキルの共有はまだできません。</p>
      </div>
      <div class="dads-tab__panel env" id="env-panel-5" role="tabpanel" aria-labelledby="env-tab-5" tabindex="0" hidden>
        <p class="desc">Microsoft 365 Copilot の宣言型エージェントにスキルを足す機能は、2026年11月の時点でプレビュー(Frontier Preview の組織)です。</p>
        <ol class="steps">
          <li>Agent Builder でエージェントを作り、スキルとして <a href="https://github.com/coji/natural-japanese/releases/latest/download/critical-thinking.zip">critical-thinking.zip</a> を追加する(1エージェントに8個まで)</li>
          <li>そのエージェントに文書を渡して頼む</li>
        </ol>
        <p class="desc">組織全体に配るには、管理者が Microsoft 365 管理センターからエージェントとして登録します。スクリプトはネットワークのないサンドボックスで動き、追加のパッケージは入れられないので、natural-japanese の機械検査は動きません。</p>
      </div>
    </div>
  </div>
  <p class="note" style="margin-top:16px">critical-thinking の検査と直しの中身は、どの環境でも同じです。各環境の手順は2026年11月に公式のヘルプで確かめたもので、画面の名前は変わることがあります。</p>
</div></section>

<section class="block" id="read"><div class="wrap">
  <h2>文書を読む</h2>
  <p class="sub">架空の稟議書です。社名・人名・製品名は実在しません。「直した後」は、書き手に3つ聞いて答えを入れた文書で、確認事項は別ファイルにあります。4本の文書の全文(元・直した後・端的にした後・組み直した後・検査の報告・確認事項)は <a href="https://github.com/coji/natural-japanese/tree/main/release-notes/data/v2.0.0">リポジトリの release-notes/data/v2.0.0</a> にあります。</p>
  <p class="sub">検査の報告はスキルの出力そのままで、logic は「筋を見る」、somosomo は「前提を疑う」の内部名です。</p>
  <div class="seg" role="group" aria-label="表示">
    <button type="button" data-m="side" aria-pressed="true">元 | 直した後</button>
    <button type="button" data-m="side3">元 | 端的にした後</button>
    <button type="button" data-m="side2">元 | 組み直した後</button>
    <button type="button" data-m="before">元の稟議書</button>
    <button type="button" data-m="after">直した後</button>
    <button type="button" data-m="concise">端的にした後</button>
    <button type="button" data-m="kak">別ファイルの確認事項</button>
    <button type="button" data-m="redesign">組み直した後</button>
    <button type="button" data-m="logic">筋を見る</button>
    <button type="button" data-m="somosomo">前提を疑う</button>
  </div>
  <label class="sync" id="syncbox"><input type="checkbox" id="sync" checked> スクロールを同期</label>
  <div class="viewer" id="viewer">
    <div class="pane" id="paneL"><p class="cap">元の稟議書</p><div class="doc" tabindex="0"></div></div>
    <div class="pane" id="paneR"><p class="cap">直した後</p><div class="doc" tabindex="0"></div></div>
  </div>
  {''.join(f'<template id="t-{k}"><article>{v}</article></template>' for k, v in DOCS.items())}
</div></section>
</main>

<footer><div class="wrap">
  <p>これまでのリリースノート <a href="{PREV[1]}">{PREV[0]}</a>{''.join(f'・<a href="{u}">{v}</a>' for v, u in OLDER)}</p>
  <p>色・書体・字詰めとタブ・開閉の部品は、デジタル庁デザインシステム(デザイントークン v2.1.0、MIT)に沿っています。</p>
</div></footer>
<script>{JS}</script>
</body>
</html>"""
def skill_chips(h):
    masks = []
    def mask(m):
        masks.append(m.group(0)); return f"\x00{len(masks)-1}\x00"
    h = re.sub(r"<title>.*?</title>|<meta[^>]*>|<div class=\"band\">[\s\S]*?</div></div>|<h1>[\s\S]*?</h1>|href=\"[^\"]*\"|aria-label=\"[^\"]*\"|<code[^>]*>[\s\S]*?</code>|<template[\s\S]*?</template>|<script>[\s\S]*?</script>", mask, h)
    h = re.sub(r"(?<![\w/\-])(critical-thinking|natural-japanese)(?![\w\-/])", r'<span class="sk">\1</span>', h)
    return re.sub(r"\x00(\d+)\x00", lambda m: masks[int(m.group(1))], h)
page = skill_chips(page).replace("(doc.md 行", "(行").replace("doc.md 行", "行").replace("doc-review.md", "直した後の文書").replace("doc.md", "元の文書").replace("直した後の文書 は", "直した後の文書は").replace("元の文書 の", "元の文書の")
OUT.write_text(page)
print("ok", OUT, {k: (SETS[k]["P0"]["body"], SETS[k]["P1"]["body"], SETS[k]["P3"]["body"]) for k in SETS}, "ov", OV_TOTAL, OV_NONE, OV_FIRST, "r46", HAVE_R46)
