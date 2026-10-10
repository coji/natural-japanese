# /// script
# requires-python = ">=3.11"
# ///
"""corpus/bench/run_bench.py — ベンチの課題をモデルに書かせる(ロードマップ S40)。

個人設定を外した各 CLI(corpus/generate.py の run_*)で、課題のプロンプトをそのまま渡す。
モデル名は「エンジン:モデル」で指定し、effort は全エンジン共通の --effort で指定する。
新しいモデルを足すときは、MODELS に1行足すか、--model engine:name で直接指定する。

出力: corpus/private/bench/out/<model>@<effort>/<task-id>.md(コミットしない)

使い方:
    uv run corpus/bench/run_bench.py --models claude-opus-5-5 gpt-6-luna gemini-3.8-flash --effort low
    uv run corpus/bench/run_bench.py --model agy:gemini-4-pro --effort medium
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "corpus"))
import generate as g  # noqa: E402

TASK_DIR = ROOT / "corpus/private/bench/tasks"
OUT_DIR = ROOT / "corpus/private/bench/out"
MODELS = {
    "claude-fable-5-1": "claude", "claude-opus-5-5": "claude", "claude-sonnet-5-5": "claude",
    "gpt-6-astra": "codex", "gpt-6.1-sol": "codex", "gpt-6-luna": "codex",
    "gemini-3.8-flash": "agy",
}
RUNNERS = {"claude": g.run_claude, "codex": g.run_codex, "agy": g.run_agy}


def run_one(engine: str, model: str, effort: str, task: dict) -> str:
    out = OUT_DIR / f"{model}@{effort}" / f"{task['id']}.md"
    if out.exists():
        return f"skip {model}@{effort} {task['id']}"
    out.parent.mkdir(parents=True, exist_ok=True)
    kwargs = {}
    if engine == "codex":
        home = g.ISOLATION_DIR / f"codex-home-{model}"
        home.mkdir(parents=True, exist_ok=True)
        (home / "auth.json").write_bytes((g.CODEX_HOME / "auth.json").read_bytes())
        kwargs["codex_home"] = home
    for attempt in range(2):
        try:
            body = RUNNERS[engine](task["prompt"], model, effort, **kwargs)
            if body:
                out.write_text(body + "\n", encoding="utf-8")
                return f"ok {model}@{effort} {task['id']} {len(body)} chars"
        except Exception as e:  # noqa: BLE001
            err = f"{e} {getattr(e, 'stderr', '')[-300:]}"
    return f"FAIL {model}@{effort} {task['id']}: {err if 'err' in dir() else 'empty'}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="*", default=[])
    ap.add_argument("--model", action="append", default=[], help="engine:name で直接指定(MODELS にないモデル)")
    ap.add_argument("--effort", default="low", choices=["low", "medium", "high"])
    ap.add_argument("--tasks", nargs="*", help="課題 ID を絞る")
    ap.add_argument("--parallel", type=int, default=3)
    a = ap.parse_args()
    targets = [(MODELS[m], m) for m in a.models] + [tuple(x.split(":", 1)) for x in a.model]
    tasks = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(TASK_DIR.glob("*/task.json"))]
    if a.tasks:
        tasks = [t for t in tasks if t["id"] in a.tasks]
    g.prepare_isolation()
    jobs = [(e, m, a.effort, t) for e, m in targets for t in tasks]
    with ThreadPoolExecutor(a.parallel) as ex:
        for r in ex.map(lambda j: run_one(*j), jobs):
            print(r, flush=True)


if __name__ == "__main__":
    main()
