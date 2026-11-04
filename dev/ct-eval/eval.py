# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""critical-thinking スキルの評価ハーネス。

dev/ct-eval/fixtures/ にある文書に logic と somosomo を複数回かけ、次を測る。
`<名前>.expected.json` がある文書は欠陥を仕込んだ文書(ringi-planted, postmortem-planted)、
ない文書は欠陥のない文書(ringi-clean, postmortem-clean)として扱う。

1. 機械的な検査(LLM を使わない。1つでも落ちれば終了コード 1)
   - 対象ファイルが変わっていない(ハッシュ)
   - logic: <ファイル>.logic.yaml が存在し、pyyaml で読め、種別が5つの中にあり、
     文書の非空行がすべてどこかの `行` に現れる
   - somosomo: 既存の YAML が変わっていない
   - 報告に「弱めるべき」「条件を足すべき」「〜べき」がない
   - 報告の指摘の各項目に行番号がある
   - 報告に「文書の性格」の行がある
2. 判定(claude を判定者にする。dev/ct-eval/prompts/judge.txt)
   - 仕込んだ欠陥ごとに found / partial / missed
   - 仕込んでいない指摘を plausible(妥当)/ false(読み違い)/ crossing(持ち込み)に分類
3. 集計
   - 欠陥ごとの検出回数(N 回中)。安定検出 = 2/3 以上で found
   - 欠陥のない文書での false(誤検知)の件数
   - crossing(持ち込み)の件数(0 が条件)
4. rewrite(「指摘を反映して直す」工程。欠陥を仕込んだ文書だけ)
   - logic と somosomo の 1 回目の報告を渡し、source-after.md に直させる
   - 機械的な検査: 本文に【要確認】の印がない、改訂の経緯を書いていない、元より長くない、
     見出しが短い名詞句のまま、確認事項が文書の中になく別ファイル(<元の文書>.確認事項.md)にある、元にない固有名詞や英字の語がない
   - 判定(prompts/judge-rewrite.txt): 欠陥ごとに fixed / deferred / remains、
     足した内容を plausible(妥当)/ crossing(持ち込み)に分類

使い方:
    uv run dev/ct-eval/eval.py --dry-run
    uv run dev/ct-eval/eval.py --repeat 3 --jobs 6 --run-label 2026-10-31-r1
    uv run dev/ct-eval/eval.py --modes logic --fixtures ringi-planted --repeat 1
    uv run dev/ct-eval/eval.py --fixtures postmortem-planted,postmortem-clean
    uv run dev/ct-eval/eval.py --modes rewrite --reports-from r12 --repeat 3   # 直す工程だけ。報告は r12 のを使う

生成物は dev/ct-eval/runs/<run-label>/ に残る(gitignore)。集計は同じディレクトリの summary.md と、
標準出力に出す。release.yml には入れない(費用と認証が要るので手で回す)。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
FIXTURES = HERE / "fixtures"
DEFAULT_FIXTURES = "ringi-planted,ringi-clean,postmortem-planted,postmortem-clean,teian-planted,teian-clean,kikaku-planted,kikaku-clean,ringi-long-planted"
RUNS = HERE / "runs"
JUDGE_PROMPT = (HERE / "prompts" / "judge.txt").read_text()
JUDGE_REWRITE_PROMPT = (HERE / "prompts" / "judge-rewrite.txt").read_text()
JUDGE_REDESIGN_PROMPT = (HERE / "prompts" / "judge-redesign.txt").read_text()
NEWFACTS = REPO / "skills" / "natural-japanese" / "scripts" / "newfacts.py"

ALLOWED_KINDS = {"事実", "推論", "意見", "前提", "見積"}
TABLE_RULE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")
FORBIDDEN = ["弱めるべき", "条件を足すべき", "べきだ", "べきです", "弱めた方が", "足した方が", "出し直して", "書き足す", "足すとよい", "書き直して"]
# cd を許さないと「cd X; cat Y」の複合コマンドが1回却下され、以後 Bash を使わなくなる(dontAsk の却下文が回避を禁じるため)
RUN_TOOLS = ["Skill", "Read", "Write", "Edit", "Glob", "Grep", "Bash(uv run:*)", "Bash(uv:*)", "Bash(python3:*)",
             "Bash(cd:*)", "Bash(cat:*)", "Bash(head:*)", "Bash(tail:*)", "Bash(echo:*)", "Bash(wc:*)", "Bash(ls:*)",
             "Bash(grep:*)", "Bash(sed:*)", "Bash(awk:*)"]
JUDGE_TOOLS = ["Read", "Write", "Glob"]
REWRITE_TOOLS = RUN_TOOLS + ["Bash(cp:*)", "Bash(diff:*)", "Bash(mkdir:*)"]
# 本文に埋めてはいけない印。直した文書にあれば落とす
MARKERS = re.compile(r"【要確認】|要確認|TODO")  # 「確認中」は食い違いを見せる書き方として許す(SKILL.md 直す 3)
# 改訂の経緯。元の文書にある分は引いて数える
REVISION_NOTES = re.compile(r"改訂|第\s*[0-9０-９一二三四五]\s*版|\bv[0-9]|指摘を反映|レビューを反映|初版|前版")

