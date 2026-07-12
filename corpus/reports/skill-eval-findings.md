# skill-eval-findings — natural-japanese スキル適用の所見集約

corpus/experiments/skill-eval/eval.py が実行した結果を集約したレポート。元文書の本文・固有名詞・数値は含まない（抽象化した所見のみ）。

## 実行メタ

- run-label: `smoke-test-1`
- manifest: `manifest.smoke.json`
- item数: 1
- doctype内訳: slide=1
- モデル: apply=`claude-sonnet-5` / critic(thesis・批評3種)=`claude-opus-4-8`

## human_ness（ブラインドA/B: スキル適用版 vs 素の生成）

- 全体: スキル適用版が「素の生成より人間らしくない」と判定された割合 = 0/1（0%）

| doctype | 判定数 | スキル版が敗北 | 敗北率 |
| --- | --- | --- | --- |
| slide | 1 | 0 | 0% |

## スキルレベル所見クラスタ（原因 file/section 別、頻度×severity降順）

| 原因ファイル | 節 | 出現item数/総item数 | 趣旨歪み件数 | severity内訳(smell) | score |
| --- | --- | --- | --- | --- | --- |
| `references/doctypes/slide.md` | 構成の型 | 1/1 | 0 | low=1, mid=1 | 3.00 |
| `references/doctypes/slide.md` | 品質基準 / 例: 営業支援ツールの提案スライド | 1/1 | 1 | - | 2.00 |
| `references/writing-constitution.md` | 5. 「担当者」でなく実名、「一部の」でなく実数で接地する | 1/1 | 1 | - | 2.00 |
| `references/doctypes/slide.md` | 必須要素 | 1/1 | 0 | mid=1 | 2.00 |
| `references/doctypes/slide.md` | 品質基準 | 1/1 | 0 | mid=1 | 2.00 |
| `references/writing-constitution.md` | 12. 結びは要約の繰り返しでなく再統合。調査ものはSo Whatまで書く | 1/1 | 0 | mid=1 | 2.00 |
| `references/doctypes/slide.md` | 例: 営業支援ツールの提案スライド | 1/1 | 0 | low=1 | 1.00 |

（各クラスタの逐語の所見文は元文書の固有名詞・数値を含みうるため、このコミット版には載せない。全文は `runs/<run-label>/report.full.md`（非コミット）を参照）

## 次にスキルのどこを直すべきか（頻度上位クラスタから）

- `references/doctypes/slide.md`（構成の型）: 1/1 item で原因として挙げられた。当該節の記述が具体例・限定条件を欠いている可能性が高く、書き手が誤って過剰一般化・テンプレ適用しないよう、適用条件や『やりすぎ』の反例を追記することを検討する。
- `references/doctypes/slide.md`（品質基準 / 例: 営業支援ツールの提案スライド）: 1/1 item で原因として挙げられた。当該節の記述が具体例・限定条件を欠いている可能性が高く、書き手が誤って過剰一般化・テンプレ適用しないよう、適用条件や『やりすぎ』の反例を追記することを検討する。
- `references/writing-constitution.md`（5. 「担当者」でなく実名、「一部の」でなく実数で接地する）: 1/1 item で原因として挙げられた。当該節の記述が具体例・限定条件を欠いている可能性が高く、書き手が誤って過剰一般化・テンプレ適用しないよう、適用条件や『やりすぎ』の反例を追記することを検討する。

## この評価自体の限界

- サンプル数が少ない（本レポート時点で item数 = 1）。クラスタの頻度・スコアは参考値であり、統計的な確定ではない。
- 批評（human_ness / thesis_preservation / structural_smell）自体もLLMによる判定であり、ノイズ・見落とし・過剰検出のいずれも起こりうる。特に human_ness のブラインドA/B は批評モデルの好み（整った文章を「人間らしい」と誤判定する等）に影響される可能性がある。
- skill_cause（file/section/quote）は批評モデルの自己申告であり、実際の因果関係を保証しない。同一クラスタに複数の異なる原因が混在している可能性がある。
- thesis 抽出・批評はすべて単一の critic モデルで行っており、モデル固有の癖が結果に系統的なバイアスとして乗る可能性がある。
