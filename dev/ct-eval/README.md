# ct-eval — critical-thinking スキルの評価ハーネス

critical-thinking の `logic` と `somosomo` が、仕込んだ欠陥を安定して見つけ、欠陥のない文書に誤検知を出さず、
「文書を書き換えない・足さない・問いの形」の約束を守り、文書の外から持ち込まないことを、実際にスキルを回して測る。

費用と認証が要るので、CI(release.yml)には入れない。スキルの指示を変えたときに手で回す。

## 使い方

```sh
uv run dev/ct-eval/eval.py --dry-run                      # 何を回すかだけ表示
uv run dev/ct-eval/eval.py --repeat 3 --jobs 8 --run-label 2026-10-31-r6        # 4素材 × 2モード × 3回
uv run dev/ct-eval/eval.py --modes logic --fixtures ringi-planted --repeat 1   # 1本だけ
uv run dev/ct-eval/eval.py --fixtures postmortem-planted,postmortem-clean      # 障害報告書だけ
uv run dev/ct-eval/eval.py --modes rewrite --reports-from r12 --repeat 3       # 直す工程だけ。報告は r12 のを足場にする
```

生成物は `dev/ct-eval/runs/<run-label>/` に残る(gitignore)。`summary.md` に集計、各 run のディレクトリに
`report.md`(スキルの出力)、`source.md.logic.yaml`、`judge.json`(判定)、`log-*.txt`(claude の出力)。

プラグインは作業ツリーからコピーして `--plugin-dir` で渡すので、未コミットの変更がそのまま評価される。

## 素材

`dev/ct-eval/fixtures/` にある。すべて架空の文書で、本物の文書は使っていない。スキルの配布物には入れない。
`<名前>.expected.json` がある文書は欠陥を仕込んだ文書、ない文書は欠陥のない文書として扱う。

- `ringi-planted.md`: 稟議書に欠陥を仕込んだもの。logic 用 9件(+任意1件)、somosomo 用 5件。分かりやすい仕込みが中心
- `ringi-clean.md`: 出典・比較した案・終了条件・担当を書いた、欠陥を仕込んでいない稟議書。誤検知の基準線
- `postmortem-planted.md`: 障害報告書に細かい欠陥を仕込んだもの。logic 用 8件(+任意1件)、somosomo 用 5件。表と本文で割れた時刻・日付・割合、原因の切り口の混在、報告日より後の「実施済み」など
- `postmortem-clean.md`: 再現の記録・原因と対策の対応・担当と期限・判断を求める事項を書いた、欠陥のない障害報告書
- `*.expected.json`: 仕込んだ欠陥の一覧(id、分類、行、must_mention)。**最初の実行より前に書き、結果を見て足さない**

## 測るもの

1. 機械的な検査(LLM なし。1つでも落ちたら FAIL)
   - 対象ファイルが変わっていない
   - logic: YAML が存在して読める、種別が5つの中、文書の非空行がすべて YAML の `行` に現れる(`scripts/coverage.py` と同じ検査)
   - somosomo: 足場の YAML が変わっていない、各指摘に「問い・倒れる場所・要る材料」がある
   - 報告に「弱めるべき」「条件を足すべき」がない、指摘の各項目に行番号がある、「文書の性格」の行がある
2. 判定(claude が `prompts/judge.txt` で判定)
   - 仕込んだ欠陥ごとに found / partial / missed
   - 仕込んでいない指摘を plausible(妥当)/ false(読み違い)/ crossing(持ち込み:文書にない事実、具体的な代替案、直し方)に分類
3. 集計と合否
   - 安定検出率(3回中2回以上 found の欠陥の割合)80% 以上
   - 欠陥のない文書での false が 1回あたり 1件以下(素材ごと)
   - crossing が 0
   - 機械的な検査が全 run で通過
4. rewrite(SKILL.md「指摘を反映して直すよう頼まれたとき」の検査。欠陥を仕込んだ文書だけ)
   - logic と somosomo の 1 回目の `report.md` を渡し、`source-after.md` に直させる。`--reports-from <run-label>` で別の run の報告を足場にできる
   - 機械的な検査: 元の文書が変わっていない、「確認事項」の節より前に【要確認】の印がない、改訂の経緯(版番号・改訂日・「指摘を反映」)を足していない、
     本編(確認事項と付録を除く)が元より長くない(空白を除いた文字数。数え方の差を吸収するため 1% まで許す)、見出しが番号を除いて 25 字以内で【 と 。 を含まない、「確認事項」があれば最後の節、
     `newfacts.py` で元にない固有名詞・英字の語が 0(数値は計算で出るので件数だけ記録)、critical-thinking の SKILL.md を読んだ(読まずに直すと手順が効かない)、natural-japanese の lint を回した
   - 判定(`prompts/judge-rewrite.txt`): 仕込んだ欠陥ごとに fixed(文書の中の材料で直した)/ deferred(確認事項に回した)/ remains(残った)。
     足した内容を plausible(元の数字の計算、矛盾の統一、仮定の形への変更)/ crossing(元にない事実、書き手の代わりに決めた日程・担当・目標値、新しい施策や宿題、推定値)に分類
   - 合否: crossing が 0、任意でない欠陥ごとに 3回中2回以上 fixed か deferred(検出側の安定検出と同じ基準)、機械的な検査が通過

## 限界

判定も LLM なので、判定自体が揺れる。欠陥ごとの検出回数(N回中)を見るのはそのためで、1回の found/missed を信じない。
素材は稟議書と障害報告書の2種類で、企画書や記事で同じ成績が出るとは限らない。素材を足すときは expected.json を先に書く。
稟議書の仕込みは r1 から一度も落ちておらず見落としの感度がないため、障害報告書には細かい仕込みを入れた。
