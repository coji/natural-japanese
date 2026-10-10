# モデル評価ベンチ

新しいモデルが「素のまま使って、自然で読みやすい日本語を書けるか」を、同じ条件で繰り返し測るための仕組み。ロードマップ(`corpus/ROADMAP.md`)の S40。

課題は作者の文書(顧客向け文書・Zenn 記事・PR 説明文)から作る。材料と生成結果は作者の文書を含むので `corpus/private/bench/` に置き、コミットしない。

## 手順

```bash
# 1. 課題を作る(一覧は corpus/private/bench/tasks.json)
uv run corpus/bench/build_tasks.py

# 2. モデルに書かせる(新しいモデルは --model engine:name で足せる)
uv run corpus/bench/run_bench.py --models claude-opus-5-5 gpt-6-luna gemini-3.8-flash --effort low
uv run corpus/bench/run_bench.py --model agy:gemini-4-pro --effort medium

# 3. 評価して成績表を出す(判定はキャッシュされ、新しいモデルの分だけ追加で判定する)
uv run corpus/bench/evaluate_bench.py
```

## 測るもの

- 読みやすさ: `corpus/selfcorpus/rubric.md` の評価軸で、作者の版(推敲課題では元の文書)と対にして比べる。判定は評価対象と別系統の2モデルが、並び順を入れ替えて2回ずつ行う
- 事実の正確さ: 材料にある事実の抜け、材料にない断定、説明のための例を数える
- AI 時代の癖: 検証済みの語彙、ダッシュ、太字、箇条書きの行の割合
- 分量: 作者の版に対する文字数の比
