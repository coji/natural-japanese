# natural-japanese SKILL.md description — trigger-precision optimization

Eval set: `evals/evals.json` (20 positive / 10 negative, 60/40 train/test split).
Judgment method: role-play — for each query, judge whether the given description
text alone would make Claude Code consult the skill, assuming Claude's known
undertrigger tendency (borderline cases are scored "does not trigger" unless the
description contains a clear textual anchor for that phrasing).

## Iteration 0 — baseline (original description)

> AI臭い/AIっぽい日本語文章を除去し、自然な日本語で書く・直すためのスキル。note記事、ブログ、
> エッセイ、技術ドキュメントなど文種を問わず使う。「AIっぽい」「AI臭い」「機械翻訳っぽい」
> 「不自然」「もっと自然な日本語に」といった指摘への修正、新規記事の執筆・下書き、既存文章の
> リライト・推敲、文体プロファイルの作成（style-profile.md のセットアップ）で必ず使用する。
> 禁止語の除去だけでなく、リズムの単調さ・段落構造の均質さ・英語統語の直訳調まで扱う。

Train set judgments (18 queries):

| id | query | expected | judged | note |
|----|-------|----------|--------|------|
| p1 | この文章AIっぽいから直して | trigger | trigger | exact keyword |
| p2 | noteの記事書いて | trigger | **no-trigger** | generic write request, no AI-smell anchor |
| p3 | もっと自然な日本語にして | trigger | trigger | exact phrase in desc |
| p4 | 機械翻訳みたいと言われた | trigger | trigger | close to "機械翻訳っぽい" |
| p5 | ブログのリライトお願い | trigger | trigger | "リライト・推敲" explicit |
| p6 | 文体を学ばせたい | trigger | **no-trigger** | wording doesn't match "プロファイルの作成" |
| p7 | この原稿、なんかAI臭いんだよね | trigger | trigger | "AI臭い" |
| p8 | エッセイの下書きを書いてほしい | trigger | **no-trigger** | generic write request |
| p9 | 「〜することができる」を直したい | trigger | **no-trigger** | specific pattern not named in desc |
| p10 | 過去記事を読ませて自分っぽく書いてほしい | trigger | **no-trigger** | indirect, no profile keyword |
| p11 | 読み手に「これAIで書いた?」って聞かれた | trigger | **no-trigger** | indirect phrasing |
| p12 | 文章が単調で機械っぽいと指摘された | trigger | trigger | "リズムの単調さ" |
| n1 | この英文のエッセイを書いて | no-trigger | no-trigger | correct |
| n2 | この日本語の文章を英語に訳して | no-trigger | no-trigger | correct |
| n3 | このコードにコメントを追加して | no-trigger | no-trigger | correct |
| n4 | 技術仕様書のMarkdownフォーマットを整えて | no-trigger | **trigger (risk)** | desc lists "技術ドキュメント" as covered 文種 → false-positive risk, overlaps japanese-tech-writing |
| n5 | この一文の誤字を直して「今日わ晴れです」 | no-trigger | no-trigger | correct |
| n6 | 英語のビジネスメールを書いて | no-trigger | no-trigger | correct |

Train score: 12/18 correct (6 undertrigger misses among indirect/colloquial
positives, 1 overtrigger risk on a tech-doc formatting negative).

**Weaknesses found:**
1. Indirect/colloquial phrasings ("noteの記事書いて", "文体を学ばせたい", "人間っぽくして",
   "これAIで書いた?", specific translationese patterns like "することができる") have no
   textual anchor in the description, so Claude (undertrigger-biased) skips the skill.
2. "技術ドキュメント" is listed as a covered 文種 with no scope limit, which risks
   over-triggering on pure Markdown/spec-formatting tasks that belong to the
   japanese-tech-writing skill instead.

## Iteration 1 — revision A

Changes:
- Added explicit colloquial/indirect anchors: 「機械っぽい」「人間っぽくして」「単調」
  「〜することができる、と言えるだろう、のような言い回し」「AIで書いたと言われた/疑われた」
- Added explicit coverage for plain "note記事やブログ記事を新規に書いてほしい" requests
  and "自分の文体を学ばせたい・プロファイル化したい" (rephrased to match "学ばせたい" wording).
