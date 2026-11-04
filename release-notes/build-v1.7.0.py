# /// script
# dependencies = ["markdown"]
# ///
"""v1.7.0 のビジュアルリリースノート(critical-thinking の初出)を release-notes/index.html に生成する。
素材は release-notes/data/v1.7.0/<文書>/(スキルなしの Claude Code に書かせた架空の稟議書・提案資料・制度企画と、検査・直し・組み直しの結果)。
  uv run release-notes/build-v1.7.0.py
"""
import re, html
from pathlib import Path
import markdown

HERE = Path(__file__).parent
DATA = HERE / "data" / "v1.7.0"
OUT = HERE / "index.html"
VER = "1.7.0"
PREV = ("v1.6.1", "https://tkewowm1d6.artifactshare.link/")
OLDER = [("v1.6.0", "https://6c8j7oke3x.artifactshare.link/"), ("v1.5.2", "https://7ttv0opj3s.artifactshare.link/"),
         ("v1.5.0", "https://x3a7rghxqv.artifactshare.link/"), ("v1.4.0", "https://2aretj5195.artifactshare.link/")]

def E(t): return html.escape(re.sub(r"\*\*|`", "", str(t)))
def nonspace(t): return len(re.sub(r"\s", "", t))
def fmt(n): return f"{n:,}"
def sections(t):
    """(見出し, 本文) の並び。先頭の # 見出しと前書きは本編に含める。"""
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
def kakunin_items(t):
    seg = "\n".join(h + "\n" + b for h, b in sections(t) if kind(h) == "kak")
    return [re.sub(r"^\s*(?:[-*]|\d+[.．])\s+", "", l).strip() for l in seg.splitlines() if re.match(r"^\s*(?:[-*]|\d+[.．])\s+", l)]
def headings(t, which):
    return [re.sub(r"^##\s*(?:\d+[.．]\s*)?", "", h) for h, _ in sections(t) if h and kind(h) == which]

def parse_qa(qmd, amd):
    """questions.md の問いと answers.md の答えを番号でそろえる。"""
    qs = re.findall(r"^\s*(\d+)[.．]\s+(.+?)(?=^\s*\d+[.．]\s+|\Z)", qmd, re.M | re.S)
    qs = [(int(n), re.sub(r"\s+", "", t.strip().split("\n\n")[0]).strip()) for n, t in qs]
    ans = {}
    for m in re.finditer(r"^\s*(\d+)[.．]\s*問い[:：](.+?)^\s*答え[:：]\s*(.+?)(?=^\s*\d+[.．]\s*問い[:：]|\Z)", amd, re.M | re.S):
        ans[int(m.group(1))] = re.sub(r"\s+", "", m.group(3)).strip()
    return [(n, q, ans.get(n, "")) for n, q in qs]
def parse_kakfile(t):
    """<文書>.確認事項.md を「先に答える問い」と「そのほか」の2つの一覧にする。"""
    first, rest, cur = [], [], None
    for l in t.splitlines():
        if re.match(r"^##\s*先に答える", l): cur = first; continue
        if re.match(r"^##\s*そのほか", l): cur = rest; continue
        m = re.match(r"^\s*(?:[-*]|\d+[.．])\s+(.+)", l)
        if m and cur is not None: cur.append(m.group(1).strip())
    return first, rest

def load(name):
    d = DATA / name
    t = {k: (d / f).read_text() for k, f in [("before", "doc.md"), ("after", "doc-review.md"), ("redesign", "doc-redesign.md"), ("logic", "report-logic.md"), ("somo", "report-somosomo.md"), ("plans_md", "plans.md"), ("q_md", "questions.md"), ("a_md", "answers.md"), ("kak_md", "doc.確認事項.md"), ("kakr_md", "doc-redesign.確認事項.md")]}
    t["P0"], t["P1"], t["P2"] = parts(t["before"]), parts(t["after"]), parts(t["redesign"])
    t["qa"] = parse_qa(t["q_md"], t["a_md"])
    t["kak_first"], t["kak_rest"] = parse_kakfile(t["kak_md"])
    t["kakr_first"], t["kakr_rest"] = parse_kakfile(t["kakr_md"])
    t["kak"] = t["kak_first"] + t["kak_rest"]; t["kak_r"] = t["kakr_first"] + t["kakr_rest"]
    assert len(t["qa"]) == 3 and all(a for _, _, a in t["qa"]), (name, t["qa"])
    assert "要確認" not in t["after"] and "要確認" not in t["redesign"], name
    assert "確認事項" not in "".join(h for h, _ in sections(t["after"])) and "確認事項" not in "".join(h for h, _ in sections(t["redesign"])), name
    assert t["P1"]["kak"] == 0 and t["P2"]["kak"] == 0, name
    return t
SETS = {n: load(n) for n in ("ringi", "teian", "kikaku")}
R0 = SETS["ringi"]
before, after, redesign, logic, somo, plans_md = (R0[k] for k in ("before", "after", "redesign", "logic", "somo", "plans_md"))
P0, P1, P2, kak, kak_r = R0["P0"], R0["P1"], R0["P2"], R0["kak"], R0["kak_r"]
assert P0["body"] == 3299, P0

def _field(body, names):
    """「**主張**:…」「- **主張**:…」のような1行の項目を取る。"""
    for n in names:
        m = re.search(r"^\s*-?\s*\*{0,2}" + n + r"\*{0,2}\s*[:：](.+)$", body, re.M)
        if m: return m.group(1).strip()
    return ""
def _block(body, names):
    """見出し行(「**縮めた決裁事項**…」)に続く箇条書きを取る。次の太字見出しか空行2つで終わる。"""
    for n in names:
        m = re.search(r"^\s*-?\s*\*{0,2}" + n + r"[^\n]*\n((?:\s*(?:[-*]|\d+\.)\s+.+\n?)+)", body, re.M)
        if m:
            out = []
            for l in m.group(1).splitlines():
                t = re.sub(r"^\s*(?:[-*]|\d+\.)\s+", "", l).strip()
                if not t: continue
                if re.match(r"\*\*", t) or re.match(r"(答える問い|弱点|この案)", t): break
                out.append(t)
            return out
    return []
def parse_plans(md):
    plans = []
    for m in re.finditer(r"^## (案[A-Z0-9０-９])\s*[:：]?\s*(.+?)$([\s\S]*?)(?=^## |\Z)", md, re.M):
        key, title, body = m.group(1), m.group(2).strip(), m.group(3)
        title = re.sub(r"\s*[-─━]{2,}\s*", " ", title)
        shrink = "小さくする" in title or "縮め" in title[:12]
        outline = _block(body, ["本編の骨組み", "骨組み"])
        if not outline:
            outline = [x.strip() for x in re.split(r"[／/]", _field(body, ["骨組み"])) if x.strip()]
        plans.append(dict(key=key, title=title, shrink=shrink,
                          claim=_field(body, ["主張"]),
                          weak=_field(body, ["弱点"]),
                          outline=outline,
                          shrunk=_block(body, ["縮めた決裁事項", "頼む中身の縮め方"]),
                          topple=_block(body, ["この案で元の決裁事項が倒れる問い", "元の決裁事項を倒しうる問い", "どの問いの答えで元の決裁事項"]),
                          first=_field(body, ["この案を選ぶなら、先に見る問いの答え", "この案を選ぶなら先に見る答え", "この案を選ぶなら先に見る問い"])))
    tail = md[md.index("## 選んだ案"):] if "## 選んだ案" in md else md
    mm = re.search(r"(案[A-Z0-9０-９])", tail)
    chosen = mm.group(1) if mm else None
    for p in plans:
        p["weak"] = re.sub(r"[(（](?:[LSR]\d|somosomo|logic)[^)）]*[)）]", "", p["weak"]).replace("背骨にする", "中心に置く").strip()
    return plans, chosen
PLANS, CHOSEN = parse_plans(plans_md)
assert len(PLANS) == 3
for n, t in SETS.items():
    t["PLANS"], t["CHOSEN"] = parse_plans(t["plans_md"])
    assert len(t["PLANS"]) == 3 and t["CHOSEN"], n

# ---------- デザイントークン(デジタル庁デザインシステム v2.1.0) ----------
TOKENS = """
:root{
  --sans:'Noto Sans JP',sans-serif;--mono:ui-monospace,'SF Mono',Menlo,monospace;
  --fs-13:.8125rem;--fs-14:.875rem;--fs-16:1rem;--fs-17:1.0625rem;--fs-18:1.125rem;--fs-20:1.25rem;--fs-24:1.5rem;--fs-28:1.75rem;--fs-32:2rem;--fs-36:2.25rem;
  --r-4:.25rem;--r-8:.5rem;--r-12:.75rem;--r-full:624.9375rem;
  --key-50:#e8f1fe;--key-100:#d9e6ff;--key-200:#c5d7fb;--key-400:#7096f8;--key-800:#0031d8;--key-900:#0017c1;--key-1000:#00118f;
  --ok:#197a4b;--ok-50:#e6f5ec;--ng:#ce0000;--ng-50:#fdeeee;--warn:#b78f00;--warn-50:#fbf5e0;--warn-100:#fff0b3;--orange:#c74700;--orange-50:#ffeee2;
  --g-50:#f2f2f2;--g-100:#e6e6e6;--g-200:#cccccc;--g-300:#b3b3b3;--g-700:#4d4d4d;--g-800:#333333;--g-900:#1a1a1a;
  --elev:0 2px 8px 1px rgba(0,0,0,.1),0 1px 5px 0 rgba(0,0,0,.3);
}
"""
JA = 'font-feature-settings:"palt" 1;line-break:strict;word-break:auto-phrase;text-autospace:normal;-webkit-text-size-adjust:100%;'
FONT = '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;700;900&display=swap" rel="stylesheet">'

DOC_CSS = """
.doc{padding:24px clamp(16px,3vw,32px) 64px;color:var(--g-900);font:400 var(--fs-16)/1.75 var(--sans)}
.doc article{max-width:40em}
.doc h1{font-size:var(--fs-24);line-height:1.4;margin:0 0 24px;text-wrap:balance}
.doc h2{font-size:var(--fs-20);line-height:1.4;margin:48px 0 12px;padding-top:16px;border-top:1px solid var(--g-200);text-wrap:balance}
.doc h3{font-size:var(--fs-17);line-height:1.5;margin:28px 0 8px}
.doc h4{font-size:var(--fs-16);margin:20px 0 6px}
.doc p{margin:0 0 1em}
.doc ul,.doc ol{padding-left:1.6em;margin:0 0 1em}
.doc li{margin:.3em 0}
.doc hr{border:0;border-top:1px solid var(--g-200);margin:32px 0}
.doc table{border-collapse:collapse;width:100%;margin:0 0 1.2em;font-size:var(--fs-14);line-height:1.6;font-variant-numeric:tabular-nums}
.doc th,.doc td{border:1px solid var(--g-200);padding:8px 10px;text-align:left;vertical-align:top}
.doc th{background:var(--g-50);font-weight:700}
.doc code{font-family:var(--mono);font-size:.92em;background:var(--g-50);padding:1px 4px;border-radius:var(--r-4)}
"""
DOCS = {k: markdown.markdown(v, extensions=["tables"]) for k, v in
        [("before", before), ("after", after), ("redesign", redesign), ("kak", R0["kak_md"]), ("logic", logic), ("somosomo", somo)]}

# ---------- 3つの例 ----------
def bars_svg(t, label="元の文書"):
    rows = [(label, t["P0"]), ("直した後", t["P1"]), ("組み直した後", t["P2"])]
    mx = max(sum(p.values()) for _, p in rows)
    W = 1000; LBL = 150; BAR = W - LBL - 110; ROW = 46; H = ROW * 3 + 40
    s = f'<svg viewBox="0 0 {W} {H}" class="fig bars" role="img" aria-label="3つの文書の字数を、本編・付録・確認事項に分けた積み上げ棒">'
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
    y = 10 + 3 * ROW + 6
    for j, (lab, cls) in enumerate((("本編(決裁者が読む)", "s-body"), ("付録", "s-app"))):
        x = LBL + j * 230
        s += f'<rect x="{x}" y="{y}" width="14" height="14" class="{cls}"/><text x="{x+20}" y="{y+12}" class="mn">{E(lab)}</text>'
    s += '</svg>'
    return s


