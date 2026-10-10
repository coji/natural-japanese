# AI が大量に書く時代の読み手の変化(調査メモ)

調査日: 2026-10-03
目的: natural-japanese の方針づくりの材料。「長文が読まれなくなった」「長文というだけで AI だと思われる」という問題意識を、データで確かめる。

## 1. 要点

- 画面で説明文を読むと、紙より理解がやや落ちる。差は小さいが、時間に追われると広がる(メタ分析で g = -0.21、手持ち端末で g = -0.11)。人はもともと Web の文章を流し読みする。
- AI の文章は大量に出回っている。LinkedIn の長文投稿の約4割が AI 生成と判定された。職場では米国の就業者の4割が、中身のない AI 文書(workslop)を1か月以内に受け取っている。
- 人は AI の文章をほとんど見抜けない。日本語の実験でも同じだった。見抜けるのは AI をよく使う人だけ。
- 信頼が落ちるのは「AI が書いた」と知ったとき、または疑ったときだ。中身を知らせずに比べると、AI の文章のほうが好まれることさえある。
- 日本の職場では反発は限定的だ。AI メールを「手抜き・不誠実」と感じる人は3.94%にとどまる。不快なメールの1位は「質問に答えていない」(44.29%)で、長さではない。AI 文章によく触れる人ほど、否定的な反応は少ない。
- 「長文というだけで AI と感じる」ことを直接測った調査は、見つからなかった(未確認)。間接証拠はある。手がかりとして挙がるのは、長さそのものより「説明しすぎ」「本人らしくない言い回し」「丁寧すぎる」といった性質だ。
- 読み手として AI も加わった。AI 要約が出ると検索結果のクリックは半分に減る。技術文書サイトへのアクセスの4割強は AI エージェントだ。一方で AI 要約は、条件や限定を落としやすい。
- まとめると、問題は長さより「短く済む話を長く読まされること」と「人が書いた痕跡のなさ」にある。

## 2. 知見

### 2.1 画面で長文を読む負担と、読まれ方の変化

**画面での読解は紙よりやや劣る。** Delgado らのメタ分析(2018年、54研究・約17万人)は、紙のほうが理解がよいと報告した(効果量 g = -0.21)。差が出るのは説明的な文章で、物語文では差がない。差は2000年から2017年にかけて大きくなっていた[1][2]。2023年のメタ分析は、タブレットなどの手持ち端末でも同じ傾向を確かめた。効果量は g = -0.113(参加者間 38研究)と -0.103(参加者内 21研究)で、小さいが有意だった[3]。

**時間に追われると差が広がる。** Delgado と Salmerón(2020年)の実験では、時間制限つきで画面で読んだ群だけ理解が落ちた。紙で読んだ群は、時間に追われると気が散る割合を減らせた。画面の群はそれができなかった[4]。仕事の文書は、まさに時間に追われて画面で読まれる。

**Web の文章はもともと流し読みされる。** Nielsen Norman Group(NN/g)は2020年の総括で、人は Web の文章を一語ずつ読まず、流し読みすると述べた。この傾向は23年間変わっていない。対策として、見出し、要点を先に書くこと、箇条書きと太字、平易な言葉を挙げている[5]。

**注意の持続は短い。** Gloria Mark の観察研究では、1つの画面にとどまる時間は2004年の平均約2分半から、2010年代後半には平均47秒に縮んだ[6]。画面を切り替えるまでの時間を測った数字で、脳の限界ではない。2023年の書籍が出典で、2024年以降の新しいデータではない。

**職場の文字量は多い。** Microsoft の Work Trend Index 2025 によると、平均的な就業者は1日に117通のメールと153件の Teams メッセージを受け取る。中断は2分に1回、1日275回だ[7]。日本のビジネスメール実態調査2026(1,293人、2026年4月)では、1日の受信は46.49通、1通を読むのに平均1分39秒かかっていた[8]。

**読了率の数字は限られる。** Chartbeat によると、2025年のニュース記事の平均閲読時間は世界で26〜30秒だった[9]。ただし原文ページに接続できず、検索結果の要約で確認しただけだ。記事の何割まで読まれるかの2024年以降の信頼できるデータは、未確認。