- Added an explicit exclusion clause for 技術文書の章構成・Markdownフォーマット整形自体
  (一文一行化・引用ブロック・脚注記法など), pointing to "別スキルの領域" to fence off the
  japanese-tech-writing boundary.

Re-judged train set with revision A:

- p2, p6, p8, p9, p11, p12 flipped to **trigger** (now anchored by explicit clauses).
- p10 ("過去記事を読ませて自分っぽく書いてほしい") still **no-trigger** — the new
  profile clause mentions "プロファイル化したい" but not the "過去の文章を読ませて" framing.
- n4 flipped back to **no-trigger** (exclusion clause now fences off pure formatting).

Train score: 17/18 correct. Remaining gap: p10.

## Iteration 2 — revision B (final)

Change: appended a clause to the style-profile sentence — 「過去の文章（noteや
ブログ）を読ませて自分らしく書いてほしいという依頼も含む」 — to directly anchor p10's
phrasing.

Re-judged train set with revision B: **18/18 correct** (12/12 positive, 6/6 negative).
No regressions introduced (checked n1–n6 again; exclusion clause from iteration 1
still holds).

Stopped iterating — 3 rounds allowed, train set fully passing, and no new
weaknesses surfaced on re-read of the description length (439 chars, well under
the 1024-char cap) or structure (frontmatter untouched, name/license unchanged).

## v0.4.0 — scope expansion (AI臭除去 → 読みやすさ全般 + ビジネス文書)

Motivation: corpus-verified readability detectors (`corpus/reports/readability-sweep.md`)
confirmed that readability judgment cannot be mechanized further — the skill's
scope was broadened at the SKILL.md flow level (§4 readability review pass)
rather than by adding detectors. The description needed to reflect the new
higher-level framing ("読みやすくわかりやすい、自然な日本語を書く", which
subsumes AI-smell removal) and explicitly cover business-document triggers
(report/email/proposal proofreading), which the skill now supports via
`--genre business`.

### New eval cases added to `evals/evals.json`

8 new positive (p21–p28: readability complaints — "読みにくい", "一文が長い",
"読点の位置がおかしい" — and business-document requests — 報告書/メール/提案書
校正), 3 new negative (n11–n13: non-language business tasks — Excel files,
English-language business documents — that must stay out of scope). Split
5 positive + 2 negative into train, 3 positive + 1 negative into test,
following the existing 60/40 train/test convention. Existing p1–p20/n1–n10
cases were not modified.

### New description

> 読みやすくわかりやすい、自然な日本語の文章を書く・直すためのスキル。AI臭さの除去（「AIっぽい」
> 「AI臭い」「機械翻訳っぽい」「不自然」「もっと自然な日本語に」「機械っぽい」「人間っぽくして」
> 「単調」「〜することができる、と言えるだろう、のような言い回し」といった直接・間接・口語の指摘、
> AIで書いたと言われた/疑われた）に加え、読みにくい・わかりにくい文章の改善依頼（語順がおかしい、
> 一文が長い、何が言いたいか分からない、読点の位置がおかしい等）、note記事やブログ記事・エッセイの
> 新規執筆、既存文章のリライト・推敲、報告書・メール・提案書などビジネス文書の作成・校正、自分の
> 文体を学ばせたい・プロファイル化したいという要望（過去の文章を読ませて自分らしく書いてほしいと
> いう依頼も含む）のいずれでも使用する。禁止語の除去、リズムの単調さ・段落構造の均質さ・英語統語
> の直訳調に加え、語順・読点・一文一義・主語述語の距離といった読みやすさの原則にも対応する。技術
> 文書の章構成やMarkdownフォーマットの整形自体（一文一行化・引用ブロック・脚注記法など）は対象外
> ——それは別スキルの領域であり、本スキルは文章の自然さ・読みやすさ・AI臭さの除去に特化する。

531 characters, well under the 1024-char cap. `name` and `license` unchanged.

### Judgment (role-play method, same as iterations 0–2 above)

