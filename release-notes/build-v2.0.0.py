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
    """検査の報告の指摘の数: 太字の L1・S1 のような項目と、「細かいもの n 件」の n。"""
    lines = report.splitlines()
    numbered = re.compile(r"^(?:- |#{1,4} )?\*{0,2}[LSP]\d+")
    n = sum(1 for ln in lines if numbered.match(ln))
    # 「細かいもの n 件」は、その後の項目に L/S の番号が付いていないときだけ足す(番号つきなら上で数えている)
    for i, ln in enumerate(lines):
        m = re.match(r"^#{0,4}\s*細かいもの(?:が)?\s*(\d+)\s*件", ln)
        if not m: continue
        nxt = next((x for x in lines[i + 1:] if x.strip()), "")
        if not numbered.match(nxt): n += int(m.group(1))
    return n
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
ICON = '<svg aria-hidden="true" width="24" height="24" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" fill="#fff"/><path d="M12 15.2 6.8 10l1.06-1.06L12 13.08l4.14-4.14L17.2 10 12 15.2Z" fill="currentColor"/><circle cx="12" cy="12" r="10.5" stroke="currentColor" fill="none"/></svg>'
def disclosure(label, body):
    return f'<details class="dsc"><summary>{ICON}<span>{E(label)}</span></summary><div class="dsc-body">{body}</div></details>'
def _norm(t): return re.sub(r"[\s|*]", "", re.sub(r"<[^>]+>", "", t))
def V(v): return v.replace("聞きたい", "判断の前に質問あり")
def _hname(h): return re.sub(r"^##\s*(?:\d+[.．]\s*)?", "", h).strip()
def md(t): return markdown.markdown(t, extensions=["tables"])

# 一本道の出力(直した後の文書に short / rebuild をかけたもの)
for _k, _t in SETS.items():
    d = DATA / _k
    _t["short"] = (d / "doc-review.short.md").read_text()
    _t["rebuild"] = (d / "doc-review.rebuild.md").read_text()
    _t["P_short"], _t["P_rebuild"] = parts(_t["short"]), parts(_t["rebuild"])
    for k in ("short", "rebuild"):
        assert "要確認" not in _t[k] and "確認事項" not in "".join(h for h, _ in sections(_t[k])), (_k, k)
    _t["n_logic"] = count_items(_t["logic"]); _t["n_somo"] = count_items(_t["somo"])

