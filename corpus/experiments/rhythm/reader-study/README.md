# reader-study

文長系列と読者評価の関係を調べる実験。人間文とAI文を当てる実験ではない。

## 状態

- [x] 仮説、主要評価、除外基準、停止基準の事前登録
- [x] 刺激12項目×3条件
- [x] 刺激の機械検査と意味同等性レビュー
- [x] 無作為割付・回答収集アプリ
- [ ] パイロット
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
uv run corpus/experiments/rhythm/reader-study/analyze.py \
  corpus/experiments/rhythm/reader-study/data/responses.jsonl
```

回答は `data/responses.jsonl` に保存される。このディレクトリはGit管理しない。解析結果は
`results/` に生成される。生データを公開せず、匿名化された集計結果と解析コードだけをコミットする。

## 収集前チェック

1. `validate_stimuli.py` と `test_app.py` を実行する。
2. 研究に参加しない2〜3人で、説明、表示、所要時間、刺激の不自然さを確認する。
3. パイロット回答は削除し、本調査用の空の `data/responses.jsonl` から収集を始める。
4. 本調査開始時のコミットIDと開始日時を記録し、以後は事前登録と刺激を変更しない。
