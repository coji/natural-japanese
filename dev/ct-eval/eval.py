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
     見出しが短い名詞句のまま、「確認事項」が最後の節、元にない固有名詞や英字の語がない
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
DEFAULT_FIXTURES = "ringi-planted,ringi-clean,postmortem-planted,postmortem-clean"
RUNS = HERE / "runs"
JUDGE_PROMPT = (HERE / "prompts" / "judge.txt").read_text()
JUDGE_REWRITE_PROMPT = (HERE / "prompts" / "judge-rewrite.txt").read_text()
NEWFACTS = REPO / "skills" / "natural-japanese" / "scripts" / "newfacts.py"

ALLOWED_KINDS = {"事実", "推論", "意見", "前提", "見積"}
FORBIDDEN = ["弱めるべき", "条件を足すべき", "べきだ", "べきです", "弱めた方が", "足した方が", "出し直して", "書き足す", "足すとよい", "書き直して"]
# cd を許さないと「cd X; cat Y」の複合コマンドが1回却下され、以後 Bash を使わなくなる(dontAsk の却下文が回避を禁じるため)
RUN_TOOLS = ["Skill", "Read", "Write", "Edit", "Glob", "Grep", "Bash(uv run:*)", "Bash(uv:*)", "Bash(python3:*)",
             "Bash(cd:*)", "Bash(cat:*)", "Bash(head:*)", "Bash(tail:*)", "Bash(echo:*)", "Bash(wc:*)", "Bash(ls:*)",
             "Bash(grep:*)", "Bash(sed:*)", "Bash(awk:*)"]
JUDGE_TOOLS = ["Read", "Write", "Glob"]
REWRITE_TOOLS = RUN_TOOLS + ["Bash(cp:*)", "Bash(diff:*)", "Bash(mkdir:*)"]
# 本文に埋めてはいけない印。確認事項の節より前にあれば落とす
MARKERS = re.compile(r"【要確認】|要確認|TODO")
# 改訂の経緯。元の文書にある分は引いて数える
REVISION_NOTES = re.compile(r"改訂|第\s*[0-9０-９一二三四五]\s*版|\bv[0-9]|指摘を反映|レビューを反映|初版|前版")

