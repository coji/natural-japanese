# corpus/ — 検出器の閾値校正用コーパス

## 目的

`skills/natural-japanese/scripts/lint.py` の各検出器(禁止語・統語パターン・統計指標など)は、
現状「経験則」で閾値を決めている。このコーパスは、その閾値を実測に基づいて
校正するために存在する。具体的には:

- 人間が書いた自然な日本語文章(人間コーパス)に対する誤検知率(FP率)を測る
- AI(Claude / GPT系)が「素の状態」(AI臭除去の指示なしで)書いた文章
  (AIコーパス)に対する検出率を測る
- 「人間側 FP率 5% 未満を保ちつつ AI 側検出率最大」となる閾値を
  `skills/natural-japanese/scripts/calibrate.py` で探索する

このコーパス自体は成果物ではなく、lint の品質を裏付けるための実験基盤。

## 構成

```
corpus/
├── README.md            このファイル
├── sources.json          人間コーパス(web/aozora)のソース定義
├── fetch.py               sources.json の type=web を取得して corpus/human/web/ に保存
├── generate.py            AI コーパスを claude/codex/agy CLI 経由で生成し corpus/ai/ に保存
├── generate-all.sh        全モデル × 全ジャンルを一括生成するランナー(generate.py のループ)
├── human/
│   ├── aozora/             青空文庫の随筆(パブリックドメイン、コミット対象)
│   └── web/                note/Zenn/官公庁 等の記事本文(著作権あり、非コミット、.gitkeep のみ)
├── ai/                     AI生成記事(非コミット、.gitkeep のみ。再生成可能なため)
├── ai-legacy/              個人設定の隔離前に生成した旧 AI 記事(非コミット、比較用に退避)
├── paired/                 対コーパス: human 記事1本ごとに各モデルの記事を対で生成(本文は非コミット)
├── timeslice/              時系列コーパス: Qiita の各年8月の記事(本文は非コミット)
├── ROADMAP.md              コーパス・検証手法の洗い出しロードマップ(改版しながら運用)
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
- `corpus/human/web/`: `sources.json` に基づき `fetch.py` で取得した記事本文 93本
  (ジャンル別: business 28 / essay 8 / slide 12 / tech 45)。
  コミット `9a8f46d` で、生成AI以前(2022年以前)の記事に絞って137件から減らした
- `corpus/sources.json`: 上記 web エントリと aozora エントリ、計 105件のソース定義
- `corpus/ai/`: 再生成待ち(空)。旧7モデル × 58本 = 406本は `corpus/ai-legacy/` に退避した。
  旧コーパスは生成時に実行者個人の設定(Claude Code の出力スタイル、`~/.agents/skills` の
  推敲スキル、codex の AGENTS.md 等)が混入していたため、新しいコーパスとは混ぜない。
  - 新しい生成対象(全モデル effort low): `claude-fable-5-1` / `claude-opus-5-5` / `claude-sonnet-5-5`
    (claude -p)、`gpt-6-astra` / `gpt-6.1-sol` / `gpt-6-luna`(codex exec)、`gemini-3.8-flash`(agy -p)
  - 各 CLI の標準のシステムプロンプトは残し、個人設定だけを外す(普通の利用者が使う状態で観測する)。
    隔離の方法は `generate.py` 冒頭のコメントを参照。agy は `corpus/.env` の `GEMINI_API_KEY` を使う
- `corpus/paired/`: 対コーパス。`collect_qiita.py` で生成AI以前の Qiita 記事を集め、
  `generate_paired.py` で記事ごとに各モデルの記事を生成し、`evaluate_pairs.py` / `analyze_detectors.py` で比べる。
  セットごとの役割(開発用・検証用)は `ROADMAP.md` 5章を参照。本文(human、各条件の生成記事)はコミットしない。
  推敲条件(`ai-polish/`)の出力は human 記事の二次的著作物なので、human 本文と同じ扱いにする
- `corpus/llmjp/`: LLM-jp コーパス v4 から選んだ、生成AI以前の説明的・実務的な Web 文章の一覧と抽出スクリプト(本文は非コミット)
- `corpus/mlm/`: 同じ BERT を AI 以前の人間の文書と生成AIの文章で別々に追加学習し、語を伏せて当てさせた差で
  AI 時代の言い回しを見つける実験(ROADMAP F40〜F47)。データとモデルは別のリポジトリで公開した:
  [coji/ja-ai-style-corpus](https://github.com/coji/ja-ai-style-corpus)(データとスクリプト。Hugging Face にも同名のデータセット)、
  [coji/ja-ai-style-bert](https://huggingface.co/coji/ja-ai-style-bert)(モデル)
- `corpus/selfcorpus/`・`corpus/collocation/`・`corpus/bench/`: 作者の文書へのスキルの適用、語の組み合わせによる判定、モデル評価ベンチ
- `corpus/timeslice/`: 時系列コーパス。`collect_qiita_timeslice.py` で Qiita の2019〜2026年の各8月の記事を集め、
  `features.py` で特徴量を出し、`replicate.py` / `lexicon.py` / `structure.py` / `embed_eval.py` で集計する。
  Qiita API のトークンは `corpus/.env` の `QIITA_TOKEN`

`corpus/` の報告のうち lint を使った数値の一部は、`main` に入っていない版の `lint.py` で出した
(URL だけの行の除外、「〜することができる」の扱いの変更、比喩の語の検出)。いまの `main` の `lint.py` で出し直すと、
数値が少し変わることがある。

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
uv run skills/natural-japanese/scripts/calibrate.py report
```

## reports の構成

`corpus/reports/` は用途別に3層に分かれている:

- **直下(`corpus/reports/*.md`)**: 現行の根拠レポート。コミット対象
  (`.gitignore` に個別の否定パターンあり)。
  - `readability-sweep.md` / `business-calibration.md` / `business-fp-check.md` /
    `antithesis-recalibration.md`
  - ドキュメント(`references/`, `skills/natural-japanese/scripts/lint.py` のコメント等)から参照される、
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
