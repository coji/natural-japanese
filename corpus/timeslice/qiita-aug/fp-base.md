# FP 基準の見直し(S16)

現行 lint(`--genre tech`)の検出器ごとの文書発火率。どれも人間の文章なので、発火は FP にあたる。

| 検出器 | 既存基準(tech, quality:high)(n=37) | H'(ストック30以上)(n=100) | H(無作為抽出)(n=600) | H: 地の文1,000字未満(n=317) | H: 1,000〜3,000字(n=242) | H: 3,000字以上(n=41) |
|---|---|---|---|---|---|---|
| antithesis_repetition | 22% | 4% | 1% | 0% | 0% | 15% |
| english_syntax_inanimate_subject | 0% | 3% | 0% | 0% | 0% | 5% |
| forbidden_phrase | 59% | 47% | 17% | 8% | 23% | 56% |
| inanimate_subject_morph | 5% | 2% | 0% | 0% | 0% | 5% |
| low_burstiness | 32% | 11% | 20% | 26% | 14% | 10% |
| low_lexical_diversity_mtld | 16% | 4% | 1% | 0% | 0% | 15% |
| low_lexical_diversity_ttr | 70% | 40% | 4% | 0% | 1% | 59% |
| low_specificity | 14% | 4% | 2% | 1% | 4% | 7% |
| nominal_ending | 0% | 3% | 0% | 0% | 0% | 5% |
| repeated_sentence_lead | 49% | 22% | 6% | 1% | 8% | 27% |
| translationese | 19% | 17% | 6% | 2% | 8% | 17% |
| uniform_paragraph_structure | 11% | 0% | 1% | 1% | 1% | 0% |