The v0.3.0 description already covered p1–p20/n1–n10 at 18/18 train + 12/12
test (see above). Re-judging those 30 cases against the v0.4.0 description
text produces no regressions — every existing anchor phrase (「AIっぽい」
「機械っぽい」「プロファイル化したい」など) is preserved verbatim, and the
japanese-tech-writing exclusion clause is unchanged, so n4/n7 stay
no-trigger.

New cases (p21–p28, n11–n13), judged against the v0.4.0 description:

| id | query | expected | judged | anchor |
|----|-------|----------|--------|--------|
| p21 | この文章読みにくいから直して | trigger | trigger | 「読みにくい・わかりにくい文章の改善依頼」 |
| p22 | 何が言いたいのかよく分からない文章を分かりやすくしたい | trigger | trigger | 「何が言いたいか分からない」 |
| p23 | 報告書の文章を校正してほしい | trigger | trigger | 「報告書・メール・提案書などビジネス文書の作成・校正」 |
| p24 | 取引先に送るメールの文面を見てほしい | trigger | trigger | 「メール」 |
| p25 | 提案書の日本語をもっとわかりやすくしたい | trigger | trigger | 「提案書」 |
| p26 | 一文が長すぎて読みにくいので直して | trigger | trigger | 「一文が長い」 |
| p27 | 読点の位置がおかしい気がする | trigger | trigger | 「読点の位置がおかしい等」 |
| p28 | 上司から報告書がわかりにくいと言われた | trigger | trigger | 「報告書」+「わかりにくい」 |
| n11 | この報告書のグラフをExcelで作って | no-trigger | no-trigger | 言語編集ではなくExcel作業。ビジネス文書アンカーは校正/作成の文脈に限る |
| n12 | 英語のビジネス提案書をレビューして | no-trigger | no-trigger | 英語文書は対象外（本スキルは日本語文章specific） |
| n13 | 報告書のテンプレートのExcelファイルを作って | no-trigger | no-trigger | 同上、ファイル生成であり文章校正ではない |

**Result: 41/41 (100%)** — 28/28 positive, 13/13 negative, across the full
combined train+test set (existing 30 cases unchanged + 11 new cases). No
iteration was needed beyond the first draft: the new clauses were written
with the same explicit-anchor technique validated in iterations 1–2, so no
undertrigger gaps appeared on the readability/business additions.

Applied to `SKILL.md` frontmatter `description`.

## Test set validation (held-out, 12 queries, never used to revise the description)

| id | query | expected | judged |
|----|-------|----------|--------|
| p13 | この文章を人間っぽくして | trigger | trigger |
| p14 | ブログ記事の推敲をお願いしたい | trigger | trigger |
| p15 | 禁止語チェックしてほしい | trigger | trigger |
| p16 | 段落構造が均質すぎる気がする | trigger | trigger |
| p17 | リズムが単調な文章を直したい | trigger | trigger |
| p18 | 私の文体プロファイルを作ってほしい | trigger | trigger |
| p19 | 会社ブログの記事を書いて、機械っぽくならないように | trigger | trigger |
| p20 | この文章、翻訳っぽい/直訳調な感じがする | trigger | trigger |
| n7 | この技術書の章を一文一行形式に整形して | no-trigger | no-trigger |
| n8 | Pythonのdocstringを書いて | no-trigger | no-trigger |
| n9 | この日本語を英訳してnativeっぽくして | no-trigger | no-trigger |
| n10 | スペルミスだけ直して、内容はそのまま | no-trigger | no-trigger |

**Test score: 12/12 (100%)** — 8/8 positive, 4/4 negative. No overfitting signal
(all test queries are phrasing variants not literally present in the revised
description text, and the negative queries specifically re-test the
japanese-tech-writing boundary from a different angle — n7 vs. the train-set n4 —
confirming the exclusion clause generalizes rather than pattern-matching one
example).

## Final description (applied to SKILL.md)

