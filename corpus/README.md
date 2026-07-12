# corpus/ — 検出器の閾値校正用コーパス

## 目的

`scripts/ai-smell-lint.py` の各検出器(禁止語・統語パターン・統計指標など)は、
現状「経験則」で閾値を決めている。このコーパスは、その閾値を実測に基づいて
校正するために存在する。具体的には:

- 人間が書いた自然な日本語文章(人間コーパス)に対する誤検知率(FP率)を測る
- AI(Claude / GPT系)が「素の状態」(AI臭除去の指示なしで)書いた文章
  (AIコーパス)に対する検出率を測る
- 「人間側 FP率 5% 未満を保ちつつ AI 側検出率最大」となる閾値を
  `scripts/calibrate.py`(Phase 2 後半で実装)で探索する

このコーパス自体は成果物ではなく、lint の品質を裏付けるための実験基盤。

## 構成

```
corpus/
├── README.md          このファイル
├── sources.json        人間コーパス(web/aozora)のソース定義
├── fetch.py            sources.json の type=web を取得して corpus/human/web/ に保存
├── generate.py         AI コーパスを claude/codex CLI 経由で生成し corpus/ai/ に保存
├── human/
│   ├── aozora/          青空文庫の随筆(パブリックドメイン、コミット対象)
│   └── web/             note/Zenn の記事本文(著作権あり、非コミット、.gitkeep のみ)
└── ai/                  AI生成記事(非コミット、.gitkeep のみ。再生成可能なため)
```

## ライセンス方針

| 区分 | 方針 | 理由 |
| --- | --- | --- |
| `corpus/human/aozora/` | **コミット可** | 青空文庫はパブリックドメイン作品(著作権保護期間満了)のみを収録。各ファイル冒頭に出典コメントを明記している。 |
| `corpus/human/web/` | **非コミット**(`.gitignore` 対象) | note/Zenn 等の著作権のある記事本文をそのまま複製することになるため、評価目的であってもリポジトリに含めない。`corpus/sources.json` に URL のみを記録し、`fetch.py` で各自ローカルに取得する運用とする。 |
| `corpus/ai/` | **非コミット**(`.gitignore` 対象) | `generate.py` で再生成可能であり、生成コスト(API呼び出し)をリポジトリサイズに持ち込む必要がないため。 |

`.gitkeep` はディレクトリ構成を保つためにコミットする(`.gitignore` の例外)。

## 使い方

```bash
# 人間コーパス(Web記事)をローカルに取得
uv run corpus/fetch.py                      # 全件
uv run corpus/fetch.py --limit 3            # 試走(先頭3件)
uv run corpus/fetch.py --id <source-id>     # 1件だけ

# AI コーパスを生成
uv run corpus/generate.py --engine claude --model claude-sonnet-4-5 --limit 1  # 動作確認
uv run corpus/generate.py --engine claude --model claude-sonnet-4-5           # 本格生成
uv run corpus/generate.py --engine codex                                       # codex CLI 経由
```

## 収録状況(Phase 2 コーパス基盤構築時点)

- `corpus/human/aozora/`: 寺田寅彦・中島敦・坂口安吾・岸田國士の随筆 12本(実収録・コミット済み)
- `corpus/sources.json`: 青空文庫12本 + note/Zenn の web記事32本(essay/tech genre)、計44エントリ
- `corpus/human/web/`: `fetch.py` で3本を試走し抽出品質を確認済み(全件取得はコーパス本格構築フェーズで実施)
- `corpus/ai/`: `generate.py` の動作確認として1本のみ生成済み(本格生成は次フェーズ)

閾値校正(`scripts/calibrate.py`)自体は Phase 2 後半の作業であり、このディレクトリはまだ含まない。