PROMPTS = {
    "logic": "critical-thinking スキルの logic モードで {file} を検査してください。結果の報告をそのまま report.md に書き出してください。確認の質問はせず、最後まで自分の判断で進めてください。",
    "somosomo": "critical-thinking スキルの somosomo モードで {file} を検査してください。結果の報告をそのまま report.md に書き出してください。確認の質問はせず、最後まで自分の判断で進めてください。",
    # 規則の中身は書かない(スキルがどう直すかを測るため)
    "rewrite": "{file} に対する critical-thinking の検査結果が report-logic.md と report-somosomo.md にあります。この指摘を反映して文書を直し、直した本文を source-after.md に保存してください。{file} そのものは書き換えないでください。確認の質問はせず、最後まで自分の判断で進めてください。",
}


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
    hits = [w for w in FORBIDDEN if w in text]
    checks["no_forbidden_phrases"] = not hits
    if hits:
        checks["forbidden_hits"] = ",".join(hits)
    # 指摘の各項目(箇条書き)に行番号があるか。「### 指摘」以降〜「YAML」より前の箇条書きだけを見る
    # 最初の「## 」見出しから「YAML の保存先」までを指摘の本体とみなす
    body = text
    m = re.search(r"^## ", text, re.M)
    if m:
        body = text[m.start():]
    m2 = re.search(r"YAML の保存先|## YAML|\*\*YAML|\.logic\.yaml", body)
    if m2:
        # 目印を含む行ごと落とす(行の途中で切ると、残った前半が箇条書きとして数えられる)
        body = body[: body.rfind("\n", 0, m2.start()) + 1]
    # 行番号を求めるのは指摘そのもの。3点セットの「問い」「要る材料」や件数の行は除き、「倒れる場所」は必ず行番号を求める
    skip = re.compile(r"^\**\s*(問い|要る材料|意図の分かるもの|分からないもの|些末|細かいもの|そのほか)")
    # 「1. **見出し**」のように全体が太字の見出しだけの項目は、行番号が下の「倒れる場所」に付くので数えない
    title_only = re.compile(r"^\*\*[^*]+\*\*\s*[::]?\s*$")
    bullets = [b for b in re.findall(r"^\s*(?:[-*]|\d+\.)\s+(.+)$", body, re.M)
               if len(b) > 20 and not skip.match(b) and not title_only.match(b.strip())]
    no_line = [b for b in bullets if not re.search(r"行\s*\d|\d+\s*行|\[\d", b)]
    checks["bullets_total"] = len(bullets)
    checks["bullets_without_line"] = len(no_line)
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
                nonempty = {i + 1 for i, l in enumerate(src.read_text().splitlines()) if l.strip()}
                missing = sorted(nonempty - lines)
                checks["all_lines_covered"] = not missing
                checks["missing_lines"] = ",".join(map(str, missing[:20]))
                checks["has_character_in_yaml"] = "文書の性格" in data
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
    # 確認事項の節より前に印がないか
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
    # 長さ。決める人が読む本編(確認事項と付録を除く)が元より長くないか
    def body_only(t: str) -> str:
        out, keep = [], True
        for line in t.splitlines():
            if re.match(r"^##\s", line):
                keep = not re.match(r"^##\s*(\d+[.．]?\s*)?(確認事項|付録|別紙)", line)
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
    for _, h in heads:
        t = re.sub(r"^#+\s*", "", h)
        t = re.sub(r"^[0-9０-９]+(?:[.．-][0-9０-９]+)*[.．]?\s*", "", t)
        t = re.sub(r"^(?:付録|別紙)\s*[A-ZＡ-Ｚ0-9０-９]*[.．:：]?\s*", "", t)
        if len(t) > 25 or "【" in t or "。" in t:
            bad_heads.append(t[:30])
    checks["headings_short"] = not bad_heads
    if bad_heads:
        checks["bad_headings"] = " / ".join(bad_heads)
    # 確認事項があるなら、付録・別紙・出典を除いて最後の節
    if kakunin:
        h2_after = [h for pos, h in heads if h.startswith("## ") and pos > kakunin[-1]]
        checks["kakunin_last"] = all(re.match(r"##\s*(付録|別紙|出典|参考)", h) for h in h2_after)
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


def one_rewrite(fixture: str, i: int, w: Path, src: Path, run_dir: Path, plugin: Path, model: str, effort: str,
                judge_model: str, dry: bool, reports_from: Path | None) -> dict:
    """「指摘を反映して直す」工程。logic と somosomo の 1 回目の報告を足場にする。"""
    name = f"{fixture}-rewrite-{i}"
    base = reports_from or run_dir
    for m in ("logic", "somosomo"):
        rep = base / f"{fixture}-{m}-1" / "report.md"
        if not rep.exists():
            return {"name": name, "fixture": fixture, "mode": "rewrite", "i": i, "error": f"missing {rep}"}
        shutil.copy(rep, w / f"report-{m}.md")
    src_sha = sha(src)
    if dry:
        return {"name": name, "dry": True}
    t = time.time()
    claude(PROMPTS["rewrite"].format(file=str(src)), w, REWRITE_TOOLS, model, effort, plugin, w / "log-run.txt")
    elapsed = time.time() - t
    checks = mechanical_rewrite(src, src_sha, w / "source-after.md", w / "log-run.txt")
    result = {"name": name, "fixture": fixture, "mode": "rewrite", "i": i, "seconds": round(elapsed), "mechanical": checks}
    exp_path = expected_path(fixture)
    shutil.copy(exp_path, w / "expected.json") if exp_path else (w / "expected.json").write_text('{"defects": []}')
    if (w / "source-after.md").exists():
        claude(JUDGE_REWRITE_PROMPT.replace("{DIR}", str(w)), w, JUDGE_TOOLS, judge_model, "medium", None,
               w / "log-judge.txt", timeout=900)
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

