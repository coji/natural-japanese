# business ジャンルプロファイル 校正レポート（2026-07）

## 目的

`scripts/lint.py` の `GENRE_PROFILES["business"]` は、これまで
「コーパスが薄いため tech と同値を暫定採用」という未検証の仮値だった。
本レポートは、AI生成の business コーパス（24件）と、少数だが実在する
human business コーパス（10件）を用いて実測し、business プロファイルを
実測値ベースに更新した記録である。

## 方法

1. `scripts/calibrate.py report` に `human_business` / `ai_business` の
   参考列を追加した（`corpus/sources.json` の `genre: "business"` で
   human 側を、ファイル名 `business-*.md` で AI 側を判定。それぞれ
   `human_web` / `ai` の部分集合であり二重集計ではない）。
2. 全検出器 x コーパス種別のヒット率マトリクスを取得（`scripts/calibrate.py report` で再生成可能。出力はローカルのみ・非コミット）。
3. `--genre` で調整可能な2値（`nominal_min_chars`, `lead_repeat_threshold`）は
   `detect_nominal_ending_and_paragraph_conjunctions` / `detect_ngram_repetition`
   を直接呼び、business コーパス（human_business n=10, ai_business n=24）に対して
   複数の閾値でスイープし、human 側の誤検知率と ai 側の検出率の両方を確認した。
4. 実験的構造検出器（`high_bullet_ratio` 等）はタスクの指示に基づき候補として
   検証したが、以下の理由から「厳しくする」方向の調整は一切行っていない
   （下記の限界セクション参照）。

## コーパス規模

| 種別 | 件数 |
| --- | --- |
| human_business（`corpus/human/web` の `genre: "business"`） | 10 |
| ai_business（`corpus/ai/*/business-*.md`） | 24（claude-haiku-4-5 ×12、claude-sonnet-5 ×12） |

## マトリクス要約（抜粋、全文は `scripts/calibrate.py report` で再生成できる）

「文書発火率 / 1000字あたり件数」。

| 検出器 | human_business (n=10) | ai_business (n=24) | 状態 |
| --- | --- | --- | --- |
| nominal_ending | 0% / 0.00 | 0% / 0.00 | 常時無反応（後述） |
| repeated_sentence_lead | 20% / 0.95 | 4% / 0.26 | lead_repeat_threshold で調整済み |
| high_bold_density | 0% / 0.00 | 58% / 0.45 | EXPERIMENTAL、business では明示的に無効化 |
| high_bullet_ratio | 0% / 0.00 | 21% / 0.16 | EXPERIMENTAL、business では明示的に無効化 |
| boilerplate_heading | 0% / 0.00 | 0% / 0.00 | EXPERIMENTAL、business では明示的に無効化（予防的） |
| numbered_phase_structure | 10% / 0.02 | 17% / 0.13 | EXPERIMENTAL、business では明示的に無効化 |
| low_burstiness | 10% / 0.02 | 38% / 0.29 | 変更なし（強い弁別力、business固有の懸念なし） |

## 閾値スイープ詳細

### nominal_min_chars（体言止め欠如検出の最低文書長）

| nominal_min_chars | human_business発火 | ai_business発火 |
| --- | --- | --- |
| 1500〜4000（全域） | 0/10 | 0/24 |

business コーパスの文書はいずれも短め（human: 2,627〜7,984字、
ai: 454〜2,937字）で、nominal_ending は閾値をどこに設定しても
一度も発火しなかった。誤検知（human側の発火）が実測上存在しないため、
「厳しくする方向の調整はしない」という指示のもと、tech と同じ
`nominal_min_chars=3000` を据え置いた。

### lead_repeat_threshold（文頭反復の閾値）

| lead_repeat_threshold | human_business発火 | ai_business発火 |
| --- | --- | --- |
| 6（共通デフォルト） | 2/10 (20%) | 1/24 (4%) |
| 7（tech と同値、採用） | 1/10 (10%) | 1/24 (4%) |
| 8 | 1/10 (10%) | 1/24 (4%) |
| 10 | 1/10 (10%) | 0/24 (0%) |

閾値7は、共通デフォルト（6）に比べ human_business の誤検知を半減させつつ
ai_business の検出率を落とさない局所最適点。閾値10までさらに緩めると
human側の誤検知はこれ以上減らず、ai側の検出力だけを失う（0%）ため
逆効果と判断し、tech と同じ7を維持した。

