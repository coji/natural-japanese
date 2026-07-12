# natural-japanese — 引き継ぎドキュメント

> 2026-07-12 の設計議論の引き継ぎ。
> このプロジェクトは「AI臭くない自然な日本語文章」を書かせる Agent Skill / Claude Code プラグイン。

## 元ネタとなる2記事

1. **なつ「いとおり」の記事** — https://note.com/art_reflection/n/n7ffd5ce3320c
   - Claude API 製の執筆エージェント。「AI臭さを消した日本語」を生成する6メカニズム:
     1. **まなざしの再現** — 著者の note 129本から視点・文体・構成を蒸留してシステムプロンプトに段階注入
     2. **再帰的推論リサーチ** — 推論→検索→推論のループ。日本語・鮮度優先
     3. **プロンプト設計** — 禁止語60語超、リズム制御、比喩の直訳チェック、人間味の追加
     4. **自己点検ループ** — 「人間に指摘された」設定で自文を再検査
     5. **静的検知** — AIは自分のAI臭さを認識できない → 機械的に検出し、修正判断だけAIに委ねる（反復パターン: 否定→肯定対比3回以上、リズム癖、読みにくさ）
     6. **揺らぎの設計** — 執筆前に重要度にムラをつけ「整いすぎた自然さ」を回避
   - **未解決の壁: 英語統語**。文章構造レベルの英語的特徴は AI が自己認識も修正もできない
   - モデル比較: Fable 5.0 が「具体性と生活の摩擦感」で最も自然、Sonnet 5.0 は整いすぎ
   - コスト: 1記事300〜500円

2. **逆瀬川ちゃんの skill-creator 分析記事** — https://nyosegawa.com/posts/skill-creator-and-orchestration-skill/
   - skill-creator（Anthropic 公式メタスキル）から抽出した7ベストプラクティス:
     1. SKILL.md はオーケストレーターに徹し agents/ に委譲
     2. 確定的処理（ループ・数値・ファイル操作）はスクリプトへオフロード
     3. references/schemas.md でスキーマ契約
     4. Why-driven 設計（NEVER の羅列でなく理由を書く。ただしスキーマ名・セキュリティは Must）
     5. description の統計的最適化（evals 20クエリ → 60/40分割 → 3反復 → test検証。Claude は undertrigger 傾向なので押し強めに）
     6. Human-in-the-Loop はチャット外へ（ローカルHTMLビューア + feedback.json）
     7. 環境別フォールバック（Claude.ai は並列サブエージェント不可 → 直列、スクリプト不可 → 文章版チェックリスト）
   - オーケストレーション2パターン: **Sub-agent型**（並列・複数視点・単体利用不可）vs **Skill Chain型**（直列・各スキル単体再利用可・スクリプトはオプショナル）

## 決定済みの設計方針

### アーキテクチャ: 「オーケストレーター + 決定的 lint」の1スキル構成

執筆フローは直列＋ループ（下書き→静的検知→自己点検→修正→再検知）なので、Sub-agent 並列型は不要、独立スキル Chain にするほど各段階に単体再利用価値なし。「フロー制御に徹する SKILL.md + 段階的開示用の references/ + AIが苦手な判定を決定化する scripts/」という構成を採用する。

```
natural-japanese/
├── SKILL.md                    # フロー制御のみ（~120行、Progressive Disclosure）
├── scripts/
│   └── ai-smell-lint.py        # PEP 723 + uv run。決定的なAI臭検知
├── references/
│   ├── forbidden-patterns.md   # 禁止語60語超・手癖構文カタログ
│   ├── translationese.md       # 英語統語の翻訳調パターン集
│   ├── revision-guide.md       # 自己点検・揺らぎ設計の手順
│   └── examples.md             # before/after 事例
└── assets/
    └── style-profile-template.md
```

Progressive Disclosure の3層: Level 1 = name+description（常時注入、~100トークン）、Level 2 = SKILL.md 本体（トリガー時）、Level 3 = references/・scripts/（フロー中に必要時のみ）。

### 勝ち筋（差別化の核）

1. **静的検知スクリプト `ai-smell-lint.py`**。「AIは自分のAI臭さを認識できない → 機械検出で突きつけ、修正判断だけAIに委ねる」を実装。検出対象案:
   - 否定→肯定対比の反復（3回以上）
   - 文長分散の低さ（リズムの均質性）
   - 禁止語ヒット
   - 翻訳調（「〜することができる」「〜と言えるだろう」）
   - 体言止め頻度、段落頭の接続詞率
   - 形態素解析は sudachipy（PEP 723: sudachipy>=0.6.8, sudachidict-core>=20240409, requires-python >=3.10, uv run で実行）
2. **英語統語への部分回答**。生成側での修正は無理でも*検出*は形態素レベルで機械化可能（無生物主語+他動詞、連体修飾の入れ子、「それは〜である。なぜなら〜だ」構文）。「検出→書き直し指示→再検出」の外部ループで、AIが自己認識できない問題を回す。記事の「未解決の壁」への挑戦がこのスキルの本気ポイント。

### skill-creator 知見の適用

- references は Why-driven の文体で書く
- description は skill-creator の eval フロー（evals.json、with/without 比較）で統計的に最適化。執筆系はトリガー競合が激しい領域
- 環境フォールバック: Claude.ai では uv run 不可 → lint の文章版チェックリストを references に持たせ、スクリプトは「あれば強化」のオプショナル扱い

### リポジトリ運用の規約（配布まで見据えた雛形）

- **SKILL.md frontmatter**: agentskills.io 仕様で必須は name / description のみ。任意で license / metadata / compatibility / allowed-tools。`license: MIT` を入れる。`triggers` のような非標準フィールドは使わず、トリガー語は description に織り込む。name はディレクトリ名と一致（小文字英数字+ハイフン）
- **配布4チャネル**: `npx skills add`（ルート SKILL.md）/ `npx openskills install`（AGENTS.md）/ Claude Code plugin marketplace（.claude-plugin/ + skills/ 配下コピー）/ GitHub Releases の .skill（実体は zip、Actions で自動ビルド）
- **single source of truth**: ルートが正、`skills/` 配下はプラグイン配布用コピー。pre-commit hook で同期（一時ディレクトリにコピー→mv のアトミック置換、set -euo pipefail）
- plugin.json と marketplace.json の version は常に一致させる

## 未決の論点（次セッションで詰める）

1. **「まなざし」の扱い** — 提案: 初回にユーザーの過去文章を数本読ませて `style-profile.md` を生成し以後参照するセットアップフローをスキル内に持つ。プロファイルなしでも動く汎用モード（AI臭除去のみ）をデフォルトに。→ ユーザー未回答
2. **既存の japanese-tech-writing スキル（coji のグローバルスキル）との関係** — 軸が違う（技術書規範 vs AI臭除去+文体）ので別スキルで良さそうだが、禁止句リスト（LLMっぽい空句）が重なるので参照関係を整理したい。→ 未決
3. **スコープ** — 提案: まずブログ/note記事特化で始めて広げる（記事の知見はエッセイ寄りで検証されているため）。→ 未決

## 推奨する最初の一手

`ai-smell-lint.py` のプロトタイプを先に作る。何をどこまで機械検出できるかが分かると、SKILL.md のフロー設計（何をスクリプトに任せ、何をAIの判断に残すか）が地に足がつく。
