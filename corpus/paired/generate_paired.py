# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""corpus/paired/generate_paired.py — 対コーパスの AI 側を生成する。

manifest.json の human 記事1本ごとに、同じタイトルと目標文字数だけを渡して
各モデルに記事を書かせ、corpus/paired/<set>/ai/<model>/<id>.md に保存する。
見出し構成は渡さない(渡すと AI 自身の見出しや箇条書きの癖が観測できなくなる)。
CLI の呼び出しと個人設定の隔離は corpus/generate.py の run_* をそのまま使う。

並列度: モデルごとに1スレッド。codex はプロセス間で auth.json を共有すると
トークン更新が競合しうるため、モデルごとに別の CODEX_HOME を切る。

使い方:
    uv run corpus/paired/generate_paired.py --set tech-qiita --limit 3
    uv run corpus/paired/generate_paired.py --set tech-qiita --models gpt-6-luna
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import generate as g  # noqa: E402

MODELS: dict[str, str] = {
    "claude-fable-5-1": "claude",
    "claude-opus-5-5": "claude",
    "claude-sonnet-5-5": "claude",
    "gpt-6-astra": "codex",
    "gpt-6.1-sol": "codex",
    "gpt-6-luna": "codex",
    "gemini-3.8-flash": "agy",
}
# 生成条件(ROADMAP.md S6)。出力先ディレクトリと、対の粒度(pair_level)を持つ
#   title:     タイトルと文字数だけを渡す(既定。出力は ai/)
#   materials: タイトルと文字数に加え、human 記事のコードブロック(コードと実行結果)を
#              作業の材料として渡す。Coding Agent が作業から記事を書く流れに近づける
#   polish:    human 記事の本文をそのまま渡して推敲させる(G′)
CONDITIONS = {
    "title": ("ai", "title+length"),
    "materials": ("ai-materials", "title+length+code"),
    "polish": ("ai-polish", "polish-of-human"),
}
PROMPT_TEMPLATE = "「{title}」というタイトルで技術ブログの記事を書いて。本文は{chars}字程度で。"
MATERIALS_TEMPLATE = (
    "「{title}」というタイトルで技術ブログの記事を書いて。本文は{chars}字程度で。"
    "以下は作業中に使ったコードと、その実行結果です。\n\n{materials}"
)
POLISH_TEMPLATE = "次の技術ブログの記事を推敲して、読みやすくして。推敲した記事の本文だけを出力して。\n\n{body}"
FENCE_BLOCK_RE = re.compile(r"^\s*(```|~~~)[^\n]*\n.*?^\s*\1\s*$", re.M | re.S)
FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.S)


def human_body(set_dir: Path, item: dict) -> str:
    text = (set_dir / "human" / f"{item['id']}.md").read_text(encoding="utf-8")
    return FRONTMATTER_RE.sub("", text, count=1).strip()


def build_prompt(condition: str, set_dir: Path, item: dict) -> str | None:
    """条件に応じたプロンプト。材料がなく条件を満たせない記事は None。"""
    chars = target_chars(item)
    if condition == "title":
        return PROMPT_TEMPLATE.format(title=item["title"], chars=chars)
    body = human_body(set_dir, item)
    if condition == "materials":
        blocks = [m.group(0).strip() for m in FENCE_BLOCK_RE.finditer(body)]
        if not blocks:
            return None
        return MATERIALS_TEMPLATE.format(title=item["title"], chars=chars, materials="\n\n".join(blocks))
    if condition == "polish":
        return POLISH_TEMPLATE.format(body=body)
    raise ValueError(condition)


MAX_TARGET_CHARS = 8000


def target_chars(item: dict) -> int:
    # コードを除いた本文の文字数を 500 字単位に丸める(指示として自然な数にする)。
    # 長すぎる指示はタイムアウトの原因になるため上限を設ける
    return min(MAX_TARGET_CHARS, max(1000, round(item["chars_without_code"] / 500) * 500))


def cli_versions() -> dict[str, str]:
    out = {}
    for name, cmd in {
        "claude": ["claude", "--version"],
        "codex": ["codex", "--version"],
        "agy": [g.agy_binary(), "--version"],
    }.items():
        try:
            out[name] = subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout.strip()
        except Exception as e:  # noqa: BLE001
            out[name] = f"unknown ({e})"
    return out


