# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""corpus/experiments/skill-eval/eval.py — natural-japanese スキル評価ハーネス。

目的: natural-japanese スキルを実文書に適用し、lint では取れない構造・修辞・
趣旨レベルの欠陥を多数の文書で炙り出し、原因となったスキル指示（file/section）
ごとにクラスタして返す。人手の目に頼らず、原因箇所つきで所見を集める。

パイプライン（1 item あたり。詳細は corpus/experiments/skill-eval/README.md）:
    1. baseline 用意    — generate: 素の生成（スキルなし）。rewrite: source をコピー。
    2. thesis 抽出      — rewrite は source から、generate は topic+baseline から、
                          文書の中心主張を1〜2文で抽出（JSON）。
    3. skill-apply      — natural-japanese スキルを実際に適用し、最終文書を書かせる。
    4. lint 記録        — scripts/lint.py --json の結果を参考記録として保存。
    5. 批評3種          — human_ness（ブラインドA/B）/ thesis_preservation /
                          structural_smell を、いずれも JSON で取得。
    6. 全 item 完了後、skill_cause（file/section）でクラスタして集約し、
       corpus/reports/skill-eval-findings.md を書き出す。

claude CLI 呼び出しの流儀は corpus/generate.py の run_claude() に合わせる
（cwd の使い分け、NONINTERACTIVE_SYSTEM_PROMPT、--disallowed-tools "*" で
「素の生成」を作る手法）。ツールを許可する段（skill-apply / 批評）は
--allowedTools と --permission-mode dontAsk を組み合わせる。dontAsk は
「許可された tool の範囲内では確認プロンプトを出さずに実行する」モードで、
bypassPermissions のように allowedTools/disallowedTools の制限そのものを
無効化しないため、批評段（Read のみ許可）の安全性を保ったまま非対話実行できる
（このリポジトリで実際に動作確認済み）。

NDA注意: manifest.local.json（実素材を指す）と runs/（生成物・批評JSON）は
.gitignore で非コミット。コミットするのは本ファイル・manifest.example.json・
README.md・corpus/reports/skill-eval-findings.md（抽象化した所見のみ）だけ。

使い方:
    uv run corpus/experiments/skill-eval/eval.py --dry-run \
        --manifest corpus/experiments/skill-eval/manifest.example.json
    uv run corpus/experiments/skill-eval/eval.py \
        --manifest corpus/experiments/skill-eval/manifest.local.json \
        --run-label 2026-07-13-round1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# パス・定数
# ---------------------------------------------------------------------------
SKILL_EVAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = SKILL_EVAL_DIR.parents[2]  # skill-eval/ -> experiments/ -> corpus/ -> repo root
RUNS_ROOT = SKILL_EVAL_DIR / "runs"
REPORTS_DIR = REPO_ROOT / "corpus" / "reports"
FINDINGS_REPORT_PATH = REPORTS_DIR / "skill-eval-findings.md"

# corpus/generate.py と同じ「素の状態」用 cwd。リポジトリ内の CLAUDE.md や
# スキルのメモリを自動読み込みさせず、素の生成を作るため（run_claude_naive 用）。
NEUTRAL_CWD = "/tmp"

# corpus/generate.py からそのまま流用: 1往復のみの非対話バッチ呼び出しである旨を
# 伝えるシステムプロンプト。これがないと素っ気ないプロンプトに対して確認質問を
# 返すだけで本文が得られないことがある。
NONINTERACTIVE_SYSTEM_PROMPT = (
    "これは1往復のみの非対話バッチ呼び出しです。フォローアップの質問はできません。"
    "確認や許可を求めず、指示に対して適切と思う内容を自分で判断し、"
    "記事本文だけをそのまま出力してください。"
)

DEFAULT_MODEL_APPLY = "claude-sonnet-5"
DEFAULT_MODEL_CRITIC = "claude-fable-5"

DOCTYPES = {"minutes", "report", "guide", "memo", "slide"}

DOCTYPE_LABELS: dict[str, str] = {
    "minutes": "議事録",
    "report": "調査レポート・分析レポート",
    "guide": "社内ガイド・マニュアル",
    "memo": "リサーチメモ・企画書",
    "slide": "プレゼン資料のスライド構成",
}

# generate モードの baseline（素の生成）用プロンプト。corpus/generate.py の
# BUSINESS_PROMPT_TEMPLATES / SLIDE_PROMPT_TEMPLATE と同じ思想: 文体・自然さの
# 指示を一切入れず、素っ気なく「〜を書いて」とだけ頼む。
NAIVE_PROMPT_TEMPLATES: dict[str, str] = {
    "minutes": "{topic}についての議事録を書いて。",
    "report": "{topic}についてのレポートを書いて。",
    "guide": "{topic}についてのガイドを書いて。",
    "memo": "{topic}についてのメモを書いて。",
    "slide": (
        "{topic}についてのプレゼン資料のスライド構成と各スライドの内容"
        "（タイトル、メッセージライン、本文の箇条書き）をテキストで書いて。"
    ),
}

# --dry-run で表示する実行順。spec の記述（1 thesis抽出 → 2 skill-apply →
# 3 baseline用意 → ...）は主題別の説明順であり、実装上は baseline 用意が
# thesis 抽出より先でなければならない（generate モードの thesis 抽出が
# baseline ファイルを読む前提のため）。この並び替えは意図的な判断で、
# README.md にも明記する。
STAGE_ORDER = [
    "baseline_prepare",
    "thesis_extract",
    "skill_apply",
    "lint_record",
    "critic_human_ness",
    "critic_thesis_preservation",
    "critic_structural_smell",
]

RETRY_JSON_SUFFIX = (
    "\n\n[再試行の注意] 前回の出力はJSONとして正しくパースできませんでした。"
    "マークダウンのコードフェンス（```）を使わず、説明や前置きも書かず、"
    "指定されたJSONスキーマに合致する生のJSONオブジェクトだけを出力してください。"
)