UNATTENDED = "この実行では対話ができません。確認したくなったことは自分で判断して進め、何をどう判断したかを最後の返答に書いてください。"
PROMPTS = {
    "logic": "critical-thinking スキルの logic モードで {file} を検査してください。結果の報告をそのまま report.md に書き出してください。" + UNATTENDED,
    "somosomo": "critical-thinking スキルの somosomo モードで {file} を検査してください。結果の報告をそのまま report.md に書き出してください。" + UNATTENDED,
    # 規則の中身は書かない(スキルがどう直すかを測るため)
    "rewrite": "{file} に対する critical-thinking の検査結果が report-logic.md と report-somosomo.md にあります。この指摘を反映して文書を直し、直した本文を source-after.md に、確認事項を source.確認事項.md に保存してください。{file} はそのまま残してください。" + UNATTENDED,
    "redesign": "{file} に対する critical-thinking の検査結果が report-logic.md と report-somosomo.md にあります。この文書を構成から組み直してください。構成案は plans.md に、組み直した本文は source-after.md に、確認事項は source.確認事項.md に保存してください。{file} はそのまま残してください。" + UNATTENDED,
    "concise": "{file} の論理構造が {file}.logic.yaml にあります。critical-thinking スキルで、この文書をもっと端的にしてください。書き直した本文は source-after.md に、確認事項があれば source.確認事項.md に保存してください。{file} はそのまま残してください。" + UNATTENDED,
    "detailed": "{file} の論理構造が {file}.logic.yaml にあります。critical-thinking スキルで、この文書をもっと丁寧にしてください。書き直した本文は source-after.md に、確認事項があれば source.確認事項.md に保存してください。{file} はそのまま残してください。" + UNATTENDED,
    # 一括経路。1回目は問いを questions.md に書いて終わる。2回目は answers.md を読んで直す
    "review": "critical-thinking スキルで {file} を決裁者の目で見て直してください。直した本文は source-after.md に、確認事項は source.確認事項.md に保存してください。{file} はそのまま残してください。この実行では書き手と対話ができません。隣に answers.md があれば、それを書き手の答えとして読み、最後まで直してください。なければ、書き手に聞きたいことを questions.md に「1. 問い」の形で書いて、この実行は終わりにしてください(答えは次の実行で渡されます)。ほかに確認したくなったことは自分で判断して進め、何をどう判断したかを最後の返答に書いてください。",
}
WRITER_PROMPT = "あなたは {file} の書き手です。あなたが知っていることは writer.json の facts に書いてあることだけです。questions.md の各問いに、facts にあることだけを使って日本語で答えてください。facts にないことは「分からない」と答えます(推測や一般論で埋めると、書き手の事実でないものが文書に入るためです)。答えは answers.md に、問いごとに「1. 問い:…\n   答え:…」の形で書いてください。読むのは questions.md と writer.json だけです。"
JUDGE_REVIEW_PROMPT = (HERE / "prompts" / "judge-review.txt").read_text()
JUDGE_LENGTH_PROMPT = (HERE / "prompts" / "judge-length.txt").read_text()
WRITER_TOOLS = ["Read", "Write"]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def make_plugin_dir() -> Path:
    """未コミットのスキルも含めるため、git archive ではなく作業ツリーをコピーする。"""
    d = Path(tempfile.mkdtemp(prefix="ct-plugin-"))
    shutil.copy(REPO / "plugin.json", d / "plugin.json")
    shutil.copytree(REPO / ".claude-plugin", d / ".claude-plugin")
    shutil.copytree(REPO / "skills", d / "skills", ignore=shutil.ignore_patterns("__pycache__"))
    return d


def claude(prompt: str, cwd: Path, tools: list[str], model: str, effort: str, plugin: Path | None, log: Path,
           timeout: int = 1800) -> None:
    # --tools は利用可能なツールの集合(パターン不可、ツール名だけ)。--allowedTools はパターンつきで自動許可
    base = sorted({t.split("(")[0] for t in tools})
    cmd = ["claude", "-p", prompt, "--model", model, "--effort", effort, "--output-format", "stream-json", "--verbose",
           "--setting-sources", "project", "--permission-mode", "dontAsk", "--strict-mcp-config",
           "--tools", ",".join(base), "--allowedTools", ",".join(tools)]
    if plugin:
        # --add-dir がないと、プラグインのディレクトリへの cd が作業ディレクトリの外として却下される
        cmd += ["--plugin-dir", str(plugin), "--add-dir", str(plugin)]
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    log.write_text(r.stdout + "\n--- stderr ---\n" + r.stderr)


# ---------------------------------------------------------------------------
# 機械的な検査
# ---------------------------------------------------------------------------

def weight_stats(data) -> dict:
    """重みの付け方の記録(CT11)。決裁に要るの本数、論点の数、記述で数値のない決裁に要る、
    決裁事項を並べた節を論点にしていないか(これだけ合否に入れる)、依存の論点で決裁に要るが 0 のもの"""
    out: dict = {}
    if not isinstance(data, dict):
        return out
    kessai_lines: set[int] = set()
    main = data.get("主結論") or {}
    for k in main.get("決裁事項") or []:
        collect_lines(k, kessai_lines)
    deps = set(main.get("依存") or [])
    n_kessai = n_ronten = n_nonum = n_dup = 0
    dep_zero: list[str] = []
    for r in data.get("論点") or []:
        if not isinstance(r, dict):
            continue
        n_ronten += 1
        gl: set[int] = set()
        collect_lines(r.get("根拠"), gl)
        if gl and kessai_lines and gl <= kessai_lines:
            n_dup += 1
        c = 0
        for g in r.get("根拠") or []:
            if isinstance(g, dict) and g.get("重み") == "決裁に要る":
                c += 1
                if r.get("種類") == "記述" and not re.search(r"\d", str(g.get("内容", ""))):
                    n_nonum += 1
        n_kessai += c
        if r.get("名前") in deps and c == 0:
            dep_zero.append(str(r.get("名前")))
    out["n_kessai"] = n_kessai
    out["n_ronten"] = n_ronten
    out["n_desc_kessai_nonum"] = n_nonum
    out["no_ronten_dup_kessai"] = n_dup == 0
    out["dep_ronten_without_kessai"] = ",".join(dep_zero)
    return out


