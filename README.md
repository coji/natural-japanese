# natural-japanese

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)
[![GitHub release](https://img.shields.io/github/v/release/coji/natural-japanese)](https://github.com/coji/natural-japanese/releases)

`natural-japanese` は、仕事の日本語文書を、自然で読みやすく書く・直すための [Agent Skill](https://docs.claude.com/en/docs/claude-code/skills) です。議事録、調査レポート、社内ガイド、技術記事、PR の説明文、ブログ記事などの執筆と推敲に使います。

> **English summary:** An Agent Skill for writing and revising Japanese work documents so they read naturally and clearly. A sudachipy-based linter flags AI-like phrasing and suggests a fix for each finding; the agent decides what to change, and never adds facts, opinions, or certainty that the original did not have.

## このスキルがすること

AI に書かせた文章には、決まった言い回し、どの段落も同じ長さで並ぶ構成、結論を最後まで言わない書き方のような癖が残りがちです。AI に「もっと自然にして」と頼んでも、自分の癖には気づきにくいので、別の決まった言い回しに置き換わるだけになることがよくあります。このスキルは、次の3つでこれに対処します。

- 書く前に、読み手、主メッセージ、見出しを決める
- 書くときに、結論を先に書く、因果は地の文で書く、同じ型を続けない、といった12の原則に沿う
- 書いたあとで、[`lint.py`](./skills/natural-japanese/scripts/lint.py) が形態素解析([sudachipy](https://github.com/WorksApplications/sudachi.rs))で疑わしい箇所を検出する。指摘ごとに直し方が付いていて、直すか残すかはエージェントが文脈を見て決める

### 元にない内容は足さない

既存の文書を直すとき、元の文書にない事実・数値・意見・方針は足しません。確信の度合いも変えません。「次回また相談する」を「合意した」に変えたり、書き手が言っていない経験を書き足したりすると、直した文書は書き手が言っていないことを書き手の言葉として伝えてしまうからです。仕上げに、直した文書を元の文書と並べ、元にない内容が入っていないかを確かめます。

## 直す例

元の文:

> このツールを使用することで、作業効率を大幅に向上させることができると言えるでしょう。

直した文:

> このツールを使うと、作業の効率は大きく上がるはずだ。

「〜することで」「〜することができる」「と言えるでしょう」を外し、言い回しだけを変えています。「と言えるでしょう」の推量は「はずだ」で残し、断定には変えていません。

元の文:

> 田中さんから在庫アラートについて説明があり、現行のしきい値だと誤検知が多いという話になった。佐藤さんはそれに対して在庫回転率を使う案を出し、鈴木さんも賛成した。最終的にどう決まったかは次回また相談することになった。

直した文:

> 在庫アラートのしきい値の決め方は結論が出ず、次回に持ち越した。現行のしきい値では誤検知が多いと田中さんが説明し、佐藤さんが在庫回転率を使う案を出して、鈴木さんも賛成した。

議事録の例です。結論(持ち越し)を先頭に置き、経緯をその後ろに回しています。決まっていないことを「合意した」とは書かず、元にない担当者や期日も足していません。

## インストール

### 1. `npx skills add`（推奨）

```bash
npx skills add coji/natural-japanese
```

Claude Code などのエージェント設定ディレクトリにインストールします。

### 2. `npx openskills install`（Cursor / ChatGPT / Codex など）

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

スキルを入れておくと、文章についての依頼で自動的に呼び出されます。

- 議事録・レポート・社内ガイド・企画書・技術記事・PR の説明文などの作成や推敲
- 「読みやすくして」「自然な日本語にして」「結論から書いて」「AI っぽいのを直して」といった依頼
- AI が書いた下書きの推敲や、AI らしさの診断
- ブログやエッセイの執筆、既存の記事のリライト

lint の指摘を一律に直すのではなく、エージェントが一つずつ直すか残すかを決め、残すときは理由を記録します。

### 診断コマンド

文書を書き換えずに、自然度(0〜100)と理由だけを知りたいときは、診断コマンドを使います。

```
/natural-japanese score path/to/document.md
```

## 検査スクリプトだけを使う

各スクリプトは、スキルを通さずに単体でも実行できます。実行には [uv](https://docs.astral.sh/uv/) が必要です。依存関係はスクリプト自身に書かれていて、`uv run` が実行時に解決します。

```bash
brew install uv
```

```bash
# 疑わしい表現の検出(指摘ごとに直し方が付く)
uv run skills/natural-japanese/scripts/lint.py path/to/draft.md

# ジャンルを指定して誤検出を減らす
uv run skills/natural-japanese/scripts/lint.py path/to/draft.md --genre tech

# 読みにくい箇所(長すぎる文、続きすぎる漢字、二重否定など)の検出
uv run skills/natural-japanese/scripts/lint.py path/to/draft.md --reading-load

# 見出しと各段落の先頭文の抽出
uv run skills/natural-japanese/scripts/outline.py path/to/draft.md

# 専門用語の初出と説明の有無の一覧
uv run skills/natural-japanese/scripts/terms.py path/to/draft.md
```

## リポジトリ構成

```
skills/natural-japanese/            # スキル本体
  SKILL.md                          # 規則と工程のすべて
  references/doctypes/              # 文書タイプ別の型(議事録・レポート・ガイド・メモ・スライド)
  references/diagnose.md            # 診断モードの採点方法
  references/manual-checklist.md    # lint が使えない環境向けの手順
  scripts/                          # 検査スクリプト(lint.py, outline.py, terms.py など)
  assets/                           # テンプレート
```

### 開発者向け

スクリプトや fixture を変更した際は、fixture 回帰チェックを実行してください。

```bash
git config core.hooksPath .githooks
./dev/check-fixtures.sh
```

## 参考にした資料

このスキルの設計にあたり、以下の公開資料やプロジェクトを参考にしています。

- [AI臭さを消した日本語執筆エージェントの設計(なつ「いとおり」)](https://note.com/art_reflection/n/n7ffd5ce3320c):機械による検出と文脈による判断を分ける考え方、濃淡の設計
- [日本語技術文書の文章規範(k16shikano)](https://gist.github.com/k16shikano/fd287c3133457c4fd8f5601d34aa817d):LLM に特有の空虚な言い回しの分類
- [meiseki(bamboo-nova)](https://github.com/bamboo-nova/meiseki):機械検出と LLM による推敲を組み合わせる方法、読みにくさの観点の整理

## ライセンス

MIT. See [LICENSE](./LICENSE).