# ---------- 3つの文書の例(タブ) ----------
# 文の中の <em> は、直す前後で変わった語。引用は文書の文そのまま。
DOCSETS = [
    ("ringi", "稟議書", "営業部の12名で、議事録を作る AI ツールを6か月、上限60万円で試験導入したいという社内の申請。読むのは経営会議。"),
    ("kikaku", "社内の制度企画", "人事企画が、内勤180名を対象に週1日の在宅勤務制度を来年4月から始めたいという企画。読むのは経営会議。"),
    ("teian", "コンサルの提案資料", "コンサルティング会社が食品卸に、営業のデジタル化支援(3か月の診断と6か月の導入支援、2,700万円)を提案する資料。読むのは先方の営業本部長と経営会議。"),
]
PICKS_BY = {
 # src: ("ask", n) は起案者への問い n の答えで直った箇所。("doc", 問い) は文書の中で答えが出るので聞かずに直した箇所
 "ringi": [
    dict(title="「週に平均8件」は部全体か、1人あたりか", src=("ask", 1),
        before=[(20, "<em>営業部では</em>、顧客打ち合わせが週に平均8件(月に約35件)ある。")],
        after=[(18, "<em>営業部全体の</em>顧客打ち合わせは週平均8件(月約35件)で、担当者は打ち合わせのあと、手書きメモから議事録を作っている。"),
               (20, "件数は、<em>営業支援システムの訪問記録の直近6か月から出した</em>。12名で割ると、<em>1人あたり月3件ほど</em>になる。")],
        note="元の文書だけでは、部全体か1人あたりか決まらない。1人あたりなら試算は12倍ずれる。起案者の答えで決まり、出どころと1人あたりの件数が本文に入った。"),
    dict(title="空欄だった時間単価が入り、損益の分かれ目が本文に出た", src=("ask", 2),
        before=[(62, "当社の営業担当者の時間単価:<em>【 】円(人事・経理部門に確認して記入)</em>")],
        after=[(25, "先月の試行と同じ30分の削減では、すべての打ち合わせで使っても、費用が、削減できる時間の人件費を上回る。下回るのは<em>1件あたり約39分以上減った場合</em>で、そこまで減るかをこの試験導入で確かめる。")],
        note="起案者が答えた標準単価(1時間3,500円)と、元の文書にある月額79,200円から、損益の分かれ目(月約22.6時間、1件あたり約39分)を計算して本文に書いた。元の試算の30分では費用が人件費を上回る、と本文が言うようになった。"),
    dict(title="契約前に確かめるとしていた解約の条件が、確かめた事実になった", src=("ask", 3),
        before=[(103, "6か月で解約できるかなど、契約期間と中途解約の条件を<em>契約前に確認する</em>")],
        after=[(48, "<em>最低契約期間はなく、月単位で解約できる(販売店に確認済み)</em>。途中で縮小や中止をすれば、費用も止められる。")],
        note="答えのうち「支払いの方法は分からない」「社内規程との突き合わせはまだ」は、本文で「どれもまだ確かめていない」と書き、確認事項の先頭の問いになった。"),
    dict(title="根拠のない言い切りは、聞かずに弱めた", src=("doc", "「議事録の正確さは担当者のメモの取り方に左右される」は、何を確かめて言っているのか。文書の中に根拠はない"),
        before=[(22, "手書きメモと記憶をもとに作るため、議事録の正確さは担当者のメモの取り方に<em>左右される</em>。")],
        after=[(21, "手書きメモと記憶をもとに作るため、議事録の正確さは担当者のメモの取り方に<em>左右されると考えている</em>。")],
        note="文書の中で答えが出る指摘(根拠のない言い切り、矛盾、計算)は、起案者に聞かずに直す。"),
 ],
 "kikaku": [
    dict(title="本日決めるのは「4月開始」か、「4月を目標に準備を始めること」か", src=("ask", 1),
        before=[(10, "内勤の従業員180名を対象に、週1日の在宅勤務制度を <em>2027年4月から</em> 始めること")],
        after=[(10, "内勤の従業員180名を対象に、週1日の在宅勤務制度を、<em>2027年4月 の開始を目標に作ること</em>"),
               (13, "<em>試行で業務に支障が出た場合は、開始を延期します。</em>")],
        note="起案者の答えは「方針の承認で、開始日は2月に改めて決めてもらう形でもよい」。決裁事項の文がそれに合わせて変わり、延期の余地が本文に書かれた。「何を支障と見るか」は答えがなかったので、確認事項の先頭の問いになった。"),
    dict(title="「退職理由の上位」が、人数の内訳になった", src=("ask", 2),
        before=[(25, "| 退職者アンケート | 「働き方の柔軟性のなさ」が<em>退職理由の上位</em> | — |")],
        after=[(22, "| 退職者アンケート | <em>回答した22名のうち9名</em>が「働き方の柔軟性のなさ」を挙げた（<em>内勤7名、内勤以外2名</em>）。自由記述で在宅勤務に触れたのは4名 | — |")],
        note="離職率は250名全体の数字で、対象は内勤180名。辞めた人が対象の中にいるのかは、起案者に聞かないと分からない。答えの数字がそのまま入り、「上位」という言葉は本文から消えた。順位は答えがなかったので確認事項に残った。"),
    dict(title="「分からない」という答えで、言い切りが消えた", src=("ask", 3),
        before=[(127, "週1日・曜日の割り当て制で始めれば、VPNの上限の<em>範囲内で運用できる見込みです</em>")],
        after=[(80, "曜日を割り当てれば、在宅勤務者の数はVPNの上限を大きく下回ります。<em>外勤の方などの利用を足した数は確認中です</em>")],
        note="外勤のVPN利用は「情報システム部に聞いているが、まだ答えをもらっていない」という答えだった。本文は分かっている範囲(在宅勤務者だけなら下回る)と分かっていない範囲を分けて書く形になった。"),
    dict(title="2つの理由を1つの言い切りにしていた文は、聞かずに分けた", src=("doc", "「辞める理由」と「選ばれない理由」の両方と言うが、採用の側は応募数や内定承諾率で確かめたのか。文書の中に材料はない"),
        before=[(27, "在宅勤務がないことは「辞める理由」と「選ばれない理由」の両方に<em>なっていると考えます</em>。")],
        after=[(17, "在宅勤務がないことは、辞める理由の一つに<em>なっていると考えます</em>。"),
               (26, "採用でも、競合2社が制度を持っているので、在宅勤務がないことが選ばれない理由に<em>なるおそれがあります</em>。")],
        note="辞める側は起案者の答え(内勤7名)で支えられたが、採用の側は文書に材料がないので、見込みの形に弱めた。"),
 ],
 "teian": [
    dict(title="「実際に失注が起きています」の出どころが、本文に入った", src=("ask", 2),
        before=[(33, "御社ではこの引き継ぎの場面で<em>実際に失注が起きています</em>。")],
        after=[(34, "<em>営業本部長からは、この引き継ぎで2社を失ったとうかがっています。ただ、その理由はまだ確かめていません。</em>昨年の異動・退職は合わせて4名とうかがっていますが、担当が替わった顧客の数や、失注の件数と金額は分かっていません。")],
        note="起案者の答えは「営業本部長が『引き継ぎで2社失った』と話したのを聞いただけ。理由は聞いていない。件数と金額は分からない」。本文はその答えを、強めも弱めもせずに書いた。提案の前提が「聞いた話」であることが、読む人に分かるようになった。"),
    dict(title="経営会議が承認するのは、2,700万円か、900万円か", src=("ask", 1),
        before=[(19, "| 費用 | 月額300万円、<em>総額2,700万円</em>(SFA のライセンス費は別途) |")],
        after=[(18, "| <em>ご承認いただきたいこと</em> | 9か月・総額2,700万円のご契約(<em>3か月目で止められる形</em>) |"),
               (128, "当社の支援費用は月額300万円です。<em>フェーズ1だけのご契約も可能で、その場合も費用は900万円です。</em>")],
        note="元の文書では、3か月目に止められると書きながら、承認を求める額がどちらか分からなかった。答えで「9か月・2,700万円。フェーズ1だけの契約もできる」と決まり、要点の表の先頭に承認を求めることが入った。止めたときの支払いの条件は答えがなく、確認事項の先頭の問いになった。"),
    dict(title="3か月目に判断するのは誰か", src=("ask", 3),
        before=[(21, "| 判断の区切り | 現状診断が終わる3か月目の時点で、診断結果をもとに導入フェーズへ進むかどうかを<em>ご判断いただけます</em> |")],
        after=[(22, "| 判断の区切り | 現状診断が終わる3か月目に、診断結果をもとに<em>営業本部長に</em>導入フェーズへ進むかどうかをご判断いただけます |")],
        note="答えは「営業本部長が判断する想定。経営会議にかけるかは分からない。基準も決めていない」。判断する人は本文に入り、基準は確認事項に残った。"),
    dict(title="見込みの効果の言い切りは、聞かずに弱めた", src=("doc", "「失注を減らせます」は導入後に起きると見込んでいることなのに、確かめた効果と同じ言い切りになっている。同じ節で「同じ数字をお約束するものではなく」とも書いていて、強さがそろっていない"),
        before=[(93, "引き継ぎルールを整えることで、口頭説明だけに頼る引き継ぎがなくなり、情報の抜け落ちによる失注を<em>減らせます</em>。")],
        after=[(94, "引き継ぎルールを整えて口頭説明だけに頼る引き継ぎをなくせば、情報の抜け落ちによる失注は<em>減らせると見込んでいます</em>。")],
        note="確信の度合いが文書の中でそろっていない箇所は、起案者に聞かずに、根拠に合う強さに直す。"),
 ],
}
SPINE = [  # 組み直しで、論の組み立てが何から何に替わったか(本文を書いた案)
    ("ringi", "効果を言い切る稟議", "6か月で3つの問い(費用に見合うだけ減るか、顧客が録音に同意するか、規程どおり管理できるか)に答える試験として頼む"),
    ("kikaku", "4月開始を一度で承認してもらう", "本日決めることと2月に決めることを分けて示す"),
    ("teian", "9か月・2,700万円の一括の提案", "最初の3か月で課題の大きさと原因を確かめ、3か月目の判断を背骨にする"),
]

def EM(t):
    """<em> だけ残してエスケープする。"""
    t = html.escape(t).replace("&lt;em&gt;", "<em>").replace("&lt;/em&gt;", "</em>").replace('&lt;em class=&quot;same&quot;&gt;', '<em class="same">')
    return t
def quote(ln, t):
    if ln is None: return f'<p class="gone">{EM(t)}</p>'
    return f'<blockquote><span class="ln">行{ln}</span><p>{EM(t)}</p></blockquote>'
def lines_label(ls): return "、".join(f"行{l}" for l in ls)

ICON = '<svg aria-hidden="true" width="24" height="24" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" fill="#fff"/><path d="M12 15.2 6.8 10l1.06-1.06L12 13.08l4.14-4.14L17.2 10 12 15.2Z" fill="currentColor"/><circle cx="12" cy="12" r="10.5" stroke="currentColor" fill="none"/></svg>'
def disclosure(label, body, cls=""):
    return f'<details class="dsc {cls}"><summary>{ICON}<span>{E(label)}</span></summary><div class="dsc-body">{body}</div></details>'

