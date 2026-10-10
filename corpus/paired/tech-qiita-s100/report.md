# 対コーパス評価: tech-qiita-s100

human 50 本、モデル 7 種。lint は `--genre tech` 相当。

## 1. 記憶の混入(AI 記事の文字10-gram のうち human 記事にも出る割合)

| モデル | 対の数 | 中央値 | 最大 | 5%超の対 |
|---|---|---|---|---|
| claude-fable-5-1 | 50 | 0.004 | 0.038 | 0 |
| claude-opus-5-5 | 50 | 0.004 | 0.038 | 0 |
| claude-sonnet-5-5 | 50 | 0.003 | 0.025 | 0 |
| gemini-3.8-flash | 50 | 0.004 | 0.023 | 0 |
| gpt-6-astra | 50 | 0.003 | 0.021 | 0 |
| gpt-6-luna | 50 | 0.003 | 0.022 | 0 |
| gpt-6.1-sol | 50 | 0.003 | 0.026 | 0 |

## 2. 文字数の追従(コードを除いた実測 / 指示した文字数)

| モデル | 中央値 | 最小 | 最大 |
|---|---|---|---|
| claude-fable-5-1 | 0.92 | 0.51 | 1.28 |
| claude-opus-5-5 | 1.05 | 0.76 | 1.61 |
| claude-sonnet-5-5 | 0.97 | 0.58 | 1.39 |
| gemini-3.8-flash | 1.44 | 0.54 | 2.41 |
| gpt-6-astra | 1.00 | 0.63 | 1.28 |
| gpt-6-luna | 1.02 | 0.69 | 1.44 |
| gpt-6.1-sol | 1.00 | 0.62 | 1.23 |

## 3. 検出器ごとの文書発火率

同じ記事 ID の対だけで数える。human 列が FP 率、各モデル列が検出率にあたる。

| 検出器 | human | claude-fable-5-1 | claude-opus-5-5 | claude-sonnet-5-5 | gemini-3.8-flash | gpt-6-astra | gpt-6-luna | gpt-6.1-sol |
|---|---|---|---|---|---|---|---|---|
| antithesis_repetition | 2% | 28% | 30% | 30% | 20% | 26% | 46% | 26% |
| english_syntax_inanimate_subject | 0% | 0% | 2% | 2% | 2% | 4% | 16% | 4% |
| forbidden_phrase | 52% | 62% | 66% | 64% | 66% | 54% | 56% | 56% |
| inanimate_subject_morph | 2% | 0% | 2% | 0% | 10% | 0% | 6% | 0% |
| low_burstiness | 10% | 70% | 58% | 66% | 12% | 90% | 100% | 98% |
| low_lexical_diversity_mtld | 6% | 0% | 0% | 0% | 0% | 0% | 2% | 0% |
| low_lexical_diversity_ttr | 42% | 18% | 32% | 18% | 14% | 68% | 72% | 72% |
| low_specificity | 2% | 8% | 10% | 8% | 12% | 22% | 22% | 28% |
| nominal_ending | 6% | 40% | 28% | 24% | 14% | 38% | 68% | 34% |
| repeated_sentence_lead | 24% | 10% | 12% | 24% | 22% | 24% | 28% | 28% |
| translationese | 18% | 10% | 16% | 16% | 20% | 16% | 12% | 12% |
| (いずれか) | 82% | 96% | 92% | 92% | 82% | 100% | 100% | 100% |