**日本の読書習慣。** 文化庁の令和5年度「国語に関する世論調査」(2024年1〜3月、16歳以上、回答3,559人)では、月に1冊も本を読まない人が62.6%だった。読書量が減ったと答えた人は69.1%で、理由の1位は「携帯電話やスマートフォンで時間が取られる」(43.6%)だった[10]。若者では、SHIBUYA109 lab. の調査(2026年2月、15〜24歳574人、一都三県)で62.2%が「スマホ疲れ」を感じていた[11]。ただし、どちらも長文の読解力そのものを測った調査ではない。

### 2.2 「AI が書いた文章」への読み手の反応

**AI の文章は大量に出回っている。** Pangram は、2026年4月以降にブラウザ拡張で集めた100万件超の投稿を判定した。250語を超える長文投稿のうち、AI 生成と判定されたのは LinkedIn で41%、X で25%だった。Pangram は検出精度に限界があると認めている[12]。論文の世界では、Kobak ら(2025年、Science Advances)が1,500万件の PubMed 抄録を分析した。"delves" などの語が急増しており、2024年の抄録の少なくとも13.5%が LLM の手を経たと推定した[13]。Merriam-Webster は2025年の今年の言葉に "slop" を選び、「AI で大量に作られる低品質なデジタルコンテンツ」と定義した[14]。

**人はほとんど見抜けない。** Jakesch ら(2023年、PNAS、4,650人)の実験では、AI が書いた自己紹介文を見抜けた割合は偶然と変わらなかった。人は「一人称」「家族の話題」を人間らしさの手がかりにするが、AI も同じように書く[15]。日本語でも同じだ。財津ら(2025年、PLOS ONE)は日本人403人に判定させた。人間の文章を正しく人間と判定できたのは31.5%だった。Claude 3.5 の文章を AI と見抜けた割合は56.8%で、GPT-4o や o1 の文章はさらに人間と誤認されやすかった。回答者は言い回し、文末、接続詞、句読点といった表面の特徴で判断していた。一方、文体の計量分析では両者をほぼ完全に分けられた[16]。

**見抜けるのは AI をよく使う人だけ。** Russell ら(2025年)の実験では、ChatGPT を執筆によく使う5人の多数決で、300本中1本しか誤らなかった。使わない人の判定はほぼ偶然だった。手がかりとして最も多く挙がったのは語彙(53.1%)で、文の構造(35.9%)、文法と句読点の完璧さ(24.8%)、独自性のなさ(23.7%)が続いた。「説明しすぎ・関係の薄い細部」(19.5%)も挙がっている[17]。

**書式の手がかり。** 英語版 Wikipedia の編集者ガイド「Signs of AI writing」は、太字の多用、太字の小見出しつき箇条書き、三つ並べ、「X ではなく Y」型の対比、節末のまとめ、誇張した意義づけなどを挙げる。同時に、人間も同じ書き方をすることがあり、誤判定の危険が大きいと注意している[18]。ただし、これは英語圏の編集者の経験則だ。日本語の読み手が箇条書きや太字を AI のしるしと見なすかを測った調査は、未確認。

**信頼が落ちるのは、AI だと知ったときだ。**

- Schilke と Reimann(2025年、Organizational Behavior and Human Decision Processes)は13の実験で、AI の使用を開示した人は開示しない人より信頼されないことを示した。上司・部下・教員・アナリストのどの立場でも、どの課題でも同じだった[19]。
- Cardon と Coman(2025年、International Journal of Business Communication、米国の就業者約1,100人)では、上司が AI を多く使って書いたメールを誠実だと見た人は40〜52%だった。AI をあまり使わないメールでは83%だった。自分の AI 利用には甘く、上司の利用には厳しいという差もあった[20]。
- Bynder(2024年、英米2,000人)では、出所を伏せると56%が AI の記事を好んだ。しかし AI だと疑ったときは、52%が関心が下がると答えた[21]。詩でも、Porter と Machery(2024年、Scientific Reports)は、AI の詩のほうが人間らしいと判定され、評価も高かったと報告した[22]。

**「長文=AI」の直接証拠はない。** 長さを AI 判定の手がかりとして挙げた人の割合を測った調査は、見つからなかった(未確認)。間接証拠は次のとおり。