KAK_TOTAL = sum(len(SETS[k]["kak"]) for k in SETS)
# ---------- 文書ごとに作者が書いた部分(引用は文書の文そのまま。build が照合する) ----------
# 決裁者が最初に聞くこと: (問い, 元の文書では, 直した後では)
ASKS = {
 "ringi": [
    ("時間単価はいくらか", "空欄(【 】円)", "経理部の標準単価 1時間3,500円。1件あたり約39分短縮できれば費用に見合う"),
    ("週8件は部全体か、1人あたりか", "書いていない", "部全体。営業支援システムの訪問記録から"),
    ("6か月で解約できるか", "契約前に確認する", "月単位で解約できる(販売店に確認済み)"),
    ("顧客は録音に同意するか", "全件で使う前提の試算", "見込みを出す材料がないと明記し、利用率の目安は空欄のまま確認事項へ"),
    ("何もしない案や、数名で試す案と比べたか", "書いていない", "本文にはなく、確認事項に残る"),
 ],
 "teian": [
    ("失注が起きているとは、何を根拠に", "「実際に失注が起きています」と言い切り", "営業本部長から2社と聞いただけで、資料では確かめていない、と明記"),
    ("営業担当は入力を続けるか", "4つの工夫を並べる", "3名に聞いて2名賛成・1名が手間を心配。続くかは確かめていない、と明記"),
    ("B社の事例は当てはまるか", "成果につながった例、と紹介", "受注率が上がった原因は営業記録の共有かどうか言えない、と明記"),
    ("効果は何で測るか", "指標を列挙", "失注率と新人の独り立ち期間で測り、入力率は定着の指標と分ける"),
 ],
 "kikaku": [
    ("本日決めるのは何か", "2027年4月から始めること", "制度を作る方針の承認と準備の着手。開始日は2月の最終案で決める"),
    ("辞めた人のうち、何名が対象か", "「退職理由の上位」", "回答者22名のうち9名、内勤7名"),
    ("離職率の差は何名か", "年間およそ30名", "31名(内勤19名、外勤など12名)"),
    ("在宅勤務で離職率は下がるのか", "辞める理由と、応募者に選ばれない理由の両方", "辞める理由の一部。在宅勤務だけで業界平均まで下がるとは考えていない"),
    ("VPN は足りるか", "上限100件、外勤の利用は確認中", "確認中のまま。確認事項に残る"),
 ],
 "postmortem": [
    ("何を決めてほしいのか", "書いていない", "2つ。再発防止の3つの方向と、調査に1週間かけてよいか"),
    ("疑っている改修は今も本番か", "書いていない", "切り戻しておらず、本番に残っている。再起動後は再発なし"),
    ("改修を疑う根拠は", "時期が近いことだけ", "同じ。半年前にも同じサーバーで通知が出た、を追加"),
    ("止まり方は全面か断続か", "確認中", "確認中(変わらず)"),
    ("対策の担当と期限は", "まだ決まっていない", "調査の結果が出てから改めて出す、と頼む形に"),
 ],
}
# 主な変更: (見出し, 説明, 元の文書の語句, 直した後の語句)。語句は文書の文そのままで、押すと左右の比較で該当箇所へ移動する
CHANGES = {
 "ringi": [
    ("前提の弱さを冒頭に", "目安の30分短縮(参考値)では費用に見合わないことと、規程との突き合わせが済んでいないことを、申請の文に添えた", "営業部の営業担当12名で6か月間試験導入したい。", "今ある参考値(1件30分の削減)では費用に見合わず"),
    ("書き手の答えを反映", "週8件は部全体の数で、出どころは訪問記録", "顧客打ち合わせが週に平均8件(月に約35件)ある。", "営業支援システムの訪問記録の直近6か月から出した"),
    ("空欄を埋める", "時間単価が入った", "【 】円(人事・経理部門に確認して記入)", "経理部が社内の試算に使う標準単価の1時間3,500円"),
    ("計算して言い切りを直す", "30分の参考値では回収できないと本文に書いた", "参考値どおり1件あたり30分減った場合の削減時間は、次のとおり", "今ある参考値の30分では届かない"),
    ("言い切りを根拠に合わせる", "確かめていないことは見立てとして書く", "担当者のメモの取り方に左右される。", "担当者のメモの取り方に左右されると見ている"),
    ("測れることを示す", "承認の前に2週間で測れる、という答えを入れた", "試験導入の開始前に測定する(8章)", "2週間あれば12名分を記録でき、承認の前に測ることもできる"),
 ],
 "teian": [
    ("出どころを示す", "失注は聞いた話で、資料では確かめていない", "御社ではこの引き継ぎの場面で実際に失注が起きています", "営業本部長からは、引き継ぎで2社を失ったとうかがっています"),
    ("言い切りを見込みに", "原因が情報の抜け落ちなら、の条件を付けた", "情報の抜け落ちによる失注を減らせます", "失注の原因が情報の抜け落ちであれば、その分の失注は減らせると見込みます"),
    ("事例の限界を書く", "B社の受注率の原因は言えない", "同業・同規模の会社で、営業記録の共有が成果につながった例です", "受注率が上がった原因が営業記録の共有かどうかは、この数字からは言えません"),
    ("書き手の答えを反映", "現場3名の声を事実として入れ、続くかは未確認と添えた", "当社はこの点を最も重要な課題と考え", "営業担当3名にうかがったところ、2名は賛成、1名は入力の手間を心配されていました"),
    ("指標を分ける", "失注率で効果を測り、入力率は定着の指標にした", "次の指標を使い、導入前後を比べて効果を確認します", "SFA の入力率は、導入後の定着を確かめる指標です"),
 ],
 "kikaku": [
    ("決めることを明記", "本日は方針の承認と準備の着手", "準備として、就業規則の改定", "作る方針を承認いただくこと"),
    ("開始日の扱い", "開始日は2月の最終案で決める", "2月の経営会議で最終案としてお諮りします。", "開始日も、その最終案で改めて決めていただきます"),
    ("書き手の答えを反映", "退職理由の上位、が人数になった", "退職理由の上位", "挙げたのは9名（うち内勤7名）"),
    ("数字の内訳", "およそ30名が、内訳つきの31名になった", "250名規模で年間およそ30名", "250名規模で31名。内勤19名、外勤など12名"),
    ("言い切りを根拠に合わせる", "採用の側は材料がないので「なりうる」に", "「辞める理由」と「選ばれない理由」の両方になっていると考えます", "「辞める理由」の一部で、「選ばれない理由」にもなりうると考えます"),
 ],
 "postmortem": [
    ("決めることを明記", "共有で終わる報告が、2つの判断を頼む報告になった", "受注管理システムの Web 画面が1時間半ほど応答しなくなりました。アプリケーションサーバー", "決めていただきたいことが2つあります"),
    ("書き手の答えを反映", "改修は本番に残っていて、再発はない", "改修が原因だとは確かめられていません。", "改修は切り戻しておらず、本番に残っています"),
    ("書き手の答えを反映", "半年前にも同じ通知があった", "根拠は反映と障害の時期が近いことだけで", "半年前に1度、同じサーバーのメモリで通知が出たことがあります"),
    ("言い切りを根拠に合わせる", "原因は「と見ています」に", "メモリが上限に達したためで、サーバーを再起動し", "メモリが上限に達したためと見ています"),
    ("頼む形にする", "対策は了承を頼み、中身は調査のあとに", "いずれも検討中で、具体的な内容、担当、期限はまだ決まっていません", "次の3つの方向でよいかの了承をお願いします"),
    ("食い違いを見せる", "再入力するのが誰かは確認中と書いた", "営業が顧客に再入力を頼みました。顧客からの問い合わせはありませんでした", "入力し直すのが営業か顧客かは確認中です"),
 ],
}
TILE_DECIDE = {  # 「決めてもらうこと」のタイル(見出し語, 数字, 単位, 説明)
 "ringi": ("決めてもらうこと", "3", "項目", "元から明記あり。目安の30分短縮(参考値)では費用に見合わないことを申請の文に添えた"),
 "teian": ("決めてもらうこと", "1", "文", "9か月・2,700万円のご契約。3か月目で止められることを要点に"),
 "kikaku": ("決めてもらうこと", "2", "項目", "4月開始の承認から、方針の承認と準備の着手に変わった"),
 "postmortem": ("決めてもらうこと", "2", "つ", "元の報告には書かれていなかった"),
}
for _k in SETS:
    _t = SETS[_k]
    for _title, _desc, _b, _a in CHANGES[_k]:
        assert _norm(_b) in _norm(_t["before"]), (_k, "before", _b[:20])
        assert _norm(_a) in _norm(_t["after"]), (_k, "after", _a[:20])