# 批評結果のうち evidence/what/how のような自由記述フィールドは、critic に
# 「NDA配慮の抽象記述にせよ」と指示してあるが、LLM がその指示に従わない
# 可能性は残る。runs/ は gitignore されるので実害はないが、集約レポート
# （コミット対象）に転記する際の追加の安全弁として長さを切り詰める。
REPORT_EVIDENCE_MAX_CHARS = 120


# ---------------------------------------------------------------------------
# manifest 読み込み・検証
# ---------------------------------------------------------------------------
def load_manifest(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"manifest が見つかりません: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError(f"manifest の 'items' が空か配列ではありません: {path}")

    seen_ids: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"manifest item が dict ではありません: {item!r}")
        item_id = item.get("id")
        doctype = item.get("doctype")
        mode = item.get("mode")
        if not item_id or not isinstance(item_id, str):
            raise ValueError(f"item に 'id' がありません: {item!r}")
        if not re.fullmatch(r"[A-Za-z0-9._-]+", item_id) or item_id in (".", ".."):
            raise ValueError(f"item id に使える文字は英数字と ._- のみ（'.', '..', パス区切りは不可）: {item_id!r}")
        if item_id in seen_ids:
            raise ValueError(f"item id が重複しています: {item_id}")
        seen_ids.add(item_id)
        if doctype not in DOCTYPES:
            raise ValueError(f"item '{item_id}' の doctype が不正です: {doctype!r}（{sorted(DOCTYPES)} のいずれか）")
        if mode not in ("generate", "rewrite"):
            raise ValueError(f"item '{item_id}' の mode が不正です: {mode!r}（'generate' か 'rewrite'）")
        if mode == "generate":
            if not item.get("topic"):
                raise ValueError(f"item '{item_id}'（mode=generate）に 'topic' がありません")
        else:  # rewrite
            if not item.get("source"):
                raise ValueError(f"item '{item_id}'（mode=rewrite）に 'source' がありません")
    return items


# ---------------------------------------------------------------------------
# claude CLI 呼び出し（corpus/generate.py の流儀に合わせる）
# ---------------------------------------------------------------------------
def run_claude_naive(prompt: str, model: str, timeout: int = 300) -> str:
    """スキル・CLAUDE.md 等を一切介さない「素の生成」。generate.py の run_claude() と同一。"""
    result = subprocess.run(
        [
            "claude",
            "-p",
            prompt,
            "--model",
            model,
            "--disallowed-tools",
            "*",
            "--append-system-prompt",
            NONINTERACTIVE_SYSTEM_PROMPT,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=True,
        cwd=NEUTRAL_CWD,
    )
    return result.stdout.strip()


# main() が CLI 引数から設定する effort（None なら claude のデフォルト）。
EFFORT_APPLY: str | None = None
EFFORT_CRITIC: str | None = None


def run_claude_tooled(
    prompt: str,
    *,
    model: str,
    cwd: Path,
    allowed_tools: str,
    disallowed_tools: str | None = None,
    timeout: int = 600,
    effort: str | None = None,
) -> str:
    """リポジトリルートを cwd にして、指定した tool だけを許可して claude -p を呼ぶ。

    --permission-mode dontAsk は「許可された tool の範囲内では確認を求めず実行する」
    モードで、--allowedTools/--disallowedTools による制限自体は尊重される
    （bypassPermissions のように制限を無効化しない）ことを事前に動作確認済み。
    これにより、批評段（Read のみ許可）でも Write/Bash が実行されない安全性を
    保ったまま、非対話でハングせずに実行できる。
    """
    cmd = [
        "claude",
        "-p",
        prompt,
        "--model",
        model,
        "--permission-mode",
        "dontAsk",
        # --tools は「利用可能なツールの集合」自体を限定する(allow-list)。
        # --allowedTools(自動許可)だけでは未列挙ツールの利用を排除できない
        # ため、両方を同じリストで渡す。--strict-mcp-config は --mcp-config を
        # 渡していないので MCP ツールを完全に無効化する。
        "--tools",
        allowed_tools,
        "--allowedTools",
        allowed_tools,
        "--strict-mcp-config",
    ]
    if disallowed_tools:
        cmd += ["--disallowedTools", disallowed_tools]
    if effort:
        cmd += ["--effort", effort]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=True,
        cwd=str(cwd),
    )
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# JSON 抽出（コードフェンス混入・前置き文字列への耐性）
# ---------------------------------------------------------------------------
def extract_json(raw: str | None) -> dict | None:
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except json.JSONDecodeError:
            pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    return None


