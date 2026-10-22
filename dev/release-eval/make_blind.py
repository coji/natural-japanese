"""判定役に渡すディレクトリを作る。直す前・分からない言葉の一覧・2つのバージョンの直した文書を、A/B に伏せて並べる。

  python3 dev/release-eval/make_blind.py --drafts <下書き> --fixed <run_fix.py の出力> --flags <宛先>=<判定役の出力.md> ... \
      --versions v1.6.0 v1.6.1 --out <score のディレクトリ>

--flags には、prompts/judge-source.txt で判定させた出力(表)を宛先ごとに渡す。
出力: <out>/<宛先>/doc_<n>/{original.md, flags.json, A.md, B.md} と <out>/keymap.json(A/B がどのバージョンか)
"""
import argparse
import json
import random
import re
import shutil
from pathlib import Path


def flags(report: str) -> dict:
    out = {}
    for line in report.splitlines():
        cols = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cols) < 5 or not cols[0].startswith("doc_"):
            continue
        m = re.match(r"(\d+)", cols[1])
        if not m or re.fullmatch(r"\d+", cols[2]):
            continue
        out.setdefault(cols[0], []).append(
            {"line": int(m.group(1)), "word": cols[2].strip("「」"), "fix": cols[3], "weak": cols[4].startswith("弱")})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--drafts", type=Path, required=True)
    ap.add_argument("--fixed", type=Path, required=True)
    ap.add_argument("--flags", action="append", required=True)
    ap.add_argument("--versions", nargs=2, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    keymap = {}
    for spec in a.flags:
        topic, report = spec.split("=", 1)
        fl = flags(Path(report).read_text())
        for n, draft in enumerate(sorted((a.drafts / topic).glob("*.md")), 1):
            d = a.out / topic / f"doc_{n}"
            d.mkdir(parents=True, exist_ok=True)
            shutil.copy(draft, d / "original.md")
            fs = fl.get(f"doc_{n}", [])
            for i, f in enumerate(fs, 1):
                f["id"] = i
            (d / "flags.json").write_text(json.dumps(fs, ensure_ascii=False, indent=1))
            vs = list(a.versions)
            random.shuffle(vs)
            for lab, v in zip("AB", vs):
                shutil.copy(a.fixed / topic / f"{draft.stem}-{v}.md", d / f"{lab}.md")
            keymap[f"{topic}/doc_{n}"] = dict(zip("AB", vs))
    (a.out / "keymap.json").write_text(json.dumps(keymap, indent=1))


if __name__ == "__main__":
    main()