# ---------- 文書ごとのパネル ----------
STEPS = [("1. 文書の中を検査", "logic"), ("2. 文書の外から問う", "somosomo"), ("3. 書き手に聞く", "3問"), ("4. 本文を直す", "fix"), ("5. 端的にする", "short"), ("6. 構成を組み直す", "rebuild")]
def step_texts(t):
    return [f"主張と根拠の対応、矛盾を{t['n_logic']}件指摘", f"前提、代案、覆る条件を{t['n_somo']}件問う", "答えが要る3問だけを聞く", "答えを本文に入れ、言い切りを根拠に合わせる", "決裁に要る根拠を本編に残し、残りは付録へ", "構成案を3つ出し、決裁事項を小さくする案も示す"]
def tiles(key):
    t = SETS[key]; o = OUTC[key]; ov = OV[key]
    b0, b1, b2 = t["P0"]["body"], t["P1"]["body"], t["P_short"]["body"]
    dec = TILE_DECIDE[key]
    return f'''<div class="tiles">
  <div class="tile"><p class="l">本編の長さ</p><div class="v">{round((1 - b2 / b0) * 100)}%<small>短縮</small></div><p class="d">{fmt(b0)}字 → 直して {fmt(b1)}字 → 端的に {fmt(b2)}字</p></div>
  <div class="tile"><p class="l">{E(dec[0])}</p><div class="v">{E(dec[1])}<small>{E(dec[2])}</small></div><p class="d">{E(dec[3])}</p></div>
  <div class="tile"><p class="l">検査で見つけた問い</p><div class="v">{t["n_logic"] + t["n_somo"]}<small>件</small></div><p class="d">論理の指摘{t["n_logic"]}件、前提への問い{t["n_somo"]}件。うち3問を書き手に聞き、残りは確認事項へ</p></div>
  <div class="tile"><p class="l">書き手に残した確認事項</p><div class="v">{len(t["kak"])}<small>件</small></div><p class="d">うち先に答える問いは3件。本文には書き込まない</p></div>
</div>'''
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
    s = f'<svg viewBox="0 0 {W} {H}" class="fig map" role="img" aria-label="元の{len(L)}節が、組み直した後のどの節へ移ったか。箱の高さは字数に比例(※は縮めている)">'
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
    docs = {"before": t["before"], "after": t["after"], "short": t["short"], "rebuild": t["rebuild"]}
    tpl = "".join(f'<template id="t-{key}-{k}"><article>{md(v)}</article></template>' for k, v in docs.items())
    # 節の対応(左の節 i → 右の各文書の節 j)
    maps = {}
    for k in ("after", "short", "rebuild"):
        mv = compute_moves(t["before"], docs[k])
        rh = [_hname(h) for h, _ in sections(docs[k]) if h]
        maps[k] = [rh.index(mv[_hname(h)][0]) if h and mv.get(_hname(h)) and mv[_hname(h)][0] in rh else -1 for h, _ in sections(t["before"]) if h]
    return f'''<div class="seg" role="group" aria-label="右に出す文書"><button type="button" data-r="after" aria-pressed="true">決裁者の目で見て直した後</button><button type="button" data-r="short">もっと端的にした後</button><button type="button" data-r="rebuild">構成から組み直した後</button></div>
<div class="viewer" data-doc="{key}" data-maps='{json.dumps(maps)}'>
  <div class="pane"><p class="cap">元の文書 <span class="ln">本編 {fmt(t["P0"]["body"])}字</span></p><div class="doc L" tabindex="0"></div></div>
  <div class="pane"><p class="cap R-cap">直した後</p><div class="doc R" tabindex="0"></div></div>
</div>{tpl}'''
def doc_panel(key):
    t = SETS[key]; desc = dict((k, d) for k, _, d, *_ in DOCSETS)[key]
    steps = "".join(f'<li><b>{E(n)} <span class="chip" data-color="gray">{E(c)}</span></b><span>{E(x)}</span></li>' for (n, c), x in zip(STEPS, step_texts(t)))
    qa = "".join(f'<li>{E(q)}{disclosure("書き手の答え", f"<p>{E(a)}</p>")}</li>' for n, q, a in t["qa"])
    kak = f'<p class="p"><b>決裁事項を小さくする案</b> {E(t["shrink"])}</p><h4>先に答えるべき問い(行番号は元の文書の行。「本文」は直した後の文書)</h4><ol class="list">{"".join(f"<li>{E(x)}</li>" for x in t["kak_first"])}</ol><h4>そのほか {len(t["kak_rest"])} 件</h4><ul class="list">{"".join(f"<li>{E(x)}</li>" for x in t["kak_rest"])}</ul>'
    return f'''<p class="p prose-max">{E(desc)}</p>
<h3>ひとめで分かる変化</h3>
{tiles(key)}
<h3>スキルがしたこと</h3>
<p class="p prose-max">文書の中で答えが出ることは黙って直し、書き手にしか答えられないことだけを聞きます。検査で出た問いのうち3問を書き手に聞き、残りと新たな問いを確認事項にまとめます。その先頭3件が先に答えるべき問いです。工程の名前は、頼むときのサブコマンドです(somosomo は「そもそも」から)。</p>
<ol class="flow">{steps}</ol>
<div class="twoc"><div><h4>工程ごとの本編の字数</h4>{bars(key)}</div><div>{asks_table(key)}</div></div>
<h4>書き手に聞いた3問と答え</h4>
<p class="p prose-max">答えは書き手の役の AI が返しました(スキルの作者が事実の一覧を先に書き、AI はそれだけを見て答え、一覧にないことは「分からない」と答えます)。</p>
<ol class="list prose-max">{qa}</ol>
{disclosure(f"別ファイルに出した確認事項 {len(t['kak'])} 件と、先頭の「決裁事項を小さくする案」", kak)}
<h3>構成がどう変わったか</h3>
<p class="p prose-max">左が元の文書、右が「構成から組み直す」の出力です。線は、元の節の文がどこへ移ったかを示します。点線は付録へ移ったものです。箱の高さは字数に比例します(※は高さを縮めています)。</p>
<div class="map-wrap">{sankey(key)}</div>
<h3>主な変更 {len(CHANGES[key])} 件</h3>
<p class="p prose-max">番号を押すと、下の比較で左右の該当箇所へ移動します。</p>
{changes_list(key)}
<h3>左右に並べて読む</h3>
<p class="p prose-max">片方をスクロールすると、対応する節が並ぶようにもう片方も動きます。主な変更の箇所には下線が付きます。右の文書は切り替えられます。</p>
{viewer(key)}'''
tabs_html = '<ul class="dads-tab__list" role="tablist" aria-label="4つの文書">' + "".join(
    f'<li><button type="button" class="dads-tab__tab" role="tab" id="doc-tab-{i+1}" aria-selected="{"true" if i == 0 else "false"}" aria-controls="doc-panel-{i+1}" tabindex="{0 if i == 0 else -1}"><span>{E(l)}</span></button></li>'
    for i, (k, l, *_) in enumerate(DOCSETS)) + '</ul>'