def expected_path(fixture: str) -> Path | None:
    p = FIXTURES / f"{fixture}.expected.json"
    return p if p.exists() else None


def one_run(fixture: str, mode: str, i: int, run_dir: Path, plugin: Path, model: str, effort: str, judge_model: str,
            dry: bool, reports_from: Path | None = None) -> dict:
    name = f"{fixture}-{mode}-{i}"
    w = run_dir / name
    w.mkdir(parents=True, exist_ok=True)
    src = w / "source.md"
    shutil.copy(FIXTURES / f"{fixture}.md", src)
    if mode == "rewrite":
        return one_rewrite(fixture, i, w, src, run_dir, plugin, model, effort, judge_model, dry, reports_from)
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
    mech_fail = [r["name"] for r in results if not r.get("mechanical", {}).get("PASS")]
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
        rs = [r for r in results if r["fixture"] == fixture and r["mode"] == "rewrite"]
        if not rs:
            continue
        exp_path = expected_path(fixture)
        expected = json.loads(exp_path.read_text())["defects"] if exp_path else []
        lines.append(f"## {fixture} / rewrite: 指摘を反映して直す({len(rs)} 回)")
        lines.append("| run | 文字数(前→後。後は本編/全体) | 本文の印 | 改訂の経緯 | 新しい語 | fixed | deferred | remains | 妥当 | 持ち込み |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|")
        for r in rs:
            m = r.get("mechanical", {})
            j = r.get("judge", {})
            st = defaultdict(int)
            for e in j.get("expected", []):
                st[e.get("status", "?")] += 1
            ad = defaultdict(int)
            for e in j.get("added", []):
                ad[e.get("status", "?")] += 1
            lines.append(f"| {r['i']} | {m.get('chars_before')}→{m.get('chars_after_body')}/{m.get('chars_after')} | {m.get('markers_in_body')} | "
                         f"{m.get('revision_notes_added')} | {m.get('new_words')} | {st['fixed']} | {st['deferred']} | "
                         f"{st['remains']} | {ad['plausible']} | {ad['crossing']} |")
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
        if unstable:
            ok = False
        lines.append("条件: 持ち込み = 0、欠陥ごとに 2/3 以上で fixed か deferred、機械的な検査が通過")
        lines.append("")
    lines.append(f"## 判定: {'PASS' if ok else 'FAIL'}")
    return "\n".join(lines), ok


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", default=DEFAULT_FIXTURES)
    ap.add_argument("--modes", default="logic,somosomo")
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--effort", default="high")
    ap.add_argument("--judge-model", default="claude-opus-5-5")
    ap.add_argument("--run-label", default=time.strftime("%Y-%m-%d-%H%M%S"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--reports-from", default=None, help="rewrite の足場にする報告を別の run から取る(run-label)")
    a = ap.parse_args()
    reports_from = RUNS / a.reports_from if a.reports_from else None
    run_dir = RUNS / a.run_label
    run_dir.mkdir(parents=True, exist_ok=True)
    fixtures = a.fixtures.split(",")
    modes = a.modes.split(",")
    plugin = make_plugin_dir()
    print(f"plugin dir: {plugin}", file=sys.stderr)
    # logic を先に回し、somosomo はその YAML を足場にする。rewrite は両方の報告を足場にし、欠陥を仕込んだ文書だけ回す
    results: list[dict] = []
    for mode in ("logic", "somosomo", "rewrite"):
        if mode not in modes:
            continue
        fs = [f for f in fixtures if expected_path(f)] if mode == "rewrite" else fixtures
        jobs = [(f, mode, i) for f in fs for i in range(1, a.repeat + 1)]
        if a.dry_run:
            for f, m, i in jobs:
                print(f"would run {f}-{m}-{i}")
            continue
        with ThreadPoolExecutor(max_workers=a.jobs) as ex:
            for r in ex.map(lambda j: one_run(*j, run_dir, plugin, a.model, a.effort, a.judge_model, False, reports_from), jobs):
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
