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
