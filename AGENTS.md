# AGENTS.md

このリポジトリは [`natural-japanese`](./skills/natural-japanese/SKILL.md) という Agent Skill を配布するためのものです。
スキル本体は `skills/natural-japanese/` にあり、`SKILL.md` と `references/`・`scripts/`・`assets/` で構成されます。

## このスキルについて

仕事の日本語文書(調査・分析レポート、議事録、社内ガイド、PR の説明文、技術記事)を、読みやすく自然な日本語で書く・直すためのスキルです。生成AIの書く日本語に増えた、英語をそのまま訳したような言い回しを、生成AI以前の書き手を基準にしたモデルで見つけ、意味を変えずに言い換えます。

役割の分け方は次のとおりです。

- **見つけるのはモデル**: `skills/natural-japanese/scripts/style_check.py` が、生成AI以前の人間の文書で学んだ BERT と、生成AIの文章で学んだ BERT の差で、生成AI時代の言い回しを含む文を示す(モデルは Hugging Face の [coji/ja-ai-style-bert](https://huggingface.co/coji/ja-ai-style-bert)。作り方は [coji/ja-ai-style-corpus](https://github.com/coji/ja-ai-style-corpus))
- **直すかどうかと言い換えは AI**: 変える必要があるかを文脈で決め、意味を変えない言い換えを作る。候補が複数あれば、どれを使うかはモデルに並べさせる
- **直した後は原文と比べる**: 推敲で原文になかった言い回しが増えていないかを `style_check.py compare` で調べる

書くときの決まりは `skills/natural-japanese/references/writing-constitution.md` にあります。

文書タイプ別の型は `skills/natural-japanese/references/doctypes/`、詳しい工程は [`SKILL.md`](./skills/natural-japanese/SKILL.md) を参照してください。

## openskills 経由で読み込む場合

```bash
npx openskills install coji/natural-japanese
npx openskills sync
```

`npx openskills sync` がこの AGENTS.md 配下に `<available_skills>` ブロックを生成し、
Claude Code 以外のエージェント（Cursor, ChatGPT, Codex 等）からもこのスキルを利用できるようにします。

## 検査スクリプトの実行

Python の実行は [uv](https://docs.astral.sh/uv/) を前提にしています。`pip install` や仮想環境の手動作成は不要です。検査スクリプトは役割ごとに分かれています。

```bash
uv run skills/natural-japanese/scripts/style_check.py flag path/to/draft.md   # 生成AI時代の言い回しを含む文(rank / compare もある)
uv run skills/natural-japanese/scripts/lint.py path/to/draft.md      # 疑いの検出（--json / --genre / --baseline）
uv run skills/natural-japanese/scripts/outline.py path/to/draft.md   # スケルトン抽出（構造レビューの入力）
uv run skills/natural-japanese/scripts/terms.py path/to/draft.md     # 専門用語の初出・説明有無の一覧
```

依存関係は各スクリプト冒頭の PEP 723 インラインメタデータで宣言されているため、`uv run` が自動的に解決します。
`style_check.py` は onnxruntime で動き(torch は使いません)、初回に Hugging Face からモデル(約450MB)をダウンロードします。共有基盤は `skills/natural-japanese/scripts/textcore.py` にまとまっています。