def collect_lines(obj, acc: set[int]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "行" and isinstance(v, list):
                acc.update(int(x) for x in v if isinstance(x, int))
            elif k == "行" and isinstance(v, int):
                acc.add(v)
            else:
                collect_lines(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            collect_lines(v, acc)


def collect_kinds(obj, acc: set[str]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "種別" and isinstance(v, str):
                acc.add(v)
            else:
                collect_kinds(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            collect_kinds(v, acc)


def mechanical(mode: str, src: Path, src_sha: str, yaml_path: Path, yaml_sha_before: str | None, report: Path) -> dict:
    checks: dict[str, bool | str] = {}
    checks["source_unchanged"] = sha(src) == src_sha
    checks["report_exists"] = report.exists()
    text = report.read_text() if report.exists() else ""
    checks["has_character_line"] = "文書の性格" in text
    # 「べきだった(か)」は過去の判断を問う形で、直し方の指示ではない
    hits = [w for w in FORBIDDEN if w in text and not (w == "べきだ" and not re.search(r"べきだ(?!った)", text))]
    checks["no_forbidden_phrases"] = not hits
    if hits:
        checks["forbidden_hits"] = ",".join(hits)
    # 指摘の各項目(箇条書き)に行番号があるか。「### 指摘」以降〜「YAML」より前の箇条書きだけを見る
    # 最初の「## 」見出しから「YAML の保存先」までを指摘の本体とみなす
    body = text
    # 指摘の節から数える。主結論の節で YAML に補った前提を箇条書きにすることがあり、それは指摘ではない
    m = re.search(r"^#{2,3}\s*(?:\d+[.．]?\s*)?(?:指摘|矛盾|前提)", text, re.M) or re.search(r"^## ", text, re.M)
    if m:
        body = text[m.start():]
    m2 = re.search(r"YAML の保存先|## YAML|\*\*YAML|\.logic\.yaml", body)
    if m2:
        # 目印を含む行ごと落とす(行の途中で切ると、残った前半が箇条書きとして数えられる)
        body = body[: body.rfind("\n", 0, m2.start()) + 1]
    # 行番号を求めるのは指摘そのもの。3点セットの「問い」「要る材料」や件数の行は除き、「倒れる場所」は必ず行番号を求める
    skip = re.compile(r"^\**\s*(問い|要る材料|意図の分かるもの|分からないもの|些末|細かいもの|そのほか|同じ文書を|直すかどうかは|ここで挙げたのは|どう倒れるか)")
    # 「1. **見出し**」のように全体が太字の見出しだけの項目は、行番号が下の「倒れる場所」に付くので数えない
    title_only = re.compile(r"^\*\*[^*]+\*\*\s*[::]?\s*$")
    # 指摘の見出し(太字や ### の行)に行番号があれば、その下の箇条書き(問いや計算の内訳)は行番号なしでよい
    has_line = re.compile(r"行\s*\d|\d+\s*行|\[\d")
    bullets, no_line = [], []
    head_has_line = head_line = False
    blines = body.splitlines()
    for idx, ln in enumerate(blines):
        mb = re.match(r"^\s*(?:[-*]|\d+\.)\s+(.+)$", ln)
        if not mb:
            if ln.strip():
                # 直前の見出しか地の文に行番号があれば、その下の箇条書きは同じ指摘の内訳とみなす
                is_head = ln.lstrip().startswith(("#", "**")) or ln.rstrip().endswith("**")
                if is_head:
                    head_line = bool(has_line.search(ln))
                head_has_line = head_line or bool(has_line.search(ln))
            continue
        b = mb.group(1)
        if len(b) <= 20 or skip.match(b) or title_only.match(b.strip()):
            continue
        bullets.append(b)
        # 指摘の見出しになっている箇条書きで、行番号がその下の子の箇条書きに付いているものも紐づいているとみなす
        nxt = next((x for x in blines[idx + 1:] if x.strip()), "")
        child_has_line = bool(re.match(r"^\s+(?:[-*]|\d+\.)\s+", nxt)) and bool(has_line.search(nxt))
        if not has_line.search(b) and not head_has_line and not child_has_line:
            no_line.append(b)
    checks["bullets_total"] = len(bullets)
    checks["bullets_without_line"] = len(no_line)
    if no_line:
        checks["bullets_without_line_list"] = " / ".join(b[:60] for b in no_line[:5])
    checks["all_bullets_have_line"] = len(no_line) == 0

    if mode == "logic":
        checks["yaml_exists"] = yaml_path.exists()
        if yaml_path.exists():
            try:
                data = yaml.safe_load(yaml_path.read_text())
                checks["yaml_parses"] = True
            except Exception as e:  # noqa: BLE001
                data = None
                checks["yaml_parses"] = False
                checks["yaml_error"] = str(e)[:200]
            if data:
                kinds: set[str] = set()
                collect_kinds(data, kinds)
                checks["kinds_valid"] = kinds <= ALLOWED_KINDS
                if not checks["kinds_valid"]:
                    checks["bad_kinds"] = ",".join(sorted(kinds - ALLOWED_KINDS))
                lines: set[int] = set()
                collect_lines(data, lines)
                # 表の罫線は coverage.py と同じく数えない(CT9)
                nonempty = {i + 1 for i, l in enumerate(src.read_text().splitlines()) if l.strip() and not TABLE_RULE.match(l)}
                missing = sorted(nonempty - lines)
                checks["all_lines_covered"] = not missing
                checks["missing_lines"] = ",".join(map(str, missing[:20]))
                checks["has_character_in_yaml"] = "文書の性格" in data
                checks.update(weight_stats(data))
    else:
        if yaml_sha_before is None:
            # 足場の YAML を渡していない run: somosomo が自分で logic の YAML を作る経路
            checks["yaml_created"] = yaml_path.exists()
        else:
            checks["yaml_unchanged"] = yaml_path.exists() and sha(yaml_path) == yaml_sha_before
        checks["three_parts"] = all(k in text for k in ("問い", "倒れる場所", "要る材料"))
    gate_keys = [k for k, v in checks.items() if isinstance(v, bool)]
    checks["PASS"] = all(checks[k] for k in gate_keys)
    return checks


def _nonspace(t: str) -> int:
    return len(re.sub(r"\s", "", t))


def mechanical_rewrite(src: Path, src_sha: str, after: Path, log: Path) -> dict:
    checks: dict[str, bool | str | int] = {}
    checks["source_unchanged"] = sha(src) == src_sha
    checks["after_exists"] = after.exists()
    if not after.exists():
        checks["PASS"] = False
        return checks
    before = src.read_text()
    text = after.read_text()
    # 印が本文にないか(確認事項の節は文書の中に作らないので、あれば落とす)
    heads = [(m.start(), m.group(0)) for m in re.finditer(r"^#{1,6}\s+.*$", text, re.M)]
    kakunin = [pos for pos, h in heads if "確認事項" in h]
    body = text[: kakunin[-1]] if kakunin else text
    n_markers = len(MARKERS.findall(body)) - len(MARKERS.findall(before))
    checks["markers_in_body"] = max(n_markers, 0)
    checks["no_markers_in_body"] = n_markers <= 0
    # 改訂の経緯
    n_rev = len(REVISION_NOTES.findall(text)) - len(REVISION_NOTES.findall(before))
    checks["revision_notes_added"] = max(n_rev, 0)
    checks["no_revision_notes"] = n_rev <= 0
    # 長さ。決める人が読む本編(付録を除く)が元より長くないか
    def body_only(t: str) -> str:
        out, keep, cut_level = [], True, 0
        for line in t.splitlines():
            m = re.match(r"^(#{1,3})\s", line)
            if m:
                level = len(m.group(1))
                # 付録は ## でも # でも始まる(r36f で「# 付録」の下の「## 背景」が本編に数えられた)。
                # 付録の見出しより深い見出しでは本編に戻らない
                if re.match(r"^#{1,3}\s*(\d+[.．]?\s*)?(確認事項|付録|別紙)", line):
                    keep, cut_level = False, level
                elif not keep and level <= cut_level:
                    keep = True
            if keep:
                out.append(line)
        return "\n".join(out)
    checks["chars_before"] = _nonspace(body_only(before))
    checks["chars_after"] = _nonspace(text)
    checks["chars_after_body"] = _nonspace(body_only(text))
    # 数え方の差(空白や表の罫線を含めるか)を吸収するため 1% まで許す
    checks["not_longer"] = checks["chars_after_body"] <= checks["chars_before"] * 1.01
    # 見出しは短い名詞句のまま(番号を除いて 25 字以内、【 と 。 を含まない)
    bad_heads = []
    # 元の文書にそのままある見出し(長い題名など)は、規則どおり「元のまま」なので数えない
    src_heads = {re.sub(r"^#+\s*", "", ln).strip() for ln in src.read_text().splitlines() if ln.startswith("#")}
    for _, h in heads:
        if re.sub(r"^#+\s*", "", h).strip() in src_heads:
            continue
        t = re.sub(r"^#+\s*", "", h)
        t = re.sub(r"^[0-9０-９]+(?:[.．-][0-9０-９]+)*[.．]?\s*", "", t)
        t = re.sub(r"^(?:付録|別紙)\s*[A-ZＡ-Ｚ0-9０-９]*[.．:：]?\s*", "", t)
        if len(t) > 25 or "【" in t or "。" in t:
            bad_heads.append(t[:30])
    checks["headings_short"] = not bad_heads
    if bad_heads:
        checks["bad_headings"] = " / ".join(bad_heads)
    # 確認事項は文書の中に置かず、別ファイル(<元の文書>.確認事項.md)に書く
    checks["no_kakunin_in_doc"] = not kakunin
    kfile = src.with_name(src.stem + ".確認事項.md")
    checks["kakunin_file_exists"] = kfile.exists()
    if kfile.exists():
        checks["kakunin_items"] = len(re.findall(r"^\s*(?:[-*]|\d+[.．])\s+", kfile.read_text(), re.M))
    # 元にない固有名詞・英字の語(数値は計算で出るので判定に回す)
    try:
        r = subprocess.run(["uv", "run", str(NEWFACTS), "--json", str(src), str(after)], capture_output=True, text=True,
                           timeout=300)
        items = json.loads(r.stdout).get("new_items", [])
        numeric = re.compile(r"^[0-9０-９][0-9０-９,.,.〜~%％]*[^0-9０-９]{0,3}$")
        nums = [i["word"] for i in items if numeric.match(i["word"])]
        words = [i["word"] for i in items if not numeric.match(i["word"])]
        checks["new_numbers"] = len(nums)
        checks["new_words"] = len(words)
        checks["no_new_words"] = not words
        if words:
            checks["new_words_list"] = ",".join(words[:10])
    except Exception as e:  # noqa: BLE001
        checks["newfacts_error"] = str(e)[:200]
    # スキルを読んだか、natural-japanese の lint を回したか(log から見る)
    logtext = log.read_text() if log.exists() else ""
    checks["skill_loaded"] = bool(re.search(r'"skill":\s*"[^"]*critical-thinking"|critical-thinking/SKILL\.md', logtext))
    checks["lint_ran"] = "lint.py" in logtext
    gate_keys = [k for k, v in checks.items() if isinstance(v, bool)]
    checks["PASS"] = all(checks[k] for k in gate_keys)
    return checks


def _body_headings(t: str) -> list[str]:
    """本編(付録を除く)の見出しを、番号を除いて返す。"""
    out, keep = [], True
    for line in t.splitlines():
        if re.match(r"^##\s", line):
            keep = not re.match(r"^##\s*(\d+[.．]?\s*)?(確認事項|付録|別紙)", line)
        if keep and re.match(r"^#{2,3}\s", line):
            h = re.sub(r"^#+\s*", "", line)
            h = re.sub(r"^[0-9０-９]+(?:[.．-][0-9０-９]+)*[.．]?\s*", "", h).strip()
            out.append(h)
    return out


def mechanical_redesign(src: Path, src_sha: str, after: Path, plans: Path, log: Path) -> dict:
    """組み直しは「直す」の検査に、構成案の有無と見出しの入れ替わりを足す。"""
    checks = mechanical_rewrite(src, src_sha, after, log)
    checks["plans_exist"] = plans.exists()
    if plans.exists():
        # 「## 案A:…」「## 構成案1」の見出しだけ数える(「選んだ案」「保つもの」は数えない)
        n = len(re.findall(r"^#{1,4}\s*(?:構成案|案)\s*[0-9０-９A-Za-zＡ-Ｚ一二三]", plans.read_text(), re.M))
        checks["plans_count"] = n
        checks["plans_two_or_more"] = n >= 2
    if after.exists():
        hb, ha = _body_headings(src.read_text()), _body_headings(after.read_text())
        new = [h for h in ha if h not in hb]
        checks["headings_before"] = len(hb)
        checks["headings_after"] = len(ha)
        checks["headings_new"] = len(new)
        # 本編の見出しの並びが同じなら、組み直したとは言えない。並べ替え・付録への移動・新しい見出しのどれかで変わる(判定は judge の restructured で見る)
        checks["headings_changed"] = hb != ha
    gate_keys = [k for k, v in checks.items() if isinstance(v, bool) and k != "PASS"]
    checks["PASS"] = all(checks[k] for k in gate_keys)
    return checks


def one_rewrite(fixture: str, i: int, w: Path, src: Path, run_dir: Path, plugin: Path, model: str, effort: str,
                judge_model: str, dry: bool, reports_from: Path | None, mode: str = "rewrite") -> dict:
    """「指摘を反映して直す」工程と「構成から組み直す」工程。logic と somosomo の 1 回目の報告を足場にする。"""
    name = f"{fixture}-{mode}-{i}"
    base = reports_from or run_dir
    for m in ("logic", "somosomo"):
        rep = base / f"{fixture}-{m}-1" / "report.md"
        if not rep.exists():
            return {"name": name, "fixture": fixture, "mode": mode, "i": i, "error": f"missing {rep}"}
        shutil.copy(rep, w / f"report-{m}.md")
    src_sha = sha(src)
    if dry:
        return {"name": name, "dry": True}
    t = time.time()
    claude(PROMPTS[mode].format(file=str(src)), w, REWRITE_TOOLS, model, effort, plugin, w / "log-run.txt")
    elapsed = time.time() - t
    if mode == "redesign":
        checks = mechanical_redesign(src, src_sha, w / "source-after.md", w / "plans.md", w / "log-run.txt")
    else:
        checks = mechanical_rewrite(src, src_sha, w / "source-after.md", w / "log-run.txt")
    result = {"name": name, "fixture": fixture, "mode": mode, "i": i, "seconds": round(elapsed), "mechanical": checks}
    exp_path = expected_path(fixture)
    shutil.copy(exp_path, w / "expected.json") if exp_path else (w / "expected.json").write_text('{"defects": []}')
    if (w / "source-after.md").exists():
        jprompt = JUDGE_REDESIGN_PROMPT if mode == "redesign" else JUDGE_REWRITE_PROMPT
        claude(jprompt.replace("{DIR}", str(w)), w, JUDGE_TOOLS, judge_model, "medium", None,
               w / "log-judge.txt", timeout=900)
        jp = w / "judge.json"
        if jp.exists():
            try:
                result["judge"] = json.loads(jp.read_text())
            except json.JSONDecodeError:
                result["judge_error"] = "parse"
    (w / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def one_length(fixture: str, i: int, w: Path, src: Path, run_dir: Path, plugin: Path, model: str, effort: str,
               judge_model: str, dry: bool, reports_from: Path | None, mode: str) -> dict:
    """「もっと端的に」(concise)と「もっと丁寧に」(detailed)。logic の 1 回目の YAML を足場にする。"""
    name = f"{fixture}-{mode}-{i}"
    base = reports_from or run_dir
    y = base / f"{fixture}-logic-1" / "source.md.logic.yaml"
    if not y.exists():
        return {"name": name, "fixture": fixture, "mode": mode, "i": i, "error": f"missing {y}"}
    shutil.copy(y, w / "source.md.logic.yaml")
    (w / "mode.txt").write_text(mode)
    src_sha = sha(src)
    if dry:
        return {"name": name, "dry": True}
    t = time.time()
    claude(PROMPTS[mode].format(file=str(src)), w, REWRITE_TOOLS, model, effort, plugin, w / "log-run.txt")
    elapsed = time.time() - t
    checks = mechanical_rewrite(src, src_sha, w / "source-after.md", w / "log-run.txt")
    # 長さの基準は向きで違う。端的は本編 70% 以下(r30 で 60% は届かず、読めることを確かめて 70% にした)、丁寧は 110% 以下
    cb, ca = checks.get("chars_before", 0), checks.get("chars_after_body", 0)
    checks["ratio"] = round(ca / cb, 3) if cb else None
    checks["not_longer"] = ca <= cb * (0.7 if mode == "concise" else 1.1)
    # 確認事項のファイルは、端的・丁寧では要らないことがある
    checks["kakunin_file_exists"] = True
    gate_keys = [k for k, v in checks.items() if isinstance(v, bool) and k != "PASS"]
    checks["PASS"] = all(checks[k] for k in gate_keys)
    result = {"name": name, "fixture": fixture, "mode": mode, "i": i, "seconds": round(elapsed), "mechanical": checks}
    if (w / "source-after.md").exists():
        claude(JUDGE_LENGTH_PROMPT.replace("{DIR}", str(w)), w, JUDGE_TOOLS, judge_model, "medium", None, w / "log-judge.txt", timeout=900)
        jp = w / "judge.json"
        if jp.exists():
            try:
                result["judge"] = json.loads(jp.read_text())
            except json.JSONDecodeError:
                result["judge_error"] = "parse"
    (w / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return result


# ---------------------------------------------------------------------------
# 1 回分
# ---------------------------------------------------------------------------

def writer_path(fixture: str) -> Path | None:
    p = FIXTURES / f"{fixture}.writer.json"
    return p if p.exists() else None


def one_review(fixture: str, i: int, w: Path, src: Path, run_dir: Path, plugin: Path, model: str, effort: str,
               judge_model: str, dry: bool, reports_from: Path | None, writer_model: str = "claude-opus-5-5") -> dict:
    """「決裁者の目で見て直す」の一括経路。1回目で問いを書かせ、模擬書き手が答え、2回目で直す。"""
    name = f"{fixture}-review-{i}"
    wj = writer_path(fixture)
    if not wj:
        return {"name": name, "fixture": fixture, "mode": "review", "i": i, "error": "missing writer.json"}
    shutil.copy(wj, w / "writer.json")
    base = reports_from or run_dir
    for m in ("logic", "somosomo"):
        rep = base / f"{fixture}-{m}-1" / "report.md"
        if rep.exists():
            shutil.copy(rep, w / f"report-{m}.md")
    src_sha = sha(src)
    if dry:
        return {"name": name, "dry": True}
    t = time.time()
    claude(PROMPTS["review"].format(file=str(src)), w, REWRITE_TOOLS, model, effort, plugin, w / "log-run1.txt")
    q = w / "questions.md"
    n_q = len(re.findall(r"^\s*(?:\d+[.．]|[-*])\s+", q.read_text(), re.M)) if q.exists() else 0
    if q.exists() and not (w / "answers.md").exists():
        claude(WRITER_PROMPT.format(file=str(src)), w, WRITER_TOOLS, writer_model, "medium", None, w / "log-writer.txt")
    if (w / "answers.md").exists():
        claude(PROMPTS["review"].format(file=str(src)), w, REWRITE_TOOLS, model, effort, plugin, w / "log-run2.txt")
    elapsed = time.time() - t
    # 機械検査は rewrite と同じ。元にない語の検査は、元の文書と書き手の答えを合わせたものと比べる
    log_all = w / "log-run.txt"
    log_all.write_text((w / "log-run1.txt").read_text() + ((w / "log-run2.txt").read_text() if (w / "log-run2.txt").exists() else ""))
    src_plus = w / "source-plus-answers.md"
    src_plus.write_text(src.read_text() + "\n\n" + ((w / "answers.md").read_text() if (w / "answers.md").exists() else ""))
    checks = mechanical_rewrite(src, src_sha, w / "source-after.md", log_all)
    # 一括経路は答えを本文に入れるので、長さの上限は「元の本編 + 答えの字数」。答え以外を足していないかは判定の持ち込みで見る
    ans_text = (w / "answers.md").read_text() if (w / "answers.md").exists() else ""
    ans_chars = sum(_nonspace(m) for m in re.findall(r"答え[:：]\s*(.+)", ans_text))
    checks["answer_chars"] = ans_chars
    checks["not_longer"] = checks.get("chars_after_body", 0) <= checks.get("chars_before", 0) * 1.01 + ans_chars
    try:
        r = subprocess.run(["uv", "run", str(NEWFACTS), "--json", str(src_plus), str(w / "source-after.md")], capture_output=True, text=True, timeout=300)
        items = json.loads(r.stdout).get("new_items", [])
        numeric = re.compile(r"^[0-9０-９][0-9０-９,.,.〜~%％]*[^0-9０-９]{0,3}$")
        words = [x["word"] for x in items if not numeric.match(x["word"])]
        checks["new_words"] = len(words); checks["no_new_words"] = not words
        checks["new_words_list"] = ",".join(words[:10]) if words else ""
    except Exception as e:  # noqa: BLE001
        checks["newfacts_error"] = str(e)[:200]
    checks["questions_exist"] = q.exists()
    checks["questions_count"] = n_q
    checks["questions_le_3"] = 1 <= n_q <= 3
    checks["answers_exist"] = (w / "answers.md").exists()
    gate_keys = [k for k, v in checks.items() if isinstance(v, bool) and k != "PASS"]
    checks["PASS"] = all(checks[k] for k in gate_keys)
    result = {"name": name, "fixture": fixture, "mode": "review", "i": i, "seconds": round(elapsed), "mechanical": checks}
    exp_path = expected_path(fixture)
    shutil.copy(exp_path, w / "expected.json") if exp_path else (w / "expected.json").write_text('{"defects": []}')
    if (w / "source-after.md").exists():
        claude(JUDGE_REVIEW_PROMPT.replace("{DIR}", str(w)), w, JUDGE_TOOLS, judge_model, "medium", None, w / "log-judge.txt", timeout=900)
        jp = w / "judge.json"
        if jp.exists():
            try:
                result["judge"] = json.loads(jp.read_text())
            except json.JSONDecodeError:
                result["judge_error"] = "parse"
    (w / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def judge_prompt_for(mode: str, w: Path) -> str:
    if mode in ("logic", "somosomo"):
        return JUDGE_PROMPT.replace("{DIR}", str(w)).replace("{MODE}", mode)
    return {"rewrite": JUDGE_REWRITE_PROMPT, "redesign": JUDGE_REDESIGN_PROMPT, "review": JUDGE_REVIEW_PROMPT,
            "concise": JUDGE_LENGTH_PROMPT, "detailed": JUDGE_LENGTH_PROMPT}[mode].replace("{DIR}", str(w))


def rejudge_one(w: Path, judge_model: str) -> dict:
    """保存した出力に判定だけをかけ直す(生成と機械検査は result.json のものを使う)。計器を替えたときの基準の置き直しに使う。"""
    result = json.loads((w / "result.json").read_text())
    if "error" in result or result.get("dry"):
        return result
    mode = result["mode"]
    out = w / ("report.md" if mode in ("logic", "somosomo") else "source-after.md")
    result.pop("judge", None); result.pop("judge_error", None)
    # 長さの基準は途中で変えた(端的 60% → 70%)ので、保存した合否ではなく今の基準で引き直す
    m = result.get("mechanical", {})
    if mode in ("concise", "detailed") and m.get("chars_before"):
        m["not_longer"] = m["chars_after_body"] <= m["chars_before"] * (0.7 if mode == "concise" else 1.1)
        m["PASS"] = all(v for k, v in m.items() if isinstance(v, bool) and k != "PASS")
    if out.exists():
        (w / "judge.json").unlink(missing_ok=True)
        claude(judge_prompt_for(mode, w), w, JUDGE_TOOLS, judge_model, "medium", None, w / "log-judge.txt", timeout=900)
        jp = w / "judge.json"
        if jp.exists():
            try:
                result["judge"] = json.loads(jp.read_text())
            except json.JSONDecodeError:
                result["judge_error"] = "parse"
    (w / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def expected_path(fixture: str) -> Path | None:
    p = FIXTURES / f"{fixture}.expected.json"
    return p if p.exists() else None


def one_run(fixture: str, mode: str, i: int, run_dir: Path, plugin: Path, model: str, effort: str, judge_model: str,
            dry: bool, reports_from: Path | None = None, writer_model: str = "claude-opus-5-5") -> dict:
    name = f"{fixture}-{mode}-{i}"
    w = run_dir / name
    w.mkdir(parents=True, exist_ok=True)
    src = w / "source.md"
    shutil.copy(FIXTURES / f"{fixture}.md", src)
    if mode == "review":
        return one_review(fixture, i, w, src, run_dir, plugin, model, effort, judge_model, dry, reports_from, writer_model)
    if mode in ("rewrite", "redesign"):
        return one_rewrite(fixture, i, w, src, run_dir, plugin, model, effort, judge_model, dry, reports_from, mode)
    if mode in ("concise", "detailed"):
        return one_length(fixture, i, w, src, run_dir, plugin, model, effort, judge_model, dry, reports_from, mode)
    yaml_path = w / "source.md.logic.yaml"
    yaml_sha_before = None
    if mode == "somosomo":
        # 足場の YAML は、同じ run の logic 1回目を使う。なければ somosomo が自分で作る
        cand = run_dir / f"{fixture}-logic-1" / "source.md.logic.yaml"
        if cand.exists():
            shutil.copy(cand, yaml_path)
            yaml_sha_before = sha(yaml_path)
    src_sha = sha(src)
    if dry:
        return {"name": name, "dry": True}
    t = time.time()
    claude(PROMPTS[mode].format(file=str(src)), w, RUN_TOOLS, model, effort, plugin, w / "log-run.txt")
    elapsed = time.time() - t
    checks = mechanical(mode, src, src_sha, yaml_path, yaml_sha_before, w / "report.md")
    result = {"name": name, "fixture": fixture, "mode": mode, "i": i, "seconds": round(elapsed), "mechanical": checks}
    # 判定。expected.json のない素材は欠陥なしとして、空の一覧を渡す
    exp_path = expected_path(fixture)
    if exp_path:
        shutil.copy(exp_path, w / "expected.json")
    else:
        (w / "expected.json").write_text(json.dumps({"defects": []}, ensure_ascii=False))
    if (w / "report.md").exists():
        claude(JUDGE_PROMPT.replace("{DIR}", str(w)).replace("{MODE}", mode), w, JUDGE_TOOLS, judge_model, "medium",
               None, w / "log-judge.txt", timeout=900)
        jp = w / "judge.json"
        if jp.exists():
            try:
                result["judge"] = json.loads(jp.read_text())
            except json.JSONDecodeError:
                result["judge_error"] = "parse"
    (w / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return result


# ---------------------------------------------------------------------------
# 集計
# ---------------------------------------------------------------------------

def summarize(results: list[dict], repeat: int, run_dir: Path) -> tuple[str, bool]:
    lines = [f"# critical-thinking eval: {run_dir.name}", ""]
    ok = True
    # concise / detailed は素材ごとに 2/3 で見るので、全体の機械検査の合否からは外す
    # concise / detailed は素材ごとに 2/3 で見る。rewrite の本編の長さも同じ(短い素材では「確認中」1か所で 1% を超える。CT6)
    def _only_length(r: dict) -> bool:
        m = r.get("mechanical", {})
        return r.get("mode") == "rewrite" and [k for k, v in m.items() if v is False and k != "PASS"] == ["not_longer"]
    mech_fail = [r["name"] for r in results if r.get("mode") not in ("concise", "detailed")
                 and not r.get("mechanical", {}).get("PASS") and not _only_length(r)]
    lines.append(f"## 機械的な検査: {len(results) - len(mech_fail)}/{len(results)} 通過")
    for r in results:
        m = r.get("mechanical", {})
        bad = [k for k, v in m.items() if v is False]
        lines.append(f"- {r['name']}: {'PASS' if m.get('PASS') else 'FAIL ' + ','.join(bad)} ({r.get('seconds')}s)")
    if mech_fail:
        ok = False
    lines.append("")
    fixtures = list(dict.fromkeys(r["fixture"] for r in results))
    for fixture in fixtures:
        exp_path = expected_path(fixture)
        expected = json.loads(exp_path.read_text())["defects"] if exp_path else []
        for mode in ("logic", "somosomo"):
            rs = [r for r in results if r["fixture"] == fixture and r["mode"] == mode and "judge" in r]
            if not rs:
                continue
            extra = defaultdict(int)
            for r in rs:
                for e in r["judge"].get("extra", []):
                    extra[e.get("status", "?")] += 1
            if exp_path:
                exp = [d for d in expected if d["mode"] == mode]
                lines.append(f"## {fixture} / {mode}: 仕込んだ欠陥の検出({len(rs)} 回)")
                lines.append("| id | 分類 | found | partial | missed | 安定 |")
                lines.append("|---|---|---|---|---|---|")
                stable = 0
                required = 0
                for d in exp:
                    c = defaultdict(int)
                    for r in rs:
                        st = next((e["status"] for e in r["judge"].get("expected", []) if e.get("id") == d["id"]), "missed")
                        c[st] += 1
                    is_stable = c["found"] * 3 >= len(rs) * 2
                    if not d.get("optional"):
                        required += 1
                        stable += is_stable
                    lines.append(f"| {d['id']} | {d['category']} | {c['found']} | {c['partial']} | {c['missed']} | {'o' if is_stable else '-'}{' (任意)' if d.get('optional') else ''} |")
                rate = stable / required if required else 0
                lines.append("")
                lines.append(f"安定検出率(任意を除く): {stable}/{required} = {rate:.0%}  (条件 80% 以上)")
                if mode == "logic":
                    ws = [(r["i"], r.get("mechanical", {})) for r in rs]
                    lines.append("重み: " + ", ".join(f"run{i}: 決裁に要る {m.get('n_kessai')} / 論点 {m.get('n_ronten')} / 記述で数値なし {m.get('n_desc_kessai_nonum')}" + (f" / 依存で0本 {m.get('dep_ronten_without_kessai')}" if m.get('dep_ronten_without_kessai') else "") for i, m in ws))
                if rate < 0.8:
                    ok = False
                lines.append(f"仕込んでいない指摘: 妥当 {extra['plausible']}, 読み違い {extra['false']}, 持ち込み {extra['crossing']}  (条件 持ち込み = 0)")
                if extra["crossing"]:
                    ok = False
            else:
                per_run_false = extra["false"] / len(rs)
                lines.append(f"## {fixture} / {mode}: 欠陥なしの文書({len(rs)} 回): 妥当 {extra['plausible']}, 読み違い {extra['false']}, 持ち込み {extra['crossing']}  (条件 読み違い ≤ 1/回、持ち込み = 0)")
                if per_run_false > 1 or extra["crossing"]:
                    ok = False
            lines.append("")
    for fixture in fixtures:
        rs = [r for r in results if r.get("fixture") == fixture and r.get("mode") == "review" and "mechanical" in r]
        if not rs:
            continue
        lines.append(f"\n## {fixture} / review: 決裁者の目で見て直す({len(rs)} 回)")
        lines.append("| run | 文字数(前→後。後は本編/全体) | 問い | 文書内で答えが出る問い | 答え used/unchanged/deferred/dropped | 確認事項 先に答える/全体(消せたはず) | fixed | deferred | remains | 持ち込み |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|")
        bad = 0
        for r in rs:
            m = r["mechanical"]; j = r.get("judge", {})
            qs = j.get("questions", []); ans = j.get("answers", []); kk = j.get("kakunin", {})
            st = {"fixed": 0, "deferred": 0, "remains": 0}
            for e in j.get("expected", []):
                if e.get("status") in st: st[e["status"]] += 1
            crossing = sum(1 for x in j.get("added", []) if x.get("status") == "crossing")
            a_in_doc = sum(1 for x in qs if x.get("answerable_in_doc"))
            used = sum(1 for x in ans if x.get("used")); unch = sum(1 for x in ans if x.get("unchanged")); dfd = sum(1 for x in ans if x.get("deferred")); drp = sum(1 for x in ans if x.get("dropped"))
            first = kk.get("first_count", kk.get("count"))
            lines.append(f"| {r['i']} | {m.get('chars_before')}→{m.get('chars_after_body')}/{m.get('chars_after')} | {m.get('questions_count')} | {a_in_doc} | {used}/{unch}/{dfd}/{drp} | {first}/{kk.get('count')}({kk.get('removable')}) | {st['fixed']} | {st['deferred']} | {st['remains']} | {crossing} |")
            if not m.get("PASS") or a_in_doc or crossing or drp or (unch < used) or (kk.get("removable") or 0) > 0 or (first or 0) > 3 or st["remains"]:
                bad += 1
        lines.append(f"条件: 問いが1〜3、文書内で答えが出る問い 0、答えは使われ改変なし、先に答える問い ≤3 で消せたはずのもの 0、remains 0、持ち込み 0、機械検査が通過。満たした run: {len(rs) - bad}/{len(rs)}  (条件 3回中2回以上。判定の揺れを1回まで許す)")
        if (len(rs) - bad) * 3 < len(rs) * 2:
            ok = False
    for fixture, mode in [(f, m) for m in ("rewrite", "redesign") for f in fixtures]:
        rs = [r for r in results if r["fixture"] == fixture and r["mode"] == mode]
        if not rs:
            continue
        exp_path = expected_path(fixture)
        expected = json.loads(exp_path.read_text())["defects"] if exp_path else []
        title = "指摘を反映して直す" if mode == "rewrite" else "構成から組み直す"
        lines.append(f"## {fixture} / {mode}: {title}({len(rs)} 回)")
        extra_cols = " 主結論 | 決裁事項 | 背骨 | 案 | 縮小案 |" if mode == "redesign" else ""
        lines.append(f"| run | 文字数(前→後。後は本編/全体) | 本文の印 | 改訂の経緯 | 新しい語 | fixed | deferred | remains | 妥当 | 持ち込み |{extra_cols}")
        lines.append("|---|---|---|---|---|---|---|---|---|---|" + ("---|---|---|---|---|" if mode == "redesign" else ""))
        kept_fail = 0
        restructured_n = 0
        shrink_n = 0
        for r in rs:
            m = r.get("mechanical", {})
            j = r.get("judge", {})
            st = defaultdict(int)
            for e in j.get("expected", []):
                st[e.get("status", "?")] += 1
            ad = defaultdict(int)
            for e in j.get("added", []):
                ad[e.get("status", "?")] += 1
            row = (f"| {r['i']} | {m.get('chars_before')}→{m.get('chars_after_body')}/{m.get('chars_after')} | {m.get('markers_in_body')} | "
                   f"{m.get('revision_notes_added')} | {m.get('new_words')} | {st['fixed']} | {st['deferred']} | "
                   f"{st['remains']} | {ad['plausible']} | {ad['crossing']} |")
            if mode == "redesign":
                k = j.get("kept", {})
                rt = j.get("restructure", {})
                yn = lambda v: "○" if v is True else ("×" if v is False else "?")  # noqa: E731
                row += f" {yn(k.get('conclusion_kept'))} | {yn(k.get('request_kept'))} | {yn(rt.get('restructured'))} | {yn(rt.get('plans_distinct'))} | {yn(rt.get('plans_shrink'))}{'' if rt.get('shrink_clean', True) else '(持ち込み)'} |"
                if k.get("conclusion_kept") is False or k.get("request_kept") is False:
                    kept_fail += 1
                if rt.get("restructured") is True:
                    restructured_n += 1
                if rt.get("plans_shrink") is True and rt.get("shrink_clean", True):
                    shrink_n += 1
            lines.append(row)
            if ad["crossing"]:
                ok = False
        # 欠陥ごとに、直したか確認事項に回した回数。検出側と同じく 2/3 以上で安定とみなす
        unstable = []
        for d in expected:
            if d.get("optional"):
                continue
            n = sum(1 for r in rs for e in r.get("judge", {}).get("expected", [])
                    if e.get("id") == d["id"] and e.get("status") in ("fixed", "deferred"))
            if n * 3 < len(rs) * 2:
                unstable.append(f"{d['id']}({n}/{len(rs)})")
        lines.append("")
        lines.append(f"安定して直した欠陥(任意を除く): {'すべて' if not unstable else '残り ' + ', '.join(unstable)}  (条件 各欠陥 2/3 以上で fixed か deferred)")
        if mode == "rewrite":
            n_len = sum(1 for r in rs if r.get("mechanical", {}).get("not_longer"))
            lines.append(f"本編が元より長くない run: {n_len}/{len(rs)}  (条件 3回中2回以上)")
            if n_len * 3 < len(rs) * 2:
                ok = False
        if unstable:
            ok = False
        if mode == "redesign":
            lines.append(f"主結論と決裁事項を保てなかった run: {kept_fail}  (条件 0)。背骨が替わった run: {restructured_n}/{len(rs)}  (条件 2/3 以上)。頼む中身を小さくする案があった run: {shrink_n}/{len(rs)}  (条件 2/3 以上、持ち込みなし)")
            if kept_fail or restructured_n * 3 < len(rs) * 2 or shrink_n * 3 < len(rs) * 2:
                ok = False
            lines.append("条件: 持ち込み = 0、欠陥ごとに 2/3 以上で fixed か deferred、主結論と決裁事項が全 run で同じ、背骨が 2/3 以上で替わる、機械的な検査が通過")
        else:
            lines.append("条件: 持ち込み = 0、欠陥ごとに 2/3 以上で fixed か deferred、機械的な検査が通過")
        lines.append("")
    for fixture in fixtures:
        for mode in ("concise", "detailed"):
            rs = [r for r in results if r["fixture"] == fixture and r["mode"] == mode and "judge" in r]
            if not rs:
                continue
            lines.append(f"## {fixture} / {mode}: {'もっと端的に' if mode == 'concise' else 'もっと丁寧に'}({len(rs)} 回)")
            lines.append("| run | 本編(前→後、比) | 主結論 | 決裁事項 | 数値 | 持ち込み | 対応なしの文 | 見出しと先頭文で読める |")
            lines.append("|---|---|---|---|---|---|---|---|")
            good = 0
            for r in sorted(rs, key=lambda r: r["i"]):
                m, j = r["mechanical"], r["judge"]
                k = j.get("kept", {}); yn = lambda v: "○" if v is True else ("×" if v is False else "?")  # noqa: E731
                crossing = sum(1 for e in j.get("added", []) if e.get("status") == "crossing")
                uns = len(j.get("unsupported", []))
                lines.append(f"| {r['i']} | {m.get('chars_before')}→{m.get('chars_after_body')} ({m.get('ratio')}) | {yn(k.get('conclusion_kept'))} | {yn(k.get('request_kept'))} | {yn(k.get('numbers_kept'))} | {crossing} | {uns} | {yn(j.get('readable', {}).get('ok'))} |")
                if m.get("PASS") and all(k.get(x) is True for x in ("conclusion_kept", "request_kept", "numbers_kept")) and crossing == 0 and uns == 0:
                    good += 1
            lim = "70%" if mode == "concise" else "110%"
            lines.append(f"条件: 本編が元の {lim} 以内、主結論・決裁事項・数値が同じ、持ち込み 0、対応なしの文 0、機械検査が通過。満たした run: {good}/{len(rs)}  (条件 3回中2回以上)")
            if good * 3 < len(rs) * 2:
                ok = False
            lines.append("")
    lines.append(f"## 判定: {'PASS' if ok else 'FAIL'}")
    return "\n".join(lines), ok


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", default=None, help=f"既定 {DEFAULT_FIXTURES}(--rejudge では全部)")
    ap.add_argument("--modes", default=None, help="既定 logic,somosomo(--rejudge では全部)")
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--effort", default="high")
    ap.add_argument("--judge-model", default="claude-sonnet-5-5", help="判定者。生成(--model)とは別のモデルにする")
    ap.add_argument("--writer-model", default="claude-opus-5-5", help="review の模擬書き手")
    ap.add_argument("--rejudge", default=None, help="生成を回さず、この run の保存した出力に判定だけをかけ直す(run-label)。結果は --run-label に写す")
    ap.add_argument("--run-label", default=time.strftime("%Y-%m-%d-%H%M%S"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--reports-from", default=None, help="rewrite / redesign の足場にする報告を別の run から取る(run-label)")
    a = ap.parse_args()
    reports_from = RUNS / a.reports_from if a.reports_from else None
    run_dir = RUNS / a.run_label
    fixtures = a.fixtures.split(",") if a.fixtures else DEFAULT_FIXTURES.split(",")
    modes = a.modes.split(",") if a.modes else ["logic", "somosomo"]
    if a.rejudge:
        src_dir = RUNS / a.rejudge
        if run_dir.exists():
            sys.exit(f"{run_dir} already exists")
        shutil.copytree(src_dir, run_dir, ignore=shutil.ignore_patterns("summary.md", "results.json"))
        dirs = sorted(d for d in run_dir.iterdir() if d.is_dir() and (d / "result.json").exists())
        if a.fixtures or a.modes:
            dirs = [d for d in dirs if (a.fixtures is None or json.loads((d / "result.json").read_text()).get("fixture") in fixtures)
                    and (a.modes is None or json.loads((d / "result.json").read_text()).get("mode") in modes)]
        results = []
        with ThreadPoolExecutor(max_workers=a.jobs) as ex:
            for r in ex.map(lambda d: rejudge_one(d, a.judge_model), dirs):
                print(f"rejudged {r['name']}", file=sys.stderr)
                results.append(r)
        (run_dir / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
        summary, ok = summarize(results, a.repeat, run_dir)
        (run_dir / "summary.md").write_text(summary)
        print(summary)
        sys.exit(0 if ok else 1)
    run_dir.mkdir(parents=True, exist_ok=True)
    plugin = make_plugin_dir()
    print(f"plugin dir: {plugin}", file=sys.stderr)
    # logic を先に回し、somosomo はその YAML を足場にする。rewrite は両方の報告を足場にし、欠陥を仕込んだ文書だけ回す
    results: list[dict] = []
    for mode in ("logic", "somosomo", "rewrite", "redesign", "review", "concise", "detailed"):
        if mode not in modes:
            continue
        fs = [f for f in fixtures if expected_path(f)] if mode in ("rewrite", "redesign") else ([f for f in fixtures if writer_path(f)] if mode == "review" else fixtures)
        jobs = [(f, mode, i) for f in fs for i in range(1, a.repeat + 1)]
        if a.dry_run:
            for f, m, i in jobs:
                print(f"would run {f}-{m}-{i}")
            continue
        with ThreadPoolExecutor(max_workers=a.jobs) as ex:
            for r in ex.map(lambda j: one_run(*j, run_dir, plugin, a.model, a.effort, a.judge_model, False, reports_from, a.writer_model), jobs):
                print(f"done {r['name']} {r.get('seconds')}s mech={'PASS' if r.get('mechanical', {}).get('PASS') else 'FAIL'}", file=sys.stderr)
                results.append(r)
    if a.dry_run:
        return
    (run_dir / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
    summary, ok = summarize(results, a.repeat, run_dir)
    (run_dir / "summary.md").write_text(summary)
    print(summary)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