- Russell らの「説明しすぎ」(19.5%)[17]
- スタンフォード大学の2024年の報告: 調査の自由回答では、AI の回答は人間より長く、誤字がなく、感じがよすぎた(原文ページは取得できず、検索結果の要約で確認)[23]
- NN/g の2026年の観察(9人): サイト内チャットボットの回答に「長すぎる」という不満が出た[24]
- 日本の個人ブログの議論: 「ちょっとしたアイデアをAIで長文記事にして公開するのをやめろ」(2026年5月、はてなブックマーク260件)は、読み手が怒るのは「短く済む話を長く読まされたとき」だと書く[25]。これは個人の意見で、補助的な材料にとどまる。

**消費者全体の空気。** Gartner(2026年6月発表、米国の消費者307人)では、49%が「AI でコンテンツの質が下がった」と答えた[26]。標本は小さい。ほかに「54% が AI 疲れ」「AI と見なされた投稿はエンゲージメントが20〜35%低い」といった数字が出回っている。一次情報をたどれなかったので、未確認として扱う。

### 2.3 職場の文書で起きていること

**workslop。** BetterUp Labs とスタンフォード大学 Social Media Lab は、2025年9月の Harvard Business Review で「workslop」という言葉を提案した。見た目は立派だが、仕事を前に進める中身のない AI 生成物を指す[27]。米国のフルタイム就業者1,150人の調査では、約4割(報道により40%または41%)が直近1か月に受け取っていた。受け取る仕事の文書の約15%が workslop だった。1件の処理に平均1時間56分かかった。受け手の53%がいらだち、42%が送り手を信頼できなくなったと答えた[27][28][29]。HBR の原文は有料で読めず、数字は報道で確認した。

**AI を使っても検証しない。** KPMG とメルボルン大学の調査(47か国の就業者32,352人)では、AI を使う就業者の66%が出力を検証せずに使っていた[29]。

**AI に読ませる行動。** Microsoft の実験(2025年、56社・6,000人超)では、Copilot を使えるようにした人はメールを読む時間が週12分(7%)減った。よく使う人では週31分(18%)減った[30]。EY の調査(2025年8月、29か国の従業員15,000人)では、88%が毎日 AI を使っていたが、主な用途は検索と文書の要約だった[31]。

**日本の職場の反応は、思ったより穏やかだ。**

| 調査 | 標本・時期 | 主な結果 |
|---|---|---|
| ビジネスメール実態調査2026[8] | 1,293人、2026年4月 | メールに生成 AI を使う 63.96%。相手のメールが AI 作成と気づく 44.86%。手がかりは「本人らしくない言い回し」48.28%、「丁寧すぎる不自然さ」45.52%。AI メールを「手抜き・不誠実」と感じる人は 3.94% |
| マイナビニュース[32] | 会員485人、2026年4〜5月 | AI が書いたと感じた経験 66.9%。「内容が正確なら問題ない」47.2%、「やや手抜き」15.3%、「不誠実」11.3%。否定的な人の割合は、気づく頻度が高い層ほど低い(よくある 10.3%、まったくない 36.6%) |
| エムフロ[33] | 就業者500人、2026年5月 | AI 文章に気づいた経験 60.4%。悪印象 42.4%(理由は「気持ちが伝わらない」25.9% など)。「気にならない」57.6% |
| ユミルリンク・ライトアップ[34] | メルマガ購読者1,000人、2026年7月 | AI 作成と感じた経験 46.3%(20代 62.4%)。印象は「冷たい・手抜き」44.1%、「効率的で読みやすい」21.1% |

不快なメールの上位は「質問に答えていない」(44.29%)と「高圧的・見下した表現」(37.3%)だった[8]。「長い」も選択肢にあるが、割合は公表資料で確認できなかった。前年の調査では、「うまい」と評価されるメールの共通点として「要点の簡潔さ」と「構成の明快さ」が挙がっている[35]。

これらの調査はネット調査で、調査会社が主体のものが多い。質問の文言によって数字は大きく変わる。調査の間で数字を直接比べることはできない。

### 2.4 逆方向の論点

**長い文章も、価値があれば読まれる。** Pew Research Center(2016年)はスマホでのニュース閲覧1億1,700万件を分析した。1,000語以上の記事の閲読時間は平均123秒で、短い記事(57秒)の約2倍だった[36]。2024年以降の範囲外だが、読まれ方の深さを示す数少ない大規模データとして残す。

