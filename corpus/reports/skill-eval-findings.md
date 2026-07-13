# skill-eval-findings — natural-japanese スキル適用の所見集約

corpus/experiments/skill-eval/eval.py が実行した結果を集約したレポート。元文書の本文・固有名詞・数値は含まない（抽象化した所見のみ）。

## 実行メタ

- run-label: `batch-4-rw (quantitative caps)`
- manifest: `manifest.local.json`
- item数: 5
- doctype内訳: guide=1, memo=1, minutes=2, report=1
- モデル: apply=`claude-sonnet-5 (effort low)` / critic(thesis・批評3種)=`claude-fable-5 (effort low)`

## human_ness（ブラインドA/B: スキル適用版 vs 素の生成）

- 全体: スキル適用版が「素の生成より人間らしくない」と判定された割合 = 0/5（0%）

| doctype | 判定数 | スキル版が敗北 | 敗北率 |
| --- | --- | --- | --- |
| guide | 1 | 0 | 0% |
| memo | 1 | 0 | 0% |
| minutes | 2 | 0 | 0% |
| report | 1 | 0 | 0% |

## スキルレベル所見クラスタ（原因 file/section 別、頻度×severity降順）

| 原因ファイル | 節 | 出現item数/総item数 | 趣旨歪み件数 | severity内訳(smell) | score |
| --- | --- | --- | --- | --- | --- |
| `references/writing-constitution.md` | 2. 見出しに結論を埋め込む。ラベルだけの見出しは書かない | 4/5 | 0 | high=2, mid=2 | 8.00 |
| `references/doctypes/minutes.md` | 構成の型 | 2/5 | 0 | low=1, mid=3 | 2.80 |
| `references/writing-constitution.md` | 12. 結びは要約の繰り返しでなく再統合。調査ものはSo Whatまで書く | 2/5 | 0 | high=1, mid=2 | 2.80 |
| `references/doctypes/minutes.md` | 必須要素 | 2/5 | 0 | mid=2 | 1.60 |
| `references/writing-constitution.md` | 3. 因果と経緯は地の文で書く。箇条書きは本当に並列なときだけ | 2/5 | 0 | low=1, mid=1 | 1.20 |
| `references/writing-constitution.md` | 9. 「〜ではなく」は本当の誤解を正すときだけ使う | 1/5 | 0 | high=1 | 0.60 |
| `references/writing-constitution.md` | 5. 「担当者」でなく実名、「一部の」でなく実数で接地する | 1/5 | 0 | high=1 | 0.60 |
| `references/doctypes/memo.md` | 文体憲法の重点条項 — 第10条(限界・未確定は明示ラベル) | 1/5 | 0 | mid=1 | 0.40 |
| `references/writing-constitution.md` | 11. 事実には出典を、意見には「筆者は」を添える | 1/5 | 0 | mid=1 | 0.40 |
| `corpus/experiments/skill-eval/../../../references/doctypes/minutes.md` | 品質基準 — 議論は地の文で、決定・宿題だけが箇条書きになっている | 1/5 | 0 | mid=1 | 0.40 |
| `references/doctypes/report.md` | 品質基準（誤読しやすい数字は著者が先に指差している） | 1/5 | 0 | mid=1 | 0.40 |
| `references/doctypes/report.md` | 品質基準（数字の意味が翻訳されている） | 1/5 | 0 | mid=1 | 0.40 |
| `references/doctypes/report.md` | 必須要素 | 1/5 | 0 | mid=1 | 0.40 |
| `references/writing-constitution.md` | 7. 重要な節は厚く書き、軽い節は正直に軽く書く | 1/5 | 0 | mid=1 | 0.40 |
| `references/writing-constitution.md` | 1. 前置きを書かない。結論はタイトルと最初の一文に渡す | 1/5 | 0 | mid=1 | 0.40 |
| `references/doctypes/memo.md` | 例: 防災アプリのコンセプトメモ | 1/5 | 0 | low=1 | 0.20 |
| `references/doctypes/memo.md` | 構成の型 | 1/5 | 0 | low=1 | 0.20 |
| `references/doctypes/minutes.md` | 雛形 | 1/5 | 0 | low=1 | 0.20 |
| `references/writing-constitution.md` | 6. 太字は文中の核1箇所だけに使う | 1/5 | 0 | low=1 | 0.20 |
| `references/doctypes/report.md` | 構成の型 | 1/5 | 0 | low=1 | 0.20 |
| `references/doctypes/guide.md` | 構成の型は章の性質で変える / このガイドも育つ | 1/5 | 0 | low=1 | 0.20 |

（各クラスタの逐語の所見文は元文書の固有名詞・数値を含みうるため、このコミット版には載せない。全文は `runs/<run-label>/report.full.md`（非コミット）を参照）

## 次にスキルのどこを直すべきか（頻度上位クラスタから）

- `references/writing-constitution.md`（2. 見出しに結論を埋め込む。ラベルだけの見出しは書かない）: 4/5 item で原因として挙げられた。当該節の記述が具体例・限定条件を欠いている可能性が高く、書き手が誤って過剰一般化・テンプレ適用しないよう、適用条件や『やりすぎ』の反例を追記することを検討する。
- `references/doctypes/minutes.md`（構成の型）: 2/5 item で原因として挙げられた。当該節の記述が具体例・限定条件を欠いている可能性が高く、書き手が誤って過剰一般化・テンプレ適用しないよう、適用条件や『やりすぎ』の反例を追記することを検討する。
- `references/writing-constitution.md`（12. 結びは要約の繰り返しでなく再統合。調査ものはSo Whatまで書く）: 2/5 item で原因として挙げられた。当該節の記述が具体例・限定条件を欠いている可能性が高く、書き手が誤って過剰一般化・テンプレ適用しないよう、適用条件や『やりすぎ』の反例を追記することを検討する。

## この評価自体の限界

- サンプル数が少ない（本レポート時点で item数 = 5）。クラスタの頻度・スコアは参考値であり、統計的な確定ではない。
- 批評（human_ness / thesis_preservation / structural_smell）自体もLLMによる判定であり、ノイズ・見落とし・過剰検出のいずれも起こりうる。特に human_ness のブラインドA/B は批評モデルの好み（整った文章を「人間らしい」と誤判定する等）に影響される可能性がある。
- skill_cause（file/section/quote）は批評モデルの自己申告であり、実際の因果関係を保証しない。同一クラスタに複数の異なる原因が混在している可能性がある。
- thesis 抽出・批評はすべて単一の critic モデルで行っており、モデル固有の癖が結果に系統的なバイアスとして乗る可能性がある。
