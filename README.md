# natural-japanese

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)
[![GitHub release](https://img.shields.io/github/v/release/coji/natural-japanese)](https://github.com/coji/natural-japanese/releases)

AI に書かせた仕事の日本語を、読みやすく直す [Agent Skill](https://docs.claude.com/en/docs/claude-code/skills) です。議事録、レポート、技術記事、PR の説明文などを、新しく書くときにも使えます。

> **English summary:** An Agent Skill that makes AI-written Japanese work documents read naturally. It never adds facts, opinions, or certainty that the original did not have.

## 直すとこうなる

### 何のことか分からない言い回しを、ふだんの言葉に

| 元の文 | 直した文 |
|---|---|
| ジョブが見たいのは「まだ決着していない行」だけ | ジョブが見たいのは、チェックインも取り消しもされていない行だけ |
| リマインドの失敗は握りつぶしていません。 | リマインドの Slack 送信が1件でも失敗すると、同じ回の取り消しが実行されません。 |

AI が書いた技術記事と PR の説明文を「読みやすくして」と直させた実際の出力から、うまく直った例を選んでいます。2行目の元の文は、失敗をきちんと扱っているように読めます。その文書の本文に書いてあったのは、1件の失敗で取り消しまで止まるという不具合でした。

### 元にないことは足さない。確信の度合いも変えない

調査レポートを、同じメモから Claude Opus 5.5 に書かせた例です。メモには、解約が増えた理由について未検証の見立てが2つ書いてありました。

| | 書いた文 |
|---|---|
| スキルなし | 3月に始めたライトの初月無料キャンペーンとの関係が強く疑われますが、まだ確かめられていません。 |
| スキルあり | チームからは、次の二つの見立てが出ている。どちらも未検証である。 |

スキルなしは、2つの見立てに触れながらも、結論ではキャンペーンとの関係を「強く疑われます」と書いています。スキルありは、メモのとおり2つを並べ、どちらも未検証と書いています。

### 太字を重ねない

5種類の文書について、種類ごとに同じ素材を5つのモデルに渡して書かせました。太字は、スキルなしの25本で551か所、スキルありの25本で13か所でした。

## 使い方

Claude Code・Cursor・Codex など、[skills](https://github.com/vercel-labs/skills) が対応するエージェントでは、次のコマンドでインストールできます。

```bash
npx skills add coji/natural-japanese
```

画面の案内に従って、インストールするスキルと利用するエージェントを選んでください。詳しくは [skills CLI の説明](https://github.com/vercel-labs/skills/blob/main/docs/commands.md#skills-add) を参照してください。

あとは、エージェントに「読みやすくして」「議事録にして」「AI っぽいところを直して」のように頼むだけです。書き換えずに自然さの点数(0〜100)と理由だけを知りたいときは、`/natural-japanese score <ファイル>` を使います。

バージョンごとの変更点は [Releases](https://github.com/coji/natural-japanese/releases) にあります。

<details>
<summary>ほかの入れ方(プラグイン・AGENTS.md 経由・手動)</summary>

Cursor プラグインとして入れる場合:

Cursor Marketplace での公開は審査待ちです。公開後は Marketplace で `natural-japanese` を探してインストールできます。公開前にローカルで試す場合は、リポジトリのルートで次を実行します。

```bash
rm -rf ~/.cursor/plugins/local/natural-japanese
mkdir -p ~/.cursor/plugins/local/natural-japanese
cp plugin.json ~/.cursor/plugins/local/natural-japanese/
cp -R skills ~/.cursor/plugins/local/natural-japanese/
```

そのあと Cursor を再起動するか、`Developer: Reload Window` を実行してください。Customize を開くと、`natural-japanese` が Skills に表示されます。

`AGENTS.md` を経由してスキルを読み込ませる場合は、[OpenSkills](https://github.com/numman-ali/openskills) も使えます。

```bash
npx openskills install coji/natural-japanese
npx openskills sync
```

Claude Code プラグイン:

```
/plugin marketplace add coji/natural-japanese
/plugin install natural-japanese@natural-japanese
```

手動で入れる場合は、[Releases](https://github.com/coji/natural-japanese/releases) から `natural-japanese.skill` をダウンロードし、エージェントのスキルディレクトリに展開してください。

</details>

## 直すときに守ること

元の文書にない事実・数値・意見・方針は足しません。確信の度合いも変えません。「次回また相談する」を「合意した」にすると、書き手が言っていないことを書き手の言葉として伝えてしまうからです。直したあとは元の文書と並べて、足した内容がないかを確かめます。

## 苦手なこと

- 英語の言い方を1語ずつ訳した熟語や、動作を名詞にまとめた言い回しは、半分ほど見逃します。書いたモデルにも直すモデルにも、自然に見えるためです
- effort(モデルが推論にかける量の設定)を下げると、手順の一部を省いて見逃しが増えます。選べる環境では high を使ってください

## 決裁者の目で見て直す(critical-thinking)

同じリポジトリに、文書の「考え」を決裁者の目で検査して直すスキル `critical-thinking` が入っています。natural-japanese が日本語を直すのに対し、こちらは中身を見ます。対象は稟議書、提案資料、企画書、報告書のような、読んだ人に何かを決めてもらう文書です。評価は、欠陥を仕込んだ架空の稟議書・障害報告書・コンサルの提案資料・社内の制度企画で行っています。

```
/critical-thinking 稟議書.md    # 全工程。検査して3つまで聞き、直した文書と、端的にした版・組み直した版を作る。full と同じ
```

入口はこの1つです。文書の中で答えが出ること(矛盾、計算、言い切りの強さ、並びのねじれ)は聞かずに直し、書き手にしか答えられないこと(文書にない事実、決めてもらうことの読み、頼む範囲)だけを3つまで聞いて、答えを本文に入れます。「分からない」と答えた問いは本文を仮定の形にし、残りの問いと合わせて文書とは別のファイル `稟議書.確認事項.md` に出します。直した文書には印も確認事項の節も入らないので、そのまま出せます。書き手の代わりに決めず、本編を元より長くしません。

<details>
<summary>工程を分けて使う(上級)</summary>

```
/critical-thinking logic 稟議書.md      # 文書の中で筋が通っているか。矛盾・根拠のない主張・事実と推論の混在・並列のねじれ
/critical-thinking somosomo 稟議書.md   # そもそも前提は合っているか。他の選択肢・覆る条件・誰のための何か
/critical-thinking fix 稟議書.md        # 検査の指摘を反映して直す
/critical-thinking short 稟議書.md      # もっと端的に。detail なら、もっと丁寧に
/critical-thinking rebuild 稟議書.md    # 構成から組み直す。構成案を出して選んでもらう
```

どちらも文書には一文字も書き込まず、行番号つきの問いと `<ファイル>.logic.yaml` を返します。直すかどうかは書き手が決めます。検査は LLM の読みに頼るため、同じ文書を2回かけると指摘は揺れます。

「もっと端的に」「もっと丁寧に」と頼むと、検査で書き出した論理構造(主結論、論点、論拠、根拠の重み)をどの深さまで本文にするかを決めて書き直します。端的は、主張と決裁に要る根拠だけを本編に残し、裏づけは付録に移します。事実と数値は落とさず、矛盾も直さず、主結論と決裁事項は変えません。AI の書いた 3,000〜4,700 字の文書で、本編は 35〜46% になりました。検査のあとで「指摘を反映して直して」と頼むと、答えられる問いは本文で直し、答えられない問いは別ファイルの確認事項に回します。「構成から組み直して」と頼むと、事実と頼む中身は保ったまま論の背骨だけを替え、構成案を2〜3つ出して書き手に選んでもらってから書きます。案のうち1つは必ず「頼む中身を小さくする案」で、検査の問いが決裁事項の前提を疑っているとき、どの問いの答えで元の頼みが倒れるかを示したうえで、縮める・分ける・先に確かめる・取り下げるのどれかを置きます。この案は書き手にしか選べないので、スキルは勝手に選びません。AI に下書きを任せた人は構成を自分の頭に持っていないことが多いので、別の組み立てを見せるのはこの工程の仕事です。

</details>

## 仕組み

疑わしい箇所は [`lint.py`](./skills/natural-japanese/scripts/lint.py) が形態素解析([sudachipy](https://github.com/WorksApplications/sudachi.rs))で検出し、直すかどうかはエージェントが文脈を見て決めます。AI は自分の書き癖に気づきにくいので、検出を機械に任せています。規則と手順はすべて [`SKILL.md`](./skills/natural-japanese/SKILL.md) にあります。

<details>
<summary>検査スクリプトを単体で使う</summary>

[uv](https://docs.astral.sh/uv/) があれば、スキルを通さずに実行できます。

```bash
uv run skills/natural-japanese/scripts/lint.py draft.md                  # 疑わしい表現と直し方
uv run skills/natural-japanese/scripts/lint.py draft.md --genre tech     # 技術文書向けの基準で
uv run skills/natural-japanese/scripts/lint.py draft.md --reading-load   # 長すぎる文、続きすぎる漢字など
uv run skills/natural-japanese/scripts/outline.py draft.md               # 見出しと各段落の先頭文
uv run skills/natural-japanese/scripts/terms.py draft.md                 # 専門用語の初出と説明の有無
uv run skills/natural-japanese/scripts/paragraphs.py draft.md            # 段落ごとの確認用の一覧
uv run skills/natural-japanese/scripts/calques.py draft.md               # 仕組みを場所にたとえた名詞と、機械の処理に当てた動詞の候補
uv run skills/natural-japanese/scripts/newfacts.py original.md revised.md  # 直した文書にだけある数値・固有名詞
```

スクリプトを変えたときは、`./dev/check-fixtures.sh` で回帰テストを実行してください(`git config core.hooksPath .githooks` を設定すると、コミット時にも実行されます)。

</details>

## 参考にした資料

- [AI臭さを消した日本語執筆エージェントの設計(なつ「いとおり」)](https://note.com/art_reflection/n/n7ffd5ce3320c):機械による検出と文脈による判断を分ける考え方
- [日本語技術文書の文章規範(k16shikano)](https://gist.github.com/k16shikano/fd287c3133457c4fd8f5601d34aa817d):LLM に特有の空虚な言い回しの分類
- [meiseki(bamboo-nova)](https://github.com/bamboo-nova/meiseki):機械検出と LLM による推敲の組み合わせ方

## ライセンス

MIT ライセンスです。詳しくは [LICENSE](./LICENSE) を見てください。
