# 生成条件の比較(S6): tech-qiita-holdout

モデル: claude-opus-5-5, gpt-6-luna, gemini-3.8-flash。各条件で全モデルがそろった記事だけを比べる。
human 列は、その条件で比べた記事 ID の元の human 記事。

| 条件 | 記事数 |
|---|---|
| title | 50 |
| materials | 0 |
| polish | 50 |

## 語彙と構造(1,000字あたり。「まとめ」は記事の割合)

| 条件 | 書き手 | 瞬間 | 効く | 境界 | 守る | 止まる | 上限 | 判断 | 土台 | 壊れる | 道具 | 実測 | 静か | 太字 | ダッシュ | 「まとめ」 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| title | human | 0.00 | 0.01 | 0.03 | 0.00 | 0.04 | 0.01 | 0.17 | 0.00 | 0.02 | 0.00 | 0.00 | 0.00 | 2.17 | 0.01 | 38% |
| title | claude-opus-5-5 | 0.06 | 0.12 | 0.11 | 0.03 | 0.08 | 0.06 | 0.21 | 0.03 | 0.07 | 0.05 | 0.01 | 0.02 | 4.67 | 0.00 | 64% |
| title | gpt-6-luna | 0.02 | 0.01 | 0.19 | 0.04 | 0.07 | 0.10 | 0.40 | 0.05 | 0.03 | 0.10 | 0.00 | 0.00 | 0.19 | 0.02 | 40% |
| title | gemini-3.8-flash | 0.25 | 0.02 | 0.08 | 0.02 | 0.03 | 0.03 | 0.06 | 0.03 | 0.04 | 0.01 | 0.00 | 0.02 | 8.34 | 0.13 | 82% |
| polish | human | 0.00 | 0.01 | 0.03 | 0.00 | 0.04 | 0.01 | 0.17 | 0.00 | 0.02 | 0.00 | 0.00 | 0.00 | 2.17 | 0.01 | 38% |
| polish | claude-opus-5-5 | 0.00 | 0.01 | 0.03 | 0.00 | 0.03 | 0.01 | 0.17 | 0.01 | 0.02 | 0.01 | 0.00 | 0.00 | 2.96 | 0.04 | 40% |
| polish | gpt-6-luna | 0.00 | 0.00 | 0.03 | 0.00 | 0.05 | 0.02 | 0.19 | 0.02 | 0.01 | 0.00 | 0.00 | 0.00 | 1.82 | 0.02 | 44% |
| polish | gemini-3.8-flash | 0.06 | 0.01 | 0.04 | 0.00 | 0.02 | 0.03 | 0.08 | 0.03 | 0.01 | 0.00 | 0.00 | 0.00 | 8.50 | 0.08 | 50% |

## lint の検出器ごとの文書発火率

| 検出器 | title/human | title/claude-opus-5-5 | title/gpt-6-luna | title/gemini-3.8-flash | polish/human | polish/claude-opus-5-5 | polish/gpt-6-luna | polish/gemini-3.8-flash |
|---|---|---|---|---|---|---|---|---|
| antithesis_repetition | 12% | 26% | 58% | 34% | 12% | 10% | 8% | 4% |
| english_syntax_inanimate_subject | 2% | 2% | 8% | 0% | 2% | 0% | 0% | 2% |
| forbidden_phrase | 48% | 78% | 62% | 72% | 48% | 60% | 38% | 40% |
| inanimate_subject_morph | 2% | 0% | 0% | 2% | 2% | 2% | 0% | 0% |
| low_burstiness | 16% | 64% | 100% | 16% | 16% | 26% | 28% | 14% |
| low_lexical_diversity_mtld | 4% | 0% | 0% | 0% | 4% | 0% | 4% | 0% |
| low_lexical_diversity_ttr | 48% | 32% | 76% | 16% | 48% | 40% | 34% | 6% |
| low_specificity | 6% | 12% | 20% | 12% | 6% | 2% | 14% | 14% |
| nominal_ending | 0% | 34% | 60% | 14% | 0% | 4% | 6% | 2% |
| repeated_sentence_lead | 24% | 32% | 36% | 30% | 24% | 24% | 30% | 14% |
| translationese | 20% | 16% | 18% | 14% | 20% | 14% | 4% | 8% |

## 推敲で新たに反応した検出器(元の human 記事では反応していなかった記事の割合)

| 検出器 | claude-opus-5-5 | gpt-6-luna | gemini-3.8-flash |
|---|---|---|---|
| antithesis_repetition | 2% | 0% | 2% |
| english_syntax_inanimate_subject | 0% | 0% | 2% |
| forbidden_phrase | 18% | 12% | 14% |
| inanimate_subject_morph | 2% | 0% | 0% |
| low_burstiness | 12% | 16% | 8% |
| low_lexical_diversity_mtld | 0% | 2% | 0% |
| low_lexical_diversity_ttr | 0% | 0% | 0% |
| low_specificity | 2% | 10% | 14% |
| nominal_ending | 4% | 6% | 2% |
| repeated_sentence_lead | 4% | 10% | 2% |
| translationese | 8% | 2% | 6% |