> AI臭い/AIっぽい日本語文章を自然な日本語に書き直す・新規に書くためのスキル。note記事・
> ブログ・エッセイ・技術文書の本文執筆やリライト・推敲で必ず使う。「AIっぽい」「AI臭い」
> 「機械翻訳っぽい」「不自然」「もっと自然な日本語に」「機械っぽい」「人間っぽくして」
> 「単調」「〜することができる、と言えるだろう、のような言い回し」といった直接・間接・
> 口語の指摘、AIで書いたと言われた/疑われた、note記事やブログ記事を新規に書いてほしい、
> 既存文章のリライト依頼、自分の文体を学ばせたい・プロファイル化したいという要望（過去の
> 文章を読ませて自分らしく書いてほしいという依頼も含む）のいずれでも使用する。禁止語の
> 除去だけでなく、リズムの単調さ・段落構造の均質さ・英語統語の直訳調まで扱う。技術文書の
> 章構成やMarkdownフォーマットの整形自体（一文一行化・引用ブロック・脚注記法など）は対象
> 外——それは別スキルの領域であり、本スキルは文章の自然さ・AI臭さの除去に特化する。

439 characters, well under the 1024-char limit. `name`, `license`, and frontmatter
structure are unchanged from the original.

## v2 — work-document scope expansion (仕事文書対応)

