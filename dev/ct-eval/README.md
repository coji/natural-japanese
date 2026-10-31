# ct-eval — critical-thinking スキルの評価ハーネス

critical-thinking の `logic` と `somosomo` が、仕込んだ欠陥を安定して見つけ、欠陥のない文書に誤検知を出さず、
「文書を書き換えない・足さない・問いの形」の線を越えないことを、実際にスキルを回して測る。

費用と認証が要るので、CI(release.yml)には入れない。スキルの指示を変えたときに手で回す。

## 使い方

```sh
uv run dev/ct-eval/eval.py --dry-run                      # 何を回すかだけ表示
uv run dev/ct-eval/eval.py --repeat 3 --jobs 6 --run-label 2026-10-31-r1
uv run dev/ct-eval/eval.py --modes logic --fixtures ringi-planted --repeat 1   # 1本だけ
```

生成物は `dev/ct-eval/runs/<run-label>/` に残る(gitignore)。`summary.md` に集計、各 run のディレクトリに
`report.md`(スキルの出力)、`source.md.logic.yaml`、`judge.json`(判定)、`log-*.txt`(claude の出力)。

プラグインは作業ツリーからコピーして `--plugin-dir` で渡すので、未コミットの変更がそのまま評価される。

## 素材

`skills/critical-thinking/fixtures/` にある。すべて架空の文書で、本物の文書は使っていない。

- `ringi-planted.md`: 稟議書に欠陥を仕込んだもの。logic 用 9件(+任意1件)、somosomo 用 5件
- `ringi-planted.expected.json`: 仕込んだ欠陥の一覧(id、分類、行、must_mention)。**最初の実行より前に書き、結果を見て足さない**
- `clean.md`: 出典・比較した案・終了条件・担当を書いた、欠陥を仕込んでいない稟議書。誤検知の基準線

## 測るもの

1. 機械的な検査(LLM なし。1つでも落ちたら FAIL)
   - 対象ファイルが変わっていない
   - logic: YAML が存在して読める、種別が5つの中、文書の非空行がすべて YAML の `行` に現れる(`scripts/coverage.py` と同じ検査)
   - somosomo: 足場の YAML が変わっていない、各指摘に「問い・倒れる場所・要る材料」がある
   - 報告に「弱めるべき」「条件を足すべき」がない、指摘の各項目に行番号がある、「文書の性格」の行がある
2. 判定(claude が `prompts/judge.txt` で判定)
   - 仕込んだ欠陥ごとに found / partial / missed
   - 仕込んでいない指摘を plausible(妥当)/ false(読み違い)/ crossing(線を越えた:文書にない事実、具体的な代替案、直し方)に分類
3. 集計と合否
   - 安定検出率(3回中2回以上 found の欠陥の割合)80% 以上
   - clean.md での false が 1回あたり 1件以下
   - crossing が 0
   - 機械的な検査が全 run で通過

## 限界

判定も LLM なので、判定自体が揺れる。欠陥ごとの検出回数(N回中)を見るのはそのためで、1回の found/missed を信じない。
素材は稟議書1種類だけなので、報告書や記事で同じ成績が出るとは限らない。素材を足すときは expected.json を先に書く。
