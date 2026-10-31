# ct-eval の結果の記録

素材は `dev/ct-eval/fixtures/`(r5b までは `skills/critical-thinking/fixtures/` にあった架空の稟議書。r6 から障害報告書を追加)。モデルは実行・判定とも claude-opus-5-5、effort high。
生成物は runs/ にあり非コミット。ここには集計だけを残す。

用語: 仕込んでいない指摘の分類は plausible=妥当、false=読み違い(文書を読めば成り立たない)、crossing=持ち込み(文書にない事実・具体的な代替案・直し方を文書の外から持ち込んだ)。

## 2026-10-31 r1(初回)

- 機械検査 4/12。落ちの大半はハーネス側(3点セットの「要る材料」に行番号を求めていた)。本物の落ちは1件:
  YAML の `限界や条件` の本文中に「(行63)」と書いて `行:` 欄に入れず、coverage.py の NG を直し切らなかった
- logic: 仕込んだ欠陥 9/9 を3回とも検出。持ち込み 0
- somosomo: 5/5 を安定検出。持ち込み 0
- clean.md の誤検知: logic 4件/3回。うち3件は素材(clean.md)に本物の矛盾が残っていた(「社外に共有しない」直後に顧客へ共有)

直したこと: ハーネスの行番号検査を「倒れる場所」だけに限定、clean.md の矛盾を解消、YAML の `限界や条件` を `内容`+`行` の形に変更

## 2026-10-31 r2

- 機械検査 11/12(残り1件は結びの箇条書きを指摘と誤認したハーネス側の問題。直して再検査すると 12/12)
- logic: 9/9 安定検出(任意の L10 は 1 found / 2 partial)。仕込んでいない指摘 plausible 21 / false 1 / crossing 0
- somosomo: 5/5 安定検出。仕込んでいない指摘 plausible 10 / false 0 / **crossing 1**
  - 3回目の結びに「評価の基準に残業時間を入れて出し直してほしい」と直し方を書いた
- clean.md: logic false 0、somosomo false 2(0.67/回、基準内)

直したこと: somosomo.md に「直し方は指摘にも反論にも結びにも書かない」を追加。ハーネスの指摘本体の切り出しを修正

## 2026-10-31 r3(somosomo のみ再実行、足場の YAML なしで開始)

- somosomo は足場の YAML がないと自分で logic の YAML を作ってから問う経路を通った。3回とも作れた
- 5/5 を3回とも found。仕込んでいない指摘 plausible 15 / false 0 / **crossing 0**
- 直し方の禁止を明記したあと、持ち込みは出なかった(3回)
- 機械検査はハーネス側の誤り(足場なしの経路で `yaml_unchanged` を求めていた)で 0/3。`yaml_created` の検査に直した

## 2026-10-31 r4(全修正後の通し実行)

- 機械検査 10/12。logic: 9/9 安定検出、crossing 0。somosomo: 5/5 安定検出、crossing 0(仕込み)。clean: logic false 1、somosomo false 1
- 落ち1(本物): logic 3回目が、リスクの箇条書き4行(並列の項目)を YAML の `並列` に文字列で書いて `行:` を付けず、coverage.py の NG を直し切れなかった。`並列` を `切り口`+`項目(内容・行)` の形に変更
- 落ち2(本物、軽微): somosomo が clean.md に「申請者の名前と所属が文書にない」を行番号なしで書いた。規則(行番号で指せない指摘は書かない)違反。規則は変えず、合否の基準もそのまま
- clean の crossing 1 は判定者側の過剰。「範囲を変える案は比べたか」は somosomo.md が許す型なので、judge.txt にその旨を明記
- 端から端まで緑の実行はまだない。r5 で確かめる

## 2026-10-31 r5(全修正後の通し実行、2回目)

- 機械検査 12/12。logic: 9/9 安定検出、crossing 0、clean false 2(0.67/回、基準内)。somosomo: 5/5 安定検出、crossing 0(仕込み)、clean false 0
- 落ち1件: somosomo が clean.md に「試用で使った無料版のまま続ける案は検討したか」と問い、判定者が crossing とした。無料版は clean.md の13行目にある事実で、外からの持ち込みではない。規則の意図(その領域の知識から代替案を持ち込まない)に合わせ、somosomo.md と judge.txt に「文書自身が書いている案を名指しして比べたかと問うのは持ち込みではない」を明記

## 2026-10-31 r5b(somosomo × clean.md のみ、上の明記後に再実行)