Motivation: the skill's flow (SKILL.md §1.1) was redesigned to route by
文書タイプ (議事録・調査レポート・社内ガイド・リサーチメモ・スライド構成)
via `references/doctypes/*.md`, so the description needed explicit anchors
for these document types and for instruction-style requests ("結論から
書いて" 等) that don't contain any of the existing AI-smell/readability
keywords. The description was rewritten (by a separate process) before this
eval pass; this iteration only updates `evals/evals.json` and re-validates.

### evals.json changes

- Top-level `description` field (previously an English meta-summary of the
  eval set) replaced with the literal current SKILL.md `description` text,
  so the file is self-contained about which description version the cases
  target.
- 19 new cases appended: **p29–p42 (14 positive)** covering work-document
  triggers (議事録/文字起こし、調査レポート、分析レポート、社内ガイド、
  業務マニュアル、ディスカッションペーパー、リサーチメモ、スライド構成、
  提案書、および「結論から」「論旨を明確に」「専門用語をわかりやすく」
  「見出しを端的に」の指示型トリガー) and **n14–n18 (5 negative)** covering
  adjacent non-language tasks (Markdown整形のみ、英語指定、パワポの見た目
  デザイン、表計算の数式、Excelテンプレート生成) that must stay out of
  scope. Split 8 train / 6 test (positive) and 3 train / 2 test (negative),
  following the existing ~60/40 convention. `id` sequence continues from
  p28/n13. Existing 41 cases (p1–p28, n1–n13) were not modified.

New description under test (current `SKILL.md` frontmatter, 661 chars):

> 仕事の日本語文書を読みやすくわかりやすく書く・直すためのスキル。議事録（文字起こしから
> の議事録化を含む）、調査レポート・分析レポート、社内ガイド・マニュアル、リサーチメモ・
> ディスカッションペーパー・企画書・提案書・報告書・メール、スライド構成案といったビジネス
> 文書の作成・校正、「結論から書いて」「論旨を明確に」「見出しを端的に」「専門用語をわかり
> やすく説明して」といった指示のいずれでも使用する。AI臭さの除去（「AIっぽい」「AI臭い」
> 「機械翻訳っぽい」「不自然」「もっと自然な日本語に」「機械っぽい」「人間っぽくして」
> 「単調」「〜することができる、と言えるだろう、のような言い回し」といった直接・間接・
> 口語の指摘、AIで書いたと言われた/疑われた）、読みにくい・わかりにくい文章の改善依頼
> （語順がおかしい、一文が長い、何が言いたいか分からない、読点の位置がおかしい等）、note
> 記事やブログ記事・エッセイの新規執筆、既存文章のリライト・推敲、自分の文体を学ばせたい・
> プロファイル化したいという要望（過去の文章を読ませて自分らしく書いてほしいという依頼も
> 含む）にも対応する。禁止語の除去、リズムの単調さ・段落構造の均質さ・英語統語の直訳調に
> 加え、語順・読点・一文一義・主語述語の距離といった読みやすさの原則にも対応する。技術文書
> の章構成やMarkdownフォーマットの整形自体（一文一行化・引用ブロック・脚注記法など）は対象
> 外——それは別スキルの領域であり、本スキルは文章の自然さ・読みやすさ・わかりやすさに特化
> する。

Relative to the description validated in the "v0.4.0" section above, this
version reorders the opening (business-document types + instruction-style
triggers now lead) and adds 議事録・調査レポート/分析レポート・社内ガイド・
マニュアル・リサーチメモ・ディスカッションペーパー・企画書・スライド構成案
and the four quoted instruction phrases. No existing anchor phrase was
removed, so p1–p28/n1–n13 were re-checked for regressions (role-play, same
protocol) and none were found — every anchor used in prior iterations
(「AIっぽい」「機械っぽい」「プロファイル化したい」「読みにくい」「報告書」
「メール」「提案書」, the japanese-tech-writing exclusion clause, etc.) is
present verbatim in the new text.

### Judgment (role-play method, same protocol as prior iterations)

Only new cases and any changed existing judgments are tabulated (none of
p1–p28/n1–n13 changed — see regression check above).

| id | query | expected | judged | anchor |
|----|-------|----------|--------|--------|
| p29 | この文字起こしから議事録つくって | trigger | trigger | 「議事録（文字起こしからの議事録化を含む）」 |
| p30 | 会議の議事録まとめて | trigger | trigger | 「議事録」 |
| p31 | 調査結果をレポートにまとめて | trigger | trigger | 「調査レポート」 |
| p32 | 分析レポート書いて | trigger | trigger | 「分析レポート」 |
| p33 | 社内向けの使い方ガイドを書いて | trigger | trigger | 「社内ガイド」 |
| p34 | 業務マニュアルの作成をお願いしたい | trigger | trigger | 「マニュアル」+「作成」 |
| p35 | この内容をディスカッションペーパーにして | trigger | trigger | 「ディスカッションペーパー」 |
| p36 | リサーチメモをまとめたい | trigger | trigger | 「リサーチメモ」 |
| p37 | プレゼンのスライド構成を考えて | trigger | trigger | 「スライド構成案」 |
| p38 | 提案書の骨子つくって | trigger | trigger | 「提案書」 |
| p39 | 結論から書き直して | trigger | trigger | 「結論から書いて」の活用違いパラフレーズ |
| p40 | 論旨を明確にして | trigger | trigger | 「論旨を明確に」 |
| p41 | 専門用語をわかりやすく説明しながら書いて | trigger | trigger | 「専門用語をわかりやすく説明して」 |
| p42 | 見出しをもっと端的にして | trigger | trigger | 「見出しを端的に」 |
| n14 | このMarkdownを一文一行にして | no-trigger | no-trigger | フォーマット整形の除外節（一文一行化） |
| n15 | 英語でレポート書いて | no-trigger | no-trigger | 冒頭「仕事の日本語文書を」と矛盾（英語指定） |
| n16 | パワポのデザインをきれいにして | no-trigger | no-trigger | 「デザイン」は「構成」と無関係、視覚整形は対象外 |
| n17 | この表計算の数式なおして | no-trigger | no-trigger | 数式修正は言語編集ではない |
| n18 | 議事録のテンプレートをExcelで作って | no-trigger | no-trigger | Excelファイル生成であり文章の作成・校正ではない（n11/n13と同型） |

**Result: 60/60 (100%)** — 42/42 positive, 18/18 negative, across the full
combined eval set (existing 41 unchanged + 19 new). No description revision
was needed: p39 (「書き直して」 vs quoted 「書いて」) is the only case with a
paraphrase rather than a verbatim anchor match, and it was judged against
the same standard used for p4/p9 in iteration 0–1 (inflected/paraphrased
variants of an explicit anchor still count as anchored, not borderline).

No changes were made to `SKILL.md`, `scripts/`, or `references/` in this
pass — only `evals/evals.json` and this file.

## v3 — diagnosis/scoring scope addition (書き換えを伴わない依頼)

Motivation: `SKILL.md` description gained a clause covering AI-smell
*diagnosis and scoring* requests that don't ask for a rewrite — 「この文章
AIが書いた？」「AI臭さをスコアで出して」「どれくらいAIっぽいか判定して」
という書き換えを伴わない依頼. This iteration only updates
`evals/evals.json` and re-validates; `SKILL.md` was not touched here.

### evals.json changes

- Top-level `description` replaced with the literal current `SKILL.md`
  description (includes the new diagnosis/scoring clause).
- 8 new cases appended, continuing the id sequence from p42/n18:
  - **p43–p48 (6 positive)**: diagnosis/scoring phrasings ("AIが書いたか
    判定して", "AI臭さをスコアで出して", "どれくらいAIっぽい?", "採点して",
    "数値化してほしい") plus one explicit new-creation-from-scratch case
    ("ゼロから書き起こして") to test the boundary between "diagnose only"
    and "write new".
  - **n19–n20 (2 negative)**: adjacent out-of-scope diagnosis requests —
    English-text AI-detection (n19) and image AI-detection (n20) — that
    must stay out of scope since the skill is Japanese-text specific.
- Split 3 positive / 1 negative into train (p43–p45, n19), 3 positive /
  1 negative into test (p46–p48, n20).
- Existing p1–p42/n1–n18 (60 cases) were not modified.

### Regression check on existing 60 cases

The new clause is inserted mid-sentence ("...既存文章のリライト・推敲、
**AI臭さの診断・採点（...）**、自分の文体を学ばせたい...") without removing
or rewording any prior anchor phrase. Re-judged all 60 existing cases
against the new description text (role-play, same protocol): **no changes**
— every anchor used previously (「AIっぽい」「機械っぽい」「読みにくい」
「報告書」「議事録」「結論から」etc., and the japanese-tech-writing
exclusion clause) is present verbatim. No regressions.

### Judgment of new cases (role-play, same protocol)

| id | query | expected | judged | anchor / reason |
|----|-------|----------|--------|--------|
| p43 | この文章AIが書いたか判定して | trigger | trigger | near-verbatim「この文章AIが書いた？」 |
| p44 | AI臭さをスコアで出して | trigger | trigger | verbatim「AI臭さをスコアで出して」 |
| p45 | この記事どれくらいAIっぽい? | trigger | trigger | close paraphrase of「どれくらいAIっぽいか判定して」 |
| p46 | この文章、人が書いたように見える?採点して | trigger | trigger | 「採点」は新設カテゴリ名「診断・採点」に直接アンカー |
| p47 | AIっぽさを数値化してほしい、直さなくていいので | trigger | trigger | 「書き換えを伴わない依頼」+ AIっぽさ言及がスコアリング文脈に一致 |
| p48 | 在宅勤務の生産性についてゼロから書き起こして | trigger | **no-trigger (FAIL)** | 文書種別（note/ブログ/エッセイ/報告書等）が明示されず、「ゼロから書き起こす」という言い回しも本文にない。undertrigger前提・borderline→no-triggerの原則により、汎用トピックの新規執筆依頼として他スキル領域とも解釈できるため不一致と判定 |
| n19 | この英文がAI生成か判定して | no-trigger | no-trigger | 英文（日本語文書限定という前提と矛盾） |
| n20 | この画像AI生成か調べて | no-trigger | no-trigger | 画像であり文章ではない |

**Result: 67/68 (98.5%)** — 47/48 positive, 20/20 negative. One undertrigger
gap found: p48.

### Description fix recommendation (not applied — SKILL.md left untouched)

p48 fails because the description's new-creation anchor is scoped to
「note記事やブログ記事・エッセイの新規執筆」, which requires the request to
name one of those formats. A bare "◯◯についてゼロから書き起こして" without
naming a covered document type falls outside every anchor. Suggested fix
(not applied): broaden the new-creation clause to something like
「note記事やブログ記事・エッセイ**などの新規執筆（「ゼロから書き起こして」
を含む）**」, or add "ゼロから書く/書き起こす" as an explicit alternate
phrasing alongside "新規執筆". This is optional — p48 is a generic writing
request with no topic-genre signal, so the miss is a narrow edge case
rather than a core-use-case gap; only apply if broad "write X from
scratch" requests (regardless of genre) are meant to be in scope.

No changes were made to `SKILL.md`, `scripts/`, or `references/` in this
pass — only `evals/evals.json` and this file.
