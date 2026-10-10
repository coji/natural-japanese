# LLM-jp 由来の基準データでの lint の誤検知(生成AI以前の説明的・実務的な Web 文章)

分類器のスコア 0.7 以上の 8,792 本から無作為に 600 本。lint は既定(--genre なし)。

| 検出器 | 全体(n=600) | 地の文1,000字未満(n=129) | 1,000〜3,000字(n=400) | 3,000字以上(n=71) |
|---|---|---|---|---|
| antithesis_repetition | 2% | 0% | 1% | 10% |
| english_syntax_inanimate_subject | 1% | 0% | 0% | 6% |
| forbidden_phrase | 22% | 10% | 22% | 45% |
| inanimate_subject_morph | 2% | 1% | 1% | 8% |
| low_burstiness | 42% | 53% | 39% | 37% |
| low_lexical_diversity_mtld | 0% | 0% | 0% | 1% |
| low_lexical_diversity_ttr | 4% | 0% | 0% | 30% |
| low_specificity | 1% | 2% | 1% | 3% |
| metaphor_vocab | 4% | 4% | 4% | 4% |
| nominal_ending | 0% | 0% | 0% | 0% |
| repeated_sentence_lead | 15% | 4% | 12% | 48% |
| translationese | 8% | 5% | 8% | 17% |
| uniform_paragraph_structure | 0% | 1% | 0% | 0% |
| (いずれか) | 67% | 63% | 65% | 86% |
