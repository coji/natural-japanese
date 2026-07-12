# natural-japanese

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)
[![GitHub release](https://img.shields.io/github/v/release/coji/natural-japanese)](https://github.com/coji/natural-japanese/releases)

AI臭い（AIっぽい／機械翻訳っぽい）日本語文章を除去し、自然な日本語で書く・直すための [Agent Skill](https://docs.claude.com/en/docs/claude-code/skills) です。note・ブログ・エッセイ・技術文書など文種を問わず使えます。

> An Agent Skill that mechanically detects and removes "AI-smelling" Japanese text via sudachipy morphological analysis, then iterates until the text converges to natural Japanese.

## 設計思想

AI は自分自身の AI 臭さを認識しにくい、という前提に立ちます。だから修正の前に、まず `scripts/ai-smell-lint.py` が形態素解析（[sudachipy](https://github.com/WorksApplications/sudachi.rs)）で決定的に検出します。何をどう直すかはエージェント（あなた）の判断に委ねます。「検出は機械、判断は人間（またはAI）」という役割分担が軸です。

- 禁止語・紋切り型フレーズの検出（`references/forbidden-patterns.md`）
- 文リズムの単調さ、段落構造の均質さの検出
- 英語統語の直訳調（無生物主語+他動詞、連体修飾の入れ子など）の検出

## 前提条件

Python スクリプトの実行には [uv](https://docs.astral.sh/uv/) が必要です。

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
# または
brew install uv
```

`pip install` や venv の手動セットアップは不要です。依存関係（sudachipy, sudachidict-core）は
`scripts/ai-smell-lint.py` 冒頭の PEP 723 インラインメタデータで宣言されており、`uv run` が実行時に自動解決します。

## インストール

このスキルは4つのチャネルで配布しています。

### 1. `npx skills add`（推奨・シンプル）

```bash
npx skills add coji/natural-japanese
```

リポジトリ直下の `SKILL.md` を読み取り、`.claude/skills/` などエージェントの設定ディレクトリにインストールします。

### 2. `npx openskills install`（Claude Code 以外のエージェントでも使う場合）

```bash
npx openskills install coji/natural-japanese
npx openskills sync
```

`AGENTS.md` を経由して Cursor / Windsurf / Aider / Codex など、AGENTS.md を読めるあらゆるエージェントから利用できます。

### 3. Claude Code plugin marketplace

```
/plugin marketplace add coji/natural-japanese
/plugin install natural-japanese@natural-japanese
```

`.claude-plugin/marketplace.json` と `.claude-plugin/plugin.json` を使い、`skills/natural-japanese/` をプラグインとして配布します。

### 4. GitHub Releases の `.skill`(zip)をダウンロード

[Releases](https://github.com/coji/natural-japanese/releases) から `natural-japanese.skill` をダウンロードして展開し、任意のエージェントのスキルディレクトリに配置してください。タグ `v*` を push すると GitHub Actions（`.github/workflows/release.yml`）が自動でビルド・添付します。

## 使い方

スキルをインストールした状態で、以下のような場面で自動的に発動します。

- 「AIっぽい」「AI臭い」「機械翻訳っぽい」「不自然」といった指摘への修正
- 新規記事の執筆・下書き
- 既存文章のリライト・推敲
- 文体プロファイル（`style-profile.md`）のセットアップ

フローは一回検出して終わりではありません。lint の指摘を「直した / 理由を付けて残す」に仕分けし、修正が新しい指摘を生まなくなるまで**収束するまでループ**します。周回ごとの差分は lint の `--baseline` オプションで機械的に追跡できます（解消・新規・継続の分類）。作業中の中間ファイルは完了時にすべて削除され、残るのは完成した文書だけです。

詳しいフローは [`SKILL.md`](./SKILL.md) を参照してください。

## lint 単体の使い方

スキル経由ではなく、lint スクリプトだけを直接使うこともできます。

```bash
uv run scripts/ai-smell-lint.py path/to/draft.md
uv run scripts/ai-smell-lint.py path/to/draft.md --json
```

CI ゲートではなく lint であるため、検出件数に関わらず exit code は `0` です。検出結果をどう直すかは
書き手（またはAI）の判断に委ねます。ファイル不在・ディレクトリ指定・読み取り不可などの入力エラーのときだけ exit code `1` になります。

## リポジトリ構成

```
SKILL.md              # スキル本体（single source of truth）
references/           # 禁止パターン・チェックリスト・翻訳調ガイドなど
scripts/               # ai-smell-lint.py と fixtures
assets/                # style-profile テンプレート
skills/natural-japanese/  # プラグイン配布用コピー（自動生成。手で編集しない）
.claude-plugin/        # Claude Code plugin manifest / marketplace 定義
.githooks/pre-commit   # ルート→skills/ の自動同期フック
```

`skills/natural-japanese/` は `SKILL.md` / `references/` / `scripts/` / `assets/` のコピーです。
**ルートが正**であり、`skills/` 配下は編集しないでください。pre-commit hook が自動的に同期します。

### 開発者向け: pre-commit hook の有効化

```bash
git config core.hooksPath .githooks
```

これでコミット時に `scripts/sync-skill.sh` が実行され、ルートの変更が `skills/natural-japanese/` に
アトミックに反映されたうえで `git add` されます。手動で同期したい場合は直接実行してください。

```bash
./scripts/sync-skill.sh
```

## 参考にした資料

このスキルの設計は、次の2つの公開資料に大きく影響を受けています。感謝します。

- [AI臭さを消した日本語執筆エージェントの設計（なつ「いとおり」）](https://note.com/art_reflection/n/n7ffd5ce3320c) — 「AIは自分のAI臭さを認識できない → 機械検出で突きつけ、判断だけを委ねる」という本スキルの核となる考え方、揺らぎ設計、自己点検ループの元になった記事
- [日本語技術文書の文章規範（k16shikano）](https://gist.github.com/k16shikano/fd287c3133457c4fd8f5601d34aa817d) — 禁止語カタログのうち「LLMっぽい空句」のカテゴリ群（正面から系・空虚な形容・空虚な動詞）の出典

## ライセンス

MIT. See [LICENSE](./LICENSE).
