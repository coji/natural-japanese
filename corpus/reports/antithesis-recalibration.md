# antithesis_repetition 再校正レポート（2026-07 コーパス校正2）

## 目的

`antithesis_repetition`（「〜ではなく」型の否定→肯定対比パターン）は、文書内で
3回以上出現すると severity=critical の finding が出現回数ぶん出る仕様だった。
実地検証（`corpus/reports/README.md` 系列とは別に、社内文書サンプルでの実運用）で
次の3点が判明した。

- (a) 長文書（約900文規模）では、絶対回数が3回以上でも文書全体に対する比率は
  数%未満に薄まることがあり、28件の critical が一度に出て件数がノイズ化する
- (b) 質の高い書き手が使う修辞技法（誤解を先に否定してから定義する等）にも、
  出現回数が3回を超えると無差別に発火する
- (c) 一方で「全文の3%を超える高頻度」は真陽性（AIの手癖）であるという実測も
  過去にあった

本レポートは、絶対回数閾値（3回、`ANTITHESIS_REPETITION_THRESHOLD`）はそのまま
維持しつつ、「検出数 / 総文数」の比率で severity を3段階化（info/warn/critical）
するための実測と、閾値決定の根拠を記録する。

## 方法

`scripts/calibrate.py` の `load_corpus()` / `mask_markdown_structure()` /
`split_sentences_with_lines()` を流用した一時集計スクリプト（リポジトリには
含めない）で、corpus/ 配下の全文書について次を計測した。

- 対象: `corpus/human/web/*.md`（quality: high のみを FP 基準とする。これは本
  プロジェクトの確立した規律）、`corpus/human/aozora/*.txt`（青空文庫、パブリック
  ドメイン。quality:high 相当として扱う）、`corpus/ai/**/*.md`（7モデル ×
  blog/business/essay/slide/tech の5ジャンル）
- 各文書について `ANTITHESIS_PATTERNS` のヒット数と、`split_sentences_with_lines`
  による総文数を数え、`比率 = ヒット数 / 総文数` を算出した
- AI 側のジャンルはファイル名の先頭要素（`blog-` `business-` `essay-` `slide-`
  `tech-`）から判定した（`corpus/sources.json` は human 側の出典メタデータのみを
  持つため）

コーパス本文の引用は一切行わない（著作権保護のため。青空文庫を含め、数値・
ファイルID・カテゴリ集計のみを記載する）。

## コーパス規模

| 種別 | 件数 |
| --- | --- |
| human_web（quality: high のみ） | 69 |
| human_aozora | 12 |
| human 合計（FP基準） | 81 |
| ai（7モデル × 5ジャンル） | 406 |

## 実測1: 絶対回数閾値（3回以上）のヒット率

| 種別 | ヒット率 |
| --- | --- |
| human quality:high 合計 | 23.5%（19/81） |
| うち human_web quality:high | 18.8%（13/69） |
| うち human_aozora | 50.0%（6/12） |
| ai 合計 | 11.8%（48/406） |

絶対回数閾値だけで見ると、human 側の方が ai 側よりもヒット率が高い
（旧仕様が指摘(b)の無差別発火を起こしていたことの裏付け）。aozora が
50%と特に高く、明治〜昭和期の随筆家の文体的特徴（対比を使った修辞）が
そのまま拾われている。

## 実測2: ヒットした文書内での「検出数/総文数」比率分布

絶対回数閾値でヒットした文書（human n=19, ai n=48）に限定した比率分布。

| 種別 | 平均 | 中央値 | 最小 | 最大 |
| --- | --- | --- | --- | --- |
| human（fired のみ） | 1.95% | 1.54% | 0.11% | 4.55% |
| ai（fired のみ） | 9.13% | 8.33% | 2.65% | 28.57% |

human の比率分布上限（最大4.55%）と ai の比率分布下限（最小2.65%）が
ほぼ重ならないことから、比率を severity 判定の軸に使えると判断した。