**散文には役割がある。** Amazon は会議資料にスライドを禁じ、6ページの文章形式のメモを使う。Bezos は、箇条書きでは考えの弱さを隠せるが、物語形式のメモではそうはいかないと述べた[37]。短くしすぎると、論理のつながりや前提が消える。短すぎるメッセージの弊害を測った2024年以降の研究は、未確認。

**流し読み向けの書式は、いまも推奨されている。** NN/g は見出し、箇条書き、太字を流し読みの助けとして勧める[5]。2026年の観察でも、利用者は短く要点がわかる回答を好み、「箇条書きのほうがいい」という声があった[24]。一方、同じ書式が AI のしるしとして挙げられている[18]。どちらに寄せても代償がある。

**AI 要約が前提になりつつある。**

- Pew(2025年3月、米国の成人900人の閲覧記録)では、AI 要約が出た検索でリンクをクリックした割合は8%、出ないときは15%だった。要約内のリンクのクリックは1%だった[38]。
- NTT ドコモ モバイル社会研究所(2025年11月、生成 AI 利用者544人)では、約64%が AI 要約を見て、リンクを開かずに済ませることがあると答えた[39]。
- Mintlify(2026年3月、自社が運営する技術文書サイトの30日分)では、リクエストの45.3%が AI エージェントからで、ブラウザ(45.8%)とほぼ同じだった[40]。用途が技術文書に偏った自社データである点に注意がいる。

**AI 要約は条件や限定を落とす。** Peters と Chin-Yee(2025年、Royal Society Open Science)は、10のモデルが作った約5,000件の科学論文の要約を調べた。AI の要約は人間の要約より約5倍、結論を一般化しすぎていた[41]。EBU と BBC の調査(2025年10月、18か国・14言語、3,000件超の回答)では、AI アシスタントのニュース回答の45%に重大な問題があった[42]。Apple は2025年1月、通知のニュース要約の誤りを受けて機能を一時停止した[43]。つまり、AI に読まれることを前提にするなら、条件や例外が要約で消えにくい書き方が要る。

### 2.5 日本固有の事情

**AI の普及は欧米より遅れて、いま急に進んでいる。** 令和7年版情報通信白書では、生成 AI の利用経験は2024年度調査で26.7%だった。米国は68.8%、中国は81.2%だった[44]。NTT ドコモ モバイル社会研究所の調査では、2025年2月の27%から2026年2月の51%に増えた[45]。調査と定義が違うので、同じ物差しの推移ではない。英語圏で起きた反発が、遅れて日本で強まる可能性はある。ただし、それは推測だ。

**日本の読み手の手がかりは「らしさ」と丁寧さ。** 日本の調査で AI の手がかりとして挙がるのは、「本人らしくない言い回し」「丁寧すぎる不自然さ」[8]、文末・接続詞・句読点[16]だった。英語圏で語られる "delve" や em dash とは中身が違う。

**関係への配慮が反発の理由になる。** エムフロの調査で悪印象の理由として最も多かったのは「気持ちが伝わらない」(25.9%)と「軽視されていると感じる」(19.8%)だった[33]。品質より、相手にかけた手間が問われている。

**AI 臭さを消す需要は大きい。** 「AIっぽさを消すプロンプト」を扱う記事は多く出ている。ただし、ほとんどが個人ブログや業者の記事で、根拠は示されていない。

## 3. スキルの方針への示唆

ここから先は、上の事実からの示唆であり、検証済みの結論ではない。

### 3.1 読みやすさの原則に足す観点

- **長さではなく情報密度を見る。** 読み手が嫌がるのは「短く済む話を長く読まされること」だ[25]。画面で、時間に追われて読む説明文ほど理解が落ちる[1][4]。新しい情報を運ばない文(前置き、自明な説明、言い換えの繰り返し、締めのまとめ)を削る。必要な長さは削らない。
- **問いに最初に答える。** 日本の職場で最も不快とされたのは「質問に答えていない」メールだった[8]。依頼や質問への返事は、冒頭の一文で答える。
- **丁寧さを盛りすぎない。** 「丁寧すぎる」は日本の読み手が AI を疑う手がかりの上位だった[8]。定型の前置きやクッション言葉の重ねを減らす。
- **書き手の痕跡を残す。** 反発の理由は「気持ちが伝わらない」「軽視されている」だった[33]。固有名詞、具体的な数字、その場の判断、書き手が実際に確かめたことを残す。一般論で埋めない。
- **要約されても条件が落ちない書き方。** AI 要約は限定を落とし、一般化しすぎる[41]。条件や例外は、主張と同じ文か直後に置く。離れた段落や脚注に回さない。見出しは中身がわかる言葉にし、段落は単独で読んでも通じるようにする。人間の流し読みにも AI の抜き出しにも効く。
- **書式は内容に合わせる。** 箇条書きと太字は流し読みを助ける[5][24]が、多用すると AI のしるしにもなる[18]。並列の情報だけ箇条書きにする。論理のつながりは文で書く。太字は1画面に数か所までにする。