## 変更内容（before → after）

| 設定 | before | after | 理由 |
| --- | --- | --- | --- |
| `nominal_min_chars` | 3000（未検証の暫定値） | 3000（実測で維持） | 全閾値域で human/ai とも0%発火。誤検知リスクが実測されていないため変更根拠なし。 |
| `lead_repeat_threshold` | 7（未検証の暫定値） | 7（実測で維持） | human_business の誤検知を最小化する局所最適点であることを確認。 |
| `disabled_categories`（新設） | なし | `{high_bullet_ratio, high_bold_density, boilerplate_heading, numbered_phase_structure}` | 事業文書（報告書・提案書・議事録等）で箇条書き・太字強調・「まとめ」等の定型見出し・フェーズ/ステップ表現は正当な慣習であり、AI側の発火率に関わらず business ジャンルでは無効化した（下記の限界セクションに基づく方針）。 |

`disabled_categories` は `lint.py` の `run_lint()` に新設した
ジャンル横断の適用ポイントで、`GENRE_PROFILES` の任意ジャンルが
`profile.get("disabled_categories", set())` で参照できる汎用の仕組み
（既存の `nominal_min_chars` / `lead_repeat_threshold` と同じ
「モジュール定数 + プロファイル上書き」の kwarg 契約に倣った）。
essay / tech のプロファイルはこのキーを設定していないため、
挙動は一切変わらない。

なお、上記4カテゴリは全て `EXPERIMENTAL_CATEGORIES` に属しており、
デフォルト実行（`--experimental` なし）では genre 指定の有無にかかわらず
そもそも出力されない。したがって今回の `disabled_categories` 追加は
「`--experimental --genre business` を同時に指定した場合」にのみ効果を持つ、
将来これらの検出器が非実験化された場合に備えた予防的な措置である。

## 検証

- `./scripts/check-fixtures.sh` → **PASSED**
  （`ai-smelly.md` default 25件 / --experimental 33件、`natural.md` 0件、変化なし）
- default プロファイル（`--genre` 未指定）への影響がないことを個別確認:
  `corpus/ai/claude-sonnet-5/business-consulting-kaizen.md` に対し
  `--experimental`（genre指定なし）では `high_bold_density`,
  `numbered_phase_structure` が発火するが、`--experimental --genre business`
  では0件になることを確認した。変更は `GENRE_PROFILES["business"]` の
  辞書と、それを参照する新設フィルタ（`profile.get("disabled_categories", ...)`）
  のみで、共有の検出器ロジックやデフォルト閾値定数は変更していない。

## 限界（重要）

**human business ジャンルのコーパスは `corpus/human/web` に10件しかなく、
統計的に有意な誤検知検証ができていない。** さらに、この10件は分析対象と
なった business プロファイルの各検出器のうち、実験的構造検出器
（`high_bullet_ratio` / `high_bold_density` / `boilerplate_heading` /
`numbered_phase_structure`）についてはいずれも0%しか発火しなかった
（=誤検知の実例そのものは今回のコーパスには現れなかった）。

つまり本校正で行った検証は「AI生成文に対してどれだけ強く発火するか」の
一方向のみであり、「正当な人間の business 文書に対してどれだけ過検知するか」
は10件という小標本でしか確認できておらず、実質的に未検証に近い。

この限界があるため、本レポートおよび `GENRE_PROFILES["business"]` の変更は
以下の方針に従っている:

- **実測データが示す「AI側で強く光る」という事実だけを根拠に、検出器を
  厳しくする・severityを上げるといった変更は一切行っていない。**
- 逆に、箇条書き・番号付きフェーズ・定型見出し・太字強調は、business
  文書（報告書・提案書・議事録・稟議書等）で一般的に使われる正当な
  執筆慣習だと業務知識的に判断できるため、今回の10件のコーパスで
  たまたま発火しなかった検出器も含めて、**予防的に無効化する側に倒した。**
- 今後 human business コーパスが拡充された場合は、この
  `disabled_categories` の妥当性（緩めすぎ・きつすぎの両方向）を
  再検証すべきである。特に `numbered_phase_structure`（human 10%/ai 17%
  と差が小さい）は、コーパスが増えれば再度弁別力ありと判定される
  可能性がある。
