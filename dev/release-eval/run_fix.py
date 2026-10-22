"""同じ下書きを、スキルの2つのバージョンで「読みやすくして」と直させる。

リリースノートの「確かめたこと」の実験に使う。下書きはスキルなしで書かせた相談文(宛先ごとに3本)。
  python3 dev/release-eval/run_fix.py --drafts <下書きのディレクトリ> --out <出力先> \
      --plugin v1.6.0=<plugin のディレクトリ> --plugin v1.6.1=<plugin のディレクトリ>

<下書きのディレクトリ>/<宛先>/N1.md のように置く。plugin のディレクトリは、.claude-plugin/ と skills/ を持つもの
(`git archive <tag> .claude-plugin skills | tar -x -C <dir>` で作れる)。.claude/ の下に置くと、
claude -p がスクリプトを実行できないので、/tmp などに置く。
出力: <出力先>/<宛先>/<下書きの名前>-<バージョン>.md と、ログ log-*.txt
"""
import argparse
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PROMPT = ("natural-japanese スキルで、draft.md の相談資料を読みやすくしてください。直した全文を output.md に書き出してください。"
          "確認の質問はせず、最後まで自分の判断で進めてください。")
TOOLS = ["Skill", "Read", "Write", "Edit", "Glob", "Grep", "Bash(uv run:*)", "Bash(python3:*)",
         "Bash(cat:*)", "Bash(wc:*)", "Bash(cp:*)", "Bash(mkdir:*)"]


def run(draft: Path, ver: str, plugin: str, out: Path, model: str, effort: str) -> str:
    w = Path(tempfile.mkdtemp(prefix=f"fix-{draft.parent.name}-{draft.stem}-"))
    shutil.copy(draft, w / "draft.md")
    cmd = ["claude", "-p", PROMPT, "--model", model, "--effort", effort, "--output-format", "stream-json", "--verbose",
           "--setting-sources", "project", "--plugin-dir", plugin, "--add-dir", "/tmp", "--allowedTools", *TOOLS]
    t = time.time()
    r = subprocess.run(cmd, cwd=w, capture_output=True, text=True, timeout=2400, stdin=subprocess.DEVNULL)
    o = out / draft.parent.name
    o.mkdir(parents=True, exist_ok=True)
    (o / f"log-{draft.stem}-{ver}.txt").write_text(r.stdout)
    if not (w / "output.md").exists():
        return f"FAIL {draft.parent.name}/{draft.stem} {ver}"
    shutil.copy(w / "output.md", o / f"{draft.stem}-{ver}.md")
    return f"ok {draft.parent.name}/{draft.stem} {ver} {time.time() - t:.0f}s"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--drafts", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--plugin", action="append", required=True, help="バージョン名=plugin のディレクトリ")
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--effort", default="high")
    ap.add_argument("--jobs", type=int, default=6)
    a = ap.parse_args()
    plugins = dict(p.split("=", 1) for p in a.plugin)
    jobs = [(d, v, p) for d in sorted(a.drafts.glob("*/*.md")) for v, p in plugins.items()]
    with ThreadPoolExecutor(a.jobs) as ex:
        for line in ex.map(lambda j: run(*j, a.out, a.model, a.effort), jobs):
            print(line, flush=True)


if __name__ == "__main__":
    main()
