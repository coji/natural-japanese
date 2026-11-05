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
from rn_demo import CSS2, JS2  # noqa: E402
CSS = CSS + CSS2
for _a, _b in (('.doc h4{', '.doc h6{'), ('.doc h3{', '.doc h5{'), ('.doc h2{', '.doc h4{'), ('.doc h1{', '.doc h3{')):
    CSS = CSS.replace(_a, _b)
# 旧の文書ビューア(#viewer)は使わないので、その初期化を外してから実演の JS を足す
_i = JS.index("const caps={before:"); _j = JS.index("mode('side');") + len("mode('side');")
JS = JS[:_i] + JS[_j:] + JS2

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
    """検査の報告の指摘の数。書式は回ごとに揺れる: 「**L1 …」「- **L1」「### S1」「1. **…**」「### 1. …」と、
    「細かいもの n 件」または「## 細かいもの」の下の箇条書き。"""
    lines = report.splitlines()
    numbered = re.compile(r"^(?:- |#{1,4} )?\*{0,2}[LSP]\d+|^\d+[.．]\s+\*\*|^###\s+\d+[.．]")
    n = sum(1 for ln in lines if numbered.match(ln))
    in_fine = False
    for i, ln in enumerate(lines):
        m = re.match(r"^#{0,4}\s*細かいもの(?:が)?\s*(\d+)\s*件", ln)
        if m:
            nxt = next((x for x in lines[i + 1:] if x.strip()), "")
            if not numbered.match(nxt): n += int(m.group(1))
            continue
        if re.match(r"^##\s*細かいもの\s*$", ln): in_fine = True; continue
        if ln.startswith("## "): in_fine = False
        if in_fine and re.match(r"^\s*[-*]\s+", ln): n += 1
    return n
def verdict(reply):
    head = reply.strip().splitlines()[0] if reply.strip() else ""
    if "出せます" in head: return "出せる"
    if "差し戻" in head: return "差し戻し"
    raise AssertionError(("判定が読めない", head[:60]))
def parse_hw(t):
    """確認事項ファイルの「出す前にやること」の番号つき項目(本文は作者の HOMEWORK で短く書き直す。ここでは件数だけ使う)。"""
    out, inside = [], False
    for l in t.splitlines():
        if l.startswith("## "): inside = l.startswith("## 出す前にやること"); continue
        if inside and re.match(r"^\d+[.．]", l): out.append(l)
    return out
def load(name):
    d1, d2 = DATA / name / "pass1", DATA / name / "pass2"
    t = {"before": (d1 / "doc.md").read_text(), "reply1": (d1 / "reply.md").read_text(), "kak1_md": (d1 / "doc.確認事項.md").read_text(),
         "logic": (d1 / "report-logic.md").read_text(), "somo": (d1 / "report-somosomo.md").read_text(),
         "q1_md": (d1 / "questions.md").read_text(), "a1_md": (d1 / "answers.md").read_text(), "after1": (d1 / "doc.review.md").read_text(),
         "after": (d2 / "doc.review.md").read_text(), "short": (d2 / "doc.review.short.md").read_text(), "rebuild": (d2 / "doc.review.rebuild.md").read_text(),
         "plans_md": (d2 / "doc.review.plans.md").read_text(), "kak_md": (d2 / "doc.確認事項.md").read_text(), "reply2": (d2 / "reply.md").read_text(),
         "q_md": (d2 / "questions.md").read_text(), "a_md": (d2 / "answers.md").read_text()}
    t["v1"], t["v2"] = verdict(t["reply1"]), verdict(t["reply2"])
    # 前提が崩れたときは、縮小案で書いた版が別に出る。ページの2回目の右側にはそれを出す
    sp = d2 / "doc.review.縮小.md"
    t["shrunk"] = sp.read_text() if sp.exists() else ""
    assert (t["v2"] == "差し戻し") == bool(t["shrunk"]), (name, t["v2"], bool(t["shrunk"]))
    t["after_show"] = t["shrunk"] or t["after"]
    t["P_show"] = parts(t["after_show"])
    t["hw1"] = parse_hw(t["kak1_md"])
    t["P0"], t["P1"], t["P_short"], t["P_rebuild"], t["P_after1"] = parts(t["before"]), parts(t["after"]), parts(t["short"]), parts(t["rebuild"]), parts(t["after1"])
    t["qa1"] = parse_qa(t["q1_md"], t["a1_md"]); t["qa"] = parse_qa(t["q_md"], t["a_md"])
    t["shrink"], t["kak_first"], t["kak_rest"] = parse_kakfile(t["kak_md"])
    t["kak"] = t["kak_first"] + t["kak_rest"]
    t["n_logic"], t["n_somo"] = count_items(t["logic"]), count_items(t["somo"])
    assert t["v1"] == "差し戻し", (name, t["v1"])
    assert 1 <= len(t["hw1"]) <= 6, (name, len(t["hw1"]))
    assert len(t["qa1"]) == 3 and all(a for _, _, a in t["qa1"]), (name, "qa1")
    assert all(a for _, _, a in t["qa"]), (name, "qa2")
    for k in ("after", "short", "rebuild", "after1"):
        assert "要確認" not in t[k] and "確認事項" not in "".join(h for h, _ in sections(t[k])), (name, k)
        assert parts(t[k])["kak"] == 0, (name, k)
    return t