def panel(prefix, i, body):
    return f'<div class="dads-tab__panel" id="{prefix}-panel-{i}" role="tabpanel" aria-labelledby="{prefix}-tab-{i}" tabindex="0"{"" if i == 1 else " hidden"}>{body}</div>'
doc_tabs = f'<div class="dads-tab" id="docs">{tabs_html}<div class="dads-tab__panels">{"".join(panel("doc", i + 1, doc_panel(k)) for i, (k, *_) in enumerate(DOCSETS))}</div></div>'
# ---------- 確かめたこと(欠陥を仕込んだ文書) ----------
def checked_html():
    rows = "".join(f'<tr><th scope="row">{E(DOC_LABEL[k])}</th><td>{E(READER[k])}</td><td>{E(V(OUTC[k]["元"]["verdict"]))}</td><td>{E(V(OUTC[k]["一括"]["verdict"]))}</td><td>{OV[k]["n"]} 件のうち {OV[k]["n"] - OV[k]["none"]} 件</td></tr>' for k, *_ in DOCSETS)
    assert HAVE_R46, "r46 系の summary がない"
    rw = rewrite_stats("r46b"); rd = rewrite_stats("r46d")
    cc = summary("r46e"); cl = summary("r46f")
    rv_rows = table_rows("r46c")
    rv_q = sum(int(r["cells"][0]) for r in rv_rows); rv_q_doc = sum(int(r["cells"][1]) for r in rv_rows)
    uudd = [tuple(int(x) for x in r["cells"][2].split("/")) for r in rv_rows]
    rv_used = sum(u[0] for u in uudd); rv_drop = sum(u[3] for u in uudd)
    cc_ok = [(int(a), int(b)) for a, b in re.findall(r"満たした run: (\d+)/(\d+)", cc + cl)]
    method = f'''<p>上司や顧客の役は別のセッションの Claude Opus 5.5 で、文書ごとに経営者、提案を受け取る会社の役員、報告を受け取る上司です。元の文書と直した後を、どちらが直した後かを知らせずに別々に渡し、返事(OK、条件つきOK、判断の前に質問あり、却下)と指摘を3回ずつ返させました。指摘と確認事項の照合は Claude Sonnet 5.5 が行い、判定が甘くないかは、別の文書どうしを組み合わせた42組(ある文書への指摘と、無関係な文書の確認事項)で全部「ない」と出ることを確かめました。</p>
<p>テスト用の文書は、スキルの作者が欠陥(表と本文で食い違う数字、根拠のない見込み、診断の後で決めるはずなのにもう書いてある製品名、報告日より後の「実施済み」など)を仕込んだ架空の文書5本と、ない欠陥を指摘しないかを見る欠陥のない4本です。問いが欠陥を捉えたか、直しが欠陥を解いたか、書き手の答えを改変せずに入れたかは Claude Sonnet 5.5 が判定しました。書かせたのも直したのも Claude Opus 5.5 で、人による確認はしていません。「構成から組み直して」は、欠陥を仕込んだ文書のうち4本を3回ずつ組み直した {rd['n']} 本すべてで決裁事項を小さくする案が出て、主結論と決裁事項は {rd['kept']} 本で元のままでした。組み直した本編が元より長くなった回が制度企画で2本(いずれも元の 2% 以内)ありました。「もっと端的に」「もっと丁寧に」は、主結論・決裁事項・数値が保たれ本編の各文が元の文書に対応することを条件とし、{sum(b for _, b in cc_ok)} 回中 {sum(a for a, _ in cc_ok)} 回で満たしました(満たさなかった1回は、丁寧にした本編が元の 110% を超えたもの)。回ごとの結果は <a href="https://github.com/coji/natural-japanese/blob/main/dev/ct-eval/RESULTS.md">dev/ct-eval/RESULTS.md</a> にあります。</p>'''
    return f'''<h3>上の4本で</h3>
  <div class="tbl-wrap"><table class="tbl"><thead><tr><th>文書</th><th>読む役</th><th>元の文書への返事</th><th>直した後への返事</th><th>元の文書への指摘のうち、確認事項にあったもの</th></tr></thead><tbody>{rows}</tbody></table></div>
  <p class="p prose-max">指摘 {OV_TOTAL} 件(同じ文書を3回読ませた合計)のうち、確認事項になかったものは {OV_NONE} 件。各文書の「先に答えるべき3件」(4本で12件)に入っていたのは {OV_FIRST} 件で、残りは「そのほか」にありました。</p>
  <h3>テスト用の文書で</h3>
  <p class="p prose-max">スキルの作者が欠陥を仕込んだ架空の文書5本と、欠陥のない4本に、このバージョンのスキルを3回ずつかけました。</p>
  <div class="tiles">
    <div class="tile"><p class="l">仕込んだ欠陥{DET["rows"]}か所を3回ずつ検査した計{DET["found"] + DET["partial"] + DET["missed"]}回のうち、問いにできた</p><div class="v">{DET["found"]}<small>回</small></div><p class="d">見落とし {DET["missed"]}</p></div>
    <div class="tile"><p class="l">検査が元にない事実を持ち込んだ</p><div class="v">{DET["crossing"]}<small>件</small></div><p class="d">欠陥のない4本で、ない欠陥を指摘したのは {sum(DET["false_clean"])} 件</p></div>
    <div class="tile"><p class="l">「決裁者の目で見て直す」が書き手に聞いた問い(3本を3回ずつ、計{len(rv_rows)}回)</p><div class="v">{rv_q}<small>件</small></div><p class="d">文書の中で答えが出るもの {rv_q_doc}。答えは改変せずに本文に入れ、落としたのは {rv_drop} 件</p></div>
    <div class="tile"><p class="l">「指摘を反映して直して」が仕込んだ欠陥を直すか確認事項に回した</p><div class="v">{rw["fixed"] + rw["deferred"]}<small>回</small></div><p class="d">残った {rw["remains"]}。本編が元より長くならなかったのは {rw["n"]} 本(5本×3回)中 {rw["not_longer"]} 本、元にない事実の持ち込み {rw["crossing"]} 件</p></div>
  </div>
  {disclosure("測り方と注", method)}'''