def pick_html(p, key, qa):
    kind_, ref = p["src"]
    if kind_ == "ask":
        n, q, ans = qa[ref - 1]
        src_tag = f'<span class="st st-ask">起案者の答えで直った</span>'
        qs = f'''<div class="q q-ask"><span class="tag">スキルの問い {n}</span><p>{E(q)}</p></div>
      <div class="q q-ans"><span class="tag">起案者の答え</span><p>{E(ans)}</p></div>'''
        dsc = disclosure(f"問い {n} と起案者の答え", qs)
    else:
        src_tag = f'<span class="st st-doc">文書の中で直した</span>'
        dsc = disclosure("検査が出した問い", f'<div class="q q-logic"><span class="tag">検査</span><p>{E(ref)}</p></div>')
    return f'''<div class="ex">
  <h4 class="ex-t">{E(p["title"])} {src_tag}</h4>
  <div class="ba">
    <div><h5>元の文書</h5>{"".join(quote(*q) for q in p["before"])}</div>
    <div><h5>直した後</h5>{"".join(quote(*q) for q in p["after"])}</div>
  </div>
  <p class="note">{E(p["note"])}</p>
  {dsc}
</div>'''

def qa_html(key, qa):
    items = "".join(f'<li><p class="qq">{E(q)}</p><p class="qa"><span class="tag">起案者の答え</span>{E(a)}</p></li>' for n, q, a in qa)
    return f'<ol class="qa-list">{items}</ol>'

def doc_panel(i, key, label, desc):
    t = SETS[key]
    nums = f'本編の字数 {fmt(t["P0"]["body"])} → {fmt(t["P1"]["body"])}。別ファイルの確認事項 {len(t["kak"])} 件(先に答える問い {len(t["kak_first"])} 件)。元にも起案者の答えにもない事実 0。' + ("" if key == "ringi" else "全文は下の「文書を読む」にはなく、リポジトリにあります。")
    kak_first = "".join(f'<li>{E(x)}</li>' for x in t["kak_first"])
    kak_rest = "".join(f'<li>{E(x)}</li>' for x in t["kak_rest"])
    kak_body = f'<p class="cap">先に答える問い</p><ol class="kak">{kak_first}</ol><p class="cap">そのほか</p><ul class="kak kak-rest">{kak_rest}</ul>'
    return f'''<div class="dads-tab__panel pick" id="doc-panel-{i}" role="tabpanel" aria-labelledby="doc-tab-{i}" tabindex="0"{"" if i == 1 else " hidden"}>
  <p class="desc">{E(desc)}</p>
  <h4 class="ex-t">スキルが起案者に聞いた3つ</h4>
  {qa_html(key, t["qa"])}
  <p class="note">答えは、このページの作者が起案者の役で、スキルを動かす前に書いた事実の一覧から、別のセッションの Claude が答えたもの。一覧にないことは「分からない」と答える決まりで動かした。</p>
  {"".join(pick_html(p, key, t["qa"]) for p in PICKS_BY[key])}
  <p class="nums">{E(nums)}</p>
  {disclosure(f"別ファイルに出した確認事項 {len(t['kak'])} 件", kak_body)}
</div>'''

def _norm(t): return re.sub(r"[\s|*]", "", re.sub(r"<[^>]+>", "", t))
for _key, _picks in PICKS_BY.items():
    _t = SETS[_key]
    for _p in _picks:
        for _ln, _q in _p["before"]:
            if _ln is not None: assert _norm(_q) in _norm(_t["before"]), (_key, "before", _ln)
        for _ln, _q in _p["after"]:
            if _ln is not None and "(中略)" not in _q: assert _norm(_q) in _norm(_t["after"]), (_key, "after", _ln)
tabs_html = '<ul class="dads-tab__list" role="tablist" aria-label="3つの文書">' + "".join(
    f'<li><button type="button" class="dads-tab__tab" role="tab" id="doc-tab-{i+1}" aria-selected="{"true" if i == 0 else "false"}" aria-controls="doc-panel-{i+1}" tabindex="{0 if i == 0 else -1}"><span>{E(label)}</span></button></li>'
    for i, (key, label, desc) in enumerate(DOCSETS)) + '</ul>'
picks_html = f'<div class="dads-tab" data-position="top">{tabs_html}<div class="dads-tab__panels">{"".join(doc_panel(i + 1, k, l, d) for i, (k, l, d) in enumerate(DOCSETS))}</div></div>'

def _shrink_of(key):
    p = next((p for p in SETS[key]["PLANS"] if p["shrink"]), None)
    return p["claim"] if p else ""
spine_html = '<table class="tbl spine"><thead><tr><th>文書</th><th>元の組み立て</th><th>決裁の範囲を絞る案(起案者が選ぶ)</th><th>本文を書いた案</th></tr></thead><tbody>' + "".join(
    f'<tr><th>{E(dict((k, l) for k, l, _ in DOCSETS)[key])}</th><td>{E(a)}</td><td class="sh">{E(_shrink_of(key))}</td><td>{E(b)}<small>本編 {fmt(SETS[key]["P0"]["body"])} → {fmt(SETS[key]["P2"]["body"])} 字</small></td></tr>'
    for key, a, b in SPINE) + '</tbody></table>'

# ---------- 図1:流れ(押すと説明が出る) ----------
NODES = {
    "src": ("文書", ["AI が書いたまま"], "src", "このページの例は、スキルなしの Claude Code(Opus 5.5)に短い依頼文から書かせた架空の稟議書・制度企画・提案資料です。わざと穴を作らせたのではなく、書かせたままの文書です。どれも丁寧に書かれていて、稟議書は1名1件の試行を「参考値」と断り、開始前に基準を測る設計まで入っています。"),
    "logic": ("筋を見る", ["文書の中だけで", "矛盾・根拠のない主張・食い違い"], "k", "文書の中だけで読み、矛盾、根拠のない主張、事実と推論の混在、挙げた項目の抜けや食い違いを、行番号つきの問いにします。稟議書の例では18件でした。"),
    "somo": ("前提を疑う", ["決裁者の立場で", "前提・他の選択肢・覆る条件"], "o", "決裁者の立場で読み、決裁者が何を決める文書かを1行で押さえたうえで、前提は妥当か、解こうとしている課題の立て方は合っているか、他の選択肢と比べたか、何が起きたら結論が覆るか、誰が実行するかを問います。決裁事項を覆しうる問いを3つまで先頭に置きます。稟議書の例では14件でした。"),
    "ask": ("起案者に3つだけ聞く", ["起案者にしか答えられないこと", "文書の中で答えが出ることは聞かない"], "q", "2つの検査の問いのうち、文書の中で答えが出るもの(矛盾、計算、言い切りの強さ、並べて挙げた項目どうしの食い違い)は聞かずに直します。起案者に聞くのは、文書にない事実、決裁者に何を決めてもらうつもりか、どこまで頼むか、のように起案者にしか答えられないことだけで、3つまでです。「分からない」という答えも答えです。"),
    "fix": ("直した文書", ["答えを本文に入れる", "残りの問いは別ファイルの確認事項に"], "k", "起案者の答えを、強めず弱めず、出どころを添えて本文に入れます。「分からない」だった箇所は仮定の形にします。文書の中で直せる指摘はすべて直し、裏づけの試算や体制は付録に移します。残りの問いは文書の中には書かず、別のファイル(稟議書.確認事項.md)に「先に答える問い」3件までと「そのほか」に分けて出します。直した文書には、直した箇所の印も確認事項の節も入らないので、そのまま出せます。事実は足さず、起案者の代わりに決めず、本編を元より長くしません。頼み方:「稟議書.md を決裁者の目で見て直して」"),
    "re": ("組み直す", ["頼んだときだけ", "事実と決裁事項は保ち、論の背骨を替える"], "k", "検査のあとに別に頼みます。事実・数値・主結論・決裁を求める事項は保ったまま、論の組み立てだけを替えます。構成案を2〜3つ出し、そのうち1つは必ず決裁の範囲を絞る案で、起案者が選んだ案で書きます。頼み方:「構成から組み直して」"),
}
def flow_svg():
    W, H = 1000, 300
    def box(key, x, y, w, h):
        title, sub, cls, _ = NODES[key]
        t = f'<g class="node {cls}" data-node="{key}" role="button" tabindex="0" aria-pressed="false" aria-label="{E(title)}の説明を見る"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" class="bx"/>'
        t += f'<text x="{x+w/2}" y="{y+34}" class="bt" text-anchor="middle">{E(title)}</text>'
        for i, s in enumerate(sub):
            t += f'<text x="{x+w/2}" y="{y+58+i*20}" class="bs" text-anchor="middle">{E(s)}</text>'
        return t + '</g>'
    def arrow(x1, y1, x2, y2):
        mx = (x1 + x2) / 2
        return f'<path d="M{x1},{y1} C{mx},{y1} {mx},{y2} {x2},{y2}" class="ar" marker-end="url(#ah)"/>'
    s = f'<svg viewBox="0 0 {W} {H}" class="fig flow" role="group" aria-label="流れ:文書を2つの見方で検査し、起案者に3つだけ聞いて、答えを入れた文書を返す。頼めば組み直す">'
    s += '<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#4d4d4d"/></marker></defs>'
    s += arrow(140, 150, 190, 80) + arrow(140, 150, 190, 220) + arrow(370, 80, 420, 150) + arrow(370, 220, 420, 150) + arrow(680, 150, 730, 80)
    s += f'<path d="M680,150 C705,150 705,220 730,220" class="ar dashed" marker-end="url(#ah)"/>'
    s += box("src", 10, 100, 130, 100) + box("logic", 190, 30, 180, 100) + box("somo", 190, 170, 180, 100)
    s += box("ask", 420, 100, 260, 100) + box("fix", 730, 30, 260, 100) + box("re", 730, 170, 260, 100)
    return s + '</svg>'
flow_list = "".join(f'<li><details class="dsc"><summary>{ICON}<span>{E(v[0])}</span></summary><div class="dsc-body"><p>{E("、".join(v[1]))}。</p><p>{E(v[3])}</p></div></details></li>' for v in NODES.values())
node_desc = "".join(f'<div class="nd" data-for="{k}" hidden><b>{E(v[0])}</b><p>{E(v[3])}</p></div>' for k, v in NODES.items())

# ---------- 図2:節の移動(ホバーで強調) ----------
MOVES_RINGI = {  # 稟議書は文を突き合わせて確かめた対応を固定で使う
    "申請内容": ["申請内容"], "背景と課題": ["付録A 背景と試算"], "導入するツール": ["付録F ツールの概要"],
    "期待効果": ["確かめること", "費用対効果", "付録A 背景と試算"], "費用": ["費用と止め方"],
    "実施体制": ["付録C 実施体制"], "リスクと対策": ["確かめること", "付録D リスクと対策"],
    "評価の方法": ["確かめること", "判断の基準", "付録B 評価の指標と測定"], "スケジュール": ["付録E スケジュール"],
    "決裁をお願いする事項": ["決裁をお願いする事項"],
}
def _hname(h): return re.sub(r"^##\s*(?:\d+[.．]\s*)?", "", h).strip()
def compute_moves(before_t, redesign_t, min_hits=2):
    """元の各節の文(14字の断片)が、組み直した後のどの節に現れるかを数えて対応を引く。"""
    new = [(_hname(h), b) for h, b in sections(redesign_t) if h and kind(h) != "kak"]
    out = {}
    for h, body in sections(before_t):
        if not h: continue
        text = "".join(l for l in body.splitlines() if l and not l.startswith("#"))
        text = re.sub(r"[|*\s]", "", text)
        hits = {}
        for i in range(0, max(1, len(text) - 14), 10):
            ch = text[i:i + 14]
            if len(ch) < 14: continue
            for nh, nb in new:
                if ch in re.sub(r"[|*\s]", "", nb): hits[nh] = hits.get(nh, 0) + 1
        out[_hname(h)] = [nh for nh, n in sorted(hits.items(), key=lambda x: -x[1]) if n >= min_hits]
    return out
