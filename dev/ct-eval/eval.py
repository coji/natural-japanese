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

使い方:
    uv run dev/ct-eval/eval.py --dry-run
    uv run dev/ct-eval/eval.py --repeat 3 --jobs 6 --run-label 2026-10-31-r1
    uv run dev/ct-eval/eval.py --modes logic --fixtures ringi-planted --repeat 1
    uv run dev/ct-eval/eval.py --fixtures postmortem-planted,postmortem-clean

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

ALLOWED_KINDS = {"事実", "推論", "意見", "前提", "見積"}
FORBIDDEN = ["弱めるべき", "条件を足すべき", "べきだ", "べきです", "弱めた方が", "足した方が", "出し直して", "書き足す", "足すとよい", "書き直して"]
RUN_TOOLS = ["Skill", "Read", "Write", "Glob", "Grep", "Bash(uv run:*)", "Bash(uv:*)", "Bash(python3:*)",
             "Bash(cat:*)", "Bash(wc:*)", "Bash(ls:*)", "Bash(grep:*)", "Bash(sed:*)", "Bash(awk:*)"]
JUDGE_TOOLS = ["Read", "Write", "Glob"]

PROMPTS = {
    "logic": "critical-thinking スキルの logic モードで {file} を検査してください。結果の報告をそのまま report.md に書き出してください。確認の質問はせず、最後まで自分の判断で進めてください。",
    "somosomo": "critical-thinking スキルの somosomo モードで {file} を検査してください。結果の報告をそのまま report.md に書き出してください。確認の質問はせず、最後まで自分の判断で進めてください。",
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
        cmd += ["--plugin-dir", str(plugin)]
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
    bullets = [b for b in re.findall(r"^\s*(?:[-*]|\d+\.)\s+(.+)$", body, re.M) if len(b) > 20 and not skip.match(b)]
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


# ---------------------------------------------------------------------------
# 1 回分
# ---------------------------------------------------------------------------

def expected_path(fixture: str) -> Path | None:
    p = FIXTURES / f"{fixture}.expected.json"
    return p if p.exists() else None


def one_run(fixture: str, mode: str, i: int, run_dir: Path, plugin: Path, model: str, effort: str, judge_model: str,
            dry: bool) -> dict:
    name = f"{fixture}-{mode}-{i}"
    w = run_dir / name
    w.mkdir(parents=True, exist_ok=True)
    src = w / "source.md"
    shutil.copy(FIXTURES / f"{fixture}.md", src)
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
    a = ap.parse_args()
    run_dir = RUNS / a.run_label
    run_dir.mkdir(parents=True, exist_ok=True)
    fixtures = a.fixtures.split(",")
    modes = a.modes.split(",")
    plugin = make_plugin_dir()
    print(f"plugin dir: {plugin}", file=sys.stderr)
    # logic を先に回し、somosomo はその YAML を足場にする
    results: list[dict] = []
    for mode in ("logic", "somosomo"):
        if mode not in modes:
            continue
        jobs = [(f, mode, i) for f in fixtures for i in range(1, a.repeat + 1)]
        if a.dry_run:
            for f, m, i in jobs:
                print(f"would run {f}-{m}-{i}")
            continue
        with ThreadPoolExecutor(max_workers=a.jobs) as ex:
            for r in ex.map(lambda j: one_run(*j, run_dir, plugin, a.model, a.effort, a.judge_model, False), jobs):
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
