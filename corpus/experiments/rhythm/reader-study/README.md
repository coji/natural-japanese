# reader-study

文長系列と読者評価の関係を調べる実験。人間文とAI文を当てる実験ではない。

パイロット公開先: https://natural-japanese-rhythm-reader-study.techtalkjp.workers.dev

## 状態

- [x] 仮説、主要評価、除外基準、停止基準の事前登録
- [x] 刺激12項目×3条件
- [x] 刺激の機械検査と意味同等性レビュー
- [x] 無作為割付・回答収集アプリ
- [ ] 人間2〜3人によるパイロット（技術パイロットは完了）
- [ ] 有効回答30人
- [ ] 統計解析
- [ ] 検出器と文書の更新

回答収集を始めた後は、`preregistration.md` を上書きしない。変更が必要なら、日付と理由を
追記した amendment を別ファイルで作る。

## 実行

```bash
uv run corpus/experiments/rhythm/reader-study/validate_stimuli.py
python corpus/experiments/rhythm/reader-study/app.py --host 127.0.0.1 --port 8765
uv run corpus/experiments/rhythm/reader-study/analyze.py --check
uv run corpus/experiments/rhythm/reader-study/test_analyze.py
uv run corpus/experiments/rhythm/reader-study/analyze.py \
  corpus/experiments/rhythm/reader-study/data/responses.jsonl
```

回答は `data/responses.jsonl` に保存される。このディレクトリはGit管理しない。解析結果は
`results/` に生成される。生データを公開せず、匿名化された集計結果と解析コードだけをコミットする。

公開環境では永続ボリュームを `/data` に割り当てる。コンテナは次のように確認できる。

```bash
docker build -t rhythm-reader-study corpus/experiments/rhythm/reader-study
docker run --rm -p 8765:8765 -v reader-study-data:/data rhythm-reader-study
curl http://127.0.0.1:8765/healthz
```

TLS終端はホスティング側で行う。収集終了後は `/data/responses.jsonl` を安全な場所へ一度だけ
書き出し、公開アプリを停止する。

本番はCloudflare Workers + TypeScript + D1で動かす。`worker/index.ts` はPython版と同じ
割付・検証を行い、D1には参加者ID、受信日時、回答JSONだけを保存する。

```bash
cd corpus/experiments/rhythm/reader-study
npm install
npm run check
npm run migrate:remote
npm run deploy

# 解析用JSONLの書き出し
mkdir -p data
npx wrangler d1 execute natural-japanese-rhythm-reader-study --remote --json \
  --command "SELECT payload_json FROM submissions ORDER BY received_at" \
  | jq -r '.[0].results[].payload_json' > data/responses.jsonl
```

パイロット後、本調査開始前にD1のパイロット行を削除する。本調査中は刺激、事前登録、Workerを
変更しない。

## 収集前チェック

1. `validate_stimuli.py` と `test_app.py` を実行する。
2. 研究に参加しない2〜3人で、説明、表示、所要時間、刺激の不自然さを確認する。
3. パイロット回答は削除し、本調査用の空の `data/responses.jsonl` から収集を始める。
4. `collection-log.md` に本調査開始時のコミットIDと開始日時を記録し、以後は事前登録と刺激を変更しない。
