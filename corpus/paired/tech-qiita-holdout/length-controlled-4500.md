# 長さをそろえた比較(S15): 先頭約 4500 字

各セルは「切りそろえた後 / 切りそろえる前(同じ記事)」の文書発火率。切りそろえる長さに満たない記事は除いた。

| 検出器 | human(n=40) | claude-opus-5-5(n=45) | gemini-3.8-flash(n=49) | gpt-6-luna(n=42) |
|---|---|---|---|---|
| antithesis_repetition | 0% / 15% | 11% / 27% | 2% / 35% | 43% / 67% |
| english_syntax_inanimate_subject | 0% / 2% | 0% / 2% | 0% / 0% | 7% / 10% |
| forbidden_phrase | 32% / 50% | 53% / 78% | 55% / 71% | 52% / 64% |
| inanimate_subject_morph | 0% / 0% | 0% / 0% | 0% / 2% | 0% / 0% |
| low_burstiness | 28% / 15% | 71% / 62% | 22% / 16% | 98% / 100% |
| low_lexical_diversity_mtld | 0% / 5% | 0% / 0% | 0% / 0% | 0% / 0% |
| low_lexical_diversity_ttr | 0% / 60% | 0% / 36% | 0% / 16% | 26% / 90% |
| low_specificity | 5% / 8% | 4% / 13% | 4% / 12% | 17% / 24% |
| nominal_ending | 0% / 0% | 9% / 38% | 2% / 14% | 48% / 64% |
| repeated_sentence_lead | 2% / 30% | 9% / 36% | 0% / 31% | 7% / 38% |
| translationese | 10% / 25% | 9% / 18% | 10% / 14% | 17% / 21% |