- 機械検査 3/3。plausible 32 / false 0 / crossing 0。判定 PASS
- これで r5 の logic 全部と仕込み somosomo、r5b の clean somosomo を合わせて、合否の基準をすべて満たした。ただし通し1回での緑ではない
- 限界: 仕込んだ欠陥は r1 から一度も落ちていない(すべて 3/3 found)。合否の基準は「持ち込みと誤検知」には効いているが「見落とし」には感度がない。表と本文に割れた矛盾など、もっと細かい仕込みを足すのは次回

## 2026-10-31 r6(素材を dev/ct-eval/fixtures/ に移し、障害報告書2本を追加しての通し。4素材 × 2モード × 3回)

- 機械検査 24/24。ringi-planted: logic 9/9、somosomo 4/5(S2 が 1 found / 2 partial、80% で基準内)。ringi-clean: false 0 / crossing 0
- postmortem-planted / logic: 7/8。**P8(報告日10月23日に対し「10月24日(実施済み)」)が missed 2/3**。初めての本物の見落とし。文の中だけ読んで日付を突き合わせていない
- postmortem-planted / somosomo: 3/5。**PS5(改修を戻す案と比べたか)が 0 found / 1 partial / 2 missed**。スキルの型が「何もしない・自前・範囲」で、「元に戻す」を持っていなかった。PS2 は 1 found / 2 partial(問いの捉え方の揺れ)
- postmortem-clean: logic false 1(0.33/回)、somosomo false 0。crossing は全素材で 0
- 直したこと: logic.md の矛盾に「日付・時刻・件数・割合を報告日・表・本文と突き合わせる」を追加。somosomo.md と judge.txt の型に「元に戻す・やめる」を追加
- 細かい仕込みで、合否の基準が見落としにも反応するようになった(稟議書では r1 から一度も落ちなかった)

## 2026-10-31 r7(r6 の2か所を直しての通し)

- 機械検査 23/24(落ちはハーネス側。YAML 保存先の行を目印の途中で切り、前半を箇条書きと誤認した。行ごと落とすように修正)
- ringi-planted: logic 9/9、somosomo 5/5。ringi-clean: false 1 / 0
- postmortem-planted / logic: 8/8。**P8 が 3/3 found**(r6 は 1/3)。日付の突き合わせの追記が効いた。ただし crossing 1:「10月21日(火)は2026年では水曜」と暦に照合した。規則上は持ち込みで、素材の曜日は作成時の誤り(実際に水曜)。素材を直し、logic.md に「暦・単位換算・業界の常識との照合も持ち込み」を明記
- postmortem-planted / somosomo: 3/5。PS5 は 3回とも「改修を元に戻す道と比べたか」を問えたが、判定者が「障害中の切り戻し」という角度を partial にした(1 found / 2 partial)。judge.txt に「仕込んだ問題を含んでいれば、別の角度を足していても found」を明記。PS2 は 1 found / 2 partial で、somosomo.md の問いそのものに「文書が読み手に何を求めているか(共有だけか、判断か)」を追加
- postmortem-clean: logic false 1、somosomo false 1(いずれも 0.33/回)。crossing 0

## 2026-10-31 r8(r7 の修正後の通し)

- 機械検査 24/24。仕込んだ欠陥は4組すべて 100%(ringi logic 9/9、somosomo 5/5、postmortem logic 8/8、somosomo 5/5)。PS2・PS5 も 3/3 found
- 欠陥なしの文書: ringi-clean logic false 2(0.67/回)、ほかは false 0。crossing 0
- 落ちは1件だけ。ringi-planted / logic の2回目が「評価は自己申告の数字に拠るが、ツール側の利用記録は使わないのか」と、文書にない測り方を持ち込んだ(crossing)。logic.md に「別の測り方や手段の代案も持ち込み。文書にある測り方の根拠を問うにとどめる」を追加

## 2026-10-31 r9(r8 の修正後の通し。端から端まで合格)

- 機械検査 24/24。仕込んだ欠陥は4組すべて 3回とも found(ringi logic 9/9、somosomo 5/5、postmortem logic 8/8、somosomo 5/5。任意の L10・P9 も 3/3)
- 仕込んでいない指摘: 持ち込み 0(全素材・全モード)。読み違いは ringi-clean で logic 1・somosomo 1(0.33/回)、postmortem-clean で 0
- 判定 PASS。素材を4本にしてから初めて、通し1回で合否の基準をすべて満たした
- r1 から r9 までにスキルの指示を変えたのは7か所。coverage.py の組み込み、直し方の禁止、YAML 2欄の構造化、文書内の案の名指しの許可、日付・時刻・割合の突き合わせ、「元に戻す」の型、暦・常識・別の測り方の持ち込み禁止、問いそのものに「文書が読み手に何を求めているか」。いずれもハーネスが先に見つけた
