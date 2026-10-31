# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""logic の YAML が、文書の非空行をすべて拾っているかを確かめる。

    uv run skills/critical-thinking/scripts/coverage.py <文書> [<YAML>]

YAML を省略すると <文書>.logic.yaml を読む。YAML のどこにも現れない行番号と、
文書にない行番号(書き間違い)、使ってはいけない種別を出す。すべて空なら OK と出て終了コード 0。
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ALLOWED_KINDS = {"事実", "推論", "意見", "前提", "見積"}


def walk(obj, lines: set[int], kinds: set[str]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "行":
                if isinstance(v, list):
                    lines.update(int(x) for x in v if isinstance(x, int))
                elif isinstance(v, int):
                    lines.add(v)
            elif k == "種別" and isinstance(v, str):
                kinds.add(v)
            else:
                walk(v, lines, kinds)
    elif isinstance(obj, list):
        for v in obj:
            walk(v, lines, kinds)


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    doc = Path(sys.argv[1])
    ypath = Path(sys.argv[2]) if len(sys.argv) > 2 else doc.with_name(doc.name + ".logic.yaml")
    data = yaml.safe_load(ypath.read_text())
    lines: set[int] = set()
    kinds: set[str] = set()
    walk(data, lines, kinds)
    src = doc.read_text().splitlines()
    nonempty = {i + 1 for i, l in enumerate(src) if l.strip()}
    missing = sorted(nonempty - lines)
    bogus = sorted(l for l in lines if l < 1 or l > len(src))
    bad_kinds = sorted(kinds - ALLOWED_KINDS)
    ok = not (missing or bogus or bad_kinds)
    if missing:
        print("YAML に現れない行:", ", ".join(map(str, missing)))
        for n in missing:
            print(f"  {n}: {src[n - 1][:60]}")
    if bogus:
        print("文書にない行番号:", ", ".join(map(str, bogus)))
    if bad_kinds:
        print("使ってはいけない種別:", ", ".join(bad_kinds))
    print("OK" if ok else "NG")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
