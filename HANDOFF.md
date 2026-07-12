# natural-japanese — 引き継ぎドキュメント

> 2026-07-12 の設計議論の引き継ぎ。v0.4.0 時点で更新。
> このプロジェクトは「読みやすくわかりやすい、自然な日本語の文章」を書かせる Agent Skill / Claude Code
> プラグイン。当初は「AI臭くない自然な日本語文章」に特化していたが、v0.4.0 でAI臭除去を含む
> 上位概念（読みやすさ全般・ビジネス文書対応）にスコープを拡張した。

## 現状（v0.4.0時点）

- v0.1.0〜v0.3.0 はリリース済み。静的検知（`ai-smell-lint.py`）・収束駆動ループ・`--baseline`
  差分モード・evals による description 統計最適化・business ジャンル対応（`--genre business`、
  正当様式表現の検出器4種を無効化）まで実装済み
- **読みやすさ検出器の機械化は断念、確定した設計方針。** 2026-07 に読みやすさ検出器候補14種を
  コーパス（人間103文書 + AI 81文書）で検証した（`corpus/reports/readability-sweep.md`）。結果、
  機械検出に安定して昇格できる候補はゼロだった。読みやすさ（語順・読点位置・一文一義・主語述語
  距離など）は閾値で切り分けられる領域ではなく、AIが文脈判断する領域だと実証的に確定した
- よって v0.4.0 は検出器を追加するのではなく、SKILL.md のフローに「読みやすさレビュー」という
  判断パスを統合する形でスコープを拡張した。lint（機械検出）と読みやすさレビュー（AI判断、
  `references/readability-principles.md` / `readability-antipatterns.md` / `genre-notes.md` を
  参照）を並行して毎周回行い、両方の finding を同じ判断台帳・収束条件で扱う
- description も「AI臭さの除去」から「読みやすくわかりやすい、自然な日本語を書く」という上位概念に
  改稿し、evals（`evals/evals.json` 41件、`evals/RESULTS.md`）で41/41通過を確認済み

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

## 決定済みの論点（2026-07-12 追記）

1. **「まなざし」の扱い** — 決定: `style-profile.md` は任意（SKILL.md 0節）。プロファイルなしでも動く汎用モードをデフォルトとし、ユーザーが明示的に求めた場合のみセットアップフロー（過去文章3〜5本を読み特徴抽出）に入る。実装済み。
2. **既存の japanese-tech-writing スキル（coji のグローバルスキル）との関係** — 決定: 別スキルのまま維持。SKILL.md frontmatter に「技術文書の章構成やMarkdownフォーマットの整形自体は対象外——それは別スキルの領域であり、本スキルは文章の自然さ・AI臭さの除去に特化する」と明記してスコープを分離した。禁止句リストの重複は japanese-tech-writing 側の知見を revision-guide.md 等に取り込む形で吸収済み（詳細は各 references/ を参照）。
3. **スコープ** — 決定: 文種を限定せず note・ブログ・エッセイ・技術文書全般をサポート（README・SKILL.md 記載どおり）。当初案の「まずブログ/note特化」から拡張した。

## v0.1.x で追加された仕組み（当初計画からの拡張）

引き継ぎ時点の設計にはなかったが、その後の実装で以下が加わった。

- **収束駆動フィードバックループ**: lint → 判断台帳への仕分け（直した/残す理由）→ 再検知 → 収束判定 → 自己点検ループ、という多段のループ構造。単発の「検知→修正」ではなく、収束条件（全 finding が仕分け済み、かつ新規 finding を生んでいない）を満たすまで回す設計になった（SKILL.md 4〜6節、`references/revision-guide.md` の「収束の状態」「発散ガード」）。
- **lint の `--baseline` 差分モード**: 直前の `--json` 出力を渡すと、今回の結果を resolved/new/persisting に自動仕分けする。ループの周回コストを下げるための追加機能（SKILL.md 3節）。
- **後片付けルール**: 完了時に台帳ファイル・lint JSON 出力・下書きバックアップ等の中間ファイルをすべて削除する規約を SKILL.md 7節として追加。プロジェクトに残してよいのは完成文書と明示的に求められた `style-profile.md` のみ。
- **evals/** ディレクトリと `RESULTS.md` を追加し、description の統計的最適化（skill-creator 知見）を実践済み。SKILL.md の description を変更する場合は evals の再実行が前提になる点に注意。

## 次に詰めるとよい論点

1. **リリースノートの薄さ** — v0.1.0〜v0.1.2 のリリースノートは `generate_release_notes` 任せで compare リンクのみ。ユーザー向けに主要変更点（収束ループ、--baseline 追加等）を手書きで補うと発見性が上がる。
2. **README の英語話者向け導線** — 現状 README は日本語のみ。英語圏での発見性を上げるなら、冒頭に1〜2文の英語サマリを添える案がある（README 自体は別エージェントが編集中の可能性があるため本ドキュメントでは提案に留める）。
3. **GitHub Social Preview 画像** — 未設定。API では設定不可なため、Settings > Social preview から手動でアップロードする必要がある。