R = SETS["ringi"]
OLDER_LINKS = ""
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
      <li><a href="#docs-sec">4つの文書で見る</a></li>
      <li><a href="#limits">言えること、言えないこと</a></li>
      <li><a href="#checked">確かめたこと</a></li>
      <li><a href="#how">頼み方</a></li>
      <li><a href="#install">インストール</a></li>
    </ol>
  </div>
</nav>

<header class="hero" id="top"><div class="wrap">
  <p class="eye">natural-japanese v{VER} リリースノート 2026年11月</p>
  <h1>上司や顧客が聞いてくることを提出前に洗い出すスキル critical-thinking を追加しました</h1>
  <p class="p lead">natural-japanese は、AI の書く日本語を自然にするスキルです。v2.0.0 では、文書の中身を検査する critical-thinking を加えました。AI に稟議書や提案資料を書かせると、丁寧で穴のなさそうな文書ができます。それでも上司や顧客は「<mark>この数字は誰の分か</mark>」「<mark>空欄のままで判断できない</mark>」と聞いてきます。critical-thinking(Claude Code や ChatGPT に読み込ませて使います)に「決裁者の目で見て直して」と頼むと、文書の中で答えが出ることは黙って直し、書き手にしか答えられないことを3つ聞いて答えを本文に入れ、残りの問いを別ファイルの確認事項に残します。</p>
  <p class="p lead">下は、スキルなしの AI が書いた架空の稟議書に通した実演です。本編(付録を除いた本文){fmt(R["P0"]["body"])} 字が、直して {fmt(R["P1"]["body"])} 字、端的にして {fmt(R["P_short"]["body"])} 字になり、空欄だった時間単価と、週8件が部全体の数であることが本文に入りました。上司や顧客の役をさせた別の AI に4本の元の文書を読ませた指摘は、すべてこのスキルの確認事項に含まれていました。</p>
