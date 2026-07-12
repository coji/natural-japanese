# AGENTS.md

このリポジトリは [`natural-japanese`](./SKILL.md) という Agent Skill を配布するためのものです。
`SKILL.md` が本体で、`references/`・`scripts/`・`assets/` を伴います。

## このスキルについて

AI臭い（AIっぽい/機械翻訳っぽい）日本語文章を除去し、自然な日本語で書く・直すためのスキルです。
note記事・ブログ・エッセイ・技術ドキュメントなど文種を問わず使います。

- 検出は機械的・決定的に（`scripts/lint.py`、sudachipy による形態素解析）
- 検出結果をどう直すかはAIの判断に委ねる
- 詳しい設計・使い方は [`SKILL.md`](./SKILL.md) を参照してください

## openskills 経由で読み込む場合

```bash
npx openskills install coji/natural-japanese
npx openskills sync
```

`npx openskills sync` がこの AGENTS.md 配下に `<available_skills>` ブロックを生成し、
Claude Code 以外のエージェント（Cursor, Windsurf, Aider, Codex 等）からもこのスキルを利用できるようにします。

## lint スクリプトの実行

Python の実行は [uv](https://docs.astral.sh/uv/) を前提にしています。`pip install` や仮想環境の手動作成は不要です。

```bash
uv run scripts/lint.py path/to/draft.md
```

依存関係（sudachipy, sudachidict-core）は PEP 723 のインラインメタデータで宣言されているため、
`uv run` が自動的に解決します。