DOCSETS = [
    ("ringi", "稟議書", "営業部の12名で、議事録を作る AI ツールを6か月、上限60万円で試験導入したいという社内の申請。読むのは経営会議。", "経営者", "exec"),
    ("kikaku", "社内の制度企画", "人事企画が、内勤180名を対象に週1日の在宅勤務制度を来年4月から始めたいという企画。昨年の離職率12%を業界平均の8%に近づけたい。全社250名で、差はおよそ10名。読むのは経営会議。", "経営者", "exec"),
    ("teian", "コンサルからの提案資料", "コンサルティング会社が食品卸の北都フーズに、営業支援システムの導入支援を提案する資料。3か月の診断と6か月の導入支援で、2,700万円。読むのは先方の営業本部長と経営会議。", "提案を受け取る会社の役員", "customer"),
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
    for ver in ("元", "1回目", "2回目"):
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
OUTC = {"ringi": load_outcome("o14-exec", "ringi"), "kikaku": load_outcome("o14-kikaku", "kikaku"),
        "teian": load_outcome("o14-customer", "teian"), "postmortem": load_outcome("o14-boss", "postmortem")}
# 提案資料の2回目は、ページに出す縮小版(o15)への返事に差し替える
OUTC["teian"]["2回目"] = load_outcome("o15-customer", "teian")["2回目"]
def load_overlap(label, name):
    rs = json.loads((RUNS / label / "results.json").read_text())
    r = next(x for x in rs if x["name"] == name)
    c = Counter(it.get("match", "none") for it in r["items"])
    return dict(n=len(r["items"]), first=c["first"], other=c["other"], none=c["none"], items=r["items"])
OV = {k: load_overlap("ov7", k) for k in ("ringi", "kikaku", "teian", "postmortem")}
OV_TOTAL = sum(v["n"] for v in OV.values()); OV_NONE = sum(v["none"] for v in OV.values()); OV_FIRST = sum(v["first"] for v in OV.values())
# 確認事項にない指摘は、1回目の書き手の答えで本文に入ったもの(稟議書の時間単価)だけ。それ以外が出たら止める
for _k, _v in OV.items():
    for _it in _v["items"]:
        assert _it.get("match", "none") != "none" or ("時間単価" in str(_it)), (_k, _it)

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
R46 = {k: summary(k) for k in ("r48b2", "r48c2", "r48d2", "r48e", "r48f")}
HAVE_R46 = all(R46.values()) and bool(DET["stable"])

# ---------- 部品 ----------
def EM(t):
    return html.escape(t).replace("&lt;em&gt;", "<em>").replace("&lt;/em&gt;", "</em>")
ICON = '<svg aria-hidden="true" width="24" height="24" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" fill="#fff"/><path d="M12 15.2 6.8 10l1.06-1.06L12 13.08l4.14-4.14L17.2 10 12 15.2Z" fill="currentColor"/><circle cx="12" cy="12" r="10.5" stroke="currentColor" fill="none"/></svg>'
def disclosure(label, body):
    return f'<details class="dsc"><summary>{ICON}<span>{E(label)}</span></summary><div class="dsc-body">{body}</div></details>'
def _norm(t): return re.sub(r"[\s|*]", "", re.sub(r"<[^>]+>", "", t))
def V(v): return v.replace("聞きたい", "判断の前に質問あり")
def _hname(h): return re.sub(r"^##\s*(?:\d+[.．]\s*)?", "", h).strip()
def md(t): return markdown.markdown(t, extensions=["tables"])
def cmd(text):
    """本文の中のコマンドを、コマンド名・サブコマンド・ファイル名で色分けする。"""
    parts = text.split(" ")
    out = [f'<span class="ck">{E(parts[0])}</span>']
    for x in parts[1:]:
        out.append(f'<span class="{"cf" if "." in x else "cs"}">{E(x)}</span>')
    return '<code class="ic">' + " ".join(out) + "</code>"
def demote(h):
    """文書の中の見出しをページの見出しより2段下げる(h1→h3 … h4→h6)。"""
    return re.sub(r"<(/?)h([1-4])\b", lambda m: f"<{m.group(1)}h{int(m.group(2)) + 2}", h)

KAK_TOTAL = sum(len(SETS[k]["kak"]) for k in SETS)
# ---------- 文書ごとに作者が書いた部分(引用は文書の文そのまま。build が照合する) ----------
# 決裁者が最初に聞くこと: (問い, 元の文書では, 直した後では)
ASKS = {
 "ringi": [
    ("週8件は部全体か、1人あたりか", "書いていない", "部全体。訪問記録から。12名の2週間の実測で、1件平均55分"),
    ("時間単価はいくらか", "空欄", "経理部の標準単価 1時間3,500円。9名なら1件36分減れば費用に見合う"),
    ("データの扱いは社内規程に合うか", "契約前に確認する", "情報システム部門が確認した。保存先は国内、AI の学習に使われない"),
    ("12名全員に要るか", "書いていない", "内勤寄りの3名を除く9名、上限50万円に縮めた"),
    ("顧客は録音に同意するか", "全件で使う前提の試算", "同意が得られない打ち合わせがあるぶん必要な削減時間は増える、と明記。利用率の目安は空欄のまま"),
 ],
 "teian": [
    ("失注はどのくらい起きているか", "「実際に失注が起きています」と言い切り", "台帳で確かめた。担当交代38社のうち2社、年間約1,200万円。半減が5社、年約900万円"),
    ("投資に見合うか", "台帳を見ていないので試算を控える、と明記", "すべて防いでも年約2,100万円で、2,700万円を下回る、と提案側が自ら明記"),
    ("何を決めてもらうのか", "9か月・2,700万円の発注", "縮小版では、最初の3か月・900万円の現状診断だけ。フェーズ2は3か月目の報告のあとに"),
    ("3か月目で止めたら、いくらで終わるか", "書いていない", "900万円で終わり、1,800万円は発生しない。契約も2つに分ける"),
    ("B社の事例は当てはまるか", "成果につながった例、と紹介", "指標が違い、同じ数字は約束しない、と明記"),
 ],
 "kikaku": [
    ("VPN は足りるか", "上限100件、外勤の利用は確認中", "外勤などの最大約40件と、いちばん多い曜日の44名で84件。16件の余り"),
    ("効果を金額で言えるか", "退職者1名あたりのコストは集計中、X 円", "1名あたり約180万円。費用の約786万円は離職者およそ4.4名分"),
    ("辞めた人のうち何名に効くか", "「退職理由の上位」", "週1日の在宅で応えられる中身を書いた内勤は4名"),
    ("費用はいくらか", "事前に確認が必要、と列挙", "ノートPC 38台で約570万円、手当は年間約216万円"),
    ("本日決めるのは何か", "2027年4月から始めること", "方針の承認と準備の着手。開始日は2月の最終案で決める"),
 ],
 "postmortem": [
    ("何を決めてほしいのか", "書いていない", "情報システム部長に2つ。再発防止の方向と、調査の1週間。営業本部長には報告のみ"),
    ("止まり方は全面か断続か", "確認中", "約8割の要求が30秒以上かかった。全面停止ではない"),
    ("再起動後に再発していないか", "再発なし、とだけ", "使用率は再起動直後45%、その後1週間は60〜70%で安定"),
    ("調査の担当と期限は", "まだ決まっていない", "運用チームの2名が検証環境で比べ、11月5日に終える"),
    ("再入力したのは誰か", "書いていない", "営業が顧客に聞き直して入力し直した。納期の遅れはない"),
 ],
}
# 主な変更: (見出し, 説明, 元の文書の語句, 直した後の語句)。語句は文書の文そのままで、押すと左右の比較で該当箇所へ移動する
CHANGES = {
 "ringi": [
    ("頼む中身を縮める", "書き手の判断で12名から9名に。上限は60万円から50万円に", "営業部の営業担当12名で6か月間試験導入したい。", "営業部の営業担当12名のうち内勤寄りの3名を除く9名で、6か月間試験導入したい。"),
    ("宿題の答えを入れる", "測る予定だった作成時間が、2週間の実測になった", "試験導入の開始前に測定する(8章)", "営業担当12名の作成時間を、2週間で打ち合わせ16件分記録した。1件あたりの平均は55分"),
    ("空欄を埋める", "時間単価が入った", "【 】円(人事・経理部門に確認して記入)", "経理部が社内の試算に使う標準単価の1時間3,500円"),
    ("線を引き直す", "30分の参考値では届かないので、本導入の線を36分に", "参考値どおり1件あたり30分減った場合の削減時間は、次のとおり", "1件あたり約36分減れば費用に見合うので、本導入へ進む線を36分とする"),
    ("宿題の答えを入れる", "規程との突き合わせが、確認の結果になった", "社内規程に合っているかどうかを情報システム部門と確認し", "顧客情報の保存と扱いは、社内規程に合っていると情報システム部門が確認した"),
    ("言い切りを根拠に合わせる", "確かめていないことは見立てとして書く", "担当者のメモの取り方に左右される。", "担当者のメモの取り方に左右されると見ている"),
 ],
 "teian": [
    ("決裁事項を小さくする", "9か月・2,700万円の発注が、最初の3か月・900万円の診断の発注に", "御社ではこの引き継ぎの場面で実際に失注が起きています", "決めていただきたいのは、この9か月のうち、最初の3か月・900万円の現状診断を当社に発注するかどうかです"),
    ("台帳の数字を入れる", "聞いた話だった失注が、件数と金額になった", "口頭説明だけに頼る引き継ぎがなくなり", "去年の異動・退職4名の担当顧客38社のうち、翌年の取引がなくなったのは2社で、合計で年間約1,200万円です"),
    ("効果の上限を書く", "すべて防いでも年約2,100万円で費用を下回る、と提案側が自ら明記", "本資料では金額での試算を控えています", "失注と取引の減少をすべて防げたとしても、効果は年間約2,100万円で、支援費用の総額2,700万円を下回ります"),
    ("止めたときの支払いを明記", "3か月目で止めれば900万円で終わる。契約も2つに分ける", "導入フェーズへ進むかどうかをご判断いただけます", "進まない場合はフェーズ1の900万円で終わり、フェーズ2の1,800万円は発生しません。契約は2つに分け"),
    ("事例の限界を書く", "B社と指標が違うことを明記", "同業・同規模の会社で、営業記録の共有が成果につながった例です", "B社と同じ数字をお約束するものではなく"),
 ],
 "kikaku": [
    ("宿題の答えを入れる", "VPN の確認中が、曜日ごとの最大人数と余りの数字になった", "現在の利用状況は情報システム部に確認中です", "外勤など内勤以外のふだんの同時接続は最大で約40件なので、足すと84件で、上限に対して16件の余りがあります"),
    ("宿題の答えを入れる", "集計中だったコストが金額になり、費用と比べられた", "これは現在、人事部で集計中です", "ノートPCの購入と手当の1年分を合わせた費用は約786万円で、離職者およそ4.4名分です"),
    ("仮の X を実額に", "X 円が約180万円に", "仮にこのコストを1名あたり X 円とすると", "退職者1名あたりの採用・育成コストは約180万円で"),
    ("宿題の答えを入れる", "退職理由の上位、が人数になった", "「働き方の柔軟性のなさ」が退職理由の上位", "そのうち内勤は4名です"),
    ("宿題の答えを入れる", "均等に分かれれば、が実際の割り当てになった", "5日に均等に分かれれば1日あたり36名です", "在宅勤務者がいちばん多い曜日は、2部署が重なる水曜の44名です"),
 ],
 "postmortem": [
    ("決めることを明記", "共有で終わる報告が、情報システム部長に2つの判断を頼む報告になった", "受注管理システムの Web 画面が1時間半ほど応答しなくなりました。アプリケーションサーバー", "情報システム部長に決めていただきたいのは、再発防止の3つの方向でよいかと"),
    ("宿題の答えを入れる", "止まり方は確認中から、約8割が30秒超に", "全面的だったのか断続的だったのかは確認中", "応答に30秒以上かかったリクエストが全体の約8割で、全面停止ではありませんでした"),
    ("宿題の答えを入れる", "再起動後のメモリの値が入った", "改修が原因だとは確かめられていません", "使用率は再起動直後が45%、その後1週間は60〜70%で推移し、増え続けてはいません"),
    ("宿題の答えを入れる", "再入力したのは営業、と分かった", "営業が顧客に再入力を頼みました", "営業が顧客に聞き直して入力し直しました"),
    ("調査の担当と期限", "検討中だった調査に、担当2名と終える日が付いた", "いずれも検討中で、具体的な内容、担当、期限はまだ決まっていません", "運用チームの担当者2名が検証環境で改修の前後のメモリ使用量を比べるもので、10月29日に始めて11月5日に終えます"),
    ("言い切りを根拠に合わせる", "原因は「と見ています」に", "メモリが上限に達したためで、サーバーを再起動し", "メモリが上限に達したことだと見ています"),
 ],
}
TILE_DECIDE = {  # 「決めてもらうこと」のタイル(見出し語, 数字, 単位, 説明)
 "ringi": ("決めてもらうこと", "3", "件", "元から明記あり。目安の30分の短縮では費用に見合わない、と添えた"),
 "teian": ("決めてもらうこと", "1", "件", "9か月・2,700万円のご契約。3か月目で止められることを要点に書き足した"),
 "kikaku": ("決めてもらうこと", "2", "件", "4月開始の承認から、方針の承認と準備の着手に変わった"),
 "postmortem": ("決めてもらうこと", "2", "件", "元の報告には書かれていなかった"),
}
for _k in SETS:
    _t = SETS[_k]
    for _title, _desc, _b, _a in CHANGES[_k]:
        assert _norm(_b) in _norm(_t["before"]), (_k, "before", _b[:20])
        assert _norm(_a) in _norm(_t["after_show"]), (_k, "after", _a[:20])


# 1回目の返答の、差し戻しの理由(決裁者の言葉)。返答の文を短くしたもの
REASON = {
    "ringi": "データの扱いの確認と2週間の測定は承認前に自分でできるのに、まだやっていない。時間単価3,500円では、参考値の30分でも費用を回収できない",
    "kikaku": "VPN の利用状況とコストの集計は、承認の前に確かめられる。柔軟性のなさを挙げた内勤の退職者は7名と分かり、ノートPCだけで約900万円かかるので、なぜ見合うのかの説明も要る",
    "teian": "失注の件数も理由も、本部長に聞けば台帳と話から出せる。確かめないまま2,700万円を頼まれている。3か月目に止めたときの費用も基準も書かれていない",
    "postmortem": "止まり方の確認と再起動後のメモリ使用量の整理は、了承を頼む前に運用チームが手元の記録でできる",
}
# 宿題: (何を調べるか, 誰に聞くか・何を見るか, 分かったら本文のどこを直すか)。確認事項ファイルの「出す前にやること」を短くしたもの
HOMEWORK = {
    "ringi": [
        ("データの扱いが社内規程に合うか", "販売店から資料を取り寄せ、情報システム部門と突き合わせる", "5章の情報漏えいの対策を、確認した結果の文に。合わなければ稟議を出さない"),
        ("12名の議事録の作成時間を2週間記録する", "営業担当12名の記録シート", "2章の「約60分」を実測の平均に。平均が約39分を切るなら頼む中身を見直す"),
        ("単価6,600円の税区分と、途中で人数を減らせるか", "販売店", "4章の「契約前に確認する」を結果に。回収の線を約39分か約43分に絞り、6.1の目安をそろえる"),
    ],
    "kikaku": [
        ("柔軟性のなさを挙げた内勤7名が、週1日の在宅で辞めずに済んだ人か", "昨年の退職者アンケートの自由記述", "1章の「理由と考えています」の文に人数を"),
        ("退職者1名あたりの採用・育成コスト", "人事部の集計。付議の前に間に合うか先に確かめる", "3章の「X 円」を金額に。4章の約900万円が離職者の何名分かを書く"),
        ("外勤の方などの、多い日の VPN 同時接続", "情報システム部", "2章の「なお」の文を件数に。まとめの「利用が大きくない限り」を外す"),
        ("部署ごとの内勤の人数と、いちばん多い曜日の在宅勤務者", "人事部の人員の記録", "2章の「1日あたり36名」のあとに、多い曜日の人数と100件に対する余りを"),
        ("在宅勤務手当の年間の総額", "1日250円 × 人数 × 年間の利用日数", "4章の手当の文のあとに総額を"),
    ],
    "teian": [
        ("失った2社の理由と時期、台帳にある失注の件数と金額", "営業本部長。経営会議の前に数字を出してもらえるかも聞く", "1章の「2社を失った」を件数と金額に"),
        ("3か月目に止めたとき、900万円で終わる契約にできるか", "自社で契約条件を決める人", "要点の表と5章に、止めたときの支払いを1文で"),
        ("3か月目の判断の基準", "書き手が決める", "5章の継続判断の次に、基準を1文で"),
    ],
    "postmortem": [
        ("再起動後のメモリ使用量の数値と推移", "運用チームが1時間ごとに見てきた記録", "概要の「再発はありません」のあとに数値と推移を1文で"),
        ("止まり方が全面的だったか断続的だったか", "入力の成功と失敗の時刻が分かる記録", "概要の「確認中です」を分かった止まり方に"),
        ("この注文をふだん入力するのは営業か顧客か", "営業本部", "概要の「顧客に再入力を頼み」を、誰が何をしたかの文に"),
    ],
}
for _k in HOMEWORK:
    assert len(HOMEWORK[_k]) == len(SETS[_k]["hw1"]), (_k, len(HOMEWORK[_k]), len(SETS[_k]["hw1"]))

# ---------- 文書ごとのパネル ----------
STEPS = [("1. 文書の中を検査", "logic"), ("2. 文書の外から問う", "somosomo"), ("3. 書き手に聞く", "3問"), ("4. 本文を直す", "fix"), ("5. 端的にする", "short"), ("6. 構成を組み直す", "rebuild")]
def step_texts(t):
    return [f"主張と根拠の対応、矛盾を{t['n_logic']}件指摘", f"前提、代案、覆る条件を{t['n_somo']}件問う", "答えが要る3問だけを聞く", "答えを本文に入れ、言い切りを根拠に合わせる", "決裁に要る根拠を本編に残し、残りは付録へ", "構成案を3つ出し、決裁事項を小さくする案も示す"]
def tiles(key):
    t = SETS[key]
    b0, b1, b2 = t["P0"]["body"], t["P1"]["body"], t["P_short"]["body"]
    v2 = t["v2"]
    v2d = "宿題を済ませた2回目は、そのまま出せる" if v2 == "出せる" else "宿題の答えで前提が崩れた。決裁事項を小さくした版を別に出す"
    return f'''<div class="tiles">
  <div class="tile"><p class="l">1回目の判定</p><div class="v">差し戻し</div><p class="d">出す前に調べられることが残っていた。宿題は{len(HOMEWORK[key])}つ</p></div>
  <div class="tile"><p class="l">2回目の判定</p><div class="v">{E(v2)}</div><p class="d">{E(v2d)}</p></div>
  <div class="tile"><p class="l">本編の長さ</p><div class="v">{round((1 - b2 / b0) * 100)}%<small>短縮</small></div><p class="d">{fmt(b0)}字 → 直して {fmt(b1)}字 → 端的に {fmt(b2)}字</p></div>
  <div class="tile"><p class="l">検査で見つけた問い</p><div class="v">{t["n_logic"] + t["n_somo"]}<small>件</small></div><p class="d">論理の指摘{t["n_logic"]}件、前提への問い{t["n_somo"]}件。うち3問を書き手に聞く</p></div>
</div>'''
def homework(key):
    rows = "".join(f'<tr><th scope="row">{E(a)}</th><td>{E(b)}</td><td>{E(c)}</td></tr>' for a, b, c in HOMEWORK[key])
    return f'''<div class="tbl-wrap"><table class="tbl"><thead><tr><th>調べること</th><th>誰に聞くか・何を見るか</th><th>分かったら直す箇所</th></tr></thead><tbody>{rows}</tbody></table></div>'''
def bars(key):
    t = SETS[key]
    rows = [("元の文書", t["P0"]["body"], ""), ("決裁者の目で見て直す", t["P1"]["body"], ""), ("もっと端的に", t["P_short"]["body"], ""), ("構成から組み直す", t["P_rebuild"]["body"], "k")]
    mx = max(r[1] for r in rows)
    out = "".join(f'<div class="bar"><span class="bl">{E(n)}</span><span class="tr"><span class="f {c}" style="width:{v / mx * 100:.1f}%"></span></span><span class="bv">{fmt(v)}字</span></div>' for n, v, c in rows)
    return f'<div class="cbars">{out}</div>'
def asks_table(key):
    rows = "".join(f'<tr><th scope="row">{E(q)}</th><td>{E(b)}</td><td>{E(a)}</td></tr>' for q, b, a in ASKS[key])
    return f'<div class="tbl-wrap"><table class="tbl"><caption>上司や顧客が最初に聞くことへの答え</caption><thead><tr><th>問い</th><th>元の文書では</th><th>直した後では</th></tr></thead><tbody>{rows}</tbody></table></div>'
def compute_moves(before_t, after_t, min_hits=2):
    new = [(_hname(h), b) for h, b in sections(after_t) if h and kind(h) != "kak"]
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
def sankey(key):
    """元の節と組み直した節を、字数に比例した高さの箱で並べ、文の移り先を線でつなぐ。"""
    t = SETS[key]
    L = [(_hname(h), nonspace(h) + nonspace(b)) for h, b in sections(t["before"]) if h]
    R = [(_hname(h), nonspace(h) + nonspace(b), kind(h)) for h, b in sections(t["rebuild"]) if h and kind(h) != "kak"]
    moves = compute_moves(t["before"], t["rebuild"])
    W = 1000; bw = 330; lx = 10; rx = W - bw - 10; GAP = 10; MINH = 34; MAXH = 120
    def hpx(n, cap): return min(MAXH, max(MINH, n / 8)), n / 8 > MAXH
    def col(items, x, cls_of):
        y = 40; out = []; pos = {}
        for i, it in enumerate(items):
            h, n = it[0], it[1]; hh, capped = hpx(n, True)
            pos[h] = (y, y + hh, i)
            out.append(f'<g class="{cls_of(it)}" data-i="{i}"><rect x="{x}" y="{y}" width="{bw}" height="{hh:.0f}" rx="6" class="mr"/><text x="{x + 12}" y="{y + hh / 2 + 6:.0f}" class="ml">{E(h)}</text><text x="{x + bw - 12}" y="{y + hh / 2 + 6:.0f}" class="mn" text-anchor="end">{fmt(n)}字{"※" if capped else ""}</text></g>')
            y += hh + GAP
        return out, pos, y
    lo, lp, ly = col(L, lx, lambda it: "src")
    ro, rp, ry = col(R, rx, lambda it: "dst " + it[2])
    H = max(ly, ry) + 10
    s = f'<svg viewBox="0 0 {W} {H}" class="fig map" role="img" aria-label="元の{len(L)}節が、組み直した後のどの節へ移ったか。箱の高さは字数に比例する。※は縮めている">'
    s += f'<text x="{lx}" y="24" class="mh">元の文書 本編 {fmt(t["P0"]["body"])}字</text><text x="{rx}" y="24" class="mh">組み直した文書 本編 {fmt(t["P_rebuild"]["body"])}字 + 付録 {fmt(t["P_rebuild"]["app"])}字</text>'
    for h, _ in L:
        for d in moves.get(h, []):
            if d not in rp: continue
            y1 = (lp[h][0] + lp[h][1]) / 2; y2 = (rp[d][0] + rp[d][1]) / 2; mx = (lx + bw + rx) / 2
            dashed = ' dashed' if rp[d][2] >= 0 and R[rp[d][2]][2] == "app" else ''
            s += f'<path d="M{lx + bw},{y1:.0f} C{mx},{y1:.0f} {mx},{y2:.0f} {rx},{y2:.0f}" class="mv{dashed}" data-src="{lp[h][2]}" data-dst="{rp[d][2]}"/>'
    return s + "".join(lo) + "".join(ro) + '</svg>'
def changes_list(key):
    items = "".join(f'<li><button type="button" class="chg" data-doc="{key}" data-b="{html.escape(b)}" data-a="{html.escape(a)}"><span class="num">{i + 1}</span><b>{E(ti)}</b><span>{E(d)}</span></button></li>' for i, (ti, d, b, a) in enumerate(CHANGES[key]))
    return f'<ol class="changes">{items}</ol>'
def viewer(key):
    t = SETS[key]
    docs = {"before": t["before"], "after": t["after_show"]}
    tpl = "".join(f'<template id="t-{key}-{k}"><article>{demote(md(v))}</article></template>' for k, v in docs.items())
    # 節の対応(左の節 i → 右の各文書の節 j)
    maps = {}
    for k in ("after",):
        mv = compute_moves(t["before"], docs[k])
        rh = [_hname(h) for h, _ in sections(docs[k]) if h]
        maps[k] = [rh.index(mv[_hname(h)][0]) if h and mv.get(_hname(h)) and mv[_hname(h)][0] in rh else -1 for h, _ in sections(t["before"]) if h]
    return f'''<div class="viewer" data-doc="{key}" data-maps='{json.dumps(maps)}'>
  <div class="pane"><p class="cap">元の文書 <span class="ln">本編 {fmt(t["P0"]["body"])}字</span></p><div class="doc L" tabindex="0"></div></div>
  <div class="pane"><p class="cap">{"縮小版" if t["shrunk"] else "直した後"} <span class="ln">本編 {fmt(t["P_show"]["body"])}字</span></p><div class="doc R" tabindex="0"></div></div>
</div>{tpl}'''
def doc_panel(key):
    t = SETS[key]; desc = dict((k, d) for k, _, d, *_ in DOCSETS)[key]
    steps = "".join(f'<li><b>{E(n)} <span class="chip" data-color="gray">{E(c)}</span></b><span>{E(x)}</span></li>' for (n, c), x in zip(STEPS, step_texts(t)))
    qa = "".join(f'<li>{E(q)}{disclosure("書き手の答え", f"<p>{E(a)}</p>")}</li>' for n, q, a in t["qa1"])
    hwa = "".join(f'<li>{E(re.sub(r"。*調べた結果を教えてください$", "", re.sub(r"^宿題[:：]", "", q)).rstrip("。") + "。")}{disclosure("宿題を済ませた書き手の答え", f"<p>{E(a)}</p>")}</li>' for n, q, a in t["qa"][3:])
    shrink_p = f'<p class="p"><b>決裁事項を小さくする案</b> {E(t["shrink"])}</p>' if t["shrink"] else ""
    kak = f'{shrink_p}<h4>先に答えるべき問い</h4><p class="p">「本文」は直した後の文書を指します。</p><ol class="list">{"".join(f"<li>{E(x)}</li>" for x in t["kak_first"])}</ol><h4>そのほか {len(t["kak_rest"])} 件</h4><ul class="list">{"".join(f"<li>{E(x)}</li>" for x in t["kak_rest"])}</ul>'
    how = f'''<p class="p prose-max">文書の中で答えが出ることはそのまま直し、書き手にしか答えられないことだけを3つまで聞きます。工程の名前は、後述の使い方で指定できるサブコマンド名です。3は full に含まれ、単独では呼べません。somosomo は「そもそも」からの名前です。</p>
<ol class="flow">{steps}</ol>
<h4>工程ごとの本編の字数</h4>{bars(key)}
{asks_table(key)}
<h4>1回目に書き手に聞いた3問と答え</h4>
<p class="p prose-max">答えは書き手の役の AI が返しました。スキルの作者が書いた事実の一覧だけを見て答え、一覧にないことは「分からない」と答えます。</p>
<ol class="list prose-max">{qa}</ol>
<h4>2回目: 宿題の答え</h4>
<p class="p prose-max">宿題を済ませて分かったことを、作者が事実の一覧に足しました。書き手の役の AI はそれを見て答えます。</p>
<ol class="list prose-max">{hwa}</ol>
{disclosure(f"スキルが本文とは別のファイルに出した確認事項 {len(t['kak'])} 件", kak)}
<h4>構成がどう変わったか</h4>
<p class="p prose-max">左が元の文書、右が「構成から組み直す」の出力です。線は文の移り先で、点線は付録へ。箱の高さは字数に比例します。</p>
<div class="map-wrap">{sankey(key)}</div>'''
    v2 = t["v2"]
    second = "宿題を済ませた書き手の答えを入れると、「このまま出せます」になりました。" if v2 == "出せる" else "宿題の答えで、決裁事項の前提が崩れました。2回目も差し戻しで、決裁事項を小さくした版を別に出しています。右はその版です。"
    return f'''<p class="p prose-max">{E(desc)}</p>
<h3>ひとめで分かる変化</h3>
{tiles(key)}
<h3>1回目: 差し戻しと宿題</h3>
<p class="p prose-max">スキルの返答は「このままでは差し戻されます」から始まります。理由は次のとおりです。{E(REASON[key])}。</p>
{homework(key)}
<h3>2回目: 宿題を済ませて出し直す</h3>
<p class="p prose-max">{E(second)}<span class="wide">左が元の文書、右が2回目に直した後です。片方を動かすと、対応する節が並ぶようにもう片方も動きます。</span><span class="narrow">上が元の文書、下が2回目に直した後です。</span></p>
{viewer(key)}
<h3>主な変更 {len(CHANGES[key])} 件</h3>
<p class="p prose-max">番号を押すと、上の比較で該当箇所へ移動します。</p>
{changes_list(key)}
<h3>どうやったか</h3>
{disclosure("工程と、決裁者の問いへの答え、構成の変化", how)}'''
tabs_html = '<ul class="dads-tab__list" role="tablist" aria-label="4つの文書">' + "".join(
    f'<li><button type="button" class="dads-tab__tab" role="tab" id="doc-tab-{i+1}" aria-selected="{"true" if i == 0 else "false"}" aria-controls="doc-panel-{i+1}" tabindex="{0 if i == 0 else -1}"><span>{E(l)}</span></button></li>'
    for i, (k, l, *_) in enumerate(DOCSETS)) + '</ul>'
def panel(prefix, i, body):
    return f'<div class="dads-tab__panel" id="{prefix}-panel-{i}" role="tabpanel" aria-labelledby="{prefix}-tab-{i}" tabindex="0"{"" if i == 1 else " hidden"}>{body}</div>'
doc_tabs = f'<div class="dads-tab" id="docs">{tabs_html}<div class="dads-tab__panels">{"".join(panel("doc", i + 1, doc_panel(k)) for i, (k, *_) in enumerate(DOCSETS))}</div></div>'
# ---------- 確かめたこと(欠陥を仕込んだ文書) ----------
def checked_html():
    rows = "".join(f'<tr><th scope="row">{E(DOC_LABEL[k])}</th><td>{E(READER[k])}</td><td>{E(V(OUTC[k]["元"]["verdict"]))}</td><td>{E(V(OUTC[k]["1回目"]["verdict"]))}</td><td>{E(V(OUTC[k]["2回目"]["verdict"]))}</td><td>{OV[k]["n"]} 件のうち {OV[k]["n"] - OV[k]["none"]} 件</td></tr>' for k, *_ in DOCSETS)
    assert HAVE_R46, "r46 系の summary がない"
    rw = rewrite_stats("r48b2"); rd = rewrite_stats("r48d2")
    cc = summary("r48e"); cl = summary("r48f")
    rv_rows = table_rows("r48c2")
    rv_q = sum(int(r["cells"][0]) for r in rv_rows); rv_q_doc = sum(int(r["cells"][1]) for r in rv_rows)
    uudd = [tuple(int(x) for x in r["cells"][2].split("/")) for r in rv_rows]
    rv_used = sum(u[0] for u in uudd); rv_drop = sum(u[3] for u in uudd)
    cc_ok = [(int(a), int(b)) for a, b in re.findall(r"満たした run: (\d+)/(\d+)", cc + cl)]
    method = f'''<p>想定した読み手は、別のセッションの Claude Opus 5.5 に役を与えたもので、文書ごとに経営者、提案を受け取る会社の役員、報告を受け取る上司です。元の文書と直した後を、どちらが直した後かを知らせずに別々に渡し、返事と指摘を3回ずつ返させました。返事は OK、条件つきOK、判断の前に質問あり、却下の4つから選びます。指摘と確認事項の照合は Claude Sonnet 5.5 が行い、判定が甘くないかは、ある文書への指摘を無関係な文書の確認事項と組み合わせた42組で、全部「ない」と出ることを確かめました。</p>
<p>テスト用の文書は、スキルの作者が欠陥を仕込んだ架空の文書5本と、ない欠陥を指摘しないかを見る欠陥のない4本です。仕込んだ欠陥は、表と本文で食い違う数字、根拠のない見込み、診断の後で決めるはずなのにもう書いてある製品名、報告日より後の「実施済み」などです。問いが欠陥を捉えたか、直しが欠陥を解いたか、書き手の答えを改変せずに入れたかは Claude Sonnet 5.5 が判定しました。書かせたのも直したのも Claude Opus 5.5 で、人による確認はしていません。「構成から組み直して」は、欠陥を仕込んだ文書のうち4本を3回ずつ組み直した {rd['n']} 本すべてで決裁事項を小さくする案が出て、主結論と決裁事項は {rd["kept"]} 本すべてで元のままでした。組み直した本編が元より長くなった回が {rd["n"]} 回中 {rd["n"] - rd["not_longer"]} 回ありました。どれも元の 4% 以内で、括弧の補足を文に開いたぶんです。「もっと端的に」「もっと丁寧に」は、主結論・決裁事項・数値が保たれ、本編の各文が元の文書に対応することを条件とし、{sum(b for _, b in cc_ok)} 回中 {sum(a for a, _ in cc_ok)} 回で満たしました。満たさなかった1回は、丁寧にした本編が元の 110% を超えたものです。回ごとの結果は <a href="https://github.com/coji/natural-japanese/blob/main/dev/ct-eval/RESULTS.md">dev/ct-eval/RESULTS.md</a> にあります。</p>'''
    return f'''<h3>上の4本で</h3>
  <p class="p prose-max">想定した読み手を演じる AI に、元の文書、1回目、2回目をそれぞれ渡し、返事と指摘を返させました。右端は、元の文書への指摘のうち、スキルが1回目に出した確認事項がすでに拾っていた数です。</p>
  <div class="tbl-wrap"><table class="tbl"><thead><tr><th>文書</th><th>想定した読み手</th><th>元の文書への返事</th><th>1回目への返事</th><th>2回目への返事</th><th>元の文書への指摘のうち、確認事項にあったもの</th></tr></thead><tbody>{rows}</tbody></table></div>
  <p class="p prose-max">読み手役の AI が元の文書に出した指摘は、1本につき3回の試行で合計 {OV_TOTAL} 件。うち {OV_TOTAL - OV_NONE} 件は、スキルが1回目に出した確認事項にすでに入っていました。{OV_FIRST} 件は宿題と「先に答えるべき問い」に、残りは「そのほか」にです。入っていなかった {OV_NONE} 件はどれも稟議書の時間単価で、1回目に書き手が答えて本文に入ったので、確認事項には残っていません。コンサルからの提案資料は、元の文書は失注を言い切っていたため「フェーズ1だけなら」と通りかけました。台帳の数字と効果の上限を正直に書くと2,700万円のままでは却下で、決裁事項を900万円の診断だけに小さくした版は3回中2回が条件つきOKでした。表の2回目はその版への返事です。</p>
  <h3>テスト用の文書で</h3>
  <p class="p prose-max">スキルの作者が欠陥を仕込んだ架空の文書5本と、欠陥のない4本に、このバージョンのスキルを3回ずつかけました。</p>
  <div class="tiles">
    <div class="tile"><p class="l">仕込んだ欠陥を問いにできた</p><div class="v">{DET["found"]}<small>/ {DET["found"] + DET["partial"] + DET["missed"]} 回</small></div><p class="d">{DET["rows"]}か所 × 3回。見落とし {DET["missed"]}</p></div>
    <div class="tile"><p class="l">元にない事実の持ち込み</p><div class="v">{DET["crossing"]}<small>件</small></div><p class="d">欠陥のない4本で誤って指摘した数も {sum(DET["false_clean"])} 件</p></div>
    <div class="tile"><p class="l">書き手への問い</p><div class="v">{rv_q}<small>件</small></div><p class="d">問いが出た3本 × 3回。文書の中で答えが出る問いは {rv_q_doc}。答えはすべて変えずに本文に入れた</p></div>
    <div class="tile"><p class="l">仕込んだ欠陥を直すか確認事項に回した</p><div class="v">{rw["fixed"] + rw["deferred"]}<small>/ {rw["fixed"] + rw["deferred"] + rw["remains"]} 回</small></div><p class="d">5本 × 3回。取りこぼし {rw["remains"]}。直した本編が元より長くなった回は {rw["n"]} 回中 {rw["n"] - rw["not_longer"]} 回</p></div>
  </div>
  {disclosure("測り方と注", method)}'''

R = SETS["ringi"]
OLDER_LINKS = ""
page = f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>natural-japanese v{VER}:AI の文書に、クリティカルシンキングを</title>
<meta name="description" content="AI が書いた稟議書や企画書、提案書を、提出する前に決裁者の目で読んで直す Agent Skill、critical-thinking を追加しました。文書の中で直せることは直し、書き手にしか答えられないことだけを3つ聞いて本文に入れます。">
<meta property="og:title" content="natural-japanese v{VER}:AI の文書に、クリティカルシンキングを">
<meta property="og:description" content="AI が書いた稟議書や企画書、提案書を、提出する前に決裁者の目で読んで直す Agent Skill、critical-thinking を追加しました。">
<meta property="og:type" content="article">
<meta name="twitter:card" content="summary">
{FONT}
<style>{CSS}</style>
</head>
<body>
<nav class="toc" aria-label="目次">
  <div class="toc-inner">
    <p class="toc-h">natural-japanese</p>
    <ol class="toc-list">
      <li><a href="#top">v{VER}</a></li>
      <li><a href="#docs-sec">4つの文書で見る</a></li>
      <li><a href="#checked">確かめたこと</a></li>
      <li><a href="#how">使い方</a></li>
      <li><a href="#install">インストール</a></li>
    </ol>
  </div>
</nav>

<header class="hero" id="top"><div class="wrap">
  <p class="eye">natural-japanese v{VER} リリースノート</p>
  <h1>AI の文書に、クリティカルシンキングを</h1>
  <p class="p lead">AI が書いた稟議書や企画書、提案書は、丁寧に見えて、決める人の問いに答えていないことがあります。<mark>根拠のない言い切り</mark>、<mark>よく見ると辻褄の合わない数字</mark>、そして<mark>論点がはっきりしないダラダラした文章</mark>。natural-japanese に同梱した新しいスキル <code class="ic sk">critical-thinking</code> は、提出する前に決裁者の目で読み、文書の中で直せることは直し、書き手にしか答えられないことだけを3つ聞いて本文に入れ、決裁に要る根拠だけを残して短くします。</p>
  <p class="p lead">下は、架空の文書4本にかけた実演です。1回目は4本とも「このままでは差し戻されます」の判定と、出す前に調べておくことの一覧が返りました。このページではその一覧を宿題と呼びます。宿題を済ませると、3本が「このまま出せます」になりました。</p>
</div></header>

<main>
<section class="block" id="docs-sec"><div class="wrap">
  <h2 data-chip>4つの文書で見る</h2>
  <p class="p prose-max">どれもスキルなしの Claude Code に短い依頼文から書かせた架空の文書です。書き手の役も別の AI で、スキルの作者が用意した事実の一覧だけを見て答えます。1回目の宿題にその AI が答え、答えを入れて2回目を回しました。出力は手直しせずに載せています。</p>
  {doc_tabs}
</div></section>


<section class="block" id="checked"><div class="wrap">
  <h2 data-chip>確かめたこと</h2>
  {checked_html()}
</div></section>

<section class="block" id="how"><div class="wrap">
  <h2 data-chip>使い方</h2>
  <p class="p prose-max">ふだんは {cmd("/critical-thinking 稟議書.md")} だけで足ります。検査から組み直しまで6つの工程を通します。文書は Markdown かテキストのファイルで渡します。工程を分けて実行するときだけ、{cmd("/critical-thinking short 稟議書.md")} のようにサブコマンドを挟みます。</p>
  <div class="tbl-wrap"><table class="tbl"><thead><tr><th>サブコマンド</th><th>同じ意味の指示</th><th>何をするか</th></tr></thead><tbody>
    <tr><th scope="row">なし、または full</th><td>「稟議書.md を決裁者の目で見て直して」</td><td>全工程を通す。検査し、書き手にしか答えられない問いを3つまで聞いて答えを本文に入れ、直した文書から端的にした版と組み直した版も作る</td></tr>
    <tr><th scope="row">logic</th><td>「筋が通っているか検査して」</td><td>文書の中だけで、矛盾・根拠のない主張・食い違いを行番号つきの問いにする</td></tr>
    <tr><th scope="row">somosomo</th><td>「決裁者目線で、前提から疑って」</td><td>文書の外から、前提、他の選択肢、結論が覆る条件、誰が得をして誰が動くのか、を問う</td></tr>
    <tr><th scope="row">fix</th><td>「指摘を反映して直して」</td><td>検査の報告を本文に反映し、残りの問いを確認事項に出す</td></tr>
    <tr><th scope="row">short / detail</th><td>「もっと端的に」「もっと丁寧に」</td><td>決裁に要る根拠だけを本編に残す / 裏づけと論拠を本編に戻す</td></tr>
    <tr><th scope="row">rebuild</th><td>「構成から組み直して」</td><td>事実と決裁事項は保ち、構成案を3つ出す。1つは決裁事項を小さくする案</td></tr>
  </tbody></table></div>
  <div class="cmd"><code id="cmd2">/critical-thinking 稟議書.md</code><button type="button" data-copy="cmd2">コピー</button></div>
</div></section>

<section class="block" id="install"><div class="wrap">
  <h2 data-chip>インストール</h2>
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
        <p class="p">Claude Code、Codex、Cursor、OpenCode、Gemini CLI、GitHub Copilot など、Agent Skills に対応したコーディングエージェントで使えます。</p>
        <div class="cmd"><code id="cmd">npx skills add coji/natural-japanese</code><button type="button" data-copy="cmd">コピー</button></div>
        <p class="p">このコマンドで natural-japanese と critical-thinking の両方が入ります。natural-japanese の検査ツールには uv と Python が要りますが、critical-thinking には要りません。入れた直後は、セッションを開き直すか {cmd("/reload-plugins")} で読み込みます。</p>
      </div>
      <div class="dads-tab__panel" id="env-panel-2" role="tabpanel" aria-labelledby="env-tab-2" tabindex="0" hidden>
        <ol class="steps">
          <li><a href="https://github.com/coji/natural-japanese/releases/latest/download/critical-thinking.skill">critical-thinking.skill</a> をダウンロードする</li>
          <li>「カスタマイズ」→「スキル」→「+」→「スキルをアップロード」で、ダウンロードした zip ファイルを選ぶ</li>
          <li>文書を貼るか添付して、「この稟議書を決裁者の目で見て直して」と指示する</li>
        </ol>
      </div>
      <div class="dads-tab__panel" id="env-panel-3" role="tabpanel" aria-labelledby="env-tab-3" tabindex="0" hidden>
        <p class="p">ChatGPT Business、Enterprise、Edu で使えます。管理者がスキルのアップロードを許可している必要があります。</p>
        <ol class="steps"><li><a href="https://github.com/coji/natural-japanese/releases/latest/download/critical-thinking.skill">critical-thinking.skill</a> をダウンロードする</li><li>「スキル」→「作成」→「コンピューターからアップロード」で、ダウンロードした zip ファイルを選ぶ</li><li>文書を添付して頼む</li></ol>
      </div>
      <div class="dads-tab__panel" id="env-panel-4" role="tabpanel" aria-labelledby="env-tab-4" tabindex="0" hidden>
        <p class="p">Gemini アプリで使えます。2026年11月の時点では個人アカウントでも使えます。</p>
        <ol class="steps"><li><a href="https://github.com/coji/natural-japanese/releases/latest/download/critical-thinking.skill">critical-thinking.skill</a> をダウンロードして展開する</li><li>「カスタマイズ」→「スキル」→「作成」から、SKILL.md を含むフォルダをアップロードする</li><li>文書を添付して頼む</li></ol>
      </div>
      <div class="dads-tab__panel" id="env-panel-5" role="tabpanel" aria-labelledby="env-tab-5" tabindex="0" hidden>
        <p class="p">Microsoft 365 Copilot の宣言型エージェントにスキルを足す機能は、2026年11月の時点でプレビューです。</p>
        <ol class="steps"><li>Agent Builder でエージェントを作り、スキルとして <a href="https://github.com/coji/natural-japanese/releases/latest/download/critical-thinking.skill">critical-thinking.skill</a> を追加する</li><li>そのエージェントに文書を渡して頼む</li></ol>
      </div>
    </div>
  </div>
  <p class="p prose-max">4本の文書の元、直した後、端的にした後、組み直した後、検査の報告、確認事項の全文は <a href="https://github.com/coji/natural-japanese/tree/main/release-notes/data/v2.0.0">リポジトリの release-notes/data/v2.0.0</a> にあります。社名・人名・製品名は実在しません。</p>
</div></section>
</main>

<footer><div class="wrap">
  <p>見た目は、デジタル庁デザインシステムの <a href="https://github.com/digital-go-jp/design-system-example-components-html">HTML 実装例</a>に基づきます。ライセンスは MIT です。</p>
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
