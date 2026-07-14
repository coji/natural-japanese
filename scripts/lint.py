# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "sudachipy>=0.6.8",
#     "sudachidict-core>=20240409",
# ]
# ///
"""lint.py — AI臭い日本語文章を決定的に検出する lint スクリプト。

設計思想（HANDOFF.md 参照）:
    「AI は自分自身の AI 臭さを認識できない」→ 機械的・決定的に検出して
    人間（または AI 自身の別セッション）に突きつけ、直すかどうかの判断は
    委ねる。これは CI ゲートではなく lint であるため、検出件数に関わらず
    exit code は常に 0 にする。
    ただし、これは「文章の中身」に関する判断を保留するという意味であり、
    ファイルが読めない・存在しない・ディレクトリが指定された等の
    「そもそも lint を実行できない」入力エラーとは区別する。
    入力エラーの場合はエラーメッセージを表示し、exit code 1 で終了する。

使い方:
    uv run scripts/lint.py <file.md> [--json]

実装メモ:
    - sudachipy の Tokenizer 生成（辞書ロード）は重いので、プロセス内で
      一度だけ生成し使い回す（lazy シングルトン、textcore.get_tokenizer）。
    - 文分割は「。」「！」「？」「\\n」を区切りとする簡易実装（textcore.split_sentences_with_lines）。
      厳密な文境界解析ではないが、決定的検出のプロトタイプとしてはこれで十分。
    - sudachi トークナイザ初期化・Markdown構造マスク・文分割・ファイル読み込みなどの
      共有基盤は textcore.py にある（scripts/outline.py, scripts/terms.py と共用）。
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import statistics
import sys
from pathlib import Path

from textcore import (
    Finding,
    SENTENCE_SPLIT_RE,
    _HEADING_RE,
    _LIST_ITEM_RE,
    get_tokenizer,
    iter_lines_with_no,
    iter_paragraphs_with_lines,
    mask_html_comments,
    mask_markdown_structure,
    read_source_file,
    split_sentences_with_lines,
)

# ---------------------------------------------------------------------------
# 辞書: 禁止語・LLM 常套句カタログ
# ここは「拡張前提」のカタログ。新しい手癖フレーズに気づいたら追記していく。
# 出典: HANDOFF.md 55-62行目、および note記事「禁止語60語超」の言及。
#
# 2026-07 コーパス校正（corpus/reports/archive/deep-analysis.md §4a）による見直し:
# 実コーパス（人間103文書 + AI 81文書）で forbidden_phrase 全体の文書発火率が
# human 58〜67% > ai 30〜33% と逆転していた。単語別ヒット数を見ると、
# 「最後に」（人間48回 vs AI 2回）と「まさに」（人間24回 vs AI 0回）の2語だけで
# 人間側ヒットの63%を占めており、これらは単なる日常語であって AI 特有の
# 手癖ではないと判明したため削除した（deep-analysis.md §5 の明示的な推奨）。
# 「重要なのは」「このように」「不可欠」「ポイントは」「さて、」は人間側でも
# 一定数ヒットする（人間6〜15回 vs AI 2回前後）ため削除まではせず、
# FORBIDDEN_PHRASES_WEAK_SIGNAL に移して severity を info に格下げしている
# （検出は残すが「重大な逆向きシグナル」としては扱わない）。
# 逆に「いかがでしょうか」「大切なのは」「根本的な」「まとめると」は
# AI側ヒットの方が優勢で、当初の設計意図どおりの語として warn のまま残す。
# ---------------------------------------------------------------------------
FORBIDDEN_PHRASES: list[str] = [
    # 結論の押し付け・まとめ口調
    "と言えるでしょう",
    "と言えるだろう",
    "と言えます",
    "ということになるでしょう",
    "のではないでしょうか",
    "重要なのは",
    "大切なのは",
    "ポイントは",
    "結論から言うと",
    "結論として",
    "いかがでしたか",
    "いかがでしょうか",
    # 「最後に」はコーパス校正で削除（人間48回 vs AI 2回、日常語であってAI手癖ではない）
    "まとめると",
    "総じて",
    # 過剰な強調・持ち上げ
    "非常に重要",
    "極めて重要",
    "言うまでもなく",
    "言うまでもありません",
    # 「まさに」はコーパス校正で削除（人間24回 vs AI 0回、日常語であってAI手癖ではない）
    "まさしく",
    # 定型導入・空疎な接続
    "さて、",
    "それでは、",
    "このように",
    "このような中",
    "ここで注目したいのは",
    "見ていきましょう",
    "紹介していきます",
    "解説していきます",
    "深掘りしていきます",
    # 予防線・免責的な言い回し
    "一概には言えません",
    "個人差がありますが",
    "あくまで一例ですが",
    # 正面から系（出典: japanese-tech-writing の規範から。中身の代わりに姿勢だけを宣言する）
    "正面から扱う",
    "正面から見る",
    "正面から書く",
    "正面から立てる",
    "正面から回収する",
    # 空虚な形容（出典: japanese-tech-writing の規範から。主張の中身を説明せず強調・網羅感だけ付ける）
    "不可欠",
    "核心的",
    "鍵となる",
    "根本的な",
    "多角的",
    "包括的",
    "総合的",
    # 空虚な動詞・予告口調（出典: japanese-tech-writing の規範から。何をどう書いたか示さず終わる）
    "掘り下げる",
    "深掘りする",
    "言語化する",
    "について見ていく",
    "を探求する",
]

# コーパス校正で「人間側でも一定数ヒットするため弱いシグナル」と判定した語。
# 削除はせず検出は残すが、severity を warn ではなく info に下げる
# （deep-analysis.md §4a: 人間6〜15回 vs AI 2回前後、比率は逆転していないが
# 絶対数として人間の日常的な使用がそれなりにある語）。
FORBIDDEN_PHRASES_WEAK_SIGNAL: set[str] = {
    "重要なのは",
    "このように",
    "不可欠",
    "ポイントは",
    "さて、",
}

# ---------------------------------------------------------------------------
# 辞書: 翻訳調パターン（英語直訳っぽい構文）
# ---------------------------------------------------------------------------
TRANSLATIONESE_PATTERNS: list[str] = [
    r"することができ(る|ます|た)",
    r"することが可能(です|だ|になる)",
    r"と言えるだろう",
    r"という点で",
    r"という観点(から|で)",
    r"にとって(重要|不可欠)",
    r"を持つ(こと|存在)",
    r"することによって",
    r"であることは間違いない",
    r"に他ならない",
]

# 段落頭に来ると「AI が構成を接続詞で誤魔化しがち」な語
PARAGRAPH_CONJUNCTIONS: list[str] = [
    "しかし",
    "また",
    "そして",
    "そのため",
    "さらに",
    "つまり",
    "一方",
    "一方で",
    "このように",
    "なぜなら",
    "したがって",
    "ただし",
]

# 否定→肯定対比の手癖パターン（正規表現）
ANTITHESIS_PATTERNS = [
    re.compile(r"ではなく、?.{0,30}"),
    re.compile(r"だけでなく.{0,10}も"),
]

# ---------------------------------------------------------------------------
# 検出器の閾値パラメータ（デフォルト値付きモジュールレベル定数）
#
# 各検出器のヒット判定に使う「回数/割合/最低サンプル数」の閾値を、関数内の
# リテラルではなくここに集約する。scripts/calibrate.py が閾値スイープで
# パラメータを変えて検出器を直接呼べるようにするための整理であり、
# ここに定義した値はすべて元のリテラルと同じ（CLI 挙動・検出結果は完全に不変）。
# 各検出関数は同名のキーワード引数でこれらをデフォルト値として受け取り、
# 呼び出し側から上書きできる。
# ---------------------------------------------------------------------------
ANTITHESIS_REPETITION_THRESHOLD = 3
# 2026-07 コーパス校正2（corpus/reports/antithesis-recalibration.md）: 絶対回数閾値
# （3回以上）だけで severity=critical を出す旧仕様は、長文書（例: 12,000文規模の
# 白書）では検出数が薄まって比率としてはノイズ同然でも critical 連打になる一方、
# 質の高い書き手の修辞技法（誤解を先に否定してから定義する等）にも無差別に発火して
# いた。実測（human quality:high、web+aozora、n=81）では絶対回数閾値ヒット率が
# 23.5%（19文書）に達したが、そのヒット文書の「検出数/総文数」比率分布は中央値
# 1.5%・90パーセンタイル2.4%・最大4.6%にとどまる。一方 AI 側のヒット文書
# （hits>=3、n=48）の比率分布は中央値8.3%・最小でも2.65%と、human とほぼ重ならない
# 分布を示した。この比率を使い、絶対回数閾値は維持しつつ severity を3段階化する:
# ratio < ANTITHESIS_RATE_INFO_BELOW は info（薄い比率＝人間の技法との区別がつかない）、
# ratio >= ANTITHESIS_RATE_CRITICAL_ABOVE は critical（高頻度＝真陽性の実測あり）、
# その中間は warn。閾値0.02/0.03で human 全体の critical化率は4.9%（<5%目標達成）。
# ただし tech ジャンルのみ human critical化率が11.1%と高く出たため、
# GENRE_PROFILES["tech"]["antithesis_rate_critical_above"] で0.045に緩めている
# （tech human critical化率は0%に低下、AI側もcritical 9/84 + warn 6/84 で検出は維持）。
ANTITHESIS_RATE_INFO_BELOW = 0.02
ANTITHESIS_RATE_CRITICAL_ABOVE = 0.03
SENTENCE_VARIANCE_MIN_SENTENCES = 5
SENTENCE_VARIANCE_CV_THRESHOLD = 0.25
NOMINAL_ENDING_MIN_SENTENCES = 5
# 2026-07 コーパス校正で検出方向を反転（corpus/reports/archive/deep-analysis.md §3, §4b）。
# 体言止めは AI の手癖ではなく人間の修辞技法で、essayジャンルでは人間60%が使う一方
# AIは0%（essay同ジャンル比較、n=50/37）。「多用」を警告する検出器としては
# 前提が誤りだったため、「長文なのに体言止めが1つもない」ことを人間的修辞の
# 欠如（AIらしさの一側面）として検出する方向に反転した。
# NOMINAL_ENDING_RATIO_THRESHOLD は「この比率以下なら欠如とみなす」閾値
# （反転前は「以上で警告」だった）。NOMINAL_ENDING_MIN_CHARS は
# 「~2000字ビンで human 67% vs ai 0%」という長さ依存の知見を踏まえたガード
# （短文書は人間でも体言止めがゼロなことが珍しくないため対象外にする）。
NOMINAL_ENDING_RATIO_THRESHOLD = 0.0
NOMINAL_ENDING_MIN_CHARS = 2000
PARAGRAPH_CONJ_MIN_PARAGRAPHS = 3
PARAGRAPH_CONJ_RATIO_THRESHOLD = 0.3
UNIFORM_PARAGRAPH_MIN_PARAGRAPHS = 4
UNIFORM_PARAGRAPH_CV_THRESHOLD = 0.15
# NESTED_ATTRIBUTIVE_THRESHOLD は 2026-07 コーパス校正で検出器ごと削除（弁別力なし）。
BURSTINESS_MIN_TOKENIZED = 6
# 2026-07 コーパス校正（corpus/reports/archive/sweep_low_burstiness.md）: 旧値-0.62では
# human/aiとも0%/0%で「無反応」だった。sweepで-0.9〜-0.2を走査した結果、
# -0.24で human FP率2.4%・AI検出率100.0%と、他の統計系検出器の中では唯一
# 弁別力を示したため、この値を採用する。ただしAI標本はn=3と極めて小さく、
# コーパス拡充後に再sweepして確定させる必要がある暫定値。
BURSTINESS_THRESHOLD = -0.24
AUTOCORR_MIN_XS = 4
AUTOCORR_THRESHOLD = 0.6
# 2026-07 コーパス校正で閾値を大幅に引き上げ、severityも格下げ（deep-analysis.md
# §3, §4）。文頭反復は human_web 93% vs ai 41%（文書発火率）と人間側で
# 圧倒的に多く、essay同ジャンルでも人間92% vs AI35%と逆転していた。
# 人間の書き手が意図的にリズムとして文頭を反復する技法と、AIの反復癖を
# この検出器だけでは区別できないため、閾値を3→6に引き上げて「明らかな
# 過剰反復」だけを拾うようにし、severityもwarnからinfoに下げて
# 判断材料の提示にとどめる。
NGRAM_LEAD_REPEAT_THRESHOLD = 6
NGRAM_TEMPLATE_MIN_COUNT = 6
NGRAM_TEMPLATE_RATIO_THRESHOLD = 0.4
LEXDIV_MIN_TOKENS = 30
TTR_THRESHOLD = 0.45
MTLD_THRESHOLD = 40
# 2026-07 コーパス校正（corpus/reports/archive/length_analysis.md）: TTRが意味のある
# 差を示すのは文書長4000字以上のビンのみ（それ未満は human/ai とも0%で無意味）。
LEXDIV_MIN_DOC_CHARS = 4000

# ---------------------------------------------------------------------------
# low_specificity（具体性/一般論臭）検出器のパラメータ
#
# Phase 3（HANDOFF.md 参照）: 「固有名詞・数値・実例がなく、抽象名詞ばかりの
# 段落」は、表層の禁止語や統語パターンとは別種のAI臭（＝素材不足のサイン）で、
# 既存の検出器では拾えない。段落単位で具体性シグナルを合成スコア化し、
# 閾値未満なら info で指摘する。
#
# 合成式: score = 固有名詞密度*重み + 数値密度*重み + 例示マーカー加点
#                - 抽象名詞率*重み
# 「密度」「率」は内容語（名詞/動詞/形容詞/副詞）数に対する割合。
# 閾値・重みはこの時点では暫定値であり、scripts/calibrate.py の corpus/ 校正
# （sweep --detector low_specificity）で確定させる前提（このコミット時点の値も
# 校正済み。閾値変更の経緯は corpus/reports/archive/sweep_low_specificity.md 参照）。
# ---------------------------------------------------------------------------
# 2026-07 コーパス校正（corpus/reports/archive/sweep_low_specificity.md、grid search
# ログはコミットしていないが手順は本ファイルのコメントに残す）: 当初の重み
# （proper=3.0, numeric=4.0, abstract=1.0, threshold=0.05）は human FP率が
# 46.6%（!）に達し、実用にならなかった。原因は「固有名詞も数値も例示マーカーも
# 一切ない段落」が多数を占め、それらが score=0 ちょうどに集中して閾値0付近で
# 一斉に発火していたため。閾値を負に大きくズラして「明確に抽象名詞が勝っている」
# 段落だけを拾うよう調整し、あわせて重みを小さくして score の分散を滑らかにした。
# 現在値は human FP率 3.9%（<5%目標達成）、AI全体検出率 7.4%、
# claude-haiku-4-5 サブセット検出率 5.9%（n=34）。
# 弁別力自体は他の校正済み検出器と比べて弱いが、コーパス標本数が小さい
# （human n=103, ai n=81）中での探索結果であり、コーパス拡充後に再校正すべき
# 暫定値として明示しておく。
LOW_SPECIFICITY_MIN_CHARS = 80
LOW_SPECIFICITY_MIN_CONTENT_WORDS = 15
LOW_SPECIFICITY_PROPER_NOUN_WEIGHT = 1.0
LOW_SPECIFICITY_NUMERIC_WEIGHT = 1.0
LOW_SPECIFICITY_EXAMPLE_MARKER_BONUS = 0.1
LOW_SPECIFICITY_ABSTRACT_NOUN_WEIGHT = 1.5
LOW_SPECIFICITY_SCORE_THRESHOLD = -0.15

# 形式名詞・抽象名詞のカタログ（拡張前提）。出典: HANDOFF.md の一般論臭の説明、
# および japanese-tech-writing の「空句」規範。辞書形（dictionary_form）で比較する。
#
# 「こと」「もの」「の」はコーパス校正で除外した: 出現頻度が極端に高く
# （human 82/103文書、ai 72/81文書で出現）、機能語に近い一般的な形式名詞のため
# 弁別力がない（corpus/reports/archive/sweep_low_specificity.md 参照）。
ABSTRACT_NOUN_WORDS: set[str] = {
    "側面",
    "観点",
    "重要性",
    "可能性",
    "あり方",
    "存在",
    "意味",
    "本質",
    "価値",
    "意義",
    "課題",
    "問題",
    "要素",
    "要因",
    "背景",
    "傾向",
    "姿勢",
    "視点",
    "概念",
    "特徴",
    "性質",
    "状況",
    "状態",
    "変化",
}

# 例示・具体化のマーカー語（段落中にあれば具体性の加点にする）
EXAMPLE_MARKER_WORDS: list[str] = [
    "たとえば",
    "例えば",
    "実際に",
    "実際には",
    "具体的には",
    "具体例として",
    "一例として",
    "先日",
    "昨日",
    "現に",
    "実例として",
]

# 数値・日付・単位付き数量の検出（半角/全角数字を単位・助数詞と一緒に拾う）
NUMERIC_QUANTITY_RE = re.compile(
    r"[0-9０-９]+"
    r"(年代|年間|世紀|年|月|日|時間|時|分|秒|人|円|%|％|kg|km|cm|mm|g|m|回|件|個|つ|割|倍|台|社|名|冊|本|杯|軒)?"
)

# ---------------------------------------------------------------------------
# --genre プロファイル（2026-07 コーパス校正で新設）
#
# deep-analysis.md はジャンル別（essay/tech/business）に人間・AI差の大きさが
# 異なることを示した: essay は nominal_ending・repeated_sentence_lead の逆転が
# 最も強く出るジャンル、tech は人間の書き手も見出し・箇条書き・太字を多用する
# ため AI との差が縮む傾向にある。business はコーパスが薄く
# （人間側n=10、AI側n=0）、単独でのプロファイル確定は時期尚早なので、
# 指示どおり tech と同じ値を使う。
# genre 未指定（デフォルト）はどのジャンルにも偏らない共通の保守的閾値
# （モジュール定数のデフォルト値そのもの）を使う。
# ---------------------------------------------------------------------------
GENRE_PROFILES: dict[str, dict] = {
    "essay": {
        # essayジャンルは体言止め欠如シグナルが最も強く出る（人間60% vs AI 0%）ため、
        # 共通閾値よりやや短い文書長からでも欠如を拾えるようにする。
        "nominal_min_chars": 1500,
        # essayも文頭反復の逆転が大きい（人間92% vs AI35%）ジャンルだが、
        # 依然として人間の意図的反復技法との区別はつかないため、共通閾値より
        # わずかに低いだけに留める（過検出を避ける）。
        "lead_repeat_threshold": 5,
    },
    "tech": {
        # tech記事は人間もAIも見出し・箇条書き構成に寄るため差が縮む。
        # 誤検知を避けるため共通閾値よりやや保守的（緩め）にする。
        "nominal_min_chars": 3000,
        "lead_repeat_threshold": 7,
        # antithesis_repetition の2026-07コーパス校正2（corpus/reports/
        # antithesis-recalibration.md）: tech ジャンルは共通閾値0.03だと
        # human quality:high の critical化率が11.1%（zennの技術記事2本）と
        # 目標の5%を超えたため、0.045に緩める（tech human critical化率0%に低下、
        # AI側もcritical 9/84 + warn 6/84 で検出は維持）。
        "antithesis_rate_critical_above": 0.045,
    },
    # business は 2026-07 の実地校正（corpus/reports/business-calibration.md）で
    # 実測した。人間側コーパスは corpus/human/web の biz-* 10件のみと薄いため、
    # 「AIで強く光る検出器を厳しくする」方向の調整はせず、事業文書の正当な慣習
    # （箇条書き・太字強調・定型見出し・フェーズ表現）と衝突しうる検出器は
    # 無効化するに留めている（詳細は上記レポート参照）。
    #   - nominal_min_chars: tech と同値（3000）を維持。実測では business
    #     コーパス（人間・AIとも）で nominal_ending が閾値に関わらず一度も
    #     発火しなかった（文書が短くAI/人間どちらの誤検知リスクも無い）ため、
    #     変更する実測的根拠がない。
    #   - lead_repeat_threshold: tech と同値（7）を維持。実測でこの値が
    #     human_business の誤検知（デフォルト閾値6で20%→閾値7で10%）を
    #     半減させつつ ai_business の検出率（4%）を落とさない局所最適点。
    #   - disabled_categories: high_bullet_ratio・high_bold_density・
    #     boilerplate_heading・numbered_phase_structure は、事業文書
    #     （報告書・提案書・議事録等）で箇条書き・太字強調・「まとめ」等の
    #     定型見出し・フェーズ/ステップ表現が正当に多用されるため、
    #     AI側の発火率がどうであれ business ジャンルでは無効化する。
    #     これらはいずれも EXPERIMENTAL_CATEGORIES に属し、デフォルトでは
    #     既に出力されない（--experimental 指定時のみ影響する）が、将来
    #     デフォルト化された場合の誤検知を防ぐため、ジャンル側でも明示的に
    #     無効化しておく。
    "business": {
        "nominal_min_chars": 3000,
        "lead_repeat_threshold": 7,
        "disabled_categories": {
            "high_bullet_ratio",
            "high_bold_density",
            "boilerplate_heading",
            "numbered_phase_structure",
        },
    },
}


def format_related_lines(related_lines: list[int]) -> str:
    """related_lines を人間可読の「対応箇所: L12, L34, ...」形式に整形する（重複除去・昇順ソート）。"""
    uniq_sorted = sorted(set(related_lines))
    return "対応箇所: " + ", ".join(f"L{n}" for n in uniq_sorted)


# ---------------------------------------------------------------------------
# --baseline 差分モード
#
# スキルの利用フローは「lint → 台帳に直した/残すを仕分け → 修正 → 再lint →
# 新規findingが出なくなるまで繰り返す」という収束駆動ループになっている。
# ループのたびに全件を目視で見比べるのは負担が大きいので、前回の --json 出力
# （baseline）と今回の結果を比較し、resolved（解消）/ new（新規）/
# persisting（継続）に分類する。
#
# 同一性キーの設計判断:
#   行番号は修正のたびに増減してズレるため、キーに含めない
#   （同じ指摘でも直した箇所より後ろの行が繰り上がるだけで「新規」扱いに
#   なってしまう）。excerpt は形態素境界のわずかな変化や、直した箇所の
#   前後の空白差などで完全一致しなくなることがあるため、正規化
#   （空白除去）した上で先頭 N 文字の前方一致とする。カテゴリ名は
#   検出器の種類そのものなので、そのまま等価比較に使う。
#   これは完全に正確な同一性判定ではないが、実装が単純で、
#   「同じ場所・同じ理由の指摘かどうか」の近似としては十分安定する。
# ---------------------------------------------------------------------------
_BASELINE_KEY_EXCERPT_PREFIX_LEN = 20

# 文書全体の統計量（burstiness・変動係数・TTR/MTLD 等）を excerpt に直接埋め込んでいる
# カテゴリ。これらは1文書につき高々1件しか出ない「集計そのもの」の finding であり、
# excerpt が「burstiness=-0.623 (...)」のように計算結果の数値そのものなので、
# 無関係な編集で文書の統計量がわずかに変化しただけで excerpt 文字列が変わり、
# 同一性キーに含めると「解消」＋「新規」の偽ペアが発生してしまう。
# このグループはカテゴリ名だけをキーにする（1文書1件が前提なので情報の欠落もない）。
#
# 一方、nominal_ending・repeated_sentence_lead・repeated_syntax_template・
# paragraph_lead_conjunction・antithesis_repetition は「文書全体集計型」ではあるが、
# excerpt 自体は実際にマッチした原文（体言止めの文末・反復した文頭など）であり、
# 数値は detail 側にしか出てこない（同一性キーは detail を見ていない）。
# これらは1文書内に複数の異なる該当箇所を持つのが普通なので、カテゴリ名だけに
# 潰さず、従来どおり excerpt の前方一致キーを使う方が精度が高い。
_CATEGORY_ONLY_KEY_CATEGORIES = {
    "low_burstiness",
    "high_length_autocorrelation",
    "low_sentence_variance",
    "uniform_paragraph_structure",
    "low_lexical_diversity_ttr",
    "low_lexical_diversity_mtld",
}


def _normalize_excerpt_for_key(excerpt: str) -> str:
    """excerpt を同一性キー用に正規化する（空白類を除去）。"""
    return re.sub(r"\s+", "", excerpt or "")


def _finding_identity_key(category: str, excerpt: str) -> tuple[str, str]:
    """(category, 正規化excerptの前方一致キー) を返す。行番号は含めない。
    _CATEGORY_ONLY_KEY_CATEGORIES に該当するカテゴリは excerpt を無視し、
    カテゴリ名のみをキーにする（理由は上のコメント参照）。
    """
    if category in _CATEGORY_ONLY_KEY_CATEGORIES:
        return (category, "")
    normalized = _normalize_excerpt_for_key(excerpt)
    return (category, normalized[:_BASELINE_KEY_EXCERPT_PREFIX_LEN])


def validate_baseline_data(baseline_data) -> tuple[dict | None, list[str]]:
    """--baseline で読み込んだ JSON の形を検証する。

    スキーマが想定外（トップレベルが dict でない、"findings" が配列でない、
    配列内の要素が dict でない等）でも compute_baseline_diff() をクラッシュ
    させたくないため、ここで軽量な検証を行い、
    - 完全に想定外の形なら (None, [警告メッセージ]) を返し、呼び出し側は
      baseline 比較そのものを諦めて通常の lint 実行にフォールバックする
      （graceful degradation。lint はそもそも CI ゲートではないので、
      baseline ファイルの不備で実行全体を落とすべきではない）
    - "findings" 配列の一部の要素だけが dict でない場合は、その要素だけを
      読み飛ばして残りで比較を続行する
    """
    warnings: list[str] = []
    if not isinstance(baseline_data, dict):
        warnings.append(
            "--baseline の内容が JSON オブジェクトではありません。baseline比較を無視して通常のlintを実行します。"
        )
        return None, warnings

    findings_raw = baseline_data.get("findings")
    if not isinstance(findings_raw, list):
        warnings.append(
            "--baseline に 'findings' 配列が見つかりません。baseline比較を無視して通常のlintを実行します。"
        )
        return None, warnings

    valid_findings = []
    skipped = 0
    for item in findings_raw:
        # dict であることに加え、_finding_identity_key() が触るフィールドの型も
        # ここで検証する（category が非文字列だと set 判定、excerpt が非文字列だと
        # re.sub がクラッシュするため。JSON としては valid でも型が壊れた baseline
        # は要素単位で読み飛ばす）。
        if (
            isinstance(item, dict)
            and isinstance(item.get("category"), str)
            and isinstance(item.get("excerpt"), str)
        ):
            valid_findings.append(item)
        else:
            skipped += 1
    if skipped:
        warnings.append(
            f"--baseline の findings 配列内に不正な要素が{skipped}件あったため読み飛ばしました。"
        )
    return {"findings": valid_findings}, warnings


def compute_baseline_diff(
    findings: list[Finding], baseline_data: dict
) -> tuple[list[dict], dict[str, int]]:
    """今回の findings と、前回の --json 出力（baseline_data、事前に
    validate_baseline_data() を通した想定）を比較する。

    各 Finding の `.status` を "new"（今回のみ）または "persisting"
    （両方に存在）に破壊的に設定する。baseline にしかない finding は
    「resolved（解消）」として別途リストで返す（対応する現在の Finding
    オブジェクトが存在しないため、baseline の生 dict のまま返す）。

    多重集合としてマッチングする（同じキーの finding が複数あっても、
    件数分だけ 1 対 1 で対応付ける）ため、同じ指摘が複数箇所にある
    ケースでも resolved/persisting の件数がズレない。
    """
    from collections import defaultdict

    baseline_findings = baseline_data.get("findings", [])
    baseline_by_key: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for bf in baseline_findings:
        key = _finding_identity_key(bf.get("category", ""), bf.get("excerpt", ""))
        baseline_by_key[key].append(bf)

    for f in findings:
        key = _finding_identity_key(f.category, f.excerpt)
        bucket = baseline_by_key.get(key)
        if bucket:
            bucket.pop(0)
            f.status = "persisting"
        else:
            f.status = "new"

    resolved = [bf for bucket in baseline_by_key.values() for bf in bucket]

    summary = {
        "resolved": len(resolved),
        "new": sum(1 for f in findings if f.status == "new"),
        "persisting": sum(1 for f in findings if f.status == "persisting"),
    }
    return resolved, summary



# ---------------------------------------------------------------------------
# 各検出器
# ---------------------------------------------------------------------------


def _raw_or_masked(raw_lines_by_no: dict[int, str] | None, no: int, fallback: str) -> str:
    """行番号に対応する原文行を返す（無ければマスク済み行にフォールバック）。"""
    if raw_lines_by_no is None:
        return fallback
    return raw_lines_by_no.get(no, fallback)


def detect_forbidden_phrases(
    lines: list[tuple[int, str]], raw_lines_by_no: dict[int, str] | None = None
) -> list[Finding]:
    """マスク済み行（コードスパン等を空白化したテキスト）でパターンマッチし、
    excerpt は同じオフセットで原文行から切り出す（マスクは解析専用、表示は原文）。
    """
    findings = []
    for no, line in lines:
        raw_line = _raw_or_masked(raw_lines_by_no, no, line)
        for phrase in FORBIDDEN_PHRASES:
            idx = line.find(phrase)
            if idx != -1:
                start = max(0, idx - 10)
                end = idx + len(phrase) + 10
                excerpt = raw_line[start:end] if len(raw_line) >= end else line[start:end]
                is_weak_signal = phrase in FORBIDDEN_PHRASES_WEAK_SIGNAL
                severity = "info" if is_weak_signal else "warn"
                detail = f"禁止語/LLM常套句ヒット: 「{phrase}」"
                if is_weak_signal:
                    detail += "（コーパス校正で人間側にも一定数出現する弱いシグナルと判定、severity低下）"
                findings.append(
                    Finding(
                        line=no,
                        category="forbidden_phrase",
                        excerpt=excerpt.strip(),
                        severity=severity,
                        detail=detail,
                    )
                )
    return findings


def detect_translationese(
    lines: list[tuple[int, str]], raw_lines_by_no: dict[int, str] | None = None
) -> list[Finding]:
    findings = []
    for no, line in lines:
        raw_line = _raw_or_masked(raw_lines_by_no, no, line)
        for pat in TRANSLATIONESE_PATTERNS:
            for m in re.finditer(pat, line):
                start = max(0, m.start() - 10)
                end = m.end() + 10
                excerpt = raw_line[start:end] if len(raw_line) >= end else line[start:end]
                findings.append(
                    Finding(
                        line=no,
                        category="translationese",
                        excerpt=excerpt.strip(),
                        severity="info",
                        detail=f"翻訳調パターン: /{pat}/ に一致",
                    )
                )
    return findings


def detect_antithesis_repetition(
    lines: list[tuple[int, str]],
    raw_lines_by_no: dict[int, str] | None = None,
    threshold: int = ANTITHESIS_REPETITION_THRESHOLD,
    rate_info_below: float = ANTITHESIS_RATE_INFO_BELOW,
    rate_critical_above: float = ANTITHESIS_RATE_CRITICAL_ABOVE,
) -> list[Finding]:
    """「〜ではなく、〜」「〜だけでなく〜も」を文書全体で数え、threshold回（デフォルト3回）
    以上なら反復として検出する。

    2026-07 コーパス校正2（corpus/reports/antithesis-recalibration.md、モジュール定数
    ANTITHESIS_RATE_INFO_BELOW / ANTITHESIS_RATE_CRITICAL_ABOVE のコメントも参照）:
    出現ごとに severity=critical を付けていた旧仕様は、長文書での薄い頻度でも
    critical が連打されノイズ化する一方、人間の意図的な修辞技法にも無差別に発火して
    いた。「検出数/総文数」の比率で severity を3段階化する: 比率が低ければ info
    （人間の技法との区別がつかない参考情報）、高ければ critical（実測で真陽性が
    多い高頻度パターン）、その中間は warn。

    どの文同士が反復としてカウントされたか追えるよう、全ヒット行番号を
    related_lines / detail の両方に含める。excerpt は原文から切り出す。
    """
    hits: list[tuple[int, str, str]] = []  # (line_no, matched_excerpt(raw), pattern_name)
    for no, line in lines:
        raw_line = _raw_or_masked(raw_lines_by_no, no, line)
        for pat in ANTITHESIS_PATTERNS:
            for m in re.finditer(pat, line):
                excerpt = raw_line[m.start() : m.end()] if len(raw_line) >= m.end() else m.group(0)
                hits.append((no, excerpt, pat.pattern))

    findings = []
    if len(hits) >= threshold:
        # 文書全体の総文数に対する検出数の比率で severity を決める（絶対回数の閾値
        # 判定とは別に、比率が文書の長さに関わらず一貫した「密度」の指標になる）。
        total_sentences = len(split_sentences_with_lines(lines, raw_lines_by_no))
        ratio = len(hits) / total_sentences if total_sentences else 0.0
        if ratio < rate_info_below:
            severity = "info"
        elif ratio >= rate_critical_above:
            severity = "critical"
        else:
            severity = "warn"

        all_lines = [no for no, _, _ in hits]
        related = format_related_lines(all_lines)
        for no, text, patname in hits:
            findings.append(
                Finding(
                    line=no,
                    category="antithesis_repetition",
                    excerpt=text.strip(),
                    severity=severity,
                    detail=(
                        f"否定→肯定対比パターンが文書内で{len(hits)}回検出（閾値{threshold}回以上、"
                        f"総文数に対する比率={ratio:.1%}）。{related}"
                    ),
                    related_lines=all_lines,
                )
            )
    return findings



def detect_low_sentence_length_variance(
    sentences: list[tuple[int, str, str]],
    threshold: float = SENTENCE_VARIANCE_CV_THRESHOLD,
    min_sentences: int = SENTENCE_VARIANCE_MIN_SENTENCES,
) -> list[Finding]:
    """文長（文字数）の変動係数（CV = 標準偏差/平均）が閾値未満なら
    「文長が均質すぎる = リズムが単調 = AI臭い」として警告する。
    最低5文以上ないと統計的に意味がないので判定しない。
    """
    lengths = [len(s) for _, s, _ in sentences if len(s) > 0]
    if len(lengths) < min_sentences:
        return []
    mean = statistics.mean(lengths)
    if mean == 0:
        return []
    stdev = statistics.pstdev(lengths)
    cv = stdev / mean
    if cv < threshold:
        first_line = sentences[0][0] if sentences else 1
        return [
            Finding(
                line=first_line,
                category="low_sentence_variance",
                excerpt=f"文数={len(lengths)}, 平均文長={mean:.1f}字, 変動係数={cv:.3f}",
                severity="warn",
                detail=f"文長の変動係数が閾値({threshold})未満。リズムが均質でAI臭い可能性",
            )
        ]
    return []


NOUN_ENDING_POS = {"名詞"}
TRAILING_SYMBOL_POS = {"補助記号", "空白"}

# 語彙多様性計測の対象とする内容語 POS
CONTENT_WORD_POS = {"名詞", "動詞", "形容詞", "副詞"}

# 「無生物主語+他動詞」判定で「主語になっても不自然でない代名詞」として許可する語。
# sudachipy は「この事実」「そのこと」を単一形態素にせず複数形態素
# （例:「この」+「事実」）に分割するため、単一形態素の表層文字列と比較する
# 判定では到達不可能。単一形態素で成立する語だけをここに残し、
# 複数形態素にまたがる語は ABSTRACT_PRONOUN_PHRASES で別途、
# 隣接形態素を連結して比較する。
ABSTRACT_PRONOUNS = {"これ", "それ", "あれ", "それら"}
# 2形態素にまたがる指示表現（連結した表層文字列で比較する）
ABSTRACT_PRONOUN_PHRASES = {"この事実", "そのこと"}
# 述語側: 直訳調でよく使われる他動詞的な動詞（辞書は拡張前提）
TRANSITIVE_SMELL_VERBS = {
    "もたらす",
    "示す",
    "意味する",
    "証明する",
    "生み出す",
    "反映する",
    "示唆する",
    "物語る",
    "浮き彫りにする",
    "後押しする",
}


@dataclasses.dataclass
class TokenizedSentence:
    line: int
    text: str  # マスク済みテキスト（形態素解析・パターンマッチ用）
    morphemes: list  # sudachipy.MorphemeList の要素（text を解析した結果）
    raw_text: str = ""  # 原文（レポートのexcerpt表示は必ずこちらを使う）


def tokenize_sentences(sentences: list[tuple[int, str, str]]) -> list[TokenizedSentence]:
    """文ごとに一度だけ形態素解析し、以後の検出器で使い回す（辞書ロードとトークナイズの
    コストを最小化するための共有キャッシュ）。
    形態素解析はマスク済みテキスト（text）に対して行うが、レポート表示用の原文
    （raw_text、インラインコードスパンのバッククォート内文字列などを含む）も保持し、
    excerpt はそちらから切り出す。
    """
    tokenizer = get_tokenizer()
    from sudachipy import SplitMode

    result = []
    for no, sent, raw_sent in sentences:
        if not sent:
            continue
        morphemes = list(tokenizer.tokenize(sent, SplitMode.C))
        result.append(TokenizedSentence(line=no, text=sent, morphemes=morphemes, raw_text=raw_sent or sent))
    return result


def _strip_trailing_symbols(morphemes: list) -> list:
    """文末の記号（」など）を除いた実質的な最終形態素列を返す。"""
    i = len(morphemes)
    while i > 0 and morphemes[i - 1].part_of_speech()[0] in TRAILING_SYMBOL_POS:
        i -= 1
    return morphemes[:i]


def detect_nominal_ending_and_paragraph_conjunctions(
    lines: list[tuple[int, str]],
    tokenized: list[TokenizedSentence],
    raw_lines_by_no: dict[int, str] | None = None,
    nominal_min_sentences: int = NOMINAL_ENDING_MIN_SENTENCES,
    nominal_ratio_threshold: float = NOMINAL_ENDING_RATIO_THRESHOLD,
    nominal_min_chars: int = NOMINAL_ENDING_MIN_CHARS,
    conj_min_paragraphs: int = PARAGRAPH_CONJ_MIN_PARAGRAPHS,
    conj_ratio_threshold: float = PARAGRAPH_CONJ_RATIO_THRESHOLD,
    uniform_min_paragraphs: int = UNIFORM_PARAGRAPH_MIN_PARAGRAPHS,
    uniform_cv_threshold: float = UNIFORM_PARAGRAPH_CV_THRESHOLD,
) -> tuple[list[Finding], dict]:
    """sudachipy で形態素解析し、
    1) 体言止めの「欠如」（長文なのに体言止めが1つもない = 人間的修辞の欠如）
    2) 段落頭の接続詞率
    を計測する。stats も返す（JSON用）。

    体言止め検出はコーパス校正（2026-07）で方向を反転した。反転前は
    「体言止めが多い」ことを AI 臭として警告していたが、実コーパスでは
    体言止めは人間側の方が圧倒的に多く使う修辞技法（essay同ジャンルで
    人間60% vs AI 0%）だったため、前提が逆だった。現在は「ある程度の
    長さの文書なのに体言止めが1つもない」ことを、人間的な修辞技法の欠如
    （AIらしさの一側面）として info レベルで示す。
    """
    nominal_ending_count = 0
    total_sentences = 0
    total_chars = 0
    last_line = 1

    for ts in tokenized:
        total_sentences += 1
        total_chars += len(ts.raw_text)
        last_line = ts.line
        effective = _strip_trailing_symbols(ts.morphemes)
        if not effective:
            continue
        last = effective[-1]
        pos = last.part_of_speech()[0]
        # 体言止め: 実質的な最終形態素が名詞（助動詞「だ/です」等が続かない）場合
        if pos in NOUN_ENDING_POS:
            nominal_ending_count += 1

    ratio = nominal_ending_count / total_sentences if total_sentences else 0.0

    findings = []
    if (
        total_sentences >= nominal_min_sentences
        and total_chars >= nominal_min_chars
        and ratio <= nominal_ratio_threshold
    ):
        # 「欠如」の検出なので、体言止めの文自体は存在しない。指摘対象の1文を
        # 指させないため、文書末尾の行に1件だけ finding を出す（一覧性重視）。
        findings.append(
            Finding(
                line=last_line,
                category="nominal_ending",
                excerpt=f"体言止め0件（全{total_sentences}文、約{total_chars}字）",
                severity="info",
                detail=(
                    "この文書には体言止めが1つもない。ある程度の長さの文書で"
                    "この修辞技法が皆無なのはAI文章に特徴的（コーパス実測: "
                    "essayジャンルで人間60% vs AI 0%が体言止めを使用）。"
                    "人間的な修辞の欠如の疑い"
                ),
            )
        )

    # 段落頭の接続詞率
    # 段落を行番号付きでグルーピングすることで、段落開始行が直接分かる
    # （re.split + テキスト検索による line_cursor 近似だと、同一内容の段落が
    # 複数回登場したときに誤帰属していたため、行ベースの分割に置き換えた）。
    paragraphs = iter_paragraphs_with_lines(lines)
    conj_paragraph_count = 0
    total_paragraphs = len(paragraphs)
    conj_findings = []
    sentence_counts_per_paragraph = []
    for para_lines in paragraphs:
        first_no, first_line_raw = para_lines[0]
        first_line_text = first_line_raw.strip()
        para_joined = "\n".join(t for _, t in para_lines)
        sentence_counts_per_paragraph.append(
            len([p for p in SENTENCE_SPLIT_RE.split(para_joined) if p.strip()])
        )
        for conj in PARAGRAPH_CONJUNCTIONS:
            if first_line_text.startswith(conj):
                conj_paragraph_count += 1
                conj_findings.append((first_no, first_line_text, conj))
                break

    conj_ratio = conj_paragraph_count / total_paragraphs if total_paragraphs else 0.0
    if total_paragraphs >= conj_min_paragraphs and conj_ratio >= conj_ratio_threshold:
        conj_lines = [no for no, _, _ in conj_findings]
        related = format_related_lines(conj_lines)
        for no, text_line, conj in conj_findings:
            excerpt_source = _raw_or_masked(raw_lines_by_no, no, text_line)
            findings.append(
                Finding(
                    line=no,
                    category="paragraph_lead_conjunction",
                    excerpt=excerpt_source[:40],
                    severity="info",
                    detail=(
                        f"段落頭が接続詞「{conj}」で始まる（文書全体の段落頭接続詞率={conj_ratio:.1%}、"
                        f"閾値{conj_ratio_threshold:.0%}以上で警告）。{related}"
                    ),
                    related_lines=conj_lines,
                )
            )

    # 段落構造の均質性: AI は「3文段落」を量産しがち。段落あたり文数の変動係数が
    # 極端に低い（＝どの段落もほぼ同じ文数）場合は定型段落の疑いとして警告する。
    para_structure_stats = {
        "paragraph_sentence_counts": sentence_counts_per_paragraph,
        "paragraph_sentence_count_cv": None,
    }
    if len(sentence_counts_per_paragraph) >= uniform_min_paragraphs:
        p_mean = statistics.mean(sentence_counts_per_paragraph)
        p_std = statistics.pstdev(sentence_counts_per_paragraph)
        p_cv = (p_std / p_mean) if p_mean else 0.0
        para_structure_stats["paragraph_sentence_count_cv"] = p_cv
        if p_cv < uniform_cv_threshold:
            findings.append(
                Finding(
                    line=1,
                    category="uniform_paragraph_structure",
                    excerpt=f"段落数={len(sentence_counts_per_paragraph)}, 各段落の文数={sentence_counts_per_paragraph}",
                    severity="info",
                    detail=(
                        f"段落あたり文数の変動係数={p_cv:.3f}（閾値{uniform_cv_threshold}未満）。"
                        "どの段落もほぼ同じ文数=定型段落（例: 3文段落の量産）の疑い"
                    ),
                )
            )

    stats = {
        "total_sentences": total_sentences,
        "nominal_ending_count": nominal_ending_count,
        "nominal_ending_ratio": ratio,
        "total_paragraphs": total_paragraphs,
        "paragraph_lead_conjunction_count": conj_paragraph_count,
        "paragraph_lead_conjunction_ratio": conj_ratio,
        **para_structure_stats,
    }
    return findings, stats


def detect_translationese_morph(tokenized: list[TokenizedSentence]) -> list[Finding]:
    """品詞列で「こと（名詞）+ が/は（助詞）+ でき〜（動詞、"でき"始まりの活用形）」の並びを
    検出する、翻訳調「〜することができる」の品詞列版。
    表層の正規表現（TRANSLATIONESE_PATTERNS）と違い、直前の動詞部分の送り仮名や
    活用（〜することができる/〜出来ます/〜出来た 等）の表記揺れに影響されない。
    注意: 「こと」の前に本当に動詞（〜する）が来ているかまでは確認していない
    （「このことができる」のような非対象ケースを完全には除外できない）。
    """
    findings = []
    for ts in tokenized:
        surfaces = [m.surface() for m in ts.morphemes]
        poss = [m.part_of_speech()[0] for m in ts.morphemes]
        n = len(ts.morphemes)
        for i in range(n):
            # 「こと」(名詞) + が/は(助詞) + でき(動詞語幹)... の並びを探す
            if surfaces[i] == "こと" and poss[i] == "名詞":
                j = i + 1
                if j < n and poss[j] == "助詞" and surfaces[j] in {"が", "は"}:
                    k = j + 1
                    if k < n and poss[k] == "動詞" and surfaces[k].startswith("でき"):
                        # excerptは形態素のbegin/end（マスク済みテキスト内オフセット）を使い、
                        # 原文（raw_text）から同じ位置を切り出す（インラインコードスパンの
                        # バッククォート内文字列が欠落しないようにするため）。
                        span_start = ts.morphemes[max(0, i - 4)].begin()
                        span_end = ts.morphemes[k].end()
                        excerpt = ts.raw_text[span_start:span_end]
                        findings.append(
                            Finding(
                                line=ts.line,
                                category="translationese_morph",
                                excerpt=excerpt,
                                severity="info",
                                detail="品詞列マッチ: 名詞/動詞+こと+が/は+できる型の翻訳調構文",
                            )
                        )
    return findings


# 拗音を作る小書き文字（ャュョァィゥェォヮ）。「キャ」のように直前の文字と
# 合わせて1モーラを構成するため、単純な文字数カウントだと過大カウントになる。
# 促音（ッ）・長音（ー）は独立した1モーラとして数えるため、ここには含めない。
_SMALL_KANA_MERGE = set("ァィゥェォャュョヮ")


def mora_length(morphemes: list) -> int:
    """読み（カタカナ）を基にモーラ数の近似値を計算する。
    拗音の小書き文字（ャュョ等）は直前の文字と合算して1モーラとして数える
    補正を行うが、それ以外の長音・促音等の厳密な処理まではしていない。
    """
    total = 0
    for m in morphemes:
        reading = m.reading_form() or m.surface()
        count = 0
        for ch in reading:
            if ch in _SMALL_KANA_MERGE and count > 0:
                # 直前の文字と合わせて1モーラなので、追加でカウントしない
                continue
            count += 1
        total += count
    return total


def detect_rhythm_statistics(
    tokenized: list[TokenizedSentence],
    min_tokenized: int = BURSTINESS_MIN_TOKENIZED,
    burstiness_threshold: float = BURSTINESS_THRESHOLD,
    autocorr_min_xs: int = AUTOCORR_MIN_XS,
    autocorr_threshold: float = AUTOCORR_THRESHOLD,
) -> tuple[list[Finding], dict]:
    """文字数だけでなくモーラ近似長を使い、単純な変動係数に加えて
    burstiness（(σ-μ)/(σ+μ)）と隣接文長の自己相関（lag-1）を計測する。
    - burstiness が負に大きい ≈ 文長が均一（AI的）
    - 自己相関が高い ≈ 「短い文の後は短い文」というリズムパターンが固定化している
    """
    if len(tokenized) < min_tokenized:
        return [], {}

    mora_lengths = [mora_length(ts.morphemes) for ts in tokenized]
    mean = statistics.mean(mora_lengths)
    std = statistics.pstdev(mora_lengths)

    findings = []
    burstiness = (std - mean) / (std + mean) if (std + mean) else 0.0

    # lag-1 自己相関（ピアソン相関を1つずらした系列同士で計算）
    xs = mora_lengths[:-1]
    ys = mora_lengths[1:]
    autocorr = None
    if len(xs) >= autocorr_min_xs and statistics.pstdev(xs) > 0 and statistics.pstdev(ys) > 0:
        mx, my = statistics.mean(xs), statistics.mean(ys)
        cov = sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / len(xs)
        autocorr = cov / (statistics.pstdev(xs) * statistics.pstdev(ys))

    # 閾値 -0.62: このスキルの原則は「自然な人間の文章で誤検知しない」こと。
    # 人間が書いた自然な文章（fixtures/natural.md 相当）でも burstiness は
    # -0.55 前後まで下がることが実測で分かっている（モーラ計算の拗音補正後の実測値）。
    # -0.55 ちょうどを閾値にすると、その実測値のごく僅かな変動で人間の文章にまで
    # 誤検知するため、マージンを取って -0.62 まで緩めている。
    if burstiness < burstiness_threshold:
        findings.append(
            Finding(
                line=tokenized[0].line,
                category="low_burstiness",
                excerpt=f"burstiness={burstiness:.3f} (モーラ近似長 平均={mean:.1f}, 標準偏差={std:.1f})",
                severity="warn",
                detail=f"burstiness が閾値({burstiness_threshold})未満。文の長短のメリハリが乏しく機械的なリズムの疑い",
            )
        )

    if autocorr is not None and autocorr > autocorr_threshold:
        findings.append(
            Finding(
                line=tokenized[0].line,
                category="high_length_autocorrelation",
                excerpt=f"lag-1 自己相関={autocorr:.3f}",
                severity="info",
                detail=f"隣接する文の長さが強く相関（閾値{autocorr_threshold}超）。文長パターンが単調に繰り返されている疑い",
            )
        )

    stats = {
        "mora_mean": mean,
        "mora_stdev": std,
        "burstiness": burstiness,
        "length_autocorrelation_lag1": autocorr,
    }
    return findings, stats



# 文頭反復の severity 判定: 固有名詞・製品名/技術用語（ラテン文字主体の表層）が
# 文頭に来る場合は「そして」「また」のような定型導入の使い回しとは性質が異なり、
# 技術文書では自然な反復（例: 「Cloudflareは」「better-authが」）なので
# severity を warn ではなく info に下げる（検出自体は残し、判断材料として提示する）。
_LATIN_TECH_TOKEN_RE = re.compile(r"^[A-Za-z][A-Za-z0-9\-_.]*$")


def _is_proper_noun_or_tech_term(morpheme) -> bool:
    """先頭形態素が固有名詞、またはラテン文字・数字主体（製品名/ライブラリ名等）かを判定する。
    カタカナ語は一般語（「クラウド」「システム」等）も多く誤って severity を下げるリスクが
    高いため、ここでは対象外とする（迷ったら対象外でよい、という方針）。
    """
    pos = morpheme.part_of_speech()
    surface = morpheme.surface()
    is_proper_noun = pos[0] == "名詞" and pos[1] == "固有名詞"
    is_latin_tech = bool(_LATIN_TECH_TOKEN_RE.match(surface))
    return is_proper_noun or is_latin_tech


def detect_ngram_repetition(
    tokenized: list[TokenizedSentence],
    lead_repeat_threshold: int = NGRAM_LEAD_REPEAT_THRESHOLD,
    template_min_count: int = NGRAM_TEMPLATE_MIN_COUNT,
    template_ratio_threshold: float = NGRAM_TEMPLATE_RATIO_THRESHOLD,
) -> tuple[list[Finding], dict]:
    """
    1) 文頭2形態素（表層形）の n-gram が3回以上繰り返される
       → 「そして、」「また、」のような定型導入の使い回し
       ただし先頭形態素が固有名詞・ラテン文字主体の技術用語（製品名/ライブラリ名等）の
       場合は技術文書として自然な反復なので severity を info に下げる（検出自体は残す）。
    2) 文頭のPOS 4-gram（品詞の粗い並び）の一致率が高い
       → 語彙は違っても構文テンプレートが同じ（AIにありがちな構造の使い回し）
    をそれぞれ検出する。
    """
    from collections import Counter

    findings = []

    lead_bigrams = []
    for ts in tokenized:
        lead_morphemes = ts.morphemes[:2]
        surfaces = [m.surface() for m in lead_morphemes]
        if len(surfaces) == 2:
            is_tech_lead = _is_proper_noun_or_tech_term(lead_morphemes[0])
            lead_bigrams.append((ts.line, ts.raw_text, "".join(surfaces), is_tech_lead))

    bigram_counter = Counter(text for _, _, text, _ in lead_bigrams)
    for bigram, count in bigram_counter.items():
        if count >= lead_repeat_threshold:
            bigram_lines = [no for no, _, text, _ in lead_bigrams if text == bigram]
            related = format_related_lines(bigram_lines)
            for no, sent, text, is_tech_lead in lead_bigrams:
                if text == bigram:
                    # コーパス校正により、人間の意図的な反復と区別できないため
                    # severity は常に info（判断材料の提示にとどめる。detail 参照）。
                    severity = "info"
                    if is_tech_lead:
                        detail = (
                            f"文頭2形態素「{bigram}」が{count}回反復（閾値{lead_repeat_threshold}回以上）。"
                            f"固有名詞/技術用語由来の可能性が高い。{related}"
                        )
                    else:
                        detail = (
                            f"文頭2形態素「{bigram}」が{count}回反復（閾値{lead_repeat_threshold}回以上）。"
                            f"人間の意図的な反復技法との区別がつかないため参考情報として提示。{related}"
                        )
                    findings.append(
                        Finding(
                            line=no,
                            category="repeated_sentence_lead",
                            excerpt=sent[:20],
                            severity=severity,
                            detail=detail,
                            related_lines=bigram_lines,
                        )
                    )

    lead_pos_ngrams = []
    for ts in tokenized:
        pos_seq = tuple(m.part_of_speech()[0] for m in ts.morphemes[:4])
        if len(pos_seq) == 4:
            lead_pos_ngrams.append((ts.line, ts.raw_text, pos_seq))

    total_with_ngram = len(lead_pos_ngrams)
    pos_counter = Counter(seq for _, _, seq in lead_pos_ngrams)
    stats = {"lead_pos_4gram_top": None, "lead_pos_4gram_ratio": None}
    if total_with_ngram >= template_min_count and pos_counter:
        top_seq, top_count = pos_counter.most_common(1)[0]
        ratio = top_count / total_with_ngram
        stats["lead_pos_4gram_top"] = "/".join(top_seq)
        stats["lead_pos_4gram_ratio"] = ratio
        if ratio >= template_ratio_threshold:
            template_lines = [no for no, _, seq in lead_pos_ngrams if seq == top_seq]
            related = format_related_lines(template_lines)
            for no, sent, seq in lead_pos_ngrams:
                if seq == top_seq:
                    findings.append(
                        Finding(
                            line=no,
                            category="repeated_syntax_template",
                            excerpt=sent[:20],
                            severity="info",
                            detail=(
                                f"文頭品詞4-gram「{'/'.join(top_seq)}」が全文の{ratio:.1%}で一致"
                                f"（閾値{template_ratio_threshold:.0%}以上）。構文テンプレートの使い回しの疑い。{related}"
                            ),
                            related_lines=template_lines,
                        )
                    )

    return findings, stats


def compute_mtld(tokens: list[str], threshold: float = 0.72) -> float | None:
    """MTLD（Measure of Textual Lexical Diversity）の簡易実装。
    文長に依存しにくい語彙多様性指標。TTR が threshold を下回るごとに
    「1ファクター」を数え、前方・後方2方向の平均をとる。
    """
    if len(tokens) < 20:
        return None

    def factors_one_direction(seq: list[str]) -> float:
        factor_count = 0
        types: set[str] = set()
        token_count = 0
        for tok in seq:
            types.add(tok)
            token_count += 1
            ttr = len(types) / token_count
            if ttr <= threshold:
                factor_count += 1
                types = set()
                token_count = 0
        # 端数分を部分ファクターとして加算
        if token_count > 0:
            types_ttr = len(types) / token_count if token_count else 1.0
            partial = (1 - types_ttr) / (1 - threshold) if types_ttr < 1 else 0.0
            factor_count += min(partial, 1.0)
        return len(seq) / factor_count if factor_count > 0 else float(len(seq))

    forward = factors_one_direction(tokens)
    backward = factors_one_direction(list(reversed(tokens)))
    return (forward + backward) / 2


def detect_lexical_diversity(
    tokenized: list[TokenizedSentence],
    min_tokens: int = LEXDIV_MIN_TOKENS,
    ttr_threshold: float = TTR_THRESHOLD,
    mtld_threshold: float = MTLD_THRESHOLD,
    min_doc_chars: int = LEXDIV_MIN_DOC_CHARS,
) -> tuple[list[Finding], dict]:
    """内容語（名詞/動詞/形容詞/副詞）の基本形を対象に TTR と MTLD を計測する。
    語彙が使い回されている（AIが同じ言い回しをループしがち）と TTR/MTLD が低くなる。

    2026-07 コーパス校正（corpus/reports/archive/length_analysis.md）: TTR は文書長
    ~4000字未満のビンではhuman/aiとも一律0%で、統計として機能していない
    ことが判明した。4000字以上のビンで初めて意味のある差（human 77%）が
    出るため、文書全体の文字数が min_doc_chars 未満の場合は「文書が短いため
    未評価」として明示的にスキップする（閾値ではなく適用条件でガードする、
    という報告書の推奨に沿った実装）。
    """
    content_tokens = []
    total_doc_chars = sum(len(ts.raw_text) for ts in tokenized)
    for ts in tokenized:
        for m in ts.morphemes:
            if m.part_of_speech()[0] in CONTENT_WORD_POS:
                content_tokens.append(m.dictionary_form())

    findings = []
    stats = {
        "ttr": None,
        "mtld": None,
        "content_token_count": len(content_tokens),
        "doc_char_count": total_doc_chars,
        "skipped_too_short": False,
    }
    if total_doc_chars < min_doc_chars:
        stats["skipped_too_short"] = True
        return findings, stats
    if len(content_tokens) >= min_tokens:
        ttr = len(set(content_tokens)) / len(content_tokens)
        mtld = compute_mtld(content_tokens)
        stats["ttr"] = ttr
        stats["mtld"] = mtld
        if ttr < ttr_threshold:
            findings.append(
                Finding(
                    line=tokenized[0].line,
                    category="low_lexical_diversity_ttr",
                    excerpt=f"TTR={ttr:.3f} (内容語 {len(content_tokens)} 語中 {len(set(content_tokens))} 種類)",
                    severity="info",
                    detail=f"TTR(Type-Token Ratio)が閾値{ttr_threshold}未満。同じ語彙の使い回しが多い疑い",
                )
            )
        if mtld is not None and mtld < mtld_threshold:
            findings.append(
                Finding(
                    line=tokenized[0].line,
                    category="low_lexical_diversity_mtld",
                    excerpt=f"MTLD={mtld:.1f}",
                    severity="info",
                    detail=f"MTLD が閾値{mtld_threshold}未満。文章長で正規化した語彙多様性が低い疑い",
                )
            )
    return findings, stats


def detect_low_specificity(
    lines: list[tuple[int, str]],
    raw_lines_by_no: dict[int, str] | None = None,
    min_chars: int = LOW_SPECIFICITY_MIN_CHARS,
    min_content_words: int = LOW_SPECIFICITY_MIN_CONTENT_WORDS,
    proper_noun_weight: float = LOW_SPECIFICITY_PROPER_NOUN_WEIGHT,
    numeric_weight: float = LOW_SPECIFICITY_NUMERIC_WEIGHT,
    example_marker_bonus: float = LOW_SPECIFICITY_EXAMPLE_MARKER_BONUS,
    abstract_noun_weight: float = LOW_SPECIFICITY_ABSTRACT_NOUN_WEIGHT,
    score_threshold: float = LOW_SPECIFICITY_SCORE_THRESHOLD,
) -> tuple[list[Finding], dict]:
    """段落単位で「具体性の欠如（一般論臭）」を検出する。

    固有名詞密度・数値/日付出現率・例示マーカーの有無を「具体性シグナル」として
    加点し、形式名詞・抽象名詞率を減点した合成スコアが閾値未満の段落を拾う。
    短い段落は誰が書いてもある程度抽象的になりうるため、文字数・内容語数の
    両方が最低ラインを超えた段落だけを判定対象にする（gate）。

    これは文体（言い回し）の問題ではなく、段落を支える固有名詞・数値・一次情報
    そのものが足りていない「素材不足」のサインであるため、detail では
    書き直しではなく情報収集を検討するよう促す
    （references/revision-guide.md の「素材不足の分岐」参照）。
    """
    tokenizer = get_tokenizer()
    from sudachipy import SplitMode

    findings: list[Finding] = []
    paragraphs = iter_paragraphs_with_lines(lines)
    evaluated = 0
    fired = 0

    for para_lines in paragraphs:
        first_no, _ = para_lines[0]
        para_masked = "\n".join(t for _, t in para_lines)
        para_chars = len(para_masked)
        if para_chars < min_chars:
            continue

        # sudachipy は1回のtokenize呼び出しに約49KBのバイト数上限があるため、
        # 段落が長大な場合（青空文庫の長い段落等）に備えて行単位で分割して
        # トークナイズし、結果を連結する（行番号・オフセットは形態素解析後は
        # 使わないため連結して問題ない）。
        morphemes = []
        for _, para_line in para_lines:
            if not para_line.strip():
                continue
            morphemes.extend(tokenizer.tokenize(para_line, SplitMode.C))
        content_words = [m for m in morphemes if m.part_of_speech()[0] in CONTENT_WORD_POS]
        if len(content_words) < min_content_words:
            continue

        evaluated += 1

        proper_noun_count = sum(
            1 for m in content_words if m.part_of_speech()[0] == "名詞" and m.part_of_speech()[1] == "固有名詞"
        )
        abstract_noun_count = sum(
            1
            for m in content_words
            if m.part_of_speech()[0] == "名詞" and m.dictionary_form() in ABSTRACT_NOUN_WORDS
        )
        numeric_hit_count = len(list(NUMERIC_QUANTITY_RE.finditer(para_masked)))
        has_example_marker = any(marker in para_masked for marker in EXAMPLE_MARKER_WORDS)

        n_content = len(content_words)
        proper_noun_density = proper_noun_count / n_content
        numeric_density = numeric_hit_count / n_content
        abstract_noun_ratio = abstract_noun_count / n_content

        score = (
            proper_noun_density * proper_noun_weight
            + numeric_density * numeric_weight
            + (example_marker_bonus if has_example_marker else 0.0)
            - abstract_noun_ratio * abstract_noun_weight
        )

        if score < score_threshold:
            fired += 1
            excerpt_source = _raw_or_masked(raw_lines_by_no, first_no, para_lines[0][1])
            findings.append(
                Finding(
                    line=first_no,
                    category="low_specificity",
                    excerpt=excerpt_source.strip()[:40],
                    severity="info",
                    detail=(
                        f"段落の具体性スコア={score:.3f}（閾値{score_threshold}未満）。"
                        f"固有名詞密度={proper_noun_density:.3f}, 数値密度={numeric_density:.3f}, "
                        f"抽象名詞率={abstract_noun_ratio:.3f}, 例示マーカー={'あり' if has_example_marker else 'なし'}。"
                        "固有名詞・数値・実例が乏しく一般論に留まっている疑い。"
                        "素材不足のサインであり、文体の修正でなく情報収集を検討する"
                        "（revision-guide.md の素材不足の分岐を参照）"
                    ),
                )
            )

    stats = {
        "paragraphs_evaluated": evaluated,
        "paragraphs_fired": fired,
    }
    return findings, stats


# nested_attributive（連体修飾の入れ子検出）は 2026-07 コーパス校正で削除した。
# sweep_nested_attributive.md: 閾値1〜6のどの値でも人間FP率が5%を切らず
# （閾値3で人間85.4%が発火、AIも100%発火。閾値6まで緩めても人間51.2%が発火）、
# deep-analysis.md でも essay同ジャンルで人間100% vs AI 92〜100%とほぼ差がない
# 「全発火・弁別力なし」と判定された。閾値調整では救えないノイズだったため、
# 検出器そのものと専用ヘルパー（旧 build_line_to_paragraph_map）を削除している。
# 経緯は references/translationese.md の該当節にも記載。

# ---------------------------------------------------------------------------
# 英語統語の検出（挑戦枠）
# ---------------------------------------------------------------------------

# 無生物主語（＋こと/事実など形式名詞化）+ 他動詞的な述語、という
# 「英語を日本語に直訳した構文」のシグナルをまず正規表現で粗く拾う。
# sudachipy で主語の生物性判定を厳密にやるのは困難なため、
# 「これ/それ/この事実/〜こと/〜という事実」+ 「は/が」+ 文末近くの
# 他動詞（〜を〜する系）という表層パターンでヒューリスティックに検出する。
INANIMATE_SUBJECT_PATTERNS = [
    re.compile(r"(これ|それ|この事実|そのこと)(は|が).{0,40}(もたらす|示す|意味する|証明する|生み出す|反映する)"),
    re.compile(r".{0,20}(こと|事実)(は|が).{0,40}(もたらす|示す|意味する|証明する|生み出す|反映する)"),
]

# 「それは〜である。なぜなら〜だ」構文（隣接する2文にまたがるので
# 文リストを走査して検出する）
CLEFT_BECAUSE_HEAD = re.compile(r"^(それ|これ|この)は.{0,60}(である|だ)$")
BECAUSE_HEAD = re.compile(r"^(なぜなら|というのも)")


def detect_english_syntax_smell(
    lines: list[tuple[int, str]], raw_lines_by_no: dict[int, str] | None = None
) -> list[Finding]:
    findings = []
    for no, line in lines:
        raw_line = _raw_or_masked(raw_lines_by_no, no, line)
        for pat in INANIMATE_SUBJECT_PATTERNS:
            for m in re.finditer(pat, line):
                excerpt = raw_line[m.start() : m.end()] if len(raw_line) >= m.end() else m.group(0)
                findings.append(
                    Finding(
                        line=no,
                        category="english_syntax_inanimate_subject",
                        excerpt=excerpt,
                        severity="info",
                        detail="無生物主語+他動詞的述語（表層パターン、英語統語の直訳調の可能性、要人間判断）",
                    )
                )

    # マスク済みテキストで構文マッチしつつ、excerpt は原文の文（raw）から組み立てる
    sentences = split_sentences_with_lines(lines, raw_lines_by_no)
    for i in range(len(sentences) - 1):
        no1, s1, r1 = sentences[i]
        no2, s2, r2 = sentences[i + 1]
        if CLEFT_BECAUSE_HEAD.match(s1) and BECAUSE_HEAD.match(s2):
            findings.append(
                Finding(
                    line=no1,
                    category="english_syntax_cleft_because",
                    excerpt=f"{r1}。{r2}",
                    severity="warn",
                    detail="「それは〜である。なぜなら〜だ」型の強調構文（英語 It is ... because ... の直訳調）",
                )
            )
    return findings


def detect_inanimate_subject_morph(tokenized: list[TokenizedSentence]) -> list[Finding]:
    """品詞列ベースで「無生物主語(抽象代名詞/形式名詞) + が/は + 他動詞的述語」を検出する。
    厳密な生物性判定（有情/非情の意味論）は sudachipy の POS だけでは困難なため、
    「これ/それ/この事実」等の抽象指示語、または「〜こと/〜という事実」のような
    形式名詞化された主語に限定して、他動詞辞書（TRANSITIVE_SMELL_VERBS）とマッチする
    述語が同一文内に現れる場合のみ検出する。表層正規表現版より活用の揺れに強い。
    """
    findings = []
    for ts in tokenized:
        surfaces = [m.surface() for m in ts.morphemes]
        poss = [m.part_of_speech()[0] for m in ts.morphemes]
        dict_forms = [m.dictionary_form() for m in ts.morphemes]
        n = len(ts.morphemes)
        # 2形態素の指示表現（例:「この事実」）を「この」で先にマッチさせた場合、
        # 続く「事実」単体も形式名詞として再マッチしてしまい、同じ箇所が
        # 二重に検出されてしまう。skip_until でその形態素インデックスまでの
        # 単独マッチを抑制する。
        skip_until = -1
        for i in range(n):
            if i <= skip_until:
                continue
            # 単一形態素で成立する指示語・形式名詞
            is_abstract_subject = surfaces[i] in ABSTRACT_PRONOUNS or (
                poss[i] == "名詞" and surfaces[i] in {"こと", "事実", "の"}
            )
            subject_end = i
            if not is_abstract_subject:
                # 2形態素にまたがる指示表現（「この」+「事実」等）を、
                # 隣接する形態素を連結した表層文字列で判定する
                if i + 1 < n and (surfaces[i] + surfaces[i + 1]) in ABSTRACT_PRONOUN_PHRASES:
                    is_abstract_subject = True
                    subject_end = i + 1
            if not is_abstract_subject:
                continue
            skip_until = max(skip_until, subject_end)
            j = subject_end + 1
            if j >= n or poss[j] != "助詞" or surfaces[j] not in {"が", "は"}:
                continue
            # 主語マーカーの後、文末までの間に直訳調の他動詞があるか探す
            for k in range(j + 1, n):
                if poss[k] == "動詞" and dict_forms[k] in TRANSITIVE_SMELL_VERBS:
                    # excerptはbegin/end（マスク済みテキスト内オフセット）を使い、
                    # 原文（raw_text）から同じ位置を切り出す
                    span_start = ts.morphemes[max(0, i - 3)].begin()
                    span_end = ts.morphemes[k].end()
                    excerpt = ts.raw_text[span_start:span_end]
                    subject_text = "".join(surfaces[i : subject_end + 1])
                    findings.append(
                        Finding(
                            line=ts.line,
                            category="inanimate_subject_morph",
                            excerpt=excerpt,
                            severity="info",
                            detail=(
                                f"品詞列マッチ: 抽象主語「{subject_text}」+ {surfaces[j]} "
                                f"+ 他動詞的述語「{dict_forms[k]}」（英語統語の直訳調の疑い）"
                            ),
                        )
                    )
                    break
    return findings


# ---------------------------------------------------------------------------
# 構造層検出器（2026-07 コーパス校正で新設）
#
# ここまでの検出器はすべて Markdown 構造をマスクした「地の文」に対して働く。
# しかし deep-analysis.md §4c の5文書精読では、AI 生成文（特に claude-haiku-4-5
# のtech系）に「太字の多用」「番号付きフェーズ構造」「『まとめ』『おわりに』
# 定型見出しでの締め」といった、文章そのものではなく Markdown 構造レベルの
# 教科書的な癖が繰り返し観測された。この一群は逆にマスク前の raw テキストを
# 見る必要があるため、run_lint() 内で mask_markdown_structure() より前に
# 呼び出す専用の検出器ファミリーとして新設する。
#
# 注意: この一群はまだ deep-analysis.md の定量コーパス計測を経ておらず、
# 5文書の質的観察のみが根拠（暫定閾値）。EXPERIMENTAL_CATEGORIES に含めて
# デフォルト無効化し、--experimental フラグを付けたときだけ有効にする。
# ---------------------------------------------------------------------------
BOLD_SPAN_RE = re.compile(r"\*\*[^*\n]+\*\*")
BOLD_DENSITY_PER_1000_THRESHOLD = 3.0
BULLET_LINE_RATIO_THRESHOLD = 0.35
BULLET_LINE_MIN_LINES = 10
# 「まとめ」「おわりに」等の定型見出し（本文の中身ではなく予告的な構成の型を示す）
BOILERPLATE_HEADING_WORDS = {
    "まとめ",
    "おわりに",
    "終わりに",
    "さいごに",
    "最後に",
    "結論",
    "総括",
    "conclusion",
}
NUMBERED_PHASE_RE = re.compile(r"(フェーズ|ステップ|段階|ステージ)\s*[0-90-9１-９]")
NUMBERED_PHASE_MIN_COUNT = 3
# 絵文字・装飾記号（代表的なものに限定。厳密な Unicode 絵文字判定は行わない）
EMOJI_SYMBOL_RE = re.compile(
    "[\U0001F300-\U0001FAFF☀-➿⭐✅❌❗❓]"
)
EMOJI_SYMBOL_PER_1000_THRESHOLD = 2.0


def detect_structural_ai_habits(raw_text: str) -> tuple[list[Finding], dict]:
    """マスク前の raw テキストに対して、Markdown 構造レベルの「教科書的AI癖」を検出する。
    太字密度・箇条書き行比率・定型見出し・番号付きフェーズ構造・絵文字/装飾記号密度の
    5種類。すべて severity="info"、EXPERIMENTAL カテゴリ扱い（デフォルト無効）。
    """
    findings: list[Finding] = []
    raw_lines = iter_lines_with_no(raw_text)
    total_chars = len(raw_text) or 1

    # 1) 太字密度
    bold_hits = list(BOLD_SPAN_RE.finditer(raw_text))
    bold_per_1000 = len(bold_hits) / total_chars * 1000
    if bold_per_1000 >= BOLD_DENSITY_PER_1000_THRESHOLD and len(bold_hits) >= 3:
        first_line = raw_text[: bold_hits[0].start()].count("\n") + 1
        findings.append(
            Finding(
                line=first_line,
                category="high_bold_density",
                excerpt=f"太字スパン{len(bold_hits)}箇所（1000字あたり{bold_per_1000:.2f}）",
                severity="info",
                detail=(
                    f"太字（**...**）の使用密度が閾値（1000字あたり{BOLD_DENSITY_PER_1000_THRESHOLD}）"
                    "以上。強調の多用は教科書的なAI生成文に見られる傾向（実験的検出器、閾値は暫定）"
                ),
            )
        )

    # 2) 箇条書き行比率
    non_blank_lines = [(no, line) for no, line in raw_lines if line.strip()]
    bullet_lines = [no for no, line in non_blank_lines if _LIST_ITEM_RE.match(line)]
    if len(non_blank_lines) >= BULLET_LINE_MIN_LINES:
        bullet_ratio = len(bullet_lines) / len(non_blank_lines)
        if bullet_ratio >= BULLET_LINE_RATIO_THRESHOLD:
            findings.append(
                Finding(
                    line=bullet_lines[0] if bullet_lines else 1,
                    category="high_bullet_ratio",
                    excerpt=f"箇条書き行{len(bullet_lines)}/{len(non_blank_lines)}行（{bullet_ratio:.1%}）",
                    severity="info",
                    detail=(
                        f"箇条書き行の比率が閾値{BULLET_LINE_RATIO_THRESHOLD:.0%}以上。"
                        "文章より箇条書きに頼る構成は教科書的なAI生成文に見られる傾向（実験的検出器）"
                    ),
                    related_lines=bullet_lines if len(bullet_lines) > 1 else None,
                )
            )

    # 3) 定型見出し（「まとめ」「おわりに」等）
    boilerplate_lines = []
    for no, line in iter_lines_with_no(raw_text):
        m = _HEADING_RE.match(line)
        if not m:
            continue
        heading_text = line[m.end() :].strip().lower()
        for word in BOILERPLATE_HEADING_WORDS:
            if heading_text.startswith(word.lower()):
                boilerplate_lines.append((no, line.strip(), word))
                break
    for no, line_text, word in boilerplate_lines:
        findings.append(
            Finding(
                line=no,
                category="boilerplate_heading",
                excerpt=line_text[:40],
                severity="info",
                detail=(
                    f"定型見出し「{word}」系での締め。予告・構成の型のみで中身を語らない"
                    "教科書的なAI生成文に見られる傾向（実験的検出器）"
                ),
            )
        )

    # 4) 番号付きフェーズ構造（「フェーズ1」「ステップ2」等が3回以上）
    phase_hits = list(NUMBERED_PHASE_RE.finditer(raw_text))
    if len(phase_hits) >= NUMBERED_PHASE_MIN_COUNT:
        first_line = raw_text[: phase_hits[0].start()].count("\n") + 1
        findings.append(
            Finding(
                line=first_line,
                category="numbered_phase_structure",
                excerpt=f"番号付きフェーズ表現が{len(phase_hits)}回出現",
                severity="info",
                detail=(
                    f"「フェーズ/ステップ/段階+番号」の表現が閾値{NUMBERED_PHASE_MIN_COUNT}回以上。"
                    "機械的な段階分割は教科書的なAI生成文に見られる傾向（実験的検出器）"
                ),
            )
        )

    # 5) 絵文字・装飾記号の密度
    emoji_hits = list(EMOJI_SYMBOL_RE.finditer(raw_text))
    emoji_per_1000 = len(emoji_hits) / total_chars * 1000
    if emoji_per_1000 >= EMOJI_SYMBOL_PER_1000_THRESHOLD and len(emoji_hits) >= 3:
        first_line = raw_text[: emoji_hits[0].start()].count("\n") + 1
        findings.append(
            Finding(
                line=first_line,
                category="high_emoji_symbol_density",
                excerpt=f"絵文字/装飾記号{len(emoji_hits)}箇所（1000字あたり{emoji_per_1000:.2f}）",
                severity="info",
                detail=(
                    f"絵文字・装飾記号の使用密度が閾値（1000字あたり{EMOJI_SYMBOL_PER_1000_THRESHOLD}）"
                    "以上（実験的検出器、閾値は暫定）"
                ),
            )
        )

    stats = {
        "bold_span_count": len(bold_hits),
        "bold_per_1000_chars": bold_per_1000,
        "bullet_line_count": len(bullet_lines),
        "non_blank_line_count": len(non_blank_lines),
        "boilerplate_heading_count": len(boilerplate_lines),
        "numbered_phase_hit_count": len(phase_hits),
        "emoji_symbol_count": len(emoji_hits),
        "emoji_symbol_per_1000_chars": emoji_per_1000,
    }
    return findings, stats


# ---------------------------------------------------------------------------
# メイン処理
# ---------------------------------------------------------------------------

# 2026-07 コーパス校正で「無反応」（human/aiともにほぼ0%発火）と判定された
# 検出器（corpus/reports/archive/deep-analysis.md §3, §5）。sweepで閾値を緩めても
# low_burstiness 以外は弁別力を示す根拠データがまだない（sweepレポート未生成）ため、
# 削除はせず「実験的（experimental）」としてデフォルト無効化する。
# 加えて、新設の構造層検出器（high_bold_density 等）もまだ定量校正前なので
# 同様に実験的カテゴリに含める。
# --experimental フラグを付けたときだけ、これらのカテゴリの finding を残す。
EXPERIMENTAL_CATEGORIES: set[str] = {
    "high_length_autocorrelation",
    "paragraph_lead_conjunction",
    "repeated_syntax_template",
    "english_syntax_cleft_because",
    "high_bold_density",
    "high_bullet_ratio",
    "boilerplate_heading",
    "numbered_phase_structure",
    "high_emoji_symbol_density",
}


def run_lint(
    raw_text: str, genre: str | None = None, experimental: bool = False
) -> tuple[list[Finding], dict]:
    """genre: "essay" | "tech" | "business" | None。指定するとジャンル別に校正した
    閾値プロファイル（GENRE_PROFILES）を適用する。指定しない場合（デフォルト）は
    共通の保守的な閾値（モジュール定数のデフォルト値）を使う。
    experimental: True にすると EXPERIMENTAL_CATEGORIES（まだ定量校正前、または
    無反応と判定された検出器）の finding も出力する。デフォルトは False で、
    それらは stats/findings から除外される。
    """
    profile = GENRE_PROFILES.get(genre, {})

    # --- 構造層検出器は Markdown マスクより前のテキストを解析するが、HTML コメント内の
    # 太字・番号付きフェーズ・絵文字を誤検知しないよう、HTML コメントのみを同じ長さの
    # 空白に置換したテキストを渡す（行番号・オフセットは raw_text と一致するため、
    # 検出器内で raw_text から excerpt を切り出す既存ロジックはそのまま使える）。
    structural_findings, structural_stats = detect_structural_ai_habits(mask_html_comments(raw_text))

    # Markdown の構造行（見出し/リスト/コードブロック/引用/表）とインラインコードスパンは
    # 文章として扱わず、行番号を保ったままマスクしてから解析用テキストとして使う。
    # ただし excerpt（レポート表示）は必ず raw_text（原文）から同じオフセットで切り出す。
    # マスクは「解析専用」であり、表示用ではないことに注意。
    text = mask_markdown_structure(raw_text)
    lines = iter_lines_with_no(text)
    raw_lines_by_no = dict(iter_lines_with_no(raw_text))
    sentences = split_sentences_with_lines(lines, raw_lines_by_no)
    # sudachipy の形態素解析結果は複数の検出器で使い回す（トークナイズは1回だけ）。
    tokenized = tokenize_sentences(sentences)

    findings: list[Finding] = []
    findings += structural_findings
    # --- 表層（正規表現）ベースの検出器 ---
    findings += detect_forbidden_phrases(lines, raw_lines_by_no)
    findings += detect_translationese(lines, raw_lines_by_no)
    findings += detect_antithesis_repetition(
        lines,
        raw_lines_by_no,
        rate_critical_above=profile.get("antithesis_rate_critical_above", ANTITHESIS_RATE_CRITICAL_ABOVE),
    )
    findings += detect_low_sentence_length_variance(sentences)
    findings += detect_english_syntax_smell(lines, raw_lines_by_no)

    # --- 形態素解析ベースの検出器（拡張: 品詞列・活用形マッチ） ---
    nominal_and_conj_findings, morph_stats = detect_nominal_ending_and_paragraph_conjunctions(
        lines,
        tokenized,
        raw_lines_by_no,
        nominal_min_chars=profile.get("nominal_min_chars", NOMINAL_ENDING_MIN_CHARS),
    )
    findings += nominal_and_conj_findings
    findings += detect_translationese_morph(tokenized)
    findings += detect_inanimate_subject_morph(tokenized)
    # nested_attributive はコーパス校正で削除済み（上のコメント参照）。

    rhythm_findings, rhythm_stats = detect_rhythm_statistics(tokenized)
    findings += rhythm_findings

    ngram_findings, ngram_stats = detect_ngram_repetition(
        tokenized,
        lead_repeat_threshold=profile.get("lead_repeat_threshold", NGRAM_LEAD_REPEAT_THRESHOLD),
    )
    findings += ngram_findings

    lexdiv_findings, lexdiv_stats = detect_lexical_diversity(tokenized)
    findings += lexdiv_findings

    low_spec_findings, low_spec_stats = detect_low_specificity(lines, raw_lines_by_no)
    findings += low_spec_findings

    # EXPERIMENTAL_CATEGORIES はデフォルトでは除外する（--experimental でのみ出力）。
    if not experimental:
        findings = [f for f in findings if f.category not in EXPERIMENTAL_CATEGORIES]

    # ジャンルプロファイルによるカテゴリ単位の無効化（現状 business のみ使用）。
    # --experimental を付けて実験的カテゴリを表示させた場合でも、そのジャンルの
    # 正当な文書慣習と衝突すると判定された検出器はここで確実に除外する。
    disabled_categories = profile.get("disabled_categories", set())
    if disabled_categories:
        findings = [f for f in findings if f.category not in disabled_categories]

    findings.sort(key=lambda f: f.line)

    stats = {
        "total_findings": len(findings),
        "by_category": {},
        "genre": genre,
        "experimental": experimental,
        **morph_stats,
        "rhythm": rhythm_stats,
        "ngram": ngram_stats,
        "lexical_diversity": lexdiv_stats,
        "structural": structural_stats,
        "low_specificity": low_spec_stats,
    }
    for f in findings:
        stats["by_category"][f.category] = stats["by_category"].get(f.category, 0) + 1

    return findings, stats


SEVERITY_LABEL = {"info": "情報", "warn": "警告", "critical": "重大"}


STATUS_LABEL = {"new": "新規", "persisting": "継続"}


def print_human_report(
    path: Path,
    findings: list[Finding],
    stats: dict,
    baseline_summary: dict[str, int] | None = None,
) -> None:
    print(f"=== lint: {path} ===")
    print(f"検出件数: {stats['total_findings']}")
    if stats["by_category"]:
        print("カテゴリ別内訳:")
        for cat, count in sorted(stats["by_category"].items(), key=lambda kv: -kv[1]):
            print(f"  - {cat}: {count}")

    # --baseline 指定時のみ、解消/新規/継続のサマリを追加表示する
    # （--baseline なしの場合はこのブロックごと出力されず、既存の挙動と完全に同じ）。
    if baseline_summary is not None:
        print(
            f"ベースライン比較: 解消: {baseline_summary['resolved']}件 / "
            f"新規: {baseline_summary['new']}件 / "
            f"継続: {baseline_summary['persisting']}件"
        )
    print()

    if not findings:
        print("検出なし。")
        return

    for f in findings:
        label = SEVERITY_LABEL.get(f.severity, f.severity)
        # baseline比較時は各行に新規/継続タグを付ける（比較しない場合は付けない＝従来どおり）
        status_tag = f"[{STATUS_LABEL.get(f.status, f.status)}] " if f.status else ""
        print(f"{status_tag}[{label}] L{f.line} ({f.category})")
        print(f"    該当箇所: {f.excerpt}")
        if f.detail:
            # 「対応箇所: L12, L34, ...」（related_lines）は detail 文字列に既に
            # 含めているため、人間可読レポートでは detail をそのまま表示すれば十分。
            print(f"    詳細    : {f.detail}")
        print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="AI臭い日本語文章を決定的に検出する lint スクリプト（CI ゲートではない）。"
    )
    parser.add_argument("file", type=Path, help="lint 対象の Markdown/テキストファイル")
    parser.add_argument("--json", action="store_true", help="機械可読な JSON で出力する")
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        metavar="PREV.json",
        help=(
            "前回の --json 出力ファイルと比較し、resolved（解消）/ new（新規）/ "
            "persisting（継続）を判定する（収束駆動の修正ループ支援。指定しない場合の"
            "挙動は完全に不変）"
        ),
    )
    parser.add_argument(
        "--genre",
        choices=sorted(GENRE_PROFILES),
        default=None,
        help=(
            "文書のジャンルに応じてコーパス校正済みの閾値プロファイルを適用する"
            "（essay/tech/business）。未指定時は共通の保守的閾値を使う"
        ),
    )
    parser.add_argument(
        "--experimental",
        action="store_true",
        help=(
            "まだコーパスで定量校正されていない、または無反応と判定された検出器"
            "（EXPERIMENTAL_CATEGORIES）も出力する。デフォルトでは除外される"
        ),
    )
    args = parser.parse_args()

    # 「文章の中身に関する判断」と「そもそも実行できない入力エラー」は区別する。
    # 前者（検出結果）は exit 0（lintでありCIゲートではない）、
    # 後者（ファイル不在/ディレクトリ指定/読み取り不可/非UTF-8等）は exit 1。
    text, err = read_source_file(args.file)
    if err is not None:
        print(err, file=sys.stderr)
        return 1

    baseline_data = None
    if args.baseline is not None:
        if not args.baseline.exists():
            print(f"エラー: --baseline ファイルが見つかりません: {args.baseline}", file=sys.stderr)
            return 1
        try:
            loaded_baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            print(f"エラー: --baseline ファイルを読み込めません: {args.baseline} ({exc})", file=sys.stderr)
            return 1

        # JSON としては読めても、スキーマが想定外（トップレベルが配列、findings が
        # 欠けている、findings 内の要素が dict でない等）だと compute_baseline_diff()
        # がクラッシュしうる。lint は CI ゲートではなく、baseline はあくまで補助
        # 情報なので、想定外の形式のときは実行全体を落とさず、baseline比較を諦めて
        # 通常の lint 実行にフォールバックする（警告は出す）。
        baseline_data, baseline_warnings = validate_baseline_data(loaded_baseline)
        for w in baseline_warnings:
            print(f"警告: {w}", file=sys.stderr)

    findings, stats = run_lint(text, genre=args.genre, experimental=args.experimental)

    resolved: list[dict] = []
    baseline_summary: dict[str, int] | None = None
    if baseline_data is not None:
        resolved, baseline_summary = compute_baseline_diff(findings, baseline_data)

    if args.json:
        output = {
            "file": str(args.file),
            "stats": stats,
            "findings": [f.to_dict() for f in findings],
        }
        # --baseline を指定したときだけ baseline セクションを追加する
        # （指定しない場合の JSON 構造は従来と完全に同じ）。
        if baseline_summary is not None:
            output["baseline"] = {
                "file": str(args.baseline),
                "summary": baseline_summary,
                "resolved": resolved,
            }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print_human_report(args.file, findings, stats, baseline_summary)

    # lint であって CI ゲートではない。文章の検出結果は件数に関わらず常に exit 0 とし、
    # 修正するかどうかの判断は人間（または後続の AI 自己点検フロー）に委ねる。
    return 0


if __name__ == "__main__":
    sys.exit(main())