def call_critic_json(prompt: str, *, model: str, cwd: Path, timeout: int) -> tuple[dict | None, dict]:
    """Read のみ許可した claude -p を呼び、JSON をパースする。失敗時は1回だけ再試行し、
    それでも失敗すれば None を返す（呼び出し元はそれを「批評なし」として記録する）。
    生の応答は meta に残す（デバッグ・監査用。runs/ は gitignore なので NDA上の問題はない）。
    """
    meta: dict = {"attempts": 0}
    raw1: str | None = None
    try:
        raw1 = run_claude_tooled(
            prompt, model=model, cwd=cwd, allowed_tools="Read",
            disallowed_tools="Bash,Edit,Write,NotebookEdit,Task,WebFetch,WebSearch", timeout=timeout, effort=EFFORT_CRITIC,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        meta["error_attempt1"] = repr(e)
    meta["attempts"] = 1
    meta["raw_attempt1"] = raw1
    parsed = extract_json(raw1)
    if parsed is not None:
        meta["parse_ok"] = True
        return parsed, meta

    raw2: str | None = None
    try:
        raw2 = run_claude_tooled(
            prompt + RETRY_JSON_SUFFIX, model=model, cwd=cwd, allowed_tools="Read",
            disallowed_tools="Bash,Edit,Write,NotebookEdit,Task,WebFetch,WebSearch", timeout=timeout, effort=EFFORT_CRITIC,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        meta["error_attempt2"] = repr(e)
    meta["attempts"] = 2
    meta["raw_attempt2"] = raw2
    parsed2 = extract_json(raw2)
    meta["parse_ok"] = parsed2 is not None
    return parsed2, meta


# ---------------------------------------------------------------------------
# プロンプト構築
# ---------------------------------------------------------------------------
JSON_ONLY_INSTRUCTION = (
    "出力は次のJSONスキーマに厳密に従い、マークダウンのコードフェンス（```）を使わず、"
    "前置きや説明文を一切書かずに、素のJSONオブジェクトだけを出力してください。"
)


def build_thesis_prompt(item: dict, baseline_path: Path) -> str:
    if item["mode"] == "rewrite":
        source_path = Path(item["source"]).expanduser().resolve()
        return (
            f"次のファイルを読み、この文書が言おうとしている中心主張・趣旨を1〜2文で抽出してください。\n\n"
            f"対象ファイル: {source_path}\n\n"
            f"{JSON_ONLY_INSTRUCTION}\n"
            '{"thesis": "..."}'
        )
    topic = item["topic"]
    doctype = item["doctype"]
    return (
        f"次のファイルは、あるトピックについて書かれた素の生成結果です。これを読み、"
        f"この文書（あるいはこのトピックで書かれるべき文書）が言おうとしている中心主張・"
        f"趣旨を1〜2文で抽出してください。\n\n"
        f"トピック: {topic}\n"
        f"文書タイプ: {doctype}（{DOCTYPE_LABELS[doctype]}）\n"
        f"対象ファイル: {baseline_path}\n\n"
        f"{JSON_ONLY_INSTRUCTION}\n"
        '{"thesis": "..."}'
    )


def build_apply_prompt(item: dict, out_path: Path) -> str:
    doctype = item["doctype"]
    label = DOCTYPE_LABELS[doctype]
    common_tail = (
        f"設計 → 執筆 → 検査（scripts/lint.py・scripts/outline.py・scripts/terms.py を"
        f"実際に実行して使う） → 収束まで、スキルの工程を省略せず行ってください。\n\n"
        f"最終的に完成した文書だけを、次の絶対パスに Write してください: {out_path}\n"
        "途中経過・作業ログ・要約・判断台帳・言い訳などは一切そのファイルに書き込まないこと。"
        "out_path の中身は完成した文書の本文のみにしてください。\n"
        "作業が終わったら、作業中に作った中間ファイル（台帳・lintのJSON出力・下書きの"
        "バックアップ等）があれば削除してください。"
    )
    if item["mode"] == "rewrite":
        source_path = Path(item["source"]).expanduser().resolve()
        return (
            "このリポジトリの natural-japanese スキルを SKILL.md から始めて忠実に適用し、"
            f"次のソースファイルを読みやすくわかりやすい{label}に書き直してください。\n\n"
            f"ソースファイル: {source_path}\n"
            f"文書タイプ: {doctype}（references/doctypes/{doctype}.md を参照）\n\n"
            f"{common_tail}"
        )
    topic = item["topic"]
    return (
        "このリポジトリの natural-japanese スキルを SKILL.md から始めて忠実に適用し、"
        f"次のトピックについて読みやすくわかりやすい{label}を新規作成してください。\n\n"
        f"トピック: {topic}\n"
        f"文書タイプ: {doctype}（references/doctypes/{doctype}.md を参照）\n\n"
        f"{common_tail}"
    )


def build_human_ness_prompt(path_a: Path, path_b: Path) -> str:
    return (
        "次の二つの文書 A と B を読み、どちらがより人間が書いたように見えるかを"
        "判定してください。均質さ・整いすぎ・機械的なリズム・テンプレ感・"
        "不自然な網羅性など、AIらしさの手がかりに注目してください。\n\n"
        f"文書A: {path_a}\n"
        f"文書B: {path_b}\n\n"
        f"{JSON_ONLY_INSTRUCTION}\n"
        '{"more_human": "A" | "B" | "tie", "confidence": "high" | "mid" | "low", '
        '"why": "...", "ai_tells_in_loser": ["...", "..."]}'
    )


def build_thesis_preservation_prompt(thesis: str, output_path: Path) -> str:
    return (
        "次の文書と、その文書が言おうとしている中心主張（thesis）を読み、趣旨が"
        "保たれているか、狭まったりずれたりした箇所がないかを判定してください。"
        "趣旨のズレが見つかった場合は、その原因になったと考えられる natural-japanese "
        "スキルの指示箇所を、SKILL.md および references/ 配下のファイルを実際に Read して"
        "特定し、file/section/quote で示してください。推測でファイル名や引用を書かず、"
        "必ず実際に読んだ内容から引用してください。\n\n"
        f"thesis: {thesis}\n"
        f"対象文書: {output_path}\n\n"
        f"{JSON_ONLY_INSTRUCTION}\n"
        '{"preserved": true | false, "distortions": [{"what": "...", "how": "...", '
        '"skill_cause": {"file": "references/...", "section": "...", "quote": "..."}}]}\n'
        "distortions が無ければ空配列にしてください。"
    )


def build_structural_smell_prompt(output_path: Path) -> str:
    return (
        "次の文書を読み、機械的な lint では検出できない構造・修辞面のAI臭"
        "（全節が同型、順位・段階の押し付け、空虚な So What、過剰なヘッジ、"
        "フラットな箇条書き列挙、テンプレ反復 等）を列挙してください。各所見について、"
        "それを誘発したと考えられる natural-japanese スキルの指示箇所を、SKILL.md "
        "および references/ 配下のファイルを実際に Read して特定し、"
        "file/section/quote で示してください。推測でファイル名や引用を書かず、"
        "必ず実際に読んだ内容から引用してください。\n\n"
        f"対象文書: {output_path}\n\n"
        "evidence は文書の本文をそのまま長く引用せず、短く抽象化した記述にしてください"
        "（固有名詞・数値・具体的な文言を書かないこと）。\n\n"
        f"{JSON_ONLY_INSTRUCTION}\n"
        '{"findings": [{"smell": "...", "severity": "low" | "mid" | "high", '
        '"evidence": "...", "skill_cause": {"file": "...", "section": "...", "quote": "..."}}]}\n'
        "findings が無ければ空配列にしてください。"
    )


# ---------------------------------------------------------------------------
# lint 連携（参考記録。判定には使わない）
# ---------------------------------------------------------------------------
def run_lint_json(target_path: Path, timeout: int = 120) -> dict:
    lint_script = REPO_ROOT / "scripts" / "lint.py"
    try:
        result = subprocess.run(
            ["uv", "run", str(lint_script), str(target_path), "--json"],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(REPO_ROOT),
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        return {"error": repr(e)}
    if result.returncode != 0:
        return {"error": f"lint.py exited {result.returncode}: {result.stderr.strip()}"}
    parsed = extract_json(result.stdout)
    if parsed is None:
        return {"error": "lint.py の --json 出力をパースできませんでした", "raw": result.stdout}
    return parsed


# ---------------------------------------------------------------------------
# A/B 割当（ブラインド human_ness 批評用）
# ---------------------------------------------------------------------------
def assign_ab(run_label: str, item_id: str) -> dict:
    """run_label + item_id から決定的に A/B 割当を決める（--run-label が同じなら
    毎回同じ割当になり、再現性を保つ）。批評者にはこの割当を渡さない。
    """
    seed_input = f"{run_label}:{item_id}"
    digest = hashlib.sha256(seed_input.encode("utf-8")).digest()
    swap = bool(digest[0] % 2)
    if swap:
        return {"A": "baseline", "B": "output", "seed_input": seed_input, "swap": swap}
    return {"A": "output", "B": "baseline", "seed_input": seed_input, "swap": swap}


# ---------------------------------------------------------------------------
# 1 item のパイプライン実行
# ---------------------------------------------------------------------------
def process_item(item: dict, *, run_dir: Path, run_label: str, model_apply: str,
                  model_critic: str, timeout_apply: int, timeout_critic: int) -> dict:
    item_id = item["id"]
    doctype = item["doctype"]
    mode = item["mode"]
    print(f"[{item_id}] 開始 (doctype={doctype}, mode={mode})", file=sys.stderr)

    result: dict = {"id": item_id, "doctype": doctype, "mode": mode, "errors": []}

    # --- 1. baseline 用意 ---
    baseline_path = run_dir / f"{item_id}.baseline.md"
    print(f"[{item_id}] baseline 用意", file=sys.stderr)
    try:
        if mode == "generate":
            naive_prompt = NAIVE_PROMPT_TEMPLATES[doctype].format(topic=item["topic"])
            baseline_text = run_claude_naive(naive_prompt, model=model_apply)
            baseline_path.write_text(baseline_text + "\n", encoding="utf-8")
        else:  # rewrite
            source_path = Path(item["source"]).expanduser().resolve()
            if not source_path.exists():
                raise FileNotFoundError(f"source が見つかりません: {source_path}")
            shutil.copyfile(source_path, baseline_path)
    except Exception as e:  # noqa: BLE001
        result["errors"].append(f"baseline_prepare failed: {e!r}")
        print(f"[{item_id}]   ERROR: baseline_prepare: {e!r}", file=sys.stderr)
        return result  # baseline なしでは何も続けられない

    # --- 2. thesis 抽出 ---
    print(f"[{item_id}] thesis 抽出", file=sys.stderr)
    thesis_prompt = build_thesis_prompt(item, baseline_path)
    thesis_result, thesis_meta = call_critic_json(
        thesis_prompt, model=model_critic, cwd=REPO_ROOT, timeout=timeout_critic
    )
    (run_dir / f"{item_id}.thesis.json").write_text(
        json.dumps({"result": thesis_result, "meta": thesis_meta}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    result["thesis"] = thesis_result
    if thesis_result is None:
        result["errors"].append("thesis_extract: JSON parse failed after retry")

    # --- 3. skill-apply ---
    print(f"[{item_id}] skill-apply（時間がかかる）", file=sys.stderr)
    out_path = run_dir / f"{item_id}.apply.md"
    apply_prompt = build_apply_prompt(item, out_path)
    apply_stdout: str | None = None
    try:
        apply_stdout = run_claude_tooled(
            apply_prompt, model=model_apply, cwd=REPO_ROOT,
            allowed_tools="Read,Bash,Write", timeout=timeout_apply, effort=EFFORT_APPLY,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        result["errors"].append(f"skill_apply failed: {e!r}")
        print(f"[{item_id}]   ERROR: skill_apply: {e!r}", file=sys.stderr)
    (run_dir / f"{item_id}.apply.stdout.txt").write_text(apply_stdout or "", encoding="utf-8")

    output_text: str | None = None
    if out_path.exists():
        output_text = out_path.read_text(encoding="utf-8")
    else:
        result["errors"].append("skill_apply: out_path が作成されませんでした")
        print(f"[{item_id}]   WARNING: out_path が作成されませんでした: {out_path}", file=sys.stderr)
    result["output_available"] = output_text is not None

    # --- 4. lint 記録（参考。判定には使わない） ---
    if output_text is not None:
        print(f"[{item_id}] lint 記録", file=sys.stderr)
        lint_json = run_lint_json(out_path)
        (run_dir / f"{item_id}.lint.json").write_text(
            json.dumps(lint_json, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        result["lint_finding_count"] = len(lint_json.get("findings", [])) if isinstance(lint_json, dict) else None

    # --- 5. 批評3種 ---
    if output_text is not None:
        # 5a. human_ness（ブラインドA/B）
        print(f"[{item_id}] 批評: human_ness", file=sys.stderr)
        ab = assign_ab(run_label, item_id)
        path_map = {"baseline": baseline_path, "output": out_path}
        path_a, path_b = path_map[ab["A"]], path_map[ab["B"]]
        hn_prompt = build_human_ness_prompt(path_a, path_b)
        hn_result, hn_meta = call_critic_json(
            hn_prompt, model=model_critic, cwd=REPO_ROOT, timeout=timeout_critic
        )
        (run_dir / f"{item_id}.ab_assignment.json").write_text(
            json.dumps(ab, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (run_dir / f"{item_id}.human_ness.json").write_text(
            json.dumps({"result": hn_result, "meta": hn_meta}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        result["human_ness"] = hn_result
        result["ab_assignment"] = ab
        if hn_result is None:
            result["errors"].append("critic_human_ness: JSON parse failed after retry")

        # 5b. thesis_preservation（thesis が取れている場合のみ）
        if thesis_result and thesis_result.get("thesis"):
            print(f"[{item_id}] 批評: thesis_preservation", file=sys.stderr)
            tp_prompt = build_thesis_preservation_prompt(thesis_result["thesis"], out_path)
            tp_result, tp_meta = call_critic_json(
                tp_prompt, model=model_critic, cwd=REPO_ROOT, timeout=timeout_critic
            )
            (run_dir / f"{item_id}.thesis_preservation.json").write_text(
                json.dumps({"result": tp_result, "meta": tp_meta}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            result["thesis_preservation"] = tp_result
            if tp_result is None:
                result["errors"].append("critic_thesis_preservation: JSON parse failed after retry")
        else:
            result["thesis_preservation"] = None
            result["errors"].append("critic_thesis_preservation: skipped (thesis not available)")

        # 5c. structural_smell
        print(f"[{item_id}] 批評: structural_smell", file=sys.stderr)
        ss_prompt = build_structural_smell_prompt(out_path)
        ss_result, ss_meta = call_critic_json(
            ss_prompt, model=model_critic, cwd=REPO_ROOT, timeout=timeout_critic
        )
        (run_dir / f"{item_id}.structural_smell.json").write_text(
            json.dumps({"result": ss_result, "meta": ss_meta}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        result["structural_smell"] = ss_result
        if ss_result is None:
            result["errors"].append("critic_structural_smell: JSON parse failed after retry")
    else:
        result["human_ness"] = None
        result["thesis_preservation"] = None
        result["structural_smell"] = None
        result["errors"].append("critics skipped: no output document")

    print(f"[{item_id}] 完了", file=sys.stderr)
    return result


# ---------------------------------------------------------------------------
# 集約
# ---------------------------------------------------------------------------
SEVERITY_WEIGHT = {"high": 3, "mid": 2, "low": 1}
DISTORTION_WEIGHT = 2  # thesis_preservation の distortion 1件あたりの重み（smell の mid 相当として扱う）


def _truncate(text: str | None, limit: int = REPORT_EVIDENCE_MAX_CHARS) -> str:
    if not text:
        return ""
    text = str(text).strip()
    return text if len(text) <= limit else text[:limit] + "…"


def aggregate(results: list[dict]) -> dict:
    total_items = len(results)

    # --- human_ness ---
    hn_judged = 0
    hn_output_lost = 0
    hn_by_doctype: dict[str, dict[str, int]] = defaultdict(lambda: {"judged": 0, "output_lost": 0})
    for r in results:
        hn = r.get("human_ness")
        ab = r.get("ab_assignment")
        if not isinstance(hn, dict) or not isinstance(ab, dict):
            continue
        verdict = hn.get("more_human")
        if verdict not in ("A", "B", "tie"):
            continue
        hn_judged += 1
        hn_by_doctype[r["doctype"]]["judged"] += 1
        if verdict != "tie":
            winner_side = ab.get(verdict)  # "baseline" | "output"
            if winner_side == "output":
                pass  # スキル適用版が勝った = 損なっていない
            elif winner_side == "baseline":
                hn_output_lost += 1
                hn_by_doctype[r["doctype"]]["output_lost"] += 1

    # --- skill_cause クラスタ（thesis_preservation.distortions + structural_smell.findings）---
    # クラスタキー: (file, section) を正規化（前後空白除去）。
    clusters: dict[tuple[str, str], dict] = {}

    def _get_cluster(file_, section_) -> dict:
        file_ = file_ if isinstance(file_, str) else ""
        section_ = section_ if isinstance(section_, str) else ""
        key = ((file_ or "(不明)").strip(), (section_ or "(未指定)").strip())
        if key not in clusters:
            clusters[key] = {
                "file": key[0],
                "section": key[1],
                "items": set(),
                "distortion_count": 0,
                "smell_severity_counts": Counter(),
                "samples": [],  # 抽象化した代表所見（最大数件）
            }
        return clusters[key]

    for r in results:
        item_id = r["id"]
        tp = r.get("thesis_preservation")
        if isinstance(tp, dict) and isinstance(tp.get("distortions"), list):
            for d in tp["distortions"]:
                if not isinstance(d, dict):
                    continue
                cause = d.get("skill_cause")
                cause = cause if isinstance(cause, dict) else {}
                c = _get_cluster(cause.get("file", ""), cause.get("section", ""))
                c["items"].add(item_id)
                c["distortion_count"] += 1
                if len(c["samples"]) < 3:
                    c["samples"].append(
                        f"[趣旨歪み] {_truncate(d.get('what'))} / {_truncate(d.get('how'))}"
                    )

        ss = r.get("structural_smell")
        if isinstance(ss, dict) and isinstance(ss.get("findings"), list):
            for f in ss["findings"]:
                if not isinstance(f, dict):
                    continue
                cause = f.get("skill_cause")
                cause = cause if isinstance(cause, dict) else {}
                c = _get_cluster(cause.get("file", ""), cause.get("section", ""))
                c["items"].add(item_id)
                sev = f.get("severity") if f.get("severity") in SEVERITY_WEIGHT else "low"
                c["smell_severity_counts"][sev] += 1
                if len(c["samples"]) < 3:
                    c["samples"].append(f"[構造の臭み/{sev}] {_truncate(f.get('smell'))}: {_truncate(f.get('evidence'))}")

    cluster_list = []
    for (file_, section_), c in clusters.items():
        weighted = c["distortion_count"] * DISTORTION_WEIGHT + sum(
            SEVERITY_WEIGHT[sev] * n for sev, n in c["smell_severity_counts"].items()
        )
        freq_ratio = len(c["items"]) / total_items if total_items else 0.0
        score = weighted * freq_ratio
        cluster_list.append(
            {
                "file": file_,
                "section": section_,
                "item_count": len(c["items"]),
                "distortion_count": c["distortion_count"],
                "smell_severity_counts": dict(c["smell_severity_counts"]),
                "samples": c["samples"],
                "score": score,
            }
        )
    cluster_list.sort(key=lambda c: c["score"], reverse=True)

    return {
        "total_items": total_items,
        "human_ness": {
            "judged": hn_judged,
            "output_lost": hn_output_lost,
            "rate": (hn_output_lost / hn_judged) if hn_judged else None,
            "by_doctype": {k: dict(v) for k, v in hn_by_doctype.items()},
        },
        "clusters": cluster_list,
    }


# ---------------------------------------------------------------------------
# レポート出力（corpus/reports/skill-eval-findings.md）
# ---------------------------------------------------------------------------
def render_report(*, run_label: str, manifest_path: Path, model_apply: str,
                   model_critic: str, results: list[dict], aggregated: dict,
                   include_samples: bool = False) -> str:
    # include_samples=False（コミット対象レポートの既定）: 批評の逐語 sample
    # （smell/evidence 文）は元文書の固有名詞・数値を含みうるため出力しない。
    # クラスタ表・件数・原因 file/section・改善候補という抽象情報だけを残す。
    # include_samples=True は runs/<label>/report.full.md（非コミット）専用。
    by_doctype = Counter(r["doctype"] for r in results)
    lines: list[str] = []
    lines.append("# skill-eval-findings — natural-japanese スキル適用の所見集約")
    lines.append("")
    lines.append(
        "corpus/experiments/skill-eval/eval.py が実行した結果を集約したレポート。"
        "元文書の本文・固有名詞・数値は含まない（抽象化した所見のみ）。"
    )
    lines.append("")
    lines.append("## 実行メタ")
    lines.append("")
    lines.append(f"- run-label: `{run_label}`")
    lines.append("- manifest: (ローカル manifest。パス・名前は非公開)")
    lines.append(f"- item数: {aggregated['total_items']}")
    lines.append(
        "- doctype内訳: "
        + ", ".join(f"{k}={v}" for k, v in sorted(by_doctype.items()))
    )
    lines.append(f"- モデル: apply=`{model_apply}` / critic(thesis・批評3種)=`{model_critic}`")
    error_items = [r["id"] for r in results if r.get("errors")]
    if error_items:
        lines.append(f"- 一部ステージでエラー・スキップが発生した item: {', '.join(error_items)}（詳細は runs/ 内のログ）")
    lines.append("")

    # --- human_ness ---
    hn = aggregated["human_ness"]
    lines.append("## human_ness（ブラインドA/B: スキル適用版 vs 素の生成）")
    lines.append("")
    if hn["judged"]:
        pct = hn["rate"] * 100
        lines.append(
            f"- 全体: スキル適用版が「素の生成より人間らしくない」と判定された割合 = "
            f"{hn['output_lost']}/{hn['judged']}（{pct:.0f}%）"
        )
        if hn["by_doctype"]:
            lines.append("")
            lines.append("| doctype | 判定数 | スキル版が敗北 | 敗北率 |")
            lines.append("| --- | --- | --- | --- |")
            for doctype, v in sorted(hn["by_doctype"].items()):
                judged = v["judged"]
                lost = v["output_lost"]
                rate = f"{(lost / judged * 100):.0f}%" if judged else "-"
                lines.append(f"| {doctype} | {judged} | {lost} | {rate} |")
    else:
        lines.append("- 有効な human_ness 判定なし（全item で批評が失敗、または対象文書が無い）")
    lines.append("")

    # skill_cause.file/section はLLMの自己申告。コミット版レポートには
    # リポジトリ内のスキルファイル参照らしきものだけをそのまま載せ、それ以外
    # （元文書のパスや固有名詞が紛れた場合）は伏せる。Markdown 表を壊す
    # 文字（| と改行）も無害化する。表・改善提案節など全出力箇所で共用する。
    def _esc(v: str, limit: int = 60) -> str:
        v = v if isinstance(v, str) else ""
        for ch, rep in (("|", "\\|"), ("\n", " "), ("\r", " "), ("`", "'")):
            v = v.replace(ch, rep)
        return v[:limit]

    def _resolve_repo_file(v) -> Path | None:
        """skill_cause.file がリポジトリ内の実在ファイルを指す場合のみ Path を返す。
        接頭辞だけの検査は 'references/../../secret' 等で迂回できるため、
        REPO_ROOT 基準で resolve し、配下かつ実在することを確認する。"""
        if not isinstance(v, str) or not v or "\x00" in v:
            return None
        try:
            resolved = (REPO_ROOT / v).resolve()
        except (OSError, ValueError):
            return None
        if not resolved.is_relative_to(REPO_ROOT.resolve()) or not resolved.is_file():
            return None
        rel = resolved.relative_to(REPO_ROOT.resolve())
        if rel.parts and rel.parts[0] in ("references", "assets", "scripts") or str(rel) == "SKILL.md":
            return resolved
        return None

    def safe_ref(v) -> str:
        resolved = _resolve_repo_file(v)
        if resolved is None:
            return "(リポジトリ外参照のため非表示)"
        return _esc(str(resolved.relative_to(REPO_ROOT.resolve())), 80)

    def safe_section(file_v, section_v) -> str:
        """section は、file が実在する場合にそのファイルの見出し行と照合し、
        含まれる見出しだけをそのまま載せる。照合できなければ伏せる。"""
        resolved = _resolve_repo_file(file_v)
        if resolved is None or not isinstance(section_v, str) or not section_v.strip():
            return "(節照合不可のため非表示)"
        try:
            text = resolved.read_text(encoding="utf-8")
        except OSError:
            return "(節照合不可のため非表示)"
        headings = [ln.lstrip("#").strip() for ln in text.splitlines() if ln.lstrip().startswith("#")]
        for part in re.split(r"\s*/\s*", section_v.strip()):
            if not any(part and part in h for h in headings):
                return "(節照合不可のため非表示)"
        return _esc(section_v.strip())

    # --- クラスタ表 ---
    lines.append("## スキルレベル所見クラスタ（原因 file/section 別、頻度×severity降順）")
    lines.append("")
    clusters = aggregated["clusters"]
    if clusters:
        lines.append("| 原因ファイル | 節 | 出現item数/総item数 | 趣旨歪み件数 | severity内訳(smell) | score |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for c in clusters:
            sev = c["smell_severity_counts"]
            sev_str = ", ".join(f"{k}={v}" for k, v in sorted(sev.items())) if sev else "-"
            lines.append(
                f"| `{safe_ref(c['file'])}` | {safe_section(c['file'], c['section'])} | {c['item_count']}/{aggregated['total_items']} | "
                f"{c['distortion_count']} | {sev_str} | {c['score']:.2f} |"
            )
        if include_samples:
            lines.append("")
            lines.append("代表的な所見（上位クラスタのみ抜粋。逐語のため非コミット版のみ）:")
            lines.append("")
            for c in clusters[:5]:
                lines.append(f"- `{c['file']}` / {c['section']}")
                for s in c["samples"]:
                    lines.append(f"  - {s}")
        else:
            lines.append("")
            lines.append(
                "（各クラスタの逐語の所見文は元文書の固有名詞・数値を含みうるため、"
                "このコミット版には載せない。全文は `runs/<run-label>/report.full.md`（非コミット）を参照）"
            )
    else:
        lines.append("- クラスタなし（distortion / structural_smell の finding が1件も得られなかった）")
    lines.append("")

    # --- 次にスキルのどこを直すべきか ---
    lines.append("## 次にスキルのどこを直すべきか（頻度上位クラスタから）")
    lines.append("")
    if clusters:
        for c in clusters[:3]:
            lines.append(
                f"- `{safe_ref(c['file'])}`（{safe_section(c['file'], c['section'])}）: {c['item_count']}/{aggregated['total_items']} item で"
                f"原因として挙げられた。当該節の記述が具体例・限定条件を欠いている可能性が高く、"
                "書き手が誤って過剰一般化・テンプレ適用しないよう、適用条件や『やりすぎ』の反例を"
                "追記することを検討する。"
            )
    else:
        lines.append("- 今回のサンプルでは明確なクラスタが得られなかった（サンプル数を増やして再実行が必要）。")
    lines.append("")

    # --- 限界 ---
    lines.append("## この評価自体の限界")
    lines.append("")
    lines.append(
        "- サンプル数が少ない（本レポート時点で item数 = "
        f"{aggregated['total_items']}）。クラスタの頻度・スコアは参考値であり、統計的な確定ではない。"
    )
    lines.append(
        "- 批評（human_ness / thesis_preservation / structural_smell）自体もLLMによる判定であり、"
        "ノイズ・見落とし・過剰検出のいずれも起こりうる。特に human_ness のブラインドA/B は"
        "批評モデルの好み（整った文章を「人間らしい」と誤判定する等）に影響される可能性がある。"
    )
    lines.append(
        "- skill_cause（file/section/quote）は批評モデルの自己申告であり、実際の因果関係を"
        "保証しない。同一クラスタに複数の異なる原因が混在している可能性がある。"
    )
    lines.append(
        "- thesis 抽出・批評はすべて単一の critic モデルで行っており、モデル固有の癖が"
        "結果に系統的なバイアスとして乗る可能性がある。"
    )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def make_run_label() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def print_dry_run(items: list[dict], *, run_label: str, model_apply: str, model_critic: str) -> None:
    by_doctype = Counter(it["doctype"] for it in items)
    print(f"[dry-run] run-label = {run_label}")
    print(f"[dry-run] model-apply = {model_apply} / model-critic = {model_critic}")
    print(f"[dry-run] items = {len(items)} ({', '.join(f'{k}={v}' for k, v in sorted(by_doctype.items()))})")
    for it in items:
        print(f"  - {it['id']} (doctype={it['doctype']}, mode={it['mode']})")
    print("[dry-run] 実行順（1 item あたり）:")
    for i, stage in enumerate(STAGE_ORDER, start=1):
        print(f"  {i}. {stage}")
    print("[dry-run] claude は一度も呼び出していません。")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="natural-japanese スキル評価ハーネス（claude CLI を subprocess で呼ぶ）"
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=SKILL_EVAL_DIR / "manifest.local.json",
        help="評価対象を列挙した manifest JSON（既定: manifest.local.json。"
        "スモークテスト等では manifest.example.json や一時 manifest を明示的に指定する）",
    )
    parser.add_argument("--dry-run", action="store_true", help="claude を呼ばず、item と段の順序だけ表示する")
    parser.add_argument(
        "--run-label",
        default=None,
        help="runs/<run-label>/ のディレクトリ名、A/B割当のseed、レポートの実行メタに使う。"
        "未指定なら実行時刻から自動生成する（再現したい場合は明示的に指定する）",
    )
    parser.add_argument("--model-apply", default=DEFAULT_MODEL_APPLY, help="skill-apply / baseline生成に使うモデル")
    parser.add_argument("--model-critic", default=DEFAULT_MODEL_CRITIC, help="thesis抽出・批評3種に使うモデル")
    parser.add_argument("--timeout-apply", type=int, default=600, help="skill-apply段のタイムアウト秒（既定600）")
    parser.add_argument("--timeout-critic", type=int, default=600, help="thesis抽出・批評段のタイムアウト秒（既定600）")
    parser.add_argument("--effort-apply", default="low", help="skill-apply の effort（low/medium/high。空文字でclaudeのデフォルト）")
    parser.add_argument("--effort-critic", default="low", help="thesis抽出・批評の effort（同上）")
    parser.add_argument(
        "--parallel", type=int, default=1,
        help="item を並列実行する数（既定1=直列）。claude CLI 待ちが支配的なのでスレッド並列。ログ行は item id 付きなので混在しても追える",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="corpus/reports/skill-eval-findings.md への書き出しをスキップする（デバッグ用）",
    )
    args = parser.parse_args()

    try:
        items = load_manifest(args.manifest)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as e:
        print(f"エラー: manifest を読み込めません: {e}", file=sys.stderr)
        return 1

    run_label = args.run_label or make_run_label()

    if args.dry_run:
        print_dry_run(items, run_label=run_label, model_apply=args.model_apply, model_critic=args.model_critic)
        return 0

    if not re.fullmatch(r"[A-Za-z0-9._-]+", run_label) or run_label in (".", ".."):
        print(f"--run-label に使える文字は英数字と ._- のみ（'.', '..' は不可）: {run_label!r}", file=sys.stderr)
        return 1
    if not (RUNS_ROOT / run_label).resolve().is_relative_to(RUNS_ROOT.resolve()):
        print(f"--run-label が runs/ の外を指しています: {run_label!r}", file=sys.stderr)
        return 1
    if args.parallel < 1:
        print(f"--parallel は1以上を指定してください: {args.parallel}", file=sys.stderr)
        return 1

    global EFFORT_APPLY, EFFORT_CRITIC
    EFFORT_APPLY = args.effort_apply or None
    EFFORT_CRITIC = args.effort_critic or None

    run_dir = RUNS_ROOT / run_label
    run_dir.mkdir(parents=True, exist_ok=True)

    started_at = time.strftime("%Y-%m-%dT%H:%M:%S")

    def _run_one(item: dict) -> dict:
        try:
            return process_item(
                item,
                run_dir=run_dir,
                run_label=run_label,
                model_apply=args.model_apply,
                model_critic=args.model_critic,
                timeout_apply=args.timeout_apply,
                timeout_critic=args.timeout_critic,
            )
        except Exception as e:  # noqa: BLE001
            # 1 item の予期しない失敗で全体を止めない。
            print(f"[{item['id']}] 予期しないエラー: {e!r}", file=sys.stderr)
            return {"id": item["id"], "doctype": item["doctype"], "mode": item["mode"], "errors": [f"unexpected: {e!r}"]}

    # item 単位で並列実行する。各 item は自分の id を接頭辞にしたファイルだけを
    # 書くので、ファイル競合はない。claude CLI の subprocess 待ちが支配的なため
    # スレッドで十分（GIL の影響を受けない）。結果は manifest の順序で保持する。
    if args.parallel > 1 and len(items) > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=args.parallel) as ex:
            results = list(ex.map(_run_one, items))
    else:
        results = [_run_one(item) for item in items]

    finished_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    run_meta = {
        "run_label": run_label,
        "manifest": str(args.manifest),
        "model_apply": args.model_apply,
        "model_critic": args.model_critic,
        "started_at": started_at,
        "finished_at": finished_at,
        "item_ids": [it["id"] for it in items],
    }
    (run_dir / "run_meta.json").write_text(json.dumps(run_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "results_summary.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    aggregated = aggregate(results)
    (run_dir / "aggregated.json").write_text(json.dumps(aggregated, ensure_ascii=False, indent=2), encoding="utf-8")

    # 全文レポート（逐語 sample 込み）は runs/ 内（非コミット）にのみ書く。
    full_report = render_report(
        run_label=run_label, manifest_path=args.manifest,
        model_apply=args.model_apply, model_critic=args.model_critic,
        results=results, aggregated=aggregated, include_samples=True,
    )
    (run_dir / "report.full.md").write_text(full_report, encoding="utf-8")

    if not args.no_report:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        report_text = render_report(
            run_label=run_label,
            manifest_path=args.manifest,
            model_apply=args.model_apply,
            model_critic=args.model_critic,
            results=results,
            aggregated=aggregated,
            include_samples=False,
        )
        FINDINGS_REPORT_PATH.write_text(report_text, encoding="utf-8")
        print(f"コミット対象レポート（抽象化）: {FINDINGS_REPORT_PATH}", file=sys.stderr)
        print(f"全文レポート（非コミット）: {run_dir / 'report.full.md'}", file=sys.stderr)

    print(f"完了: {len(results)} item, runs/{run_label}/", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