</div></header>

<main>
<section class="block" id="docs-sec"><div class="wrap">
  <h2 data-chip>4つの文書で見る</h2>
  <p class="p prose-max">どれもスキルなしの Claude Code(Opus 5.5)に短い依頼文から書かせた架空の文書で、書かせたままです。「決裁者の目で見て直して」のあとに「もっと端的に」「構成から組み直して」を続けました。問いと答え、確認事項の引用は出力のままです。</p>
  {doc_tabs}
</div></section>

<section class="block" id="limits"><div class="wrap">
  <h2 data-chip>この実演で言えること、言えないこと</h2>
  <ul class="list prose-max">
    <li>言えること: 上司や顧客の役の AI が元の文書に出した指摘は、4本とも、すべてスキルの確認事項にありました。直した後の文書への指摘は、「他の案と比べたか」のように書き手の判断を求めるものに変わります。</li>
    <li>言えないこと: 本物の上司や顧客では試していません。書き手の答え、直す側、読む役はすべて AI で、直す側と読む役は同じモデル(Claude Opus 5.5)です。読み手役の AI の返事(下の表)は直す前からほぼ「条件つきOK」で、直してもほとんど変わりません。4本とも元から形は整っているためです。</li>
    <li>書き手に聞くのは3つまでなので、聞かなかった問いは確認事項に残ります。稟議書では{len(R["kak"])}件でした。</li>
    <li>書き手の答えが本文に入ると、申請の弱さがそのまま見えます。下のテスト用の文書(欠陥を仕込んだ稟議書)では、答えを入れた文書を経営者役が「最良の前提でも効果が費用を下回る」と差し戻しました。スキルはそのとき、確認事項の先頭に決裁事項を小さくする案を書いています。</li>
    <li>文書の外の事実は調べに行きません。他社の事例が本当かは、問いにして返すだけです。検査は LLM の読みに頼るので、同じ文書をもう一度検査すると、指摘の数や言い方は揺れます。</li>
  </ul>