NEW_OVERRIDE = {}
def mapping_svg(t, moves, key):
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
        new = (h in NEW_OVERRIDE[key]) if key in NEW_OVERRIDE else (k == "body" and not any(h in b or b in h for b in before_names))
        s += f'<g class="dst" data-dst="{i}"><rect x="{rx}" y="{y+3}" width="{bw}" height="{ROW-6}" rx="4" class="mr {k}{" new" if new else ""}"/>'
        s += f'<text x="{rx+10}" y="{y+ROW/2+5}" class="ml">{E(h)}{"(新しい節)" if new else ""}</text><text x="{rx+bw-10}" y="{y+ROW/2+5}" class="mn" text-anchor="end">{fmt(n)}</text></g>'
    x1, x2 = lx + bw, rx
    for i, (h, _) in enumerate(L):
        for d in moves.get(h, []):
            if d not in ry: continue
            y1 = ly[h]; y2, j = ry[d]
            mx = (x1 + x2) / 2
            s += f'<path d="M{x1},{y1} C{mx},{y1} {mx},{y2} {x2},{y2}" class="mv" data-src="{i}" data-dst="{j}"/>'
    return s + '</svg>'

# ---------- 構成案 ----------
LABELS = {}
def _clean(t):
    """検査の問いの番号(S3・L2-3、R1、反論A)はページの読み手には意味がないので落とす。行番号は残す。"""
    tok = r"(?:[SLRP]S?\d[\d\-]*|反論\d|反論[A-Z]|somosomo\s*\d[\d\-]*|logic\s*\d[\d\-]*)"
    t = re.sub(r"^" + tok + r"(?:\s*[・/、]\s*" + tok + r")*(?:[(（][^)）]*[)）])?\s*[:：]\s*", "", t)
    t = re.sub(r"[(（](?:[SLRP]S?\d[\d\-・/、SLRP]*|somosomo\s*[^)）]*|logic\s*[^)）]*)[)）]", "", t)
    t = re.sub(r"(?:[SLRP]S?\d[\d\-]*|反論\d|反論[A-Z])\s*(?:のとおり|の読みが立つ)[、。]?", "", t)
    t = re.sub(r"(?:[、(（]\s*)?(?:S\d[\d\-]*|L\d[\d\-]*|R\d|反論[A-Z0-9])(?:\s*[・/]\s*(?:S\d[\d\-]*|L\d[\d\-]*|R\d|反論[A-Z0-9]))*(?:[)）])?", lambda m: "" if m.group(0).strip().startswith(("、", "(", "（")) else m.group(0), t)
    t = re.sub(r"(?:[SLRP]S?\d[\d\-]*)\s*[(（]([^)）]*)[)）]", r"\1", t)
    t = re.sub(r"L矛盾\d+|S\d+-\d+", "", t)
    for k, v in LABELS.items(): t = t.replace(k, v)
    t = re.sub(r"[、，]\s*[、，]", "、", t).replace("(、", "(").replace("・)", ")").replace("()", "")
    return re.sub(r"\s{2,}", " ", t).strip("、 ")
def plan_block(p, chosen):
    sel = p["key"] == chosen
    title = re.sub(r"^頼む中身を(?:小さくする|保つ)案?\s*[:：]?\s*", "", p["title"])
    title = re.sub(r"\s*[(（](?:採用|選んだ案)[)）]\s*", "", title).strip()
    p = dict(p, title=title, claim=_clean(p["claim"]), weak=_clean(p["weak"]))
    ol = "".join(f"<li>{E(x)}</li>" for x in p["outline"]) if p["outline"] else ""
    body = f'<p class="claim">{E(p["claim"])}</p>' + (f'<ol>{ol}</ol>' if ol else '') + f'<p class="weak"><b>弱点</b> {E(p["weak"])}</p>'
    if p["shrink"]:
        shrunk = "".join(f"<li>{E(_clean(x))}</li>" for x in p["shrunk"][:3])
        topple = "".join(f"<li>{E(_clean(x))}</li>" for x in p["topple"][:3])
        return f'''<div class="plan shrink"><h4>{E(p.get("label", p["key"]))} {E(p["title"])} <span class="st st-shrink">決裁の範囲を絞る案</span></h4>
      <p class="claim">{E(p["claim"])}</p>
      {('<p class="lbl">縮めた決裁事項</p><ul>' + shrunk + '</ul>') if shrunk else ''}
      {('<p class="lbl">どの問いの答えで、元の決裁事項が倒れるか</p><ul>' + topple + '</ul>') if topple else ''}
      {('<p class="weak"><b>先に答えを確かめたい問い</b> ' + E(_clean(p["first"])) + '</p>') if p["first"] else ''}
      <p class="weak"><b>弱点</b> {E(p["weak"])}</p></div>'''
    if sel:
        return f'<div class="plan sel"><h4>{E(p.get("label", p["key"]))} {E(p["title"])} <span class="st st-fixed">本文を書いた案</span></h4>{body}</div>'
    return disclosure(f'{p.get("label", p["key"])} {p["title"]}', body, "plan-alt")
WHY = {
    "ringi": "案1は決裁を「開始前の確認と測定」に絞り、契約条件とデータの扱い、担当者ごとの打ち合わせ件数と作成時間を手元で確かめてから、その結果を添えて改めて導入を頼む案です。",
    "kikaku": "案1は本日の決裁を「準備と試行への着手」だけに絞り、4月から始めるかどうかは、試行の結果と退職理由の内訳がそろう2月に決めてもらう案です。",
    "teian": "案1は、引き継ぎ失注の規模を提案先の手元の数字で経営会議の前に概算し、そのうえで「3か月・900万円の現状診断」だけを先に頼み、フェーズ2は診断のあとで改めて頼む案です。コンサルの受注が小さくなる案を、スキルが代わりに選ぶことはありません。",
}
MAP_NOTE = {
    "ringi": "本編は「申請内容 → 背景 → 効果の見込み → 確かめ方と判断の基準 → 情報管理と顧客の同意 → 費用 → 決裁をお願いする事項」の7節になり、ツールの概要・試算・評価の指標・体制・スケジュールは付録に下がりました。「確かめ方と判断の基準」と「情報管理と顧客の同意」は、元の文書の評価の方法とリスクの表から、試験で答えを出す3つの問いとして組み直した節です。",
    "kikaku": "本編は「本日お諮りしたいこと → 本日決めることと2月に決めること → 導入する理由 → 制度の形 → VPNの上限 → 懸念と対策 → 進め方」の7節になり、制度の詳細・対策を決めている懸念・期待効果と測り方は付録に下がりました。「本日決めることと2月に決めること」は元にない節で、元の文書が「確認中」「2月の最終案で示す」と書いていた項目を1つに集めています。",
    "teian": "本編は「ご判断いただきたいこと → 現状の課題 → 最初の3か月で確かめること → 3か月目のご判断 → 進む場合の6か月 → 期待効果 → 費用 → 今後の進め方」になり、「ご判断いただきたいこと」と「3か月目のご判断」が独立した節になりました。B社の事例、定着の工夫、体制は付録です。",
}
DOC_LABEL = {k: l for k, l, _ in DOCSETS}
def redesign_panel(i, key):
    t = SETS[key]
    moves = compute_moves(t["before"], t["redesign"])
    _ordered = sorted(t["PLANS"], key=lambda p: 0 if p["shrink"] else 1)
    for _i, _p in enumerate(_ordered): _p["label"] = f"案{_i + 1}"
    LABELS.clear(); LABELS.update({_p["key"]: _p["label"] for _p in _ordered})
    plans = "".join(plan_block(p, t["CHOSEN"]) for p in _ordered)
    bars = bars_svg(t, "元の文書")
    note = disclosure("線の引き方", "<p>線は、元の節の文がどの節に移ったかを示します。作者が、元の各節の文を組み直した後の文書からスクリプトで探して引きました。1つの節から複数の線が出ているところは、文が分かれて移っています。</p>")
    return f'''<div class="dads-tab__panel pick" id="rd-panel-{i}" role="tabpanel" aria-labelledby="rd-tab-{i}" tabindex="0"{"" if i == 1 else " hidden"}>
  <h3 class="sec" style="margin-top:8px">構成案を3つ出し、起案者が1つ選ぶ</h3>
  <p class="sub">{E(WHY[key])} 3本とも、この例では作者が選ばずにスキルに任せたので、本文は決裁事項を変えない案で書いてあります。</p>
  {plans}
  <h3 class="sec">元の{len([h for h, _ in sections(t["before"]) if h])}節は、どこへ移ったか</h3>
  <p class="sub">{E(MAP_NOTE[key])} 左の節にポインタを重ねるか押すと、移った先の節が強く表示されます。</p>
  <div class="map-wrap">{mapping_svg(t, moves, key)}</div>
  <h3 class="sec">{"全体は増えたが、決裁者が読む本編は短くなった" if sum(t["P2"].values()) > t["P0"]["body"] else "本編を短くし、裏づけは付録に移した"}</h3>
  <p class="sub">決裁者が読む本編は {fmt(t["P0"]["body"])} 字から {fmt(t["P2"]["body"])} 字になりました。付録(決裁者が裏づけを見たいときに読む)を足すと、全体は {fmt(sum(t["P2"].values()))} 字です。確認事項は文書の外の別ファイルにあり、ここには数えていません。</p>
  <div class="bars-wrap">{bars}</div>
</div>'''
rd_tabs = '<ul class="dads-tab__list" role="tablist" aria-label="組み直した3つの文書">' + "".join(
    f'<li><button type="button" class="dads-tab__tab" role="tab" id="rd-tab-{i+1}" aria-selected="{"true" if i == 0 else "false"}" aria-controls="rd-panel-{i+1}" tabindex="{0 if i == 0 else -1}"><span>{E(label)}</span></button></li>'
    for i, (key, label, _) in enumerate(DOCSETS)) + '</ul>'
redesign_html = f'<div class="dads-tab" data-position="top">{rd_tabs}<div class="dads-tab__panels">{"".join(redesign_panel(i + 1, k) for i, (k, _, _) in enumerate(DOCSETS))}</div></div>'