def codex_home_for(model: str) -> Path:
    home = g.ISOLATION_DIR / f"codex-home-{model}"
    home.mkdir(parents=True, exist_ok=True)
    shutil.copy2(g.CODEX_HOME / "auth.json", home / "auth.json")
    return home


def run(engine: str, model: str, prompt: str, effort: str, codex_home: Path | None) -> str:
    if engine == "claude":
        return g.run_claude(prompt, model, effort)
    if engine == "codex":
        return g.run_codex(prompt, model, effort, codex_home=codex_home)
    if engine == "agy":
        return g.run_agy(prompt, model, effort)
    raise ValueError(engine)


def generate_for_model(
    model: str,
    items: list[dict],
    set_dir: Path,
    effort: str,
    versions: dict,
    retries: int,
    lock: threading.Lock,
    condition: str = "title",
) -> tuple[int, int]:
    engine = MODELS[model]
    out_sub, pair_level = CONDITIONS[condition]
    out_dir = set_dir / out_sub / model
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = set_dir / "logs" / f"{condition}-{model}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    codex_home = codex_home_for(model) if engine == "codex" else None
    ok = failed = 0
    for item in items:
        out_path = out_dir / f"{item['id']}.md"
        if out_path.exists():
            continue
        chars = target_chars(item)
        prompt = build_prompt(condition, set_dir, item)
        if prompt is None:
            continue
        body = None
        for attempt in range(retries + 1):
            try:
                body = run(engine, model, prompt, effort, codex_home)
                if not body:
                    raise RuntimeError("empty response")
                break
            except Exception as e:  # noqa: BLE001
                body = None
                stderr = getattr(e, "stderr", "") or ""
                with log_path.open("a", encoding="utf-8") as f:
                    f.write(f"[{dt.datetime.now().isoformat(timespec='seconds')}] {item['id']} attempt {attempt + 1}: {e}\n{stderr[-3000:]}\n\n")
        if body is None:
            failed += 1
            with lock:
                print(f"  FAIL {model} {item['id']}", file=sys.stderr)
            continue
        meta = {
            "id": item["id"],
            "pair_of": item["id"],
            "set": set_dir.name,
            "genre": "tech",
            "engine": engine,
            "model": model,
            "effort": effort,
            "isolated": True,
            "pair_level": pair_level,
            "condition": condition,
            "target_chars": chars,
            "cli_version": versions.get(engine, ""),
            "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
            "prompt": prompt,
        }
        fm = "---\n" + "".join(f"{k}: {json.dumps(v, ensure_ascii=False)}\n" for k, v in meta.items()) + "---\n\n"
        out_path.write_text(fm + body + "\n", encoding="utf-8")
        ok += 1
        with lock:
            print(f"  ok {model} {item['id']} ({len(body)} chars)", file=sys.stderr)
    return ok, failed


def main() -> None:
    parser = argparse.ArgumentParser(description="対コーパスの AI 側を生成する")
    parser.add_argument("--set", default="tech-qiita")
    parser.add_argument("--models", nargs="*", default=list(MODELS))
    parser.add_argument("--limit", type=int, help="先頭 N 対だけ生成する(試走用)")
    parser.add_argument("--effort", default="low", choices=["low", "medium", "high"])
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--condition", choices=list(CONDITIONS), default="title")
    args = parser.parse_args()

    set_dir = HERE / args.set
    items = json.loads((set_dir / "manifest.json").read_text(encoding="utf-8"))["items"]
    if args.limit:
        items = items[: args.limit]
    unknown = [m for m in args.models if m not in MODELS]
    if unknown:
        raise SystemExit(f"unknown model: {unknown}")

    g.prepare_isolation()
    versions = cli_versions()
    lock = threading.Lock()
    with ThreadPoolExecutor(len(args.models)) as ex:
        futures = {
            m: ex.submit(
                generate_for_model, m, items, set_dir, args.effort, versions, args.retries, lock, args.condition
            )
            for m in args.models
        }
        for m, fut in futures.items():
            ok, failed = fut.result()
            print(f"{m}: ok={ok} failed={failed}", file=sys.stderr)


if __name__ == "__main__":
    main()
