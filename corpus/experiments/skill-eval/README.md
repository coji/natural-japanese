# skill-eval — natural-japanese スキル評価ハーネス

natural-japanese スキルを実文書に適用し、**lint では取れない構造・修辞・趣旨レベルの
欠陥**を、原因となったスキル指示（`SKILL.md` / `references/*.md` の file/section）
ごとにクラスタして炙り出すためのハーネス。人手の目に頼らず、多数の文書で機械的に
所見を集める。

パイプラインの詳細な設計思想・判断根拠は `eval.py` のモジュールdocstringとコメントに
書いてある。ここでは使い方だけを説明する。

## 使い方

### 1. dry-run（claudeを呼ばず、段の順序とitem一覧だけ確認）

```sh
uv run corpus/experiments/skill-eval/eval.py --dry-run \
  --manifest corpus/experiments/skill-eval/manifest.example.json
```

### 2. 実走

```sh
uv run corpus/experiments/skill-eval/eval.py \
  --manifest corpus/experiments/skill-eval/manifest.local.json \
  --run-label 2026-07-13-round1
```

- `--run-label` を省略すると実行時刻から自動生成される。同じ manifest・同じ
  `--run-label` で再実行すると、human_ness のA/B割当（後述）は同じになる
  （再現性のため）。
- `--model-apply` / `--model-critic` でモデルを上書きできる（既定:
  apply=`claude-sonnet-5`、critic=`claude-opus-4-8`）。
- 1 item あたり claude 呼び出しは最大 6 回（baseline生成 or source コピー、
  thesis抽出、skill-apply、human_ness、thesis_preservation、structural_smell。
  rewrite モードは baseline がコピーなので呼び出しが1回減る）。skill-apply は
  スキルの検査工程（lint.py/outline.py/terms.pyの実行含む）をフルで回すため、
  他の呼び出しより時間がかかる。

### 3. 出力の見方

- `corpus/experiments/skill-eval/runs/<run-label>/` に item ごとの生成物・
  批評JSONがすべて残る（**gitignore対象、NDA含みうるため非コミット**）。
  - `<id>.baseline.md` — 素の生成（generate）または source のコピー（rewrite）
  - `<id>.apply.md` — スキル適用後の最終文書
  - `<id>.apply.stdout.txt` — skill-apply段の claude 標準出力（作業ログ相当）
  - `<id>.thesis.json` / `<id>.human_ness.json` / `<id>.thesis_preservation.json` /
    `<id>.structural_smell.json` — 各段の `{"result": ..., "meta": {...}}`。
    `result` が `null` の場合はJSONパースが2回とも失敗したことを意味する
    （`meta.raw_attempt1` / `raw_attempt2` に生の応答が残る）。
  - `<id>.lint.json` — `scripts/lint.py --json` の生出力（参考記録。判定には使わない）
  - `<id>.ab_assignment.json` — human_ness批評でA/Bどちらが baseline/output かの
    割当（批評者には見せていない、ハーネス側だけが持つ鍵）
  - `run_meta.json` / `results_summary.json` / `aggregated.json` — run全体のメタ・
    生の集計結果
- `corpus/reports/skill-eval-findings.md` — 全item集約後の**抽象化した所見レポート**
  （コミット対象）。元文書の本文・固有名詞・数値は書かれない。human_ness の
  敗北率、skill_cause（file/section）別クラスタ表、直すべき箇所の候補、
  この評価自体の限界が載る。

## manifest.local.json の作り方

`manifest.example.json` をコピーして `manifest.local.json` を作り、実素材を
指す item を追加する（`manifest.local.json` は **gitignore で非コミット**）。

```sh
cp corpus/experiments/skill-eval/manifest.example.json \
   corpus/experiments/skill-eval/manifest.local.json
```

スキーマ:

```json
{
  "items": [
    {"id": "slide-syn-1", "doctype": "slide", "mode": "generate",
     "topic": "架空の営業支援ツールの提案スライド構成", "baseline": "naive"},

    {"id": "memo-real-1", "doctype": "memo", "mode": "rewrite",
     "source": "/絶対パス/for/your/source.txt", "baseline": "source"}
  ]
}
```

- `doctype`: `minutes` | `report` | `guide` | `memo` | `slide`
  （`references/doctypes/<doctype>.md` に対応）
- `mode: generate`: `topic` からスキルで新規生成する。baseline は
  ハーネスが同じモデルで「素の生成」（スキルなし）を別途作る
  （`baseline: "naive"` は記録用のラベルで、値自体は今のところ参照していない）。
- `mode: rewrite`: `source`（**ローカル絶対パス**）をスキルで書き直す。
  baseline は source そのもの（`baseline: "source"`）。
  **source が実素材（社外秘・NDA対象）を指す場合、そのパスと中身は
  `manifest.local.json` にしか残らず、runs/ 以下の生成物も gitignore される。
  commit対象になるのは skill-eval-findings.md の抽象化された所見だけ。**

## NDA注意

- `manifest.local.json` と `runs/` は `.gitignore` されている。実素材（社外秘の
  議事録・提案書等）を扱うときは必ず `manifest.local.json` を使い、
  `manifest.example.json` を直接書き換えないこと。
- `corpus/reports/skill-eval-findings.md` は eval.py が集約時に生成する
  レポートで、批評（thesis_preservation / structural_smell）には
  「evidenceは抽象化して書け、固有名詞・数値・原文引用は書くな」と指示して
  ある。ただしLLMがその指示に必ず従う保証はないため、実素材で実走した後は
  コミット前に自分の目で `corpus/reports/skill-eval-findings.md` を確認し、
  具体的な本文・固有名詞・数値が紛れ込んでいないか確認すること。
- `skill_cause.quote` はこのリポジトリ自身の `SKILL.md`/`references/*.md` からの
  引用であり、実素材の引用ではない（NDA対象外）。

## 検証（スモークテスト）

合成トピックのみの `manifest.example.json` で通しの動作確認ができる。1本に
絞った一時 manifest を使えば claude 呼び出しは6回程度で済む:

```sh
# 1本だけの一時manifestを作る例
python3 -c "
import json
data = json.load(open('corpus/experiments/skill-eval/manifest.example.json'))
data['items'] = [data['items'][-1]]  # slide-syn-1 のみ
json.dump(data, open('/tmp/manifest.smoke.json', 'w'), ensure_ascii=False, indent=2)
"
uv run corpus/experiments/skill-eval/eval.py \
  --manifest /tmp/manifest.smoke.json --run-label smoke-test
```
