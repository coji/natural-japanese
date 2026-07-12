# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "sudachipy>=0.6.8",
#     "sudachidict-core>=20240409",
# ]
# ///
"""outline.py — 文書のスケルトン（見出し・各段落の先頭文・箇条書き）を抽出する。

設計原則「検出は機械、判断はAI」に基づき、良し悪しの判断はせず、決定的な抽出のみを
行う。SKILL.md §4 の構造レビュー（スケルトン通読）への入力として使う。

使い方:
    uv run scripts/outline.py <file.md> [--json]

入力エラー（ファイル不在・ディレクトリ指定・読み取り不可等）は exit code 1、
それ以外は exit code 0（判断は人間/AIに委ねる。他の検査層エントリと同じ方針）。

sudachipy への依存はこのスクリプト自体では使わないが、textcore.py の共有基盤
（他のエントリと共通のマスク処理・ヘルパー）を import するため PEP 723
メタデータは textcore.py と同じ内容を宣言しておく。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from textcore import (
    _BLOCKQUOTE_RE,
    _CODE_FENCE_RE,
    _FRONT_MATTER_DELIM_RE,
    _HEADING_RE,
    _LIST_ITEM_RE,
    _TABLE_DELIMITER_RE,
    _TABLE_ROW_RE,
    _heading_level_and_text,
    mask_html_comments,
    read_source_file,
)

# ---------------------------------------------------------------------------
# --outline（スケルトン抽出）
#
# 設計原則「検出は機械、判断はAI」に基づき、文書の構造（見出し・各段落の先頭文・
# 箇条書きブロック）を決定的に抽出するだけで、良し悪しの判断はしない。
# SKILL.md §4 の構造レビュー（スケルトン通読）への入力として使う。
#
# 見出し・コードブロック・引用・表のマスクには mask_markdown_structure() は使わない
# （見出し行そのものが空文字になってしまい、スケルトンの主役である見出しテキストが
# 消えてしまうため）。かわりに、見出し検出は生テキストに対して直接行い、
# 段落は「空行区切りの行グループ」として独自に走査する。HTMLコメントのみ
# mask_html_comments() で先に空白化し、コメント内の見出し風・箇条書き風の行を
# 誤ってスケルトンに含めないようにする。
# ---------------------------------------------------------------------------


def build_outline(raw_text: str) -> list[dict]:
    """文書のスケルトン（見出し・各段落の先頭文・箇条書きプレースホルダ）を
    行番号付きで抽出する。判断はせず、決定的な抽出のみを行う。

    - 見出し行（#〜######）: kind="heading", level=1-6
    - 空行区切りの段落のうち、箇条書き・コードブロック・引用・表以外: kind="lead"
      （段落先頭行の最初の文、句点等が無ければ先頭行全体）
    - 箇条書きだけの段落: kind="bullets"（「(箇条書き N 項目)」プレースホルダ）
    - コードブロック・引用・表の段落は出力しない（スキップ）

    ブロックの区切りは空行だけではない。箇条書き行の直後に空行なしで通常段落行が
    続く（またはその逆順の）場合も、そこでブロック種別が切り替わるため flush する
    （空行がないからといって同じブロックにまとめてしまうと、後続ブロックの内容が
    丸ごと出力から消えてしまう）。
    """
    text = mask_html_comments(raw_text)
    lines = text.split("\n")

    outline: list[dict] = []
    buffer: list[tuple[int, str]] = []
    in_fence = False
    fence_char = ""
    fence_len = 0
    in_front_matter = False

    def line_kind(line_text: str) -> str:
        """flush_buffer() のブロック種別判定（buffer[0] 基準）と対応する、
        単一行の分類。ブロック種別が切り替わったかどうかの判定に使う。"""
        if _LIST_ITEM_RE.match(line_text):
            return "bullets"
        if _BLOCKQUOTE_RE.match(line_text):
            return "blockquote"
        if (_TABLE_ROW_RE.match(line_text) and line_text.count("|") >= 2) or _TABLE_DELIMITER_RE.match(
            line_text
        ):
            return "table"
        return "lead"

    def flush_buffer() -> None:
        if not buffer:
            return
        first_no, first_line = buffer[0]
        if _LIST_ITEM_RE.match(first_line):
            count = sum(1 for _, line_text in buffer if _LIST_ITEM_RE.match(line_text))
            outline.append(
                {"line": first_no, "kind": "bullets", "level": None, "text": f"(箇条書き {count} 項目)"}
            )
        elif _BLOCKQUOTE_RE.match(first_line):
            pass  # 引用ブロックは段落として扱わずスキップ
        elif (_TABLE_ROW_RE.match(first_line) and first_line.count("|") >= 2) or _TABLE_DELIMITER_RE.match(
            first_line
        ):
            pass  # 表はスキップ
        else:
            m = re.search(r"[。！？]", first_line)
            lead = first_line[: m.end()] if m else first_line
            lead = lead.strip()
            if lead:
                outline.append({"line": first_no, "kind": "lead", "level": None, "text": lead})
        buffer.clear()

    for i, line in enumerate(lines, start=1):
        if i == 1 and _FRONT_MATTER_DELIM_RE.match(line):
            in_front_matter = True
            continue
        if in_front_matter:
            if _FRONT_MATTER_DELIM_RE.match(line):
                in_front_matter = False
            continue

        fence_match = _CODE_FENCE_RE.match(line)
        if fence_match:
            flush_buffer()
            fence_run = fence_match.group(1)
            fc, fl = fence_run[0], len(fence_run)
            is_close_eligible = line[fence_match.end() :].strip() == ""
            if not in_fence:
                in_fence = True
                fence_char, fence_len = fc, fl
            elif fc == fence_char and fl >= fence_len and is_close_eligible:
                in_fence = False
            continue
        if in_fence:
            continue

        if not line.strip():
            flush_buffer()
            continue

        if _HEADING_RE.match(line):
            flush_buffer()
            level, heading_text = _heading_level_and_text(line)
            outline.append({"line": i, "kind": "heading", "level": level, "text": heading_text})
            continue

        # 空行を挟まずにブロック種別（箇条書き/引用/表/通常段落）が切り替わった
        # 場合も、そこで現在のバッファを確定させてから新しいブロックを始める。
        # ただし箇条書きブロックの途中に現れるインデントされた継続行（折り返された
        # 項目の2行目以降。行頭に空白がありマーカーを持たない）は、種別変化とみなさず
        # 同じ箇条書きブロックに含める（マーカー行だけを項目数として数えるので、
        # 継続行が項目数を水増しすることはない）。
        if buffer:
            cur_kind = line_kind(buffer[0][1])
            is_indented_continuation = (
                cur_kind == "bullets"
                and line_kind(line) == "lead"
                and re.match(r"^\s+\S", line) is not None
            )
            if cur_kind != line_kind(line) and not is_indented_continuation:
                flush_buffer()

        buffer.append((i, line))

    flush_buffer()
    return outline


def print_outline_human(path: Path, outline: list[dict]) -> None:
    print(f"=== outline: {path} ===")
    print()
    if not outline:
        print("(スケルトンなし)")
        return
    for entry in outline:
        line_tag = f"L{entry['line']}"
        if entry["kind"] == "heading":
            indent = "  " * max(0, entry["level"] - 1)
            prefix = "#" * entry["level"]
            print(f"{line_tag:>6}  {indent}{prefix} {entry['text']}")
        else:
            print(f"{line_tag:>6}    {entry['text']}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="文書のスケルトン（見出し・各段落の先頭文・箇条書き）を抽出する（CI ゲートではない）。"
    )
    parser.add_argument("file", type=Path, help="対象の Markdown/テキストファイル")
    parser.add_argument("--json", action="store_true", help="機械可読な JSON で出力する")
    args = parser.parse_args()

    # 「文章の中身に関する判断」と「そもそも実行できない入力エラー」は区別する。
    # 前者（抽出結果）は exit 0、後者（ファイル不在/ディレクトリ指定/読み取り不可等）は exit 1。
    text, err = read_source_file(args.file)
    if err is not None:
        print(err, file=sys.stderr)
        return 1

    outline = build_outline(text)
    if args.json:
        print(json.dumps({"outline": outline}, ensure_ascii=False, indent=2))
    else:
        print_outline_human(args.file, outline)
    return 0


if __name__ == "__main__":
    sys.exit(main())