CSS = TOKENS + """
:root{--yellow-300:#ffd43d;--g-420:#949494;--key-1200:#000060;--key-300:#9db7f9}
*{box-sizing:border-box}
html{scroll-behavior:smooth;scroll-padding-top:24px}
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}*{transition:none!important}}
body{margin:0;background:#fff;color:var(--g-900);font:400 var(--fs-16)/1.75 var(--sans);""" + JA + """}
::selection{background:var(--key-100)}
a{color:var(--key-900);text-decoration-thickness:1px;text-underline-offset:.2em}
a:hover{text-decoration-thickness:3px;color:var(--key-1000)}
a:active{color:var(--orange)}
:focus-visible{outline:4px solid #000;outline-offset:2px;border-radius:4px;box-shadow:0 0 0 2px var(--yellow-300)}
p{margin:0}
.wrap{max-width:1120px;margin:0 auto;padding:0 clamp(16px,4vw,40px)}
.band{background:var(--key-900);color:#fff;font-size:var(--fs-14);padding:10px 0}
.band .wrap{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap}
.band a{color:#fff}

/* 目次(DADS の toc を土台に、現在地をスクロールで追う) */
.toc{position:sticky;top:0;z-index:5;background:#fff;border-bottom:1px solid var(--g-200)}
.toc-inner{max-width:1120px;margin:0 auto;padding:0 clamp(16px,4vw,40px);display:flex;align-items:center;gap:16px}
.toc-h{margin:0;font-size:var(--fs-14);font-weight:700;color:var(--g-800);flex:none}
.toc-list{list-style:none;margin:0;padding:0;display:flex;gap:4px;overflow-x:auto;scrollbar-width:none;-webkit-overflow-scrolling:touch}
.toc-list::-webkit-scrollbar{display:none}
.toc-list li{flex:none}
.toc-list a{display:block;padding:10px 10px 8px;border-bottom:3px solid transparent;color:var(--g-800);text-decoration:none;font-size:var(--fs-14);white-space:nowrap;line-height:1.4}
.toc-list a:hover{text-decoration:underline;text-underline-offset:3px;color:var(--key-1000)}
.toc-list a[aria-current=location]{color:var(--g-900);font-weight:700;border-bottom-color:var(--key-900)}
@media (min-width:1560px){
  .toc{position:fixed;top:120px;left:calc((100vw - 1120px)/2 - 220px);width:200px;background:transparent;border:0;z-index:5}
  .toc-inner{display:block;padding:0}
  .toc-h{margin-bottom:8px;font-size:var(--fs-16)}
  .toc-list{display:block;overflow:visible;border-left:1px solid var(--g-200)}
  .toc-list a{padding:6px 12px;border-bottom:0;border-left:3px solid transparent;margin-left:-1px;white-space:normal}
  .toc-list a[aria-current=location]{border-left-color:var(--key-900)}
}
html{scroll-padding-top:56px}
@media (min-width:1560px){html{scroll-padding-top:24px}}
.hero{padding:48px 0 40px;border-bottom:1px solid var(--g-200)}
.hero .ver{font-size:clamp(3.5rem,9vw,6.5rem);font-weight:900;line-height:1;letter-spacing:-.03em;margin:0;color:var(--key-900);font-variant-numeric:tabular-nums}
.hero .ver small{font-size:.35em;font-weight:700;letter-spacing:0;margin-right:.15em}
.hero .meta{color:var(--g-700);font-size:var(--fs-14);margin:8px 0 28px}
.hero h1{font-size:clamp(var(--fs-24),3.2vw,var(--fs-36));line-height:1.4;margin:0 0 16px;text-wrap:balance;letter-spacing:-.01em;max-width:24em}
.hero .lead{font-size:var(--fs-17);max-width:40em;text-wrap:pretty;margin-bottom:12px}
.sk{font-family:var(--mono);font-size:.9em;background:var(--g-50);border:1px solid var(--g-200);border-radius:var(--r-4);padding:0 .35em;white-space:nowrap;color:var(--g-900)}
mark{background:var(--warn-100);color:inherit;padding:0 .1em;border-radius:2px}
mark.ok{background:var(--ok-50);box-shadow:inset 0 -2px 0 var(--ok)}
mark.key{background:var(--key-50);box-shadow:inset 0 -2px 0 var(--key-900)}
.cap{font-size:var(--fs-14);color:var(--g-700);margin:28px 0 8px}
.hero4{display:grid;grid-template-columns:1fr auto 1.1fr auto 1.1fr auto 1fr;gap:10px;align-items:start;margin-top:8px}
.hero4>div{font-size:var(--fs-14);line-height:1.7}
.hero4 h4{font-size:var(--fs-14);font-weight:700;margin:0 0 8px;padding-bottom:6px;border-bottom:1px solid var(--g-900);display:flex;justify-content:space-between;align-items:center;gap:8px}
.hero4 .arrow{align-self:center;color:var(--g-700);font-size:var(--fs-24);font-weight:700;padding-top:20px}
.hero4 .arrow::before{content:'→'}
.hero4 .tag{display:inline-block;font-weight:700;font-size:var(--fs-13);padding:0 8px;border-radius:var(--r-4);line-height:1.6}
.hero4 .tag-ask{background:var(--key-900);color:#fff}
blockquote.q-ask{background:var(--key-50);border:1px solid var(--key-200)}
blockquote.q-ans{background:var(--warn-50);border:1px solid var(--warn)}
.hero3{display:grid;grid-template-columns:1fr auto 1.2fr auto 1fr;gap:12px;align-items:start;margin-top:8px}
.hero3>div{font-size:var(--fs-14);line-height:1.7}
.hero3 h4{font-size:var(--fs-14);font-weight:700;margin:0 0 8px;padding-bottom:6px;border-bottom:1px solid var(--g-900);display:flex;justify-content:space-between;align-items:center;gap:8px}
.hero3 .arrow{align-self:center;color:var(--g-700);font-size:var(--fs-24);font-weight:700;padding-top:20px}
.hero3 .arrow::before{content:'→'}
.hero3 blockquote.q-somo{background:var(--orange-50);border:1px solid #ffc199}
.hero3 blockquote em{font-style:normal;background:var(--ok-50);box-shadow:inset 0 -2px 0 var(--ok)}
.hero3 .tag{display:inline-block;font-weight:700;font-size:var(--fs-13);padding:0 8px;border-radius:var(--r-4);line-height:1.6}
.hero3 .tag-somo{background:var(--orange);color:#fff}
.ba{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.ba h4{font-size:var(--fs-14);font-weight:700;margin:0 0 8px;padding-bottom:6px;border-bottom:1px solid var(--g-900);display:flex;justify-content:space-between;align-items:center;gap:8px}
blockquote{margin:0 0 10px;padding:12px 14px;background:var(--g-50);border-radius:var(--r-8);font-size:var(--fs-14);line-height:1.7}
blockquote p{margin:2px 0 0}
blockquote em{font-style:normal;background:var(--ok-50);box-shadow:inset 0 -2px 0 var(--ok);padding:0 .1em}
.ba>div:first-child blockquote em{background:var(--warn-100);box-shadow:none}
blockquote em.same{background:var(--ng-50);box-shadow:inset 0 -2px 0 var(--ng)}
.gone{font-size:var(--fs-14);color:var(--g-700);margin:0 0 10px;padding:0 14px}
.ln{display:inline-block;font-size:var(--fs-14);color:var(--g-700);font-variant-numeric:tabular-nums}
.legend{font-size:var(--fs-13);color:var(--g-700);margin:6px 0 0}
.legend i{display:inline-block;width:12px;height:12px;vertical-align:-1px;margin:0 4px 0 10px;border-radius:2px}

main section.block{padding:44px 0;border-bottom:1px solid var(--g-200)}
main h2{font-size:var(--fs-24);line-height:1.4;margin:0 0 8px;text-wrap:balance}
main .sub{max-width:40em;color:var(--g-800);margin-bottom:20px;text-wrap:pretty}
main h3.sec{font-size:var(--fs-18);margin:36px 0 8px}

/* ディスクロージャー(DADS) */
.dsc summary{display:flex;width:fit-content;align-items:flex-start;gap:8px;cursor:default;list-style:none;font-weight:700;font-size:var(--fs-16);color:var(--g-900)}
.dsc summary::-webkit-details-marker{display:none}
.dsc summary svg{flex:none;color:var(--key-1000);margin-top:calc((1lh - 24px)/2);transition:transform .15s}
.dsc[open]>summary svg{transform:rotate(180deg)}
.dsc summary:hover{text-decoration:underline;text-underline-offset:3px}
.dsc-body{padding:12px 0 4px 32px;font-size:var(--fs-14);line-height:1.7}
.dsc{margin:12px 0 0}

/* タブ(DADS) */
.dads-tab{position:relative;z-index:0;display:flex;flex-direction:column;font-size:var(--fs-16);line-height:1.7}
.dads-tab__list{position:relative;z-index:0;margin:-6px;overflow:hidden;display:flex;flex-wrap:wrap;padding:7px 6px 6px 7px;list-style:none}
.dads-tab__list>li{margin:0;display:contents}
.dads-tab__list::after{position:relative;flex-grow:1;border:0 solid var(--g-420);content:"";margin-left:-1px;width:1px;border-bottom-width:1px}
.dads-tab__tab{isolation:isolate;appearance:none;margin:-1px 0 0 -1px;display:flex;border:1px solid var(--g-420);background:#fff;padding:0;color:inherit;font:inherit;text-align:left;cursor:default;position:relative}
.dads-tab__tab::before{content:"";position:absolute;bottom:6px;width:100%;border:0 solid #fff}
.dads-tab__tab>span{position:relative;display:flex;flex-grow:1;align-items:center;gap:8px;border:0 solid var(--g-50);border-top-width:5px;padding:14px 16px;font-size:var(--fs-16);line-height:1.2}
.dads-tab__tab>span::before{content:"";position:absolute;top:-6px;right:0;left:0;height:6px}
.dads-tab__tab[aria-selected=true]>span{font-weight:700}
.dads-tab__tab[aria-selected=true]:not(:focus-visible)::before{border-bottom-width:1px}
.dads-tab__tab[aria-selected=true]>span::before{background:var(--key-900)}
.dads-tab__tab:not([aria-selected=true]):hover{background:var(--g-50)}
.dads-tab__tab:not([aria-selected=true]):hover>span{text-decoration:underline;text-underline-offset:3px}
.dads-tab__tab:not([aria-selected=true]):hover>span::before{background:var(--g-420)}
.dads-tab__tab:focus-visible{overflow:hidden;z-index:1}
.dads-tab__panels{flex-grow:1;display:flex;flex-direction:column}
.dads-tab__panel{border:solid var(--g-420);border-width:0 1px 1px;background:#fff;padding:20px clamp(16px,2.5vw,28px) 24px}
.tnum{display:inline-grid;place-items:center;width:24px;height:24px;border-radius:var(--r-full);background:var(--key-900);color:#fff;font-size:var(--fs-14);font-variant-numeric:tabular-nums}
.pick .desc{font-size:var(--fs-14);color:var(--g-800);margin:0 0 4px;max-width:44em}
.pick .nums{font-size:var(--fs-13);color:var(--g-700);margin:0 0 20px;font-variant-numeric:tabular-nums}
.ex{padding:16px 0 4px;border-top:1px solid var(--g-100)}
.ex-t{font-size:var(--fs-17);line-height:1.4;margin:0 0 12px;text-wrap:balance}
.ex-t .st{margin-left:8px;vertical-align:middle}
.ba h5{font-size:var(--fs-14);font-weight:700;margin:0 0 8px;padding-bottom:6px;border-bottom:1px solid var(--g-900)}
.spine{margin:8px 0 28px}
.spine td.n{white-space:nowrap}
.spine small{display:block;color:var(--g-700)}
.pick h3{font-size:var(--fs-18);line-height:1.4;margin:0 0 16px;text-wrap:balance}
.pick h3 .st{margin-left:8px;vertical-align:middle}
.q{margin:0 0 12px;padding:12px 14px;border:1px solid var(--g-200);border-radius:var(--r-8);font-size:var(--fs-14);line-height:1.7}
.q .tag{display:inline-block;font-weight:700;font-size:var(--fs-13);padding:0 8px;border-radius:var(--r-4);margin-right:8px;line-height:1.6}
.q-logic{border-color:var(--key-200);background:var(--key-50)}
.q-logic .tag{background:var(--key-900);color:#fff}
.q-somo{border-color:#ffc199;background:var(--orange-50)}
.q-somo .tag{background:var(--orange);color:#fff}
.q p{margin:4px 0 0}
.st{font-weight:700;font-size:var(--fs-13);padding:1px 10px;border-radius:var(--r-full);white-space:nowrap;display:inline-block}
.st-fixed{background:var(--ok);color:#fff}
.st-deferred{background:var(--warn-100);color:var(--g-900);border:1px solid var(--warn)}
.st-remains{background:var(--ng);color:#fff}
.st-ask{background:var(--key-900);color:#fff}
.st-doc{background:var(--g-100);color:var(--g-900);border:1px solid var(--g-700)}
.q-ask{border-color:var(--key-200);background:var(--key-50)}.q-ask .tag{background:var(--key-900);color:#fff}
.q-ans{border-color:var(--warn);background:var(--warn-50)}.q-ans .tag{background:var(--warn);color:var(--g-900)}
.qa-list{padding-left:1.6em;margin:0 0 16px;max-width:48em}.qa-list li{margin:0 0 12px}.qa-list .qq{margin:0;font-weight:700;font-size:var(--fs-14);line-height:1.7}.qa-list .qa{margin:4px 0 0;font-size:var(--fs-14);line-height:1.7}.qa-list .qa .tag{display:inline-block;font-weight:700;font-size:var(--fs-13);padding:0 8px;border-radius:var(--r-4);margin-right:6px;background:var(--warn);color:var(--g-900)}
.kak-rest{list-style:disc}
.st-shrink{background:var(--orange-50);color:var(--orange);border:1px solid var(--orange)}
.plan.shrink{border:2px dashed var(--orange)}
.plan .lbl{font-weight:700;margin:8px 0 2px}
.plan.shrink ul{margin:0 0 8px;padding-left:1.4em;color:var(--g-800)}
.hero3 blockquote.q-shrink{background:var(--orange-50);border:1px dashed var(--orange)}
.spine td.sh{color:var(--g-900)}
.note{font-size:var(--fs-14);line-height:1.7;color:var(--g-800);text-wrap:pretty;margin-top:8px}

/* 流れ図 */
.fig{width:100%;height:auto;display:block;font-family:var(--sans)}
.fig text{fill:var(--g-900);font-size:15px}
.flow .bx{fill:#fff;stroke:var(--g-300);stroke-width:1.5;transition:fill .15s}
.flow .k .bx{stroke:var(--key-900);stroke-width:2}
.flow .o .bx{stroke:var(--orange);stroke-width:2}
.flow .q .bx,.flow .src .bx{fill:var(--g-50);stroke:var(--g-900)}
.flow .bt{font-size:19px;font-weight:700}
.flow .bs{font-size:13px;fill:var(--g-700)}
.flow .ar.dashed{stroke-dasharray:6 5}.flow .ar{fill:none;stroke:var(--g-700);stroke-width:1.5}
.flow .node{cursor:pointer}
.flow .node:hover .bx{fill:var(--key-50)}
.flow .node[aria-pressed=true] .bx{fill:var(--key-900);stroke:var(--key-900)}
.flow .node[aria-pressed=true] text{fill:#fff}
.flow .node:focus-visible{outline:4px solid #000;outline-offset:2px;border-radius:8px}
.flow-hint{font-size:var(--fs-14);color:var(--g-700);margin:6px 0 0}
.nd{margin-top:12px;padding:16px 20px;border-left:4px solid var(--key-900);background:var(--key-50);border-radius:0 var(--r-8) var(--r-8) 0;max-width:44em}
.nd b{display:block;margin-bottom:4px}
.nd p{font-size:var(--fs-14);line-height:1.7}
.flow-list{display:none;list-style:none;margin:0;padding:0;font-size:var(--fs-14)}
.flow-list li{padding:6px 14px;border:1px solid var(--g-200);border-radius:var(--r-8);margin:0 0 8px}
.flow-list .dsc{margin:0}
.flow-list .dsc-body p{color:var(--g-800);margin-top:4px}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:28px}.stats.four{grid-template-columns:repeat(2,1fr)}
.stat{border:1px solid var(--g-200);border-radius:var(--r-8);padding:16px 18px}
.stat b{display:block;font-size:var(--fs-16);margin-bottom:2px}
.stat .n{font-size:var(--fs-32);font-weight:900;color:var(--key-900);line-height:1.1;font-variant-numeric:tabular-nums}
.stat .n small{font-size:var(--fs-14);font-weight:400;color:var(--g-700);margin-left:4px}
.stat .dsc summary{font-weight:400;font-size:var(--fs-14);color:var(--key-900)}
.stat .dsc-body{color:var(--g-800)}

/* 組み直す */
.keep{display:grid;grid-template-columns:1fr auto 1fr;gap:16px;align-items:stretch;margin:8px 0 8px}
.keep>div{border-radius:var(--r-8);padding:16px 20px;font-size:var(--fs-14);line-height:1.7}
.keep .k{border:2px solid var(--key-900)}
.keep .c{border:2px dashed var(--orange)}
.keep h4{margin:0 0 8px;font-size:var(--fs-16)}
.keep ul{margin:0;padding-left:1.3em}
.keep .mid::before{content:'→'}
.keep .mid{align-self:center;font-weight:700;color:var(--g-700);font-size:var(--fs-28);text-align:center;padding:0}
.plan{border:1px solid var(--key-900);box-shadow:inset 0 0 0 1px var(--key-900);border-radius:var(--r-8);padding:16px 18px;font-size:var(--fs-14);line-height:1.7;margin-bottom:8px}
.plan h4{font-size:var(--fs-16);margin:0 0 8px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.plan .claim,.dsc-body .claim{margin:0 0 10px;text-wrap:pretty}
.plan ol,.dsc-body ol{margin:0 0 10px;padding-left:1.6em;color:var(--g-800)}
.plan li,.dsc-body li{margin:1px 0}
.plan .weak,.dsc-body .weak{margin:0;color:var(--g-800)}
.plan-alt{margin:4px 0 0}
.map .mh{font-size:15px;font-weight:700}
.map .mr{fill:#fff;stroke:var(--g-300)}
.map .mr.body{stroke:var(--key-900);stroke-width:1.5}
.map .mr.app{fill:var(--g-50)}
.map .mr.new{fill:var(--warn-50);stroke:var(--warn)}
.map .ml{font-size:15px}
.map .mn{font-size:13px;fill:var(--g-700);font-variant-numeric:tabular-nums}
.map .mv{fill:none;stroke:var(--key-400);stroke-width:1.5;opacity:.8;transition:opacity .15s,stroke-width .15s}
.map .src{cursor:default}
.map.hl .mv{opacity:.12}
.map.hl .mv.on{opacity:1;stroke:var(--key-900);stroke-width:2.5}
.map.hl .dst .mr{opacity:.35}
.map.hl .dst.on .mr{opacity:1;stroke:var(--key-900);stroke-width:2}
.map.hl .dst text{opacity:.35}.map.hl .dst.on text{opacity:1}
.map .src:hover .mr,.map .src.on .mr{fill:var(--key-50);stroke:var(--key-900)}
.map .src:focus-visible{outline:4px solid #000;outline-offset:2px}
.bars .s-body{fill:var(--key-900)}.bars .s-app{fill:var(--key-400)}.bars .s-kak{fill:var(--key-200)}
.bars .bl{font-size:13px;font-variant-numeric:tabular-nums}.bars .bl.inv{fill:#fff}
.bars .mn{font-size:13px;fill:var(--g-700);font-variant-numeric:tabular-nums}.bars .ml{font-size:15px}

.kak{padding-left:1.6em;margin:0;font-size:var(--fs-14);line-height:1.7;max-width:44em}
.kak li{margin:0 0 10px;padding-left:4px}
.kak li::marker{color:var(--key-900);font-weight:700;font-variant-numeric:tabular-nums}
.kak li:target{background:var(--warn-50);border-radius:var(--r-4)}
.dsc-body .kak{padding-left:1.6em}

.tbl{border-collapse:collapse;width:100%;font-size:var(--fs-14);line-height:1.6;font-variant-numeric:tabular-nums;margin:8px 0 16px}
.tbl th,.tbl td{padding:10px 12px;border-top:1px solid var(--g-200);text-align:left;vertical-align:top}
.tbl thead th{border-top:0;border-bottom:2px solid var(--g-900);font-weight:700}
.tbl tbody th{font-weight:700;white-space:nowrap}
.tbl small{color:var(--g-700)}
.limits{max-width:40em;text-wrap:pretty;padding-left:1.3em;margin:0}
.limits li{margin:8px 0}
.cmd{display:flex;align-items:center;gap:12px;background:var(--g-900);color:#fff;border-radius:var(--r-8);padding:12px 16px;font-family:var(--mono);font-size:var(--fs-14);margin:8px 0 20px;max-width:44em}
.cmd code{flex:1;overflow:auto;white-space:nowrap}
.cmd button{appearance:none;border:1px solid #fff;background:transparent;color:#fff;border-radius:var(--r-4);padding:4px 12px;font:inherit;font-family:var(--sans);cursor:pointer;min-height:28px}
.cmd button:hover{background:#fff;color:var(--g-900);text-decoration:underline}
.env .desc{font-size:var(--fs-14);color:var(--g-800);margin:0 0 12px;max-width:44em}
.steps{margin:0 0 12px;padding-left:1.6em;font-size:var(--fs-14);line-height:1.7;max-width:44em}
.steps li{margin:4px 0}
.env .cmd{margin:4px 0 12px}
.asks{list-style:none;padding:0;margin:0;display:grid;grid-template-columns:repeat(2,1fr);gap:8px 24px;max-width:44em;font-size:var(--fs-14)}
.asks li{padding:8px 12px;background:var(--g-50);border-radius:var(--r-8)}
.asks li span{display:block;color:var(--g-700);font-size:var(--fs-13)}

.seg{display:inline-flex;border:1px solid var(--g-420);border-radius:var(--r-8);overflow:hidden;margin:0 16px 16px 0;flex-wrap:wrap}
.seg button{appearance:none;border:0;background:#fff;color:var(--key-900);font:inherit;font-size:var(--fs-14);padding:8px 16px;cursor:pointer;border-right:1px solid var(--g-420);min-height:36px}
.seg button:last-child{border-right:0}
.seg button[aria-pressed=true]{background:var(--key-900);color:#fff}
.seg button:hover:not([aria-pressed=true]){background:var(--key-200);color:var(--key-1000);text-decoration:underline}
.sync{font-size:var(--fs-14);display:inline-flex;align-items:center;gap:6px;vertical-align:top;padding-top:8px}
.viewer{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.viewer.single{grid-template-columns:1fr}
.pane{border:1px solid var(--g-200);border-radius:var(--r-8);overflow:hidden;background:#fff;box-shadow:var(--elev)}
.pane .cap{font-size:var(--fs-14);font-weight:700;padding:8px 14px;border-bottom:1px solid var(--g-200);background:var(--g-50);margin:0;color:var(--g-900)}
.pane .doc{height:min(80vh,900px);overflow:auto;overscroll-behavior:contain}
[hidden]{display:none!important}
footer{padding:32px 0 64px;font-size:var(--fs-14);color:var(--g-700)}
footer p{margin:0 0 8px}

@media (max-width:900px){
  .ba,.stats,.asks,.hero3{grid-template-columns:1fr}
  .hero3 .arrow{padding:0;text-align:center}.hero3 .arrow::before{content:'↓'}
  .keep{grid-template-columns:1fr}.keep .mid{padding:4px 0}.keep .mid::before{content:'↓'}
  .viewer{grid-template-columns:1fr}
  .flow-wrap,.nd-wrap{display:none}.flow-list{display:block}
  .map{min-width:720px}.map-wrap{overflow:auto}
  .bars{min-width:640px}.bars-wrap{overflow:auto}
  .spine{min-width:600px}.spine-wrap{overflow:auto}
}
""" + DOC_CSS