## 閾値決定

`ANTITHESIS_RATE_INFO_BELOW = 0.02`、`ANTITHESIS_RATE_CRITICAL_ABOVE = 0.03`
（絶対回数閾値は変更なし、3回のまま）とし、次の3段階にした。

- 比率 < 2%: severity=info（人間の技法との区別がつかない参考情報）
- 2% <= 比率 < 3%: severity=warn
- 比率 >= 3%: severity=critical（実測で真陽性が多い高頻度帯）

この閾値での human quality:high 全体（n=81）の内訳:

| severity | 件数 | 比率 |
| --- | --- | --- |
| info | 10 | 12.3% |
| warn | 5 | 6.2% |
| critical | 4 | 4.9% |

critical 化率 4.9% は目標（<5%）を満たす。ai 側（n=406）は critical
47件（11.6%）、warn 1件（0.2%）、info 0件で、絶対回数閾値だけの旧仕様
（critical 48件 = 11.8%）とほぼ同じ検出力を critical 帯に残せている。

### ジャンル別の内訳（human quality:high、共通閾値0.02/0.03時点）

| ジャンル | n | info | warn | critical | critical化率 |
| --- | --- | --- | --- | --- | --- |
| business | 29 | 4 | 2 | 1 | 3.4% |
| essay（aozoraを含む） | 30 | 4 | 1 | 1 | 3.3% |
| slide | 4 | 0 | 0 | 0 | 0.0% |
| tech | 18 | 2 | 2 | 2 | 11.1% |

business・essay・slide は共通閾値のままで <5% を満たすが、tech のみ
11.1%（zenn記事2本）と目標を超えたため、`GENRE_PROFILES["tech"]` に
`antithesis_rate_critical_above: 0.045` を追加した。この上書きにより
tech の human critical化率は 0% に下がり、ai 側（tech, n=84）は
critical 9件（10.7%）+ warn 6件（旧仕様なら critical 15件相当）を
維持している。business・essay・slide には genre 別上書きを追加していない
（共通閾値のままで目標を満たすため）。

## 参考: AI側のジャンル別・モデル別ヒット率（絶対回数閾値3回時点）

| ジャンル | ai n | ヒット率 |
| --- | --- | --- |
| blog | 70 | 27.1% |
| business | 84 | 3.6% |
| essay | 84 | 7.1% |
| slide | 84 | 6.0% |
| tech | 84 | 17.9% |

| モデル | n | ヒット率（最大ヒット数） |
| --- | --- | --- |
| claude-fable-5 | 58 | 8.6%（5） |
| claude-haiku-4-5 | 58 | 8.6%（6） |
| claude-opus-4-8 | 58 | 3.4%（3） |
| claude-sonnet-5 | 58 | 3.4%（4） |
| gpt-5.6-luna | 58 | 22.4%（7） |
| gpt-5.6-sol | 58 | 32.8%（5） |
| gpt-5.6-terra | 58 | 3.4%（4） |

モデル間でばらつきが大きい（gpt-5.6-sol は32.8%、claude-opus-4-8/sonnet-5/
gpt-5.6-terra は3.4%）ため、モデル別プロファイルは導入していない
（標本数・分散の両面でモデル別閾値を確定させるには時期尚早と判断）。

## 限界・today's decision に含まれない今後の課題

- 標本数はコーパス全体の規模に律速される（human quality:high n=81、
  aozora n=12）。特に aozora の50%という高いヒット率は12件という
  小標本の影響を受けている可能性があり、コーパス拡充後に再確認が必要
- business/essay/slide は現時点で共通閾値のままで目標を満たしているが、
  これも標本数が18〜30件程度と少なく、暫定値として扱う
- モデル別のばらつき（gpt系で顕著）は、将来 `--genre` とは別軸の
  モデル依存プロファイルを検討する余地があることを示唆するが、本校正の
  スコープ外とした
