# AGENTS.md

このリポジトリは [`natural-japanese`](./skills/natural-japanese/SKILL.md) という Agent Skill を配布するためのものです。
スキル本体は `skills/natural-japanese/` にあり、`SKILL.md` と `references/`・`scripts/`・`assets/` で構成されます。

## このスキルについて

仕事の日本語文書を、自然で読みやすく書く・直すためのスキルです。議事録・調査レポート・社内ガイド・リサーチメモ・スライド構成といった仕事の文書から、技術記事・PR の説明文・ブログ・エッセイまで扱います。AI らしい書き癖を取り除くことも、この工程に含まれます。

設計の要点は次の3つです。

- 既存の文書を直すとき、元の文書にない事実・数値・意見・方針は足さない。確信の度合いも変えない
- 疑わしい箇所の検出は `skills/natural-japanese/scripts/lint.py`(sudachipy による形態素解析)が機械的に行い、直すかどうかはエージェントが文脈を見て決める。lint の各指摘には直し方が付いている
- 書く前に読み手・主メッセージ・見出しを決め、書くときは SKILL.md §2 の12の原則に沿う

規則と工程はすべて [`SKILL.md`](./skills/natural-japanese/SKILL.md) にあります。`references/` には、文書タイプ別の型(`doctypes/`)、診断モードの算出方法(`diagnose.md`)、lint が使えない環境向けの手順(`manual-checklist.md`)だけを置いています。

## openskills 経由で読み込む場合

```bash
npx openskills install coji/natural-japanese
npx openskills sync
```

`npx openskills sync` がこの AGENTS.md 配下に `<available_skills>` ブロックを生成し、
Claude Code 以外のエージェント（Cursor, ChatGPT, Codex 等）からもこのスキルを利用できるようにします。

## 検査スクリプトの実行

Python の実行は [uv](https://docs.astral.sh/uv/) を前提にしています。`pip install` や仮想環境の手動作成は不要です。検査のスクリプトは役割ごとに3つあります。

```bash
uv run skills/natural-japanese/scripts/lint.py path/to/draft.md      # 疑いの検出（--json / --genre / --baseline）
uv run skills/natural-japanese/scripts/outline.py path/to/draft.md   # 見出しと各段落の先頭文の抽出（構造の点検に使う）
uv run skills/natural-japanese/scripts/terms.py path/to/draft.md     # 専門用語の初出・説明有無の一覧
```

依存関係（sudachipy, sudachidict-core）は各スクリプト冒頭の PEP 723 インラインメタデータで宣言されているため、
`uv run` が自動的に解決します。共有基盤は `skills/natural-japanese/scripts/textcore.py` にまとまっています。