JS = r"""
// タブ(DADS の矢印キー操作)
(function(){
  document.querySelectorAll('[role=tablist]').forEach(list=>{
  const tabs=[...list.querySelectorAll('[role=tab]')];
  function select(i,focus){tabs.forEach((t,j)=>{const on=i===j;t.setAttribute('aria-selected',on);t.tabIndex=on?0:-1;document.getElementById(t.getAttribute('aria-controls')).hidden=!on;});if(focus)tabs[i].focus();}
  tabs.forEach((t,i)=>{t.addEventListener('click',()=>select(i,false));
    t.addEventListener('keydown',e=>{const n=tabs.length;let j=null;
      if(e.key==='ArrowRight')j=(i+1)%n;else if(e.key==='ArrowLeft')j=(i-1+n)%n;else if(e.key==='Home')j=0;else if(e.key==='End')j=n-1;
      if(j!==null){e.preventDefault();select(j,true);}});});
  });
})();
// 流れ図の箱
(function(){
  const nodes=[...document.querySelectorAll('.flow .node')];const descs=[...document.querySelectorAll('.nd')];
  function pick(key){nodes.forEach(n=>n.setAttribute('aria-pressed',n.dataset.node===key));descs.forEach(d=>d.hidden=d.dataset.for!==key);}
  nodes.forEach(n=>{n.addEventListener('click',()=>pick(n.dataset.node));n.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();pick(n.dataset.node);}});});
  pick('q');
})();
// 節の移動図
(function(){
  document.querySelectorAll('.map').forEach(svg=>{
  const srcs=[...svg.querySelectorAll('.src')],paths=[...svg.querySelectorAll('.mv')],dsts=[...svg.querySelectorAll('.dst')];
  function on(i){svg.classList.add('hl');srcs.forEach(s=>s.classList.toggle('on',s.dataset.src===i));
    const hit=new Set();paths.forEach(p=>{const m=p.dataset.src===i;p.classList.toggle('on',m);if(m)hit.add(p.dataset.dst);});
    dsts.forEach(d=>d.classList.toggle('on',hit.has(d.dataset.dst)));}
  function off(){svg.classList.remove('hl');srcs.forEach(s=>s.classList.remove('on'));paths.forEach(p=>p.classList.remove('on'));dsts.forEach(d=>d.classList.remove('on'));}
  srcs.forEach(s=>{s.addEventListener('mouseenter',()=>on(s.dataset.src));s.addEventListener('mouseleave',off);s.addEventListener('focus',()=>on(s.dataset.src));s.addEventListener('blur',off);
  });
  });
})();
// 目次:いま読んでいる節を追う
(function(){
  const links=[...document.querySelectorAll('.toc-list a')];if(!links.length)return;
  const targets=links.map(a=>document.querySelector(a.getAttribute('href'))).filter(Boolean);
  function setCurrent(id){links.forEach(a=>{const on=a.getAttribute('href')==='#'+id;if(on)a.setAttribute('aria-current','location');else a.removeAttribute('aria-current');
    if(on&&window.innerWidth<1560){const l=a.closest('.toc-list');const r=a.getBoundingClientRect(),lr=l.getBoundingClientRect();l.scrollLeft+=(r.left+r.width/2)-(lr.left+lr.width/2);}});}
  function update(){const y=window.scrollY+window.innerHeight*0.3;let cur=targets[0];for(const t of targets){if(t.offsetTop<=y)cur=t;}setCurrent(cur.id);}
  let ticking=false;window.addEventListener('scroll',()=>{if(!ticking){requestAnimationFrame(()=>{update();ticking=false;});ticking=true;}},{passive:true});
  window.addEventListener('resize',update);update();
})();
// 確認事項へのリンク:折りたたみの中にある項目を開いてから移動
function openTarget(){const el=location.hash&&document.getElementById(decodeURIComponent(location.hash.slice(1)));if(!el)return;let d=el.closest('details');while(d){d.open=true;d=d.parentElement&&d.parentElement.closest('details');}el.scrollIntoView({block:'center'});}
window.addEventListener('hashchange',openTarget);openTarget();
// ビューア
const caps={before:'元の稟議書',after:'直した後',kak:'別ファイルの確認事項',redesign:'組み直した後',logic:'筋を見る(検査の報告)',somosomo:'前提を疑う(検査の報告)'};
const viewer=document.getElementById('viewer');
const pL=document.getElementById('paneL'),pR=document.getElementById('paneR');
const dL=pL.querySelector('.doc'),dR=pR.querySelector('.doc');
function load(d,key){if(d.dataset.key!==key){d.replaceChildren(document.getElementById('t-'+key).content.cloneNode(true));d.dataset.key=key;d.scrollTop=0;}}
function mode(m){
  document.querySelectorAll('.seg button').forEach(b=>b.setAttribute('aria-pressed',b.dataset.m===m));
  const side=m==='side'||m==='side2';
  viewer.classList.toggle('single',!side);pR.hidden=!side;document.getElementById('syncbox').hidden=!side;
  if(side){const r=m==='side'?'after':'redesign';load(dL,'before');load(dR,r);pL.querySelector('.cap').textContent=caps.before;pR.querySelector('.cap').textContent=caps[r];}
  else{load(dL,m);pL.querySelector('.cap').textContent=caps[m];}
}
document.querySelectorAll('.seg button').forEach(b=>b.addEventListener('click',()=>mode(b.dataset.m)));
let lock=false;
function bind(a,b){a.addEventListener('scroll',()=>{if(lock||!document.getElementById('sync').checked||pR.hidden)return;
  const r=a.scrollTop/Math.max(1,a.scrollHeight-a.clientHeight);lock=true;b.scrollTop=r*(b.scrollHeight-b.clientHeight);requestAnimationFrame(()=>lock=false);});}
bind(dL,dR);bind(dR,dL);
mode('side');
document.querySelectorAll('[data-copy]').forEach(b=>b.addEventListener('click',async()=>{await navigator.clipboard.writeText(document.getElementById(b.dataset.copy).textContent);b.textContent='コピーした';setTimeout(()=>b.textContent='コピー',1500);}));
"""

