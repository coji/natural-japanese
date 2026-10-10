# 対コーパス評価: tech-qiita

human 50 本、モデル 7 種。lint は `--genre tech` 相当。

## 1. 記憶の混入(AI 記事の文字10-gram のうち human 記事にも出る割合)

| モデル | 対の数 | 中央値 | 最大 | 5%超の対 |
|---|---|---|---|---|
| claude-fable-5-1 | 50 | 0.004 | 0.019 | 0 |
| claude-opus-5-5 | 50 | 0.004 | 0.018 | 0 |
| claude-sonnet-5-5 | 50 | 0.003 | 0.020 | 0 |
| gemini-3.8-flash | 50 | 0.003 | 0.013 | 0 |
| gpt-6-astra | 50 | 0.002 | 0.018 | 0 |
| gpt-6-luna | 50 | 0.003 | 0.018 | 0 |
| gpt-6.1-sol | 50 | 0.002 | 0.020 | 0 |

## 2. 文字数の追従(コードを除いた実測 / 指示した文字数)

| モデル | 中央値 | 最小 | 最大 |
|---|---|---|---|
| claude-fable-5-1 | 0.86 | 0.50 | 1.24 |
| claude-opus-5-5 | 0.97 | 0.72 | 1.51 |
| claude-sonnet-5-5 | 0.94 | 0.60 | 1.49 |
| gemini-3.8-flash | 1.44 | 0.76 | 2.20 |
| gpt-6-astra | 0.98 | 0.54 | 1.24 |
| gpt-6-luna | 0.96 | 0.59 | 1.34 |
| gpt-6.1-sol | 1.01 | 0.50 | 1.20 |

## 3. 検出器ごとの文書発火率

同じ記事 ID の対だけで数える。human 列が FP 率、各モデル列が検出率にあたる。

| 検出器 | human | claude-fable-5-1 | claude-opus-5-5 | claude-sonnet-5-5 | gemini-3.8-flash | gpt-6-astra | gpt-6-luna | gpt-6.1-sol |
|---|---|---|---|---|---|---|---|---|
| antithesis_repetition | 6% | 24% | 30% | 32% | 36% | 30% | 52% | 24% |
| english_syntax_inanimate_subject | 6% | 0% | 0% | 0% | 2% | 8% | 8% | 6% |
| forbidden_phrase | 42% | 44% | 76% | 60% | 78% | 62% | 54% | 50% |
| inanimate_subject_morph | 2% | 4% | 0% | 4% | 0% | 0% | 0% | 6% |
| low_burstiness | 12% | 68% | 64% | 74% | 14% | 94% | 100% | 94% |
| low_lexical_diversity_mtld | 2% | 0% | 0% | 0% | 0% | 0% | 0% | 0% |
| low_lexical_diversity_ttr | 38% | 14% | 26% | 16% | 10% | 60% | 58% | 62% |
| low_specificity | 6% | 8% | 12% | 14% | 10% | 14% | 20% | 28% |
| nominal_ending | 0% | 32% | 26% | 18% | 18% | 28% | 50% | 34% |
| repeated_sentence_lead | 20% | 12% | 14% | 22% | 14% | 34% | 32% | 34% |
| translationese | 16% | 12% | 26% | 22% | 14% | 14% | 8% | 10% |
| (いずれか) | 74% | 96% | 98% | 92% | 86% | 98% | 100% | 100% |