### 3.2 検証で測るべきもの

- 冒頭(たとえば最初の100〜200字)に結論や答えがあるか
- 段落あたりの新しい情報の量。前置き・繰り返し・締めのまとめの文の割合
- 原文に対する削減率と、削ったあとも必要な情報が残っているか(情報の欠落チェック)
- 丁寧表現・クッション言葉の密度
- 箇条書き・太字・見出しの密度
- AI 要約に通したとき、条件や数字が保たれるか(元の文書と要約を比べる)
- 可能なら読み手の評価: 「AI が書いたと思うか」「信頼できるか」「答えがすぐ見つかったか」を、書き直し前後で比べる

### 3.3 やりすぎの注意

- **短さを目標にしない。** 長い文書が要る場面はある[36][37]。前提や理由を削りすぎると、受け手が聞き返す手間が増える。
- **「AI らしさ」の目録を追いかけすぎない。** 手がかりはモデルの更新で変わる。人間の判定も当てにならない[15][16]。表面の特徴を消すことより、中身(答え、具体性、書き手の判断)を優先する。
- **読み手の多くは気にしていない。** 日本の職場では「内容が正確なら問題ない」が多数派だ[8][32]。AI 臭さの除去を、正確さや伝わりやすさより上に置かない。
- **流し読み向けの書式を一律に禁じない。** 手順や比較など、箇条書きや表が向く内容はある。
- **英語圏の知見をそのまま持ち込まない。** 日本語の読み手の手がかりは英語圏と違う[8][16]。日本語の調査はネット調査が中心で、標本の偏りがある。

## 4. 出典一覧

一次情報を優先した。報道・まとめ経由のものはその旨を書いた。