</div></section>

<section class="block" id="checked"><div class="wrap">
  <h2 data-chip>確かめたこと</h2>
  {checked_html()}
</div></section>

<section class="block" id="how"><div class="wrap">
  <h2 data-chip>頼み方</h2>
  <p class="p prose-max">文書は Markdown かテキストのファイルで渡します。基本は「決裁者の目で見て直して」の1つで、工程を分けるときはサブコマンドか、同じ意味の言葉で頼みます。Claude Code では <code>/critical-thinking short 稟議書.md</code> のように、コマンドにサブコマンドとファイル名を続けます。「決裁者の目で見て直す」のあとには、次にできること(short / rebuild / ここで終える)が返答の最後に示されます。</p>
  <div class="tbl-wrap"><table class="tbl"><thead><tr><th>サブコマンド</th><th>同じ意味の頼み方</th><th>何をするか</th></tr></thead><tbody>
    <tr><th scope="row">(なし)</th><td>「稟議書.md を決裁者の目で見て直して」</td><td>検査から直しまでを1回で通す。書き手にしか答えられない問いを3つまで聞き、答えを本文に入れる</td></tr>
    <tr><th scope="row">logic</th><td>「筋が通っているか検査して」</td><td>文書の中だけで、矛盾・根拠のない主張・食い違いを行番号つきの問いにする</td></tr>
    <tr><th scope="row">somosomo(「そもそも」から)</th><td>「決裁者目線で、前提から疑って」</td><td>文書の外から、前提・他の選択肢・覆る条件・利害と実行を問う</td></tr>
    <tr><th scope="row">fix</th><td>「指摘を反映して直して」</td><td>検査の報告を本文に反映し、残りの問いを確認事項に出す</td></tr>
    <tr><th scope="row">short / detail</th><td>「もっと端的に」「もっと丁寧に」</td><td>決裁に要る根拠だけを本編に残す / 裏づけと論拠を本編に戻す</td></tr>
    <tr><th scope="row">rebuild</th><td>「構成から組み直して」</td><td>事実と決裁事項は保ち、構成案を3つ出す。1つは決裁事項を小さくする案</td></tr>
  </tbody></table></div>
  <div class="cmd"><code id="cmd2">/critical-thinking short 稟議書.md</code><button type="button" data-copy="cmd2">コピー</button></div>
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
        <p class="p">Claude Code、Codex、Cursor、Gemini CLI、GitHub Copilot など、Agent Skills に対応したコーディングエージェント。</p>
        <div class="cmd"><code id="cmd">npx skills add coji/natural-japanese</code><button type="button" data-copy="cmd">コピー</button></div>
        <p class="p">このコマンドで natural-japanese と critical-thinking の両方が入ります。natural-japanese の検査ツールと違い、critical-thinking に uv と Python は要りません。入れた直後は、セッションを開き直すか `/reload-plugins` で読み込みます。</p>
      </div>
      <div class="dads-tab__panel" id="env-panel-2" role="tabpanel" aria-labelledby="env-tab-2" tabindex="0" hidden>
        <ol class="steps">
          <li><a href="https://github.com/coji/natural-japanese/releases/latest/download/critical-thinking.skill">critical-thinking.skill</a> をダウンロードする</li>
          <li>「カスタマイズ」→「スキル」→「+」→「スキルをアップロード」で、ダウンロードしたファイル(zip 形式)を選ぶ</li>
          <li>文書を貼るか添付して、「この稟議書を決裁者の目で見て直して」と頼む</li>
        </ol>
      </div>
      <div class="dads-tab__panel" id="env-panel-3" role="tabpanel" aria-labelledby="env-tab-3" tabindex="0" hidden>
        <p class="p">ChatGPT Business、Enterprise、Edu。管理者がスキルのアップロードを許可している必要があります。</p>
        <ol class="steps"><li><a href="https://github.com/coji/natural-japanese/releases/latest/download/critical-thinking.skill">critical-thinking.skill</a> をダウンロードする</li><li>「スキル」→「作成」→「コンピューターからアップロード」で、ダウンロードしたファイル(zip 形式)を選ぶ</li><li>文書を添付して頼む</li></ol>
      </div>
      <div class="dads-tab__panel" id="env-panel-4" role="tabpanel" aria-labelledby="env-tab-4" tabindex="0" hidden>
        <p class="p">Gemini アプリ。2026年11月の時点で個人アカウントで使えます。</p>
        <ol class="steps"><li><a href="https://github.com/coji/natural-japanese/releases/latest/download/critical-thinking.skill">critical-thinking.skill</a> をダウンロードして展開する</li><li>「カスタマイズ」→「スキル」→「作成」から、SKILL.md を含むフォルダをアップロードする</li><li>文書を添付して頼む</li></ol>
      </div>
      <div class="dads-tab__panel" id="env-panel-5" role="tabpanel" aria-labelledby="env-tab-5" tabindex="0" hidden>
        <p class="p">Microsoft 365 Copilot の宣言型エージェントにスキルを足す機能は、2026年11月の時点でプレビューです。</p>
        <ol class="steps"><li>Agent Builder でエージェントを作り、スキルとして <a href="https://github.com/coji/natural-japanese/releases/latest/download/critical-thinking.skill">critical-thinking.skill</a> を追加する</li><li>そのエージェントに文書を渡して頼む</li></ol>
      </div>
    </div>
  </div>
  <p class="p prose-max">4本の文書の全文(元・直した後・端的にした後・組み直した後・検査の報告・確認事項)は <a href="https://github.com/coji/natural-japanese/tree/main/release-notes/data/v2.0.0">リポジトリの release-notes/data/v2.0.0</a> にあります。社名・人名・製品名は実在しません。</p>
</div></section>
</main>

<footer><div class="wrap">
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