p1 = dict(before=[(54, "月額費用79,200円を月あたりの削減時間で割ると、削減できる1時間あたりの費用になる。営業担当者の時間単価(人件費)がこの金額を<em>上回れば、費用は回収できる</em>。"), (62, "")],
          after=[(35, "30分減った場合、削減1時間あたりの費用は約4,600円になる。(中略)削減した時間をほかの仕事に<em>充てられるとすれば</em>、営業担当者の時間単価がこの金額を上回るとき、<em>費用に見合う</em>。")])
_tq = SETS["teian"]["qa"][1]
hero_example = f"""
<p class="cap">例: コンサル会社が食品卸に出す架空の提案資料(営業のデジタル化支援、9か月・2,700万円)。スキルなしの Claude Code に書かせたもの。</p>
<div class="hero4">
  <div><h4>元の文</h4><blockquote><p>{E("御社ではこの引き継ぎの場面で実際に失注が起きています。")}</p></blockquote><p class="note">だから SFA(営業支援システム)を入れる、という提案の前提。</p></div>
  <div class="arrow" aria-hidden="true"></div>
  <div><h4>スキルの問い <span class="tag tag-ask">起案者にしか答えられない</span></h4><blockquote class="q-ask"><p>{E("「引き継ぎの場面で実際に失注が起きている」は、何をもとに書きましたか。件数や金額で、いま分かっていることはありますか。")}</p></blockquote></div>
  <div class="arrow" aria-hidden="true"></div>
  <div><h4>起案者の答え</h4><blockquote class="q-ans"><p>{E("営業本部長が「引き継ぎで2社失った」と話したのを聞いたことがもとです。失注の理由を確かめた記録はなく、件数と金額は分かりません。")}</p></blockquote></div>
  <div class="arrow" aria-hidden="true"></div>
  <div><h4>直した文</h4><blockquote><p>{EM("<em>営業本部長からは、この引き継ぎで2社を失ったとうかがっています。ただ、その理由はまだ確かめていません。</em>")}</p></blockquote><p class="note">答えを強めず弱めず、出どころを添えて本文に入れた。聞いた話を前提にした提案だと、読む人に分かる。</p></div>
</div>"""

# 「確かめたこと」の数字。出どころは dev/ct-eval/runs/r27*(nums27.py で集計)
RV = dict(runs=6, q=18, q_in_doc=0, used=15, unchanged=18, deferred=5, dropped=0, defects=90, remains=0, crossing=0, longer=0, kak_first=3, kak_min=12, kak_max=15)
checked_detail = f"""
<p>用意した文書は8本です。作者が欠陥を仕込んだ架空の稟議書(15か所)、障害報告書(14か所)、コンサルの提案資料(15か所)、社内の制度企画(15か所)の4本と、ない欠陥を指摘しないかを見るために欠陥を除いた4本です。欠陥は、表と本文で食い違う数字、根拠のない見込み、診断の後で決めるはずなのにもう書いてある製品名、報告日より後の「実施済み」などです。</p>
<p>検査は8本すべてに、直す・組み直すは欠陥ありの4本に、決裁者の目で見て直すは稟議書と提案資料の2本に、3回ずつかけました。決裁者の目で見て直すでは、起案者だけが知っている事実の一覧を作者が先に書き、別のセッションの Claude がその一覧だけを見て起案者の役で答えました。一覧にないことは「分からない」と答えます。合否は「欠陥ごとに3回中2回以上、問いが欠陥を捉えた」で見ていて、対象の56か所はすべて合格でした。59か所のうち3か所(稟議書・障害報告書・提案資料に1か所ずつ)は、仕込んだときに「細かすぎて見つからなくても不合格にしない」と決めた欠陥で、合否の計算からは外していますが、上の延べ回数には含めています。</p>
<p>表の「直す」は、起案者に聞かずに検査の指摘だけで直す工程で、「決裁者の目で見て直す」の中でも使われます。「組み直す」は、直すの決まりに加えて論の組み立てを替える工程なので、仕込んだ欠陥の扱いは直すと同じ数え方で見ています。</p>
<p>検査の2工程(筋を見る・前提を疑う)は、確認事項を別ファイルに出す前の版で測り、最終版では測り直していません。最終版で変えたのは直す側の規則だけで、検査の規則は変えていないためです。「決裁者の目で見て直す」「直す」「組み直す」は最終版で測りました。</p>
<p>問いが欠陥を捉えたか、直しが欠陥を解いたか、起案者の答えを改変せずに入れたかは、別のセッションの Claude(Opus 5.5)が判定しました。書かせたのも直したのも同じモデルで、人による確認はしていません。</p>
<table class="tbl">
  <thead><tr><th>工程</th><th>仕込んだ欠陥のうち</th><th>元にない事実を足した</th><th>そのほか</th></tr></thead>
  <tbody>
    <tr><th>検査(筋を見る・前提を疑う)</th><td><b>177回のうち 171回</b><small> で欠陥を捉えた(6回は部分的)</small></td><td><b>0</b><small> 件</small></td><td>欠陥のない文書で、ない欠陥を指摘したのは1本1回あたり0〜1件</td></tr>
    <tr><th>決裁者の目で見て直す</th><td><b>{RV["defects"]}回のうち {RV["defects"] - RV["remains"]}回</b><small> で直すか確認事項に回した</small></td><td><b>{RV["crossing"]}</b><small> 件(元の文書と起案者の答えのどちらにもない事実)</small></td><td>起案者に聞いた問いは{RV["runs"]}回とも3つで、文書の中で答えが出る問いは {RV["q_in_doc"]} 件。{RV["q"]}件の答えのうち{RV["used"]}件が本文に入り、「分からない」の答えで本文を仮定の形にしたのが{RV["deferred"]}件(重なりあり)、落としたのは {RV["dropped"]} 件。改変なしは{RV["unchanged"]}件。本編の字数は、答えを入れる工程なので「元の本編+答えの字数」を上限にし、{RV["runs"]}本すべてで収まった(元より短いのは4本)。別ファイルの確認事項は{RV["kak_min"]}〜{RV["kak_max"]}件で、先に答える問いは3件</tr>
    <tr><th>直す</th><td><b>177回のうち 177回</b><small> で直すか確認事項に回した</small></td><td><b>0</b><small> 件</small></td><td>本編の字数は12本(4本×3回)すべてで元以下。確認事項は12本すべてで別ファイルに出て、文書の中にはない</td></tr>
    <tr><th>組み直す</th><td><b>直すと同じく 177回のうち 177回</b><small> で直すか確認事項に回した</small></td><td><b>0</b><small> 件</small></td><td>決裁の範囲を絞る案は12本(4本×3回)すべてにあり、元の文書にない事実の持ち込みなし。主結論と決裁事項は12本とも元のまま。組み立ては9本で替わり、3本(提案資料1回、制度企画2回)は節の並べ替えにとどまった。案は毎回3つ</td></tr>
  </tbody>
</table>
<p>測りながら規則を4つ直しました。「前提を疑う」が提案資料に対して1度、「引き継ぎ期間や同行訪問で解ける」のように文書にない手段を代案として挙げたので、代案でも手段の名前は出さないようにしました。「直す」が障害報告書で1度、文書の別の箇所にある事実を結論の新しい根拠としてつないだので、根拠として挙げてよいのは文書がそう書いているものだけにしました。「組み直す」は、3本とも段取りを替えるだけの案に収束したので、決裁の範囲を絞る案を必ず出すようにしました。「決裁者の目で見て直す」は、提案資料で起案者の答えを入れた分だけ本編が1〜4%長くなる回が続いたので、答えを入れた字数と同じだけ、要らなくなった断り書きを削るようにしました。それでも提案資料では、答えが「分からない」のときに「台帳から確かめる」のような新しい段取りを書き足す回が続いたので、元の文書にある確かめ方の文をそのまま使う規則を足しました。あわせて、答えを入れる工程なので本編の上限を「元の本編+答えの字数」に改めました。提案資料はこれらを直しながら5回(各3本)測り、表には最後の回を載せています。稟議書も最後の規則で測り直しました。測り方と回ごとの結果は <a href="https://github.com/coji/natural-japanese/blob/main/dev/ct-eval/RESULTS.md">dev/ct-eval/RESULTS.md</a> にあります。</p>"""