1. Delgado, P. et al. (2018). Don't throw away your printed books: A meta-analysis on the effects of reading media on reading comprehension. *Educational Research Review*, 25, 23–38. https://www.sciencedirect.com/science/article/pii/S1747938X18300101 (本文は取得できず、数字は [2] と検索結果で確認)
2. TUM Center for Educational Technologies「Don't throw away your printed books」解説. https://www.edtech.tum.de/dont-throw-away-your-printed-books-why-reading-performance-is-better-on-paper-than-on-screens/
3. Salmerón, L. et al. (2023). Reading comprehension on handheld devices vs. on paper: A narrative review and meta-analysis. *Journal of Educational Psychology*. https://doi.org/10.1037/edu0000830 (プレプリント: https://www.uv.es/lasalgon/papers/Salmeron%202023%20manuscript_tablets.pdf)
4. Delgado, P. & Salmerón, L. (2020). The inattentive on-screen reading. *Learning and Instruction*. https://pmc.ncbi.nlm.nih.gov/articles/PMC7463273/
5. Nielsen Norman Group (2020-04-05). How People Read Online: New and Old Findings. https://www.nngroup.com/articles/how-people-read-online/
6. Gloria Mark『Attention Span』(2023) の紹介. https://gloriamark.com/attention-span/ ほか https://www.sciline.org/public-health/shrinking-attention-spans/
7. Microsoft Work Trend Index 2025(報道経由). https://www.microsoft.com/en-us/microsoft-365/blog/2025/06/26/how-microsoft-365-copilot-and-agents-help-tackle-the-infinite-workday/ 、https://en.wikipedia.org/wiki/Infinite_workday
8. 日本ビジネスメール協会「ビジネスメール実態調査2026」. https://businessmail.or.jp/research/2026-result/ 、プレスリリース https://www.value-press.com/pressrelease/375260
9. Chartbeat, Global audience insights 2025(Q1〜Q3). https://chartbeat.com/resources/articles/third-quarter-global-audience-insights-2025/ (接続できず、検索結果の要約で確認)
10. 文化庁「令和5年度 国語に関する世論調査」. https://www.bunka.go.jp/tokei_hakusho_shuppan/tokeichosa/kokugo_yoronchosa/index.html 、数字は nippon.com の整理 https://www.nippon.com/ja/japan-data/h02135/ で確認
11. SHIBUYA109 lab.「Z世代のアテンション・デトックスに関する調査」(2026). https://www.shibuya109.co.jp/shibuya109lab/reports/20260312/
12. The Register (2026-07-09). AI slop writing has taken over the internet, particularly LinkedIn and X(Pangram の分析). https://www.theregister.com/ai-and-ml/2026/07/09/ai-slop-writing-has-taken-over-the-internet-particularly-linkedin-and-x/5269525
13. Kobak, D. et al. (2025). Delving into LLM-assisted writing in biomedical publications through excess vocabulary. *Science Advances*, 11(27). https://www.science.org/doi/10.1126/sciadv.adt3813
14. NBC News (2025-12-15). Merriam-Webster names 'slop' as its 2025 word of the year. https://www.nbcnews.com/news/us-news/merriam-webster-word-of-the-year-2025-rcna247864
15. Jakesch, M. et al. (2023). Human heuristics for AI-generated language are flawed. *PNAS*. https://ui.adsabs.harvard.edu/abs/2023PNAS..12008839J/abstract
16. Zaitsu, W. et al. (2025). Stylometry can reveal artificial intelligence authorship, but humans struggle. *PLOS ONE*. https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0335369
17. Russell, J., Karpinska, M. & Iyyer, M. (2025). People who frequently use ChatGPT for writing tasks are accurate and robust detectors of AI-generated text. ACL 2025. https://arxiv.org/abs/2501.15654
18. Wikipedia: Signs of AI writing. https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing
19. Schilke, O. & Reimann, M. (2025). The transparency dilemma: How AI disclosure erodes trust. *Organizational Behavior and Human Decision Processes*. https://par.nsf.gov/biblio/10597787-transparency-dilemma-how-ai-disclosure-erodes-trust
20. Cardon, P. W. & Coman, A. W. (2025). Professionalism and Trustworthiness in AI-Assisted Workplace Writing. *International Journal of Business Communication*(紹介記事). https://www.sciencedaily.com/releases/2025/08/250811104226.htm
21. Bynder (2024-04-03). AI vs human-made content study. https://www.bynder.com/en/press-media/ai-vs-human-made-content-study/ (企業調査)
22. Porter, B. & Machery, E. (2024). AI-generated poetry is indistinguishable from human-written poetry and is rated more favorably. *Scientific Reports*. https://www.nature.com/articles/s41598-024-76900-1
23. Stanford Report (2024-11). AI-generated survey responses could make research less accurate. https://news.stanford.edu/stories/2024/11/ai-generated-survey-responses-could-make-research-less-accurate-lot-less-interesting (取得できず、検索結果の要約で確認)
24. Nielsen Norman Group (2026-04-17). Less Chat, More Answer: Site AI Chatbots Need to Get to the Point. https://www.nngroup.com/articles/less-chat-more-answer/
25. todesking (2026-05-12)「ちょっとしたアイデアをAIで長文記事にして公開するのをやめろ」(個人ブログ). https://zenn.dev/todesking/articles/fba4cc93baf0a9 、はてなブックマーク https://b.hatena.ne.jp/entry/s/zenn.dev/todesking/articles/fba4cc93baf0a9
26. CX Today. Gartner Data: 49% of U.S. Consumers Say AI Has Made Content Quality Worse(報道経由). https://www.cxtoday.com/marketing-sales-technology/gartner-ai-generated-content-quality-marketing-fatigue/
27. Niederhoffer, K. et al. (2025-09-22). AI-Generated "Workslop" Is Destroying Productivity. *Harvard Business Review*. https://hbr.org/2025/09/ai-generated-workslop-is-destroying-productivity (有料。数字は [28][29] ほかの報道で確認)
28. UNLEASH. 40% of AI-generated content is 'workslop'. https://www.unleash.ai/artificial-intelligence/news/40-of-ai-generated-content-is-workslop-and-it-drives-over-9-million-in-lost-productivity-annually-finds-betterup ; The Hustle https://thehustle.co/news/workers-are-irritating-colleagues-with-useless-workslop
29. The Conversation. AI 'workslop' is creating unnecessary extra work. https://theconversation.com/ai-workslop-is-creating-unnecessary-extra-work-heres-how-we-can-stop-it-267110 (KPMG・メルボルン大学の調査の数字もここで確認)
30. Dillon, E. W. et al. (2025). Early Impacts of M365 Copilot. https://arxiv.org/html/2504.11443v1
31. EY (2025-11). EY 2025 Work Reimagined Survey. https://www.ey.com/en_gl/newsroom/2025/11/ey-survey-reveals-companies-are-missing-out-on-up-to-40-percent-of-ai-productivity-gains-due-to-gaps-in-talent-strategy
32. マイナビニュース (2026-05-14)「ChatGPTの文章はバレる？ 受け手485人のアンケート結果が示す本音」. https://news.mynavi.jp/techplus/article/revealed_chatgpt-1sUbRTdS/
33. エムフロ調査(2026年5月)の報道. Forbes JAPAN https://forbesjapan.com/articles/detail/100190 、まいどなニュース https://maidonanews.jp/article/16760736
34. Web担当者Forum (2026-09-04). ユミルリンク・ライトアップ調査. https://webtan.impress.co.jp/n/2026/09/04/53245
35. 日本ビジネスメール協会「ビジネスメール実態調査2025」プレスリリース. https://www.value-press.com/pressrelease/356743
36. Pew Research Center (2016-05-05). Long-Form Reading Shows Signs of Life in Our Mobile News World. https://www.pewresearch.org/journalism/2016/05/05/long-form-reading-shows-signs-of-life-in-our-mobile-news-world/
37. CNBC (2018-04-23). Why Jeff Bezos makes Amazon execs read 6-page memos. https://www.cnbc.com/2018/04/23/what-jeff-bezos-learned-from-requiring-6-page-memos-at-amazon.html
38. Pew Research Center (2025-07-22). Google users are less likely to click on links when an AI summary appears in the results. https://www.pewresearch.org/short-reads/2025/07/22/google-users-are-less-likely-to-click-on-links-when-an-ai-summary-appears-in-the-results/
39. NTT ドコモ モバイル社会研究所 (2026-02-05)「6割超がAI要約で検索完結」. https://www.moba-ken.jp/project/lifestyle/20260205.html
40. Mintlify (2026-04-03). The state of agent traffic in documentation (March 2026). https://www.mintlify.com/blog/state-of-ai (企業の自社データ)
41. Peters, U. & Chin-Yee, B. (2025). Generalization bias in large language model summarization of scientific research. *Royal Society Open Science*. https://doi.org/10.1098/rsos.241776 (紹介記事 https://phys.org/news/2025-05-prominent-chatbots-routinely-exaggerate-science.html)
42. EBU & BBC (2025-10). News Integrity in AI Assistants. https://www.ebu.ch/files/live/sites/ebu/files/Publications/MIS/open/EBU-MIS-BBC_News_Integrity_in_AI_Assistants_Toolkit_2025.pdf
43. CNBC (2025-01-16). Apple disables AI notifications for news in its beta iPhone software. https://www.cnbc.com/2025/01/16/apple-disables-ai-notifications-for-news-in-its-beta-iphone-software.html
44. 総務省「令和7年版 情報通信白書」個人におけるAI利用の現状. https://www.soumu.go.jp/johotsusintokei/whitepaper/ja/r07/html/nd112210.html
45. NTT ドコモ モバイル社会研究所 (2026-04-06)「生成AI利用率、過半数に」. https://www.moba-ken.jp/project/lifestyle/20260406.html

### 確認できなかったもの

- 「長文というだけで AI と感じる」人の割合を直接測った調査
- 日本語の読み手が箇条書き・太字を AI のしるしと見なすかを測った調査
- 2024年以降の記事の読了率(どこまで読まれるか)の信頼できるデータ
- 短すぎるメッセージの弊害を測った2024年以降の研究
- 出回っている次の数字の一次情報: 「54% が AI 疲れ」、AI と見なされた投稿のエンゲージメント20〜35%減、Deloitte の「70% がオンラインの内容に懐疑的」、IDC の要約ツール週次利用34%、YouGov の「AI の文章をよく見抜ける 8%」
