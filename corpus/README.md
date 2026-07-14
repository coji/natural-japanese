# corpus/ — 検出器の閾値校正用コーパス

## 目的

`scripts/lint.py` の各検出器(禁止語・統語パターン・統計指標など)は、
現状「経験則」で閾値を決めている。このコーパスは、その閾値を実測に基づいて
校正するために存在する。具体的には:

- 人間が書いた自然な日本語文章(人間コーパス)に対する誤検知率(FP率)を測る
- AI(Claude / GPT系)が「素の状態」(AI臭除去の指示なしで)書いた文章
  (AIコーパス)に対する検出率を測る
- 「人間側 FP率 5% 未満を保ちつつ AI 側検出率最大」となる閾値を
  `scripts/calibrate.py` で探索する

このコーパス自体は成果物ではなく、lint の品質を裏付けるための実験基盤。

## 構成

```
corpus/
├── README.md            このファイル
├── sources.json          人間コーパス(web/aozora)のソース定義
├── fetch.py               sources.json の type=web を取得して corpus/human/web/ に保存
├── generate.py            AI コーパスを claude/codex CLI 経由で生成し corpus/ai/ に保存
├── generate-all.sh        全モデル × 全ジャンルを一括生成するランナー(generate.py のループ)
├── human/
│   ├── aozora/             青空文庫の随筆(パブリックドメイン、コミット対象)
│   └── web/                note/Zenn/官公庁 等の記事本文(著作権あり、非コミット、.gitkeep のみ)
├── ai/                     AI生成記事(非コミット、.gitkeep のみ。再生成可能なため)
├── experiments/            検出器候補の使い捨て検証スクリプト・生データ(非コミット、一部例外あり)
└── reports/                calibrate.py 等の出力レポート(下記「reports の構成」参照)
```

## ライセンス方針

| 区分 | 方針 | 理由 |
| --- | --- | --- |
| `corpus/human/aozora/` | **コミット可** | 青空文庫はパブリックドメイン作品(著作権保護期間満了)のみを収録。各ファイル冒頭に出典コメントを明記している。 |
| `corpus/human/web/` | **非コミット**(`.gitignore` 対象) | note/Zenn/官公庁サイト等の著作権のある記事本文をそのまま複製することになるため、評価目的であってもリポジトリに含めない。`corpus/sources.json` に URL のみを記録し、`fetch.py` で各自ローカルに取得する運用とする。 |
| `corpus/ai/` | **非コミット**(`.gitignore` 対象) | `generate.py` / `generate-all.sh` で再生成可能であり、生成コスト(API呼び出し)をリポジトリサイズに持ち込む必要がないため。 |

`.gitkeep` はディレクトリ構成を保つためにコミットする(`.gitignore` の例外)。

各ソースエントリ(`sources.json`)には `register`(文体レジスタ)フィールドを付与している。
青空文庫(`aozora`)は文体レジスタが古い(文語寄り)ものが多いため、1本ずつ実際に本文を読んで判定し、
現代の口語文法・語彙に近いものは `register: "modern-colloquial-classic"`、旧仮名遣いや文語特有の助動詞
(「〜たり」「〜けり」「〜べし」等)が目立つものは従来どおり `register: "literary-classic"` とした
(判定根拠は各エントリの `notes` に追記済み)。web エントリは全て `register: "modern"`。

さらに web エントリには `quality` フィールド(`"high"` / `"ordinary"`)を付与している。これも文字数などの
機械的指標ではなく、1本ずつ本文を読んで「文章としての完成度」(リズム・冗長性のなさ・読む際の負荷の低さ)
を主観評価したもの。

**閾値校正(FP基準)の使い分け**: 検出器の人間側 FP 率は、`quality: "high"` の web エントリと
`register: "modern-colloquial-classic"` の aozora エントリ(＝上手な書き手による現代文)のみを基準集合とする。
`quality: "ordinary"` の web エントリや `register: "literary-classic"` の aozora エントリは参考ビンとして
保持するが、閾値算出には使わない。下手な(粗い)人間の文章に lint が反応すること自体は、必ずしも
「誤検知」とは言い切れない — 検出器が捉えている冗長さ・紋切り型表現は、実際に文章の質の低さの一因でも
あるため、閾値校正の基準には含めない方針とする。

**公開時期による除外(AI混入リスク)**: web エントリには `published`(YYYY-MM、記事本文中の公開日表記から
確認)を付与している。2023年以降に公開された記事は、生成AIによる執筆・校正支援が混入している可能性を
完全には排除できないため `ai_era_risk: true` を付与する。除外はしない(参考ビンとして残す)が、
**人間側正例は原則として2022年以前(`ai_era_risk` の付いていない)記事を優先する**方針とする。
理想的には、閾値校正のFP基準集合は「`quality: high` かつ `ai_era_risk` なし(2022年以前)」の記事に
絞り込むことが望ましい。