page = f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>natural-japanese v{VER}:決裁者の目で見て直す critical-thinking を追加</title>
<meta name="description" content="稟議書・提案資料・企画書を、出す前に決裁者の目で読み、起案者にしか答えられないことを3つだけ聞いて、答えを入れた文書を返す Agent Skill、critical-thinking を追加しました。">
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
      <li><a href="#examples">3つの文書で、どう直ったか</a></li>
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
  <h1>決裁者に出す文書を、出す前に決裁者の目で読み直すスキル critical-thinking を追加しました</h1>
  <p class="lead">AI に稟議書や提案書を書かせると、前提を疑わないまま結論まで走った文書ができます。上司や経営会議に「<mark>そもそも原因はそれなのか</mark>」「<mark>この数字はどこから</mark>」と差し戻される。考えの穴なので、日本語を直しても埋まりません。</p>
  <p class="lead">critical-thinking に「<mark class="key">決裁者の目で見て直して</mark>」と頼むと、文書を決裁者の立場で読み、文書の中で答えが出ることは黙って直し、起案者にしか答えられないことだけを<mark class="key">3つ</mark>聞いて、答えを本文に入れた文書を返します。事実は足さず、起案者の代わりに決めません。</p>
  {hero_example}
</div></header>

<main>
<section class="block" id="how"><div class="wrap">
  <h2>何をするか</h2>
  <p class="sub">対象は、稟議書、企画書、提案資料、障害報告書のような、読んだ人に判断を求める文書です。natural-japanese が言い回しを直すのに対し、critical-thinking は論の筋を見ます。各項目を押すと説明が出ます。</p>
  <div class="flow-wrap">{flow_svg()}</div>
  <div class="nd-wrap">{node_desc}</div>
  <ol class="flow-list">{flow_list}</ol>
  <div class="stats">
    <div class="stat"><b>起案者に聞いた問い(稟議書の例)</b><div class="n">3<small>件</small></div>{disclosure("数え方", "<p>検査が出した問いは「筋を見る」で18件、「前提を疑う」で14件でした。そのうち起案者に聞いたのは、部全体か1人あたりか、時間単価、契約の条件の3つで、どれも文書の中では答えが出ないものです。残りは、文書の中で答えが出るものは本編で直し、出ないものは別ファイルの確認事項に回しました。</p>")}</div>
    <div class="stat"><b>足した事実(稟議書の例)</b><div class="n">0<small>件</small></div>{disclosure("数え方", "<p>直した後の文書に出てくる数字と語が、元の文書か起案者の答えのどちらかにあるかを、このページの作者がスクリプトで確かめました。直した稟議書で見つかったのは、起案者が答えた時間単価と元の月額から計算した「約39分」「約22.6時間」などの値だけで、新しい事実ではありません。</p>")}</div>
    <div class="stat"><b>直した後の本編の字数(稟議書の例)</b><div class="n">{fmt(P1["body"])}<small>字(元は {fmt(P0["body"])} 字)</small></div>{disclosure("数え方", "<p>決裁者が読む本編だけを、空白を除いて数えました。付録は含みません。確認事項は文書の外にあります。</p>")}</div>
  </div>
</div></section>

<section class="block" id="examples"><div class="wrap">
  <h2>3つの文書で、どう直ったか</h2>
  <p class="sub">どれもスキルなしの Claude Code(Opus 5.5)に書かせた架空の文書で、わざと穴を作らせたのではなく、書かせたままです。丁寧に書かれていても、決裁者が読めば引っかかる箇所が残っていました。それぞれに「決裁者の目で見て直して」と頼み、スキルが聞いた3つに起案者が答えると、こう変わりました。</p>
  <p class="legend" style="margin:-8px 0 16px">色の意味<i style="background:var(--ok-50);box-shadow:inset 0 -2px 0 var(--ok)"></i>直す前後で変わった言い方<i style="background:var(--key-50);border:1px solid var(--key-200)"></i>スキルの問い<i style="background:var(--warn-50);border:1px solid var(--warn)"></i>起案者の答え</p>
  {picks_html}
</div></section>

<section class="block" id="redesign"><div class="wrap">
  <h2>構成から組み直す</h2>
  <p class="sub">構成案は2〜3つ出し、そのうち1つは必ず「決裁の範囲を絞る案」です。検査の問いが決裁事項の前提を疑っているとき、決裁事項を保ったまま段取りを替えるだけでは答えになりません。この案は決裁事項を縮める・分ける・先に確かめる・取り下げるのどれかで、どの問いの答え次第で元の決裁事項が成り立たなくなるかを示します。決裁事項を変えるので選べるのは起案者だけで、起案者が選ばずに任せた場合、スキルは決裁事項を変えない案の中から選んで書きます。</p>
  <div class="keep">
    <div class="k"><h4>保つ</h4><ul><li>事実と数値、出典</li><li>主結論と、決裁をお願いする事項</li><li>起案者の制約(開始時期、評価の時期、上限の額)</li></ul></div>
    <div class="mid" aria-hidden="true"></div>
    <div class="c"><h4>替えてよい</h4><ul><li>先頭に何を置くか</li><li>本編と付録の切り分け</li><li>申請の立て方(効果を言い切るか、確かめる試験にするか、判断を何回に分けるか)</li></ul></div>
  </div>
  <div class="spine-wrap">{spine_html}</div>
  {redesign_html}
  {disclosure("線の引き方", "<p>線は、元の節の文がどの節に移ったかを示します。作者が、元の各節の文を組み直した後の文書からスクリプトで探して引きました。1つの節から複数の線が出ているところは、文が分かれて移っています。3本の文書の全文(元・直した後・組み直した後・検査の報告)は <a href=\"https://github.com/coji/natural-japanese/tree/main/release-notes/data/v1.7.0\">リポジトリの release-notes/data/v1.7.0</a> にあります。</p>")}
</div></section>

<section class="block" id="checked"><div class="wrap">
  <h2>確かめたこと</h2>
  <p class="sub">上の3本は例です。欠陥をどれだけ見つけられるか、起案者の答えを改変せずに入れるか、回ごとにどれだけ結果が変わるかを見るために、欠陥を仕込んだ架空の文書4種類(稟議書、社内の制度企画、コンサルの提案資料、障害報告書)で3回ずつ測りました。</p>
  <div class="stats four">
    <div class="stat"><b>仕込んだ欠陥59か所を3回ずつ検査して、問いにした</b><div class="n">177<small>回のうち 171回。残り6回は部分的、見落とし 0</small></div></div>
    <div class="stat"><b>「決裁者の目で見て直す」が起案者に聞いた問い</b><div class="n">{RV["q"]}<small>件のうち、文書の中で答えが出るもの {RV["q_in_doc"]}。答えを改変せずに入れたのは {RV["unchanged"]} 件</small></div></div>
    <div class="stat"><b>「直す」が本編を直すか確認事項に回した</b><div class="n">177<small>回のうち 177回</small></div></div>
    <div class="stat"><b>「組み直す」で、決裁の範囲を絞る案を出した</b><div class="n">12<small>本のうち 12本。主結論と決裁事項も 12本とも元のまま</small></div></div>
  </div>
  {disclosure("測り方と注", checked_detail)}
</div></section>

<section class="block" id="limits"><div class="wrap">
  <h2>苦手なこと</h2>
  <ul class="limits">
    <li>文書の外の事実は調べに行きません。稟議書が挙げる他社の事例が本当かは、問いにして返すだけです。</li>
    <li>起案者に聞くのは3つまでなので、聞かなかった問いは別ファイルの確認事項に残ります。稟議書の例では{len(kak)}件でした。3つに答えただけでは、文書は決裁者に出せる形に近づきますが、確認事項が空になるわけではありません。</li>
    <li>本編が劇的に変わる場面は少なく、直しの大半は、答えを本文に入れる、言い切りを仮定の形に変える、試算を付録に移す、の3種類です。決裁事項そのものを変える案は「組み直す」で出しますが、選ぶのは起案者です。制度企画では、組み直しても節の並べ替えにとどまったと判定された回が3回のうち2回ありました。</li>
    <li>検査は LLM の読みに頼るので、同じ文書をもう一度検査すると、指摘の数や言い方は揺れます。</li>
    <li>「直す」には、根拠があるのに弱腰な言い方を言い切りに戻す決まりもありますが、AI が書いた下書きには、根拠があるのに弱く言っている箇所がほとんどなく、わざと強い言い切りで書かせた提案資料でも出番はありませんでした。弱める方向にしか働いていません。</li>
  </ul>
</div></section>

<section class="block" id="install"><div class="wrap">
  <h2>インストールと頼み方</h2>
  <p class="sub">使う環境を選んでください。頼み方はどの環境でも同じで、文書のファイルを示して「稟議書.md を決裁者の目で見て直して」と頼みます。スキルが3つまで質問するので、答えると直した文書が返ります。工程を分けて使いたいときの頼み方は、次の3つです。</p>
  <ul class="limits" style="margin-top:-8px">
    <li>検査だけ:「稟議書.md の筋が通っているか検査して」「稟議書.md を決裁者目線で、前提から疑って」</li>
    <li>検査のあとで、聞かずに直す:「指摘を反映して直して」</li>
    <li>論の組み立てから替える:「構成から組み直して」</li>
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
        <p class="desc">このコマンドで natural-japanese と critical-thinking の両方が入ります。critical-thinking はスクリプトを使わないので、uv や Python は要りません。natural-japanese の機械検査スクリプトには uv と Python が要ります。</p>
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
  <p class="note" style="margin-top:16px">critical-thinking はスクリプトを使わないので、どの環境でも検査と直しの中身は同じです。各環境の手順は2026年11月に公式のヘルプで確かめたもので、画面の名前は変わることがあります。</p>
</div></section>

<section class="block" id="read"><div class="wrap">
  <h2>文書を読む</h2>
  <p class="sub">架空の稟議書です。社名・人名・製品名は実在しません。「直した後」は、起案者に3つ聞いて答えを入れた文書で、確認事項は別ファイルにあります。</p>
  <p class="sub">検査の報告はスキルの出力そのままで、logic は「筋を見る」、somosomo は「前提を疑う」の内部名です。</p>
  <div class="seg" role="group" aria-label="表示">
    <button type="button" data-m="side" aria-pressed="true">元 | 直した後</button>
    <button type="button" data-m="side2">元 | 組み直した後</button>
    <button type="button" data-m="before">元の稟議書</button>
    <button type="button" data-m="after">直した後</button>
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
page = skill_chips(page)
OUT.write_text(page)
print("ok", OUT, P0, P1, P2, len(kak), len(kak_r))
