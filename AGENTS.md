# AGENTS.md

このリポジトリは [`natural-japanese`](./SKILL.md) という Agent Skill を配布するためのものです。
`SKILL.md` が本体で、`references/`・`scripts/`・`assets/` を伴います。

## このスキルについて

仕事の日本語文書を読みやすくわかりやすく書く・直すためのスキルです。議事録・調査レポート・社内ガイド・リサーチメモ・スライド構成といったビジネス文書から、note・ブログ・エッセイまで扱います。AI臭さの除去は、このスキルの一工程として組み込まれています。

設計は二軸です。

- **検出は機械、判断はAI**: 疑いの検出は `scripts/lint.py`（sudachipy による形態素解析）が決定的に行い、どう直すかはAIが文脈で判断する
- **事後修正より生成時制約**: 書いた後にAI臭を消すより、書く前の設計（読者・主メッセージ・見出しスケルトン）と書くときの制約（`references/writing-constitution.md` の文体憲法12箇条）で発生自体を防ぐ

文書タイプ別の型は `references/doctypes/`、詳しい工程は [`SKILL.md`](./SKILL.md) を参照してください。

## openskills 経由で読み込む場合

```bash
npx openskills install coji/natural-japanese
npx openskills sync
```

`npx openskills sync` がこの AGENTS.md 配下に `<available_skills>` ブロックを生成し、
Claude Code 以外のエージェント（Cursor, Windsurf, Aider, Codex 等）からもこのスキルを利用できるようにします。

## 検査スクリプトの実行

Python の実行は [uv](https://docs.astral.sh/uv/) を前提にしています。`pip install` や仮想環境の手動作成は不要です。機械検査層は役割ごとに3つのエントリに分かれています。

```bash
uv run scripts/lint.py path/to/draft.md      # 疑いの検出（--json / --genre / --baseline）
uv run scripts/outline.py path/to/draft.md   # スケルトン抽出（構造レビューの入力）
uv run scripts/terms.py path/to/draft.md     # 専門用語の初出・説明有無の一覧
```

依存関係（sudachipy, sudachidict-core）は各スクリプト冒頭の PEP 723 インラインメタデータで宣言されているため、
`uv run` が自動的に解決します。共有基盤は `scripts/textcore.py` にまとまっています。