## 収録状況

- `corpus/human/aozora/`: 寺田寅彦・中島敦・坂口安吾・岸田國士の随筆 12本(実収録・コミット済み)
- `corpus/human/web/`: `sources.json` に基づき `fetch.py` で取得した記事本文 125本
  (note エッセイ 38 + Zenn 技術記事 43 + 官公庁系ビジネス文書 32 + スライド系資料 12)
- `corpus/sources.json`: 上記 web エントリ 137件のソース定義(ジャンル別内訳: essay 50 / tech 43 / business 32 / slide 12。
  一部エントリは genre ラベルと human/web/ 上のファイル接頭辞(note-/zenn-/biz-/slide-)が対応する)
- `corpus/ai/`: 7モデル × 58本(essay/tech/blog 各10 + business 12 + slide 12) = 406本
  (`generate.py` / `generate-all.sh` で全モデル・全ジャンル生成済み)
  - Claude 系: `claude-haiku-4-5` / `claude-sonnet-5` / `claude-opus-4-8` / `claude-fable-5`
  - Codex 系: `gpt-5.6-sol` / `gpt-5.6-terra` / `gpt-5.6-luna`

## 再現手順

```bash
# 1. 人間コーパス(Web記事)をローカルに取得
uv run corpus/fetch.py                      # 全件
uv run corpus/fetch.py --limit 3            # 試走(先頭3件)
uv run corpus/fetch.py --id <source-id>     # 1件だけ

# 2. AI コーパスを生成
uv run corpus/generate.py --engine claude --model claude-sonnet-5 --limit 1  # 動作確認
uv run corpus/generate.py --engine claude --model claude-sonnet-5            # 1モデル・全ジャンル
uv run corpus/generate.py --engine codex --genre business                    # 1モデル・1ジャンル
./corpus/generate-all.sh                                                     # 全モデル × 全ジャンル一括
#   generate.py は出力ファイルが既に存在する場合スキップするため、
#   generate-all.sh は何度実行しても未生成分だけを追加生成する(安全に再実行可能)。

# 3. 検出器の閾値校正・集計レポートを生成
uv run scripts/calibrate.py report
```

## reports の構成

`corpus/reports/` は用途別に3層に分かれている:

- **直下(`corpus/reports/*.md`)**: 現行の根拠レポート。コミット対象
  (`.gitignore` に個別の否定パターンあり)。
  - `readability-sweep.md` / `business-calibration.md` / `business-fp-check.md` /
    `antithesis-recalibration.md`
  - ドキュメント(`references/`, `scripts/lint.py` のコメント等)から参照される、
    現行の検出器設計の根拠となっているレポート。
- **`corpus/reports/archive/`**: v0.3.0 校正期に作成された旧世代レポート。非コミット
  (ローカルのみ、再生成しない過去のスナップショット)。ドキュメント中の経緯説明コメントから
  参照されることがある(例: `deep-analysis.md`, `sweep_low_burstiness.md` 等)が、
  再生成の対象ではない。
- **`corpus/reports/research/`**: 収集・調査メモは原則として非コミット。
  `business-corpus-sources.md`, `embed-research.md` などの作業ログはローカルに置く。一方、
  公開用に出典・方法・限界を整理した文献レビューと証拠表は、`.gitignore` で個別に指定して
  コミット対象とする。公開した調査を再現する実験スクリプトも、`corpus/experiments/` の
  対応するサブディレクトリで個別にコミット対象へ戻す。

`calibrate.py` および `corpus/experiments/readability-sweep.py` の出力先は
`corpus/reports/` 直下のまま(サブディレクトリ化していない)。次回実行時は直下に新しい版が
生成される運用とし、必要であれば手動で `archive/` に退避する。

## 収集の規律

- **公開時期**: 人間側正例は原則として pre-2023(2022年以前公開、`ai_era_risk` なし)を優先する。
  2023年以降の記事は生成AIによる執筆・校正支援の混入リスクがあるため `ai_era_risk: true` を付与し、
  参考ビンとして残すが閾値校正の基準集合には含めない。
- **quality 判定**: 機械的指標ではなく、1本ずつ本文を読んで文章としての完成度(リズム・冗長性のなさ・
  読む際の負荷の低さ)を主観評価し `quality: "high"` / `"ordinary"` を付与する。
- **FP基準集合**: 検出器の人間側 FP 率算出には `quality: "high"` かつ(aozora の場合)
  `register: "modern-colloquial-classic"` のエントリのみを使う。`quality: "ordinary"` や
  `register: "literary-classic"` は参考ビンとして保持するが、閾値算出には使わない。
