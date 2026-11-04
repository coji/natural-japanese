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
uv run dev/ct-eval/eval.py --modes redesign --reports-from r9 --repeat 3       # 組み直す工程だけ
uv run dev/ct-eval/eval.py --rejudge r27j --run-label r27j-sj                  # 生成を回さず、保存した出力に判定だけをかけ直す(判定者を替えたときの基準の置き直し)
uv run --with pyyaml dev/ct-eval/outcome.py --label o3 --repeat 3 ringi-元=dev/ct-eval/fixtures/ringi-planted.md   # 成果物の評価(経営者役)
```

生成は Opus 5.5(`--model`、effort は `--effort`、既定 high)、判定は Sonnet 5.5(`--judge-model`。生成と別のモデルにする)、review の模擬書き手は Opus 5.5(`--writer-model`)。
判定の問い(`prompts/judge-*.txt`)は、Opus 5.5 のプロンプトガイドに沿って、役を1文、ファイル・基準・出力を XML で区切り、基準は肯定文で書いている。経営者役(`prompts/exec.txt`)は同じ形に書き直すと役が変わった(肯定文だけにすると元の文書にも毎回3つ聞き、「条件を付けて通す」を足すと何も聞かない)ので、o1 のときの文面のままにしている。

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
- `teian-planted.md`: コンサルティング会社がクライアントの営業本部長に出す提案資料に欠陥を仕込んだもの。logic 用 9件(+任意1件)、somosomo 用 5件。期間と費用の不一致、診断で決めるはずの製品名、入力率だけで測る効果など
- `teian-clean.md`: 出典・比較した案・3か月目の判断・リスクと測り方を書いた、欠陥のない提案資料
- `kikaku-planted.md`: 人事企画が経営会議に出す制度企画(週1日の在宅勤務)に欠陥を仕込んだもの。logic 用 9件(+任意1件)、somosomo 用 5件。対象人数と PC 台数の不一致、曜日の割り当てと希望日の矛盾、VPN の計算など
- `kikaku-clean.md`: 出典・比較した案・懸念と対策・評価と見直しの条件を書いた、欠陥のない制度企画
- `*.writer.json`: 書き手だけが知っている事実(review モードの模擬書き手が使う。ringi-planted と teian-planted)
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
   - 機械的な検査: 元の文書が変わっていない、本文に【要確認】の印がない、改訂の経緯(版番号・改訂日・「指摘を反映」)を足していない、
     本編(付録を除く)が元より長くない(空白を除いた文字数。数え方の差を吸収するため 1% まで許す)、見出しが番号を除いて 25 字以内で【 と 。 を含まない、確認事項の節が文書の中になく別ファイル(`source.確認事項.md`)にある、
     `newfacts.py` で元にない固有名詞・英字の語が 0(数値は計算で出るので件数だけ記録)、critical-thinking の SKILL.md を読んだ(読まずに直すと手順が効かない)、natural-japanese の lint を回した
   - 判定(`prompts/judge-rewrite.txt`): 仕込んだ欠陥ごとに fixed(文書の中の材料で直した)/ deferred(確認事項に回した)/ remains(残った)。
     足した内容を plausible(元の数字の計算、矛盾の統一、仮定の形への変更)/ crossing(元にない事実、書き手の代わりに決めた日程・担当・目標値、新しい施策や宿題、推定値)に分類
   - 合否: crossing が 0、任意でない欠陥ごとに 3回中2回以上 fixed か deferred(検出側の安定検出と同じ基準)、機械的な検査が通過。本編の長さだけは 3回中2回以上(940 字の素材では「確認中」を1か所書くと 1% の許容を超えることがある)
5. redesign(SKILL.md「構成から組み直すよう頼まれたとき」の検査。欠陥を仕込んだ文書だけ)
   - rewrite と同じ報告を渡し、構成案を `plans.md` に、組み直した本文を `source-after.md` に書かせる
   - 機械的な検査: rewrite の検査すべてに加えて、`plans.md` に案が2つ以上ある、本編の見出しが1つ以上替わっている
   - 判定(`prompts/judge-redesign.txt`): rewrite と同じ fixed / deferred / remains と plausible / crossing に加えて、
     主結論と決裁事項が元と同じ中身か(conclusion_kept / request_kept)、論の背骨が替わったか(restructured。並べ替えや見出しの言い換えだけなら false)、案が背骨の違いで分かれているか(plans_distinct)、
     「頼む中身を小さくする案」があるか(plans_shrink。決裁事項を縮める・分ける・先に置く・取り下げる案で、どの問いの答えで元の決裁事項が倒れるかを示しているもの)と、その案に持ち込みがないか(shrink_clean)
   - 合否: rewrite の条件に加えて、主結論と決裁事項が全 run で保たれ、背骨が 3回中2回以上替わり、頼む中身を小さくする案(持ち込みなし)が 3回中2回以上ある

6. review(SKILL.md「決裁者の目で見て直すよう頼まれたとき(一括)」の検査。`<名前>.writer.json` のある素材だけ)
   - 依頼1で検査と問い(questions.md、3つまで)を書かせて止め、模擬書き手(`--writer-model`、writer.json だけを知る)が answers.md を書き、依頼2で答えを反映して直す
   - 機械的な検査: rewrite と同じ(元にない語は、元の文書と answers.md を合わせたものと比べる)。問いが 1〜3 件
   - 機械的な検査は rewrite と同じだが、本編の長さの上限は「元の本編 + 答えの字数」(答えを本文に入れる工程なので)。答え以外を足していないかは判定の持ち込みで見る
   - 判定(`prompts/judge-review.txt`): 各問いが文書の中で答えが出るものでないか、各答えが本文に使われ改変されていないか(「分からない」は仮定の形で `source.確認事項.md` へ)、確認事項の件数(先に答える問い / 全体。別ファイルから数える)と答えで消せたはずの残り、欠陥ごとの fixed / deferred / remains、持ち込み
   - 合否: 問いが 1〜3、文書内で答えが出る問い 0、答えは使われ改変なし、先に答える問い ≤3 で消せたはずのもの 0、remains 0、持ち込み 0、機械検査が通過。これを 3回中2回以上

7. concise / detailed(SKILL.md「もっと端的に・もっと丁寧にと頼まれたとき」の検査)
   - logic の 1 回目の YAML(`論拠` と `重み` のある形)を渡し、`source-after.md` に書き直させる。`--reports-from <run-label>` で別の run の YAML を使える
   - 機械的な検査: rewrite と同じ(印、改訂の経緯、見出し、確認事項の節が文書にない、元にない語)。本編の長さは端的が元の 70% 以下、丁寧が 110% 以下
   - 判定(`prompts/judge-length.txt`): 主結論・決裁事項・数値(付録に移っていてもよい)が同じか、元にも YAML にもない内容の持ち込み、端的では本編の各文が元の文書のどの行に対応するか(対応なしの文を数える)、丁寧では論拠の文が YAML の論拠に対応するか、見出しと各節の先頭文だけで何を決める文書か分かるか
   - 合否: 素材ごとに 3 回中 2 回以上。仕込んだ欠陥は見ない(直す工程ではない)

8. outcome(`outcome.py`。規則の合否ではなく、成果物が決裁者にとって良くなったかの計測)
   - スタートアップ経営者役(`prompts/exec.txt`。戻せる判断は速く通し、起案者が自分で決めているか・一番怪しいところを自分で言っているか・他に何を捨てたかを見る)に文書を1本だけ渡し、返事(OK / 条件つきOK / 聞きたい / 却下)、一言、聞きたいこと(3つまで。文書の中で答えが出るものか、起案者にしか答えられないものか)、返事を決めるまでに読んだ行数と字数を返させる
   - 元の文書と各工程の出力を伏せて別々に渡し、同じ文書に3回かけて多数決。`runs/<label>/summary.md` に文書ごとの表
   - 見るもの: 元 → 出力で「聞きたい」が減ったか、文書の中で答えが出る問いが 0 に近づいたか、読んだ字数が増えていないか。1つでも悪化していれば「改悪の疑い」として工程ごとに記録する

## 限界

判定も LLM なので、判定自体が揺れる。欠陥ごとの検出回数(N回中)を見るのはそのためで、1回の found/missed を信じない。
素材は稟議書・障害報告書・提案資料・制度企画の4種類で、記事や研究計画で同じ成績が出るとは限らない。素材を足すときは expected.json を先に書く。
稟議書の仕込みは r1 から一度も落ちておらず見落としの感度がないため、障害報告書には細かい仕込みを入れた。
