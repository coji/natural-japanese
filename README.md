# natural-japanese

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)
[![GitHub release](https://img.shields.io/github/v/release/coji/natural-japanese)](https://github.com/coji/natural-japanese/releases)

仕事でAIに文章を書かせると、どこか独特の「匂い」が残ります。

見出しは中身を言わず、どの段落も同じような長さで均等に並び、当たり障りのない結論で安全にまとめられる。あとから手作業で直そうとしても、骨組み全体に手癖が染み込んでいて、結局ゼロから書き直したほうが早いと感じることも少なくありません。

`natural-japanese` は、仕事の日本語を読みやすく書く・直すための [Agent Skill](https://docs.claude.com/en/docs/claude-code/skills) です。議事録・調査レポート・社内ガイド・企画書・ブログ記事などを対象に、論旨がすっきり通る自然な文章への執筆や推敲を支援します。

> **English summary:** An Agent Skill for writing clear, readable Japanese work documents. It prevents "AI-smelling" patterns using a style constitution and mechanically detects issues with sudachipy-based linting.

## 設計の考え方

書き上がった文章からAI臭を抜くのは、料理のあとから塩を抜くような難しさがあります。AI自身に「もっと自然にして」と頼んでも、自分の手癖を認識できないため、別の定型句に置き換わるだけになりがちです。

そのため、このスキルでは設計を根本から分けています。

### あとから直すより、書く前に防ぐ

書く前に見出しの骨組み（スケルトン）を固め、12箇条の文体憲法を制約として適用します。「結論から書く」「同じ型を繰り返さない」といったルールで縛り、最初から歪みの少ない文章を出力させます。

### 検出は機械、判断は人間（またはエージェント）

それでも混ざる手癖は、形態素解析（[sudachipy](https://github.com/WorksApplications/sudachi.rs)）を使ったスクリプト [`lint.py`](./skills/natural-japanese/scripts/lint.py) で機械的に洗い出します。紋切り型のフレーズ、単調な文リズム、英語の直訳調をルールベースで突きつけます。

ただし、指摘を機械的に全置換すると文章のニュアンスが失われます。何を直し、文脈上あえて何を残すかは人間やエージェント自身が判断します。

なお、語順や読点の位置といった「そもそも読みにくい」領域は、機械的な判定が難しいことがコーパス検証（180本超の比較分析）で分かっています。こうした箇所はルールカタログに基づく目視レビューや、補助的な読解負荷チェック（`--reading-load`）を組み合わせて丁寧に推敲します。

## 変換の例

**Before**
> リモートワークの普及は、働き方に大きな変化をもたらした。重要なのは、通勤時間の削減による生活の質の向上だ。また、オフィスコストの削減という企業側のメリットも見逃せない。このように、リモートワークは労働者と企業の双方にとって恩恵のある働き方だと言えるだろう。

**After**
> リモートワークが広まってから、通勤で潰れていた1時間が自分の時間に戻ってきた人は多いはずだ。企業側もオフィスの家賃を削れる。誰も損をしていないように見える働き方だが、実際にそう言い切れるのかは、もう少し先まで見ないと分からない。

`重要なのは` `このように` `と言えるだろう` といった手癖の定型句を外し、結論を急いで押し付ける構えを、実感と留保のある表現に変えています。その他の例は [`examples.md`](./skills/natural-japanese/references/examples.md) を参照してください。

## インストール

### 1. `npx skills add`（推奨）

```bash
npx skills add coji/natural-japanese
```

Claude Code などのエージェント設定ディレクトリにインストールします。

### 2. `npx openskills install`（Cursor / Windsurf / Codex など）

```bash
npx openskills install coji/natural-japanese
npx openskills sync
```

`AGENTS.md` を経由して各エージェントから利用できるようになります。

### 3. Claude Code プラグイン

```
/plugin marketplace add coji/natural-japanese
/plugin install natural-japanese@natural-japanese
```

### 4. 手動配置

[Releases](https://github.com/coji/natural-japanese/releases) から `natural-japanese.skill` をダウンロードし、エージェントのスキルディレクトリに展開して配置してください。

## 使い方

スキルを導入すると、エージェントへの日常的な依頼の中で自動的に呼び出されます。

- 議事録・レポート・社内ガイド・企画書などの作成や校正
- 「読みやすくして」「結論から書いて」「不自然な表現を直して」といった指示
- AIが書いた下書きの推敲や、AI臭さの診断（スコア測定）
- ブログやエッセイの下書き作成、既存記事のリライト

指摘を一括置換するのではなく、エージェントが指摘を仕分けし、さらに「6軸推敲ルーブリック（脱AI臭・情報密度・体温など）」で合格基準に達するまで自律的に推敲ループを回します。

### 診断コマンド

文書を書き換えずに自然度（0〜100）を測定したい場合は、診断コマンドを実行できます。

```
/natural-japanese score path/to/document.md
```

## 検査スクリプト単体での利用

各スクリプトはスキルを介さず単体でも実行できます。実行には [uv](https://docs.astral.sh/uv/) が必要です。依存関係はスクリプト自身に記述されており、`uv run` が実行時に自動で解決します。

```bash
brew install uv
```

```bash
# 疑いのある表現の検出
uv run skills/natural-japanese/scripts/lint.py path/to/draft.md

# ジャンル指定（誤検知の抑制）
uv run skills/natural-japanese/scripts/lint.py path/to/draft.md --genre tech

# 読解負荷（一文の長さや読点の偏りなど）のチェック
uv run skills/natural-japanese/scripts/lint.py path/to/draft.md --reading-load

# 構成（見出し・段落先頭文）の抽出
uv run skills/natural-japanese/scripts/outline.py path/to/draft.md

# 専門用語と初出説明の確認
uv run skills/natural-japanese/scripts/terms.py path/to/draft.md
```

## リポジトリ構成

```
skills/natural-japanese/            # スキル本体
  SKILL.md                          # スキル定義
  references/                       # 文体憲法・禁止パターン・6軸ルーブリックなど
  references/doctypes/              # 文書タイプ別の型（議事録・レポート・ガイドなど）
  scripts/                          # 検査スクリプト（lint.py, outline.py, terms.py など）
  assets/                           # テンプレート
```

### 開発者向け

スクリプトや fixture を変更した際は、fixture 回帰チェックを実行してください。

```bash
git config core.hooksPath .githooks
./dev/check-fixtures.sh
```

## 参考にした資料

このスキルの設計にあたり、以下の公開資料やプロジェクトを参考にしています。感謝します。

- [AI臭さを消した日本語執筆エージェントの設計（なつ「いとおり」）](https://note.com/art_reflection/n/n7ffd5ce3320c) — 機械検出と文脈判断の分離、濃淡設計、自己点検ループの着想元
- [日本語技術文書の文章規範（k16shikano）](https://gist.github.com/k16shikano/fd287c3133457c4fd8f5601d34aa817d) — LLM特有の空虚な言い回し（空句）の分類基準
- [meiseki（bamboo-nova）](https://github.com/bamboo-nova/meiseki) — 機械検出とLLM推敲を組み合わせるアプローチや、読解負荷の観点整理

## クレジット

本 README の執筆・推敲: Cursor Agent (Gemini 3.8 Flash High)

## ライセンス

MIT. See [LICENSE](./LICENSE).
