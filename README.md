# natural-japanese

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)
[![GitHub release](https://img.shields.io/github/v/release/coji/natural-japanese)](https://github.com/coji/natural-japanese/releases)

仕事の日本語を、読みやすくわかりやすく書く・直すための [Agent Skill](https://docs.claude.com/en/docs/claude-code/skills) です。議事録・調査レポート・社内ガイド・リサーチメモ・スライド構成といった仕事の文書から、note・ブログ・エッセイまで。AIと文書を作るとき毎回プロンプトに書いている指示——結論から書いて、論旨を明確に、見出しは端的に、専門用語は文中で説明して——を、書く前の設計・書くときの制約・書いた後の検査の全工程に組み込みます。AI臭さ（AIっぽい／機械翻訳っぽい）の除去は工程の一部です。

> An Agent Skill for writing clear, readable Japanese work documents — designing the argument before writing, constraining generation with a 12-article style constitution, then mechanically detecting "AI-smelling" patterns via sudachipy morphological analysis and iterating until the text converges.

## 設計思想

軸は二つあります。

第一に「検出は機械、判断は人間（またはAI）」。AI は自分自身の AI 臭さを認識しにくい、という前提に立ち、修正の前にまず `scripts/lint.py` が形態素解析（[sudachipy](https://github.com/WorksApplications/sudachi.rs)）で決定的に検出します。何をどう直すかはエージェント（あなた）の判断に委ねます。

- 禁止語・紋切り型フレーズの検出（`references/forbidden-patterns.md`）
- 文リズムの単調さ、段落構造の均質さの検出
- 英語統語の直訳調（無生物主語+他動詞、連体修飾の入れ子など）の検出

第二に「事後修正より生成時制約」。書いた後にAI臭を消すより、書く前の設計（読者・主メッセージ・見出しスケルトン）と書くときの制約（`references/writing-constitution.md` の文体憲法12箇条）で発生自体を防ぐほうが効きます。文書タイプ別の型——議事録・調査レポート・社内ガイド・リサーチメモ/ディスカッションペーパー・スライド構成——は `references/doctypes/` にまとめてあります。

一方で、語順・読点の位置・一文一義・主語述語の距離といった「そもそも読みにくい」領域は、コーパス検証の結果、機械的な閾値化ができない判断領域だと判明しています（`corpus/reports/readability-sweep.md`）。この領域は検出器を増やすのではなく、`references/readability-principles.md`（ジャンル横断の一般原則）と `references/readability-antipatterns.md`（悪文パターンカタログ）を参照しながら、AI自身が周回ごとに目視でレビューする設計にしています。ジャンル（tech/business/essay/公用文）ごとの判断の重みづけの違いは `references/genre-notes.md` にまとめてあります。

## 前提条件

Python スクリプトの実行には [uv](https://docs.astral.sh/uv/) が必要です。

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
# または
brew install uv
```

`pip install` や venv の手動セットアップは不要です。依存関係（sudachipy, sudachidict-core）は
検査層の3エントリスクリプト（`scripts/lint.py` / `scripts/outline.py` / `scripts/terms.py`）
それぞれの冒頭にある PEP 723 インラインメタデータで宣言されており、`uv run` が実行時に自動解決します
（共有基盤の `scripts/textcore.py` はエントリポイントではないため、このメタデータを持ちません）。

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

- 議事録の作成（文字起こしからの議事録化を含む）、調査レポート・分析レポート、社内ガイド・マニュアル、リサーチメモ・ディスカッションペーパー・企画書、スライド構成案といった仕事の文書の作成・校正（ビジネス文書なら `--genre business` を使う）
- 「結論から書いて」「論旨を明確に」「見出しを端的に」「専門用語をわかりやすく説明して」といった指示
- 「AIっぽい」「AI臭い」「機械翻訳っぽい」「不自然」といった指摘への修正
- 「読みにくい」「何が言いたいか分からない」「一文が長い」「読点の位置がおかしい」といった読みやすさの改善依頼
- 新規記事の執筆・下書き（note・ブログ・エッセイ）、既存文章のリライト・推敲
- 文体プロファイル（`style-profile.md`）のセットアップ

フローは一回検出して終わりではありません。lint の指摘を「直した / 理由を付けて残す」に仕分けし、修正が新しい指摘を生まなくなるまで**収束するまでループ**します。周回ごとの差分は lint の `--baseline` オプションで機械的に追跡できます（解消・新規・継続の分類）。作業中の中間ファイルは完了時にすべて削除され、残るのは完成した文書だけです。

詳しいフローは [`SKILL.md`](./SKILL.md) を参照してください。

## 検査スクリプト単体の使い方

スキル経由ではなく、検査層の3スクリプトだけを直接使うこともできます。役割ごとに分かれています
（共有基盤 `scripts/textcore.py` は3スクリプトが内部で使うのみで、直接実行するものではありません）。

### `lint.py` — 疑いの検出

```bash
uv run scripts/lint.py path/to/draft.md
uv run scripts/lint.py path/to/draft.md --json
```

CI ゲートではなく lint であるため、検出件数に関わらず exit code は `0` です。検出結果をどう直すかは
書き手（またはAI）の判断に委ねます。ファイル不在・ディレクトリ指定・読み取り不可などの入力エラーのときだけ exit code `1` になります。

### `outline.py` / `terms.py` — 判断ではなく素材の抽出

findings の代わりに構造・用語の「素材」だけを機械的に抽出するスクリプトもあります（どちらも判断はせず抽出のみ。exit code の方針は `lint.py` と同じ）。

```bash
uv run scripts/outline.py path/to/draft.md   # 見出し・各段落の先頭文・箇条書きプレースホルダを行番号付きで抽出
uv run scripts/terms.py path/to/draft.md     # カタカナ複合語/ASCII略語/固有名詞らしき語を初出順に抽出（説明マーカーの有無つき）
```

## リポジトリ構成

```
SKILL.md              # スキル本体（single source of truth）
references/           # 文体憲法・禁止パターン・チェックリスト・翻訳調ガイド・読みやすさ原則/悪文カタログ/ジャンル差分など
references/doctypes/  # 文書タイプ別の型（議事録・調査レポート・社内ガイド・メモ/DP・スライド）
scripts/               # textcore.py（共有基盤）/ lint.py・outline.py・terms.py（検査層エントリ）/ calibrate.py / fixtures
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

`scripts/lint.py` / `scripts/textcore.py` や `scripts/fixtures/` を変更した場合は `./scripts/check-fixtures.sh` で
期待検出件数（fixture 回帰）を確認してください。同条件で変更が staged されていれば pre-commit hook が
自動実行し、リリース時は `.github/workflows/release.yml` でも実行されます。

## 参考にした資料

このスキルの設計は、次の2つの公開資料に大きく影響を受けています。感謝します。

- [AI臭さを消した日本語執筆エージェントの設計（なつ「いとおり」）](https://note.com/art_reflection/n/n7ffd5ce3320c) — 「AIは自分のAI臭さを認識できない → 機械検出で突きつけ、判断だけを委ねる」という本スキルの核となる考え方、濃淡設計（旧称: 揺らぎ設計）、自己点検ループの元になった記事
- [日本語技術文書の文章規範（k16shikano）](https://gist.github.com/k16shikano/fd287c3133457c4fd8f5601d34aa817d) — 禁止語カタログのうち「LLMっぽい空句」のカテゴリ群（正面から系・空虚な形容・空虚な動詞）の出典

## ライセンス

MIT. See [LICENSE](./LICENSE).
