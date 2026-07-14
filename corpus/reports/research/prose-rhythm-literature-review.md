# 文章のリズムは何を指し、何が分かっているか

## 調査目的

「文章のリズム」は研究上どのように扱われてきたかを調べ、文長の変動、文末、読点、反復、語彙・構文の多様性について、分かっていることと分かっていないことを切り分ける。あわせて、`natural-japanese` の検出器が先行研究とどのような関係にあるかを確認する。

調査では、次の四つを意識して分けた。

1. 文体を記述・識別する特徴
2. 読みやすさや理解を改善する特徴
3. 人間文とAI生成文を区別する特徴
4. 読者がリズムとして知覚する特徴

同じ文長や読点を扱っていても、この四つは別の問いである。著者識別に有効な特徴が読みやすさを高めるとは限らず、ある生成モデルを識別できる特徴が人間らしさの一般条件になるとも限らない。

## 調査方法と範囲

日本語と英語の査読論文を中心に、計量文体学、可読性、心理言語学、自然言語処理、AI生成文検出を調べた。主な探索先はJ-STAGE、CiNii Research、ACL Anthology、PMLR、出版社の論文ページである。検索では「文章 リズム」「文長 分布」「計量文体」「日本語 可読性」「prose rhythm」「sentence length variation」「AI-generated text stylometry」などを組み合わせた。主要文献について研究対象、測定方法、結果、限界を確認し、`natural-japanese` の検出項目と照合した。調査日は2026年7月14日である。

これは系統的レビューではない。検索式、データベース、採否基準を事前登録した網羅調査ではなく、概念と主要研究を把握するための探索的レビューである。特に日本語の散文リズムを読者実験で扱った研究は、検索語によって漏れている可能性がある。AI生成文の研究はモデル更新が速いため、個々の精度よりも、どの条件で結果が変わるかを重視した。

## 結論

文章のリズムは、単一の確立した尺度ではない。研究上は少なくとも、音声・韻律、文長系列、句読点による暗黙の韻律、文末や統語の反復、語や話題の再出現といった複数の現象に分かれている。

文長、文長分布、読点の位置・間隔、文末表現、品詞・助詞の系列は、古くから文体を記述する特徴として使われてきた。文長の並び順や自己相関を散文リズムとして扱う研究も、少なくとも1996年には存在する。したがって、「文章のリズムに着目する」という発想そのものに新規性はない。

一方、今回確認した範囲では、次の一般則を直接支持する研究は見つからなかった。

- 文長のばらつきが大きいほど文章は読みやすい
- 文長のばらつきが大きいほど文章の質が高い
- 文長のばらつきが大きいほど人間らしい
- 反復が少ないほど自然である

AI生成文が特定条件で人間文より均質になるという報告はある。しかし、差の方向と大きさは言語、ジャンル、人間側の比較集団、モデル、プロンプト、生成時の語の選び方に依存する。文長などの変動が小さい状態を指す “burstinessの低さ” は、AI文章に必ず現れる特徴ではない。

`natural-japanese` のリズム検出器は、編集時に読み直す箇所を示すヒューリスティックと位置づけるのが妥当である。AI判定や普遍的な品質評価には使えない。現行の「検出は機械、判断はAI」という設計は、この研究状況と整合する。

## 1. 「文章のリズム」は一つの概念ではない

### 1.1 音声的・知覚的なリズム

散文リズムの初期の実験研究として、Patterson（1917）がある。散文を音節単位の打音へ変換して聴取させ、読者が不規則な音配列をどのように組織化するかを調べた。歴史的には重要だが、標本は12名で、現代の実験計画としては根拠が弱い。

この系統で扱うのは、紙面上の文字数よりも、強勢、時間、休止、文の調子といった音声的な現象である。Steinhauer & Friederici（2001）やDrury et al.（2016）は、脳波から言語処理を調べるERP（事象関連電位）実験を行った。黙読時の句読点にも、音声の韻律境界と似た脳反応が現れた。Hirotani et al.（2006）の眼球運動実験も、読点とイントネーション境界が節末・文末の処理に影響することを示す。

読点が韻律処理に関与しても、その数や間隔だけで「良いリズム」は採点できない。読点の効果は統語、意味、読み手の習慣と相互作用する。

### 1.2 文長の分布と並び順

Yule（1939）は文長を散文の統計的な文体特徴として扱った。Sichel（1974）は文長分布に確率分布を当てはめている。この系譜が扱うのは、主として作者や文章の特徴であり、読みやすさや美的価値ではない。

Roberts（1996）はさらに踏み込み、Joyce Caryの小説3作について、1〜5文離れた文長どうしの相関を調べた。2作では4文間隔、1作では3文間隔の周期的な傾向を報告している。この研究は、長短の文が並ぶ順序をリズムとして測った。分散の大小だけを見たものではない。単一作家の3抜粋による探索的な事例研究なので、結果は一般化できない。

文長の「変化」には少なくとも次の別々の尺度がある。

- 分布の散らばり：標準偏差、変動係数
- 隣接文の差：前後の文長がどれほど変わるか
- 自己相関：一定の間隔で長短が繰り返されるか
- 長距離相関：文章全体に複数スケールの構造があるか

これらは交換可能ではない。Grabska-Gradzińska et al.（2012）は、複数の時間幅にまたがる複雑な規則性を調べる手法で文学作品30作を解析した。明確な規則性を示した作品は少数だった。Marinho et al.（2018）は約500冊で文長の測り方を比較し、語数・文字数など複数の測定法が似た挙動を示すことを報告した。いずれの研究も「分散が大きいほど良い」とは示していない。

### 1.3 反復と平行構造

反復は必ずしも欠陥ではない。語句、統語、意味の系列を意図的に対応させるparallelismは、文章に期待とリズムを作る修辞法である。Bothwell et al.（2023）は修辞的parallelismの自動検出を扱い、厳格な評価ではF1が0.40〜0.43にとどまった。表層的な反復と意図的な平行法を機械だけで区別するのは難しい。

Altmann et al.（2009）が扱う “burstiness” は、同じ語が再び現れるまでの間隔である。AI文章検出で俗に使われる「文長のばらつき」とは別概念なので、同じ用語として扱わないほうがよい。

## 2. 日本語の研究では何が測られてきたか

### 2.1 可読性

Tateisi, Ono & Yamada（1988）は、平均文長、文字種ごとの連続、読点と句点の比などを使った日本語可読性式を提案した。77文章から主成分を求め、文章中の空欄を補う課題と解答時間で妥当性を確認している。文長は可読性に関わる表層特徴の一つだが、文長変動は扱っていない。

Sato, Matsuyoshi & Kondoh（2008）は、小学校から大学までの教科書127冊から1,478文章、約100万字のコーパスを作った。文字1字ごとの出現確率から学年相当を推定し、実際の学年との相関は0.9を超えた。語彙・文字分布によって教材難易度を高い精度で推定できたが、成人向け文章の読みやすさやリズムを直接測った研究ではない。

吉田・中山・清水（2002）は文章理解実験を行い、一文一内容の文章が複数内容を含む文より解答時間を短くすること、内容境界や息の切れ目に置いた読点が理解を助けることを報告した。これは編集原則への比較的直接的な根拠である。ただし、文長分散や文章全体のリズムは検証していない。

柴崎（2014）が指摘するように、可読性式が測るのはテキスト側の特徴である。読者の知識、目的、状況まで含む「読みやすさ」全体とは区別する必要がある。

### 2.2 計量文体学と著者識別

日本語の計量文体研究では、次の特徴が長く使われている。

- 平均文長と文長分布
- 読点の位置、直前品詞、読点間隔
- 品詞・助詞・機能語の頻度とn-gram
- 文節パターン
- 文末表現
- 文字種や文字n-gram
- 語彙多様性

金・樺島・村上（1993）は読点位置や間隔を作家の個性として分析した。金（2013）は文節パターンによる書き手識別を検証し、黄・金（2020）は機能フレーズが著者識別に有効であることを示した。李・金（2019）は『明暗』と『続明暗』の文体模倣を、平均文長、形態素、品詞、文節パターンから分析している。孟（2022）は夏目漱石23作品の文末表現に通時変化があることを示した。

これらは、文長、読点、文末、助詞などが文体を記述する特徴であることを支持する。しかし、その特徴の高低が「良い」「自然」「読みやすい」を意味するわけではない。

### 2.3 係り受け距離

張・尾関（1997）は、日本語の係り受けでは直後への係りが最も多く、文末を除けば距離とともに頻度が低下することを示した。これは日本語の統語分布についての証拠であり、係り受け解析にも有効だった。ただし、長距離依存が読みにくいことを直接測った心理実験ではない。可読性の根拠として使う場合は間接証拠と明記する必要がある。

## 3. AI生成文はリズムが均質なのか

### 3.1 条件付きでは支持される

Muñoz-Ortiz, Gómez-Rodríguez & Vilares（2024）は、英語ニュースについて人間記事と6つのLLMの生成文を比較した。人間文は文長分布と語彙がより多様で、構成素が短く、dependency distanceも異なった。文長分布の均質さを直接扱う一次研究として重要である。

日本語では、Zaitsu & Jin（2023）が、人間の学術論文72本と、その題名からGPT-3.5・GPT-4が生成した各72本を比較した。連続する2品詞、連続する2助詞、読点位置、機能語率を特徴に使った。データを10分割して学習と評価を繰り返す検証で、全特徴を合わせた精度は96.3%だった。日本語でも、この生成条件では文体差が現れた。ただし、文長変動は測っていない。

### 3.2 普遍的特徴とはいえない

Macko et al.（2023）のMULTITuDEは、11言語、8モデル、74,081文章を用いて検出器を比較した。性能は言語とモデルに強く左右され、英語から他言語への一般化も安定しなかった。日本語は含まれていない。

Wang et al.（2024）のM4、Dugan et al.（2024）のRAIDも、未知の文章領域、生成モデル、語の選択方法、反復を抑える設定、検出回避のための軽微な改変によって検出性能が大きく変わることを示す。RAIDは600万件を超える生成文、11モデル、8領域、4種類の生成戦略、11種類の検出回避改変を含む。

語彙多様性についても結果は一方向ではない。人間が書いたニュースとLLMを比べた研究では、人間側の語彙が多様だった。一方、外国語として英語を学ぶ学生の作文と比べたFredrick & Craven（2025）では、ChatGPT側の語彙多様性が高かった。比較する人間集団を変えるだけで結論が反転しうる。

言語モデルにとっての予測しにくさを表すperplexityも、単純な「人間らしさ」の尺度ではない。DetectGPT（Mitchell et al., 2023）は、元の文章と少し書き換えた文章の生成確率を比べる。Sadasivan et al.（2023）は、言い換えによって複数方式の検出率が大きく低下することを実証した。Liang et al.（2023）は英語非母語話者の文章がAI生成と誤判定されやすいことを示している。

したがって、AI生成文と人間文に統計的な差が観察されることと、個々の文章をAI生成と判定できることは分けなければならない。

## 4. `natural-japanese` との照合

### 4.1 先行研究と整合する部分

- 文長、読点、文末、品詞、助詞、語彙多様性を文体特徴として扱うこと
- 文長の平均だけでなく、分布や並び順を見ること
- 反復を機械検出しつつ、修辞的な平行法かどうかを文脈で判断すること
- ジャンル別に分布と閾値を校正すること
- 機械検出を最終判定にしないこと

### 4.2 自前実験に依存する部分

- `low_sentence_variance` をAI的な均質さの疑いとすること
- `low_burstiness` の具体的な算出式と閾値
- 体言止めの欠如を補助信号にすること
- 段落構造の均質さをAI的傾向とみなすこと
- 日本語の現在のLLMに対する各検出器の弁別力

これらは先行研究から直接導ける一般則ではない。リポジトリ内のコーパスで観察された、対象モデル・対象ジャンル・対象時点に限定された結果として扱うのがよい。

### 4.3 見直すべき用語と主張

`low_burstiness` という名前は注意が必要である。burstinessは、語の再出現間隔、token probabilityの変動、文長の変動など、研究によって別の意味を持つ。現在の実装が文長系列のどの統計量を測っているかを名称か説明文に出したほうがよい。

また、「文リズムの単調さを検出する」という説明は測定内容より広い。実際に検出しているのは文長などの代理変数なので、「文長系列の均質さを検出し、単調に感じられる可能性を提示する」と説明するほうが正確である。

## 5. 研究上まだ分からないこと

今回の調査から、次の空白が残った。

1. 現代日本語の実務文で、文長変動が読解時間・理解・主観評価にどう影響するか
2. 文長の標準偏差、変動係数、隣接差、自己相関のどれが知覚されるリズムに対応するか
3. 同じ内容を保ったまま文長系列だけを変えた統制実験
4. 反復が修辞として効く場合と、テンプレ反復として不自然になる場合の境界
5. 現在の日本語LLMを、複数ジャンル・複数生成条件で比較した研究
6. 人間のみの執筆、AIによる軽微な推敲、全面生成と、AIの関与度が異なる文章の評価

`natural-japanese` のコーパス実験は、複数の日本語LLMを比較する問いに部分的に答えている。一方、読者実験がないため、読解時間や知覚されるリズムとの関係は分からない。

その後に実施した[文長系列分析](./sentence-length-analysis.md)では、人間文71件とAI生成文381件を比較した。モーラ文長の変動係数は人間中央値0.698、AI中央値0.431で、このコーパスでは人間文の変動が大きかった。ただし、差はessay・techで大きく、businessで弱まり、標本の少ないslideでは有意でなかった。`burstiness` は変動係数の単調変換にすぎず、現行閾値では人間文の32.4%に発火した。lag-1自己相関は人間中央値0.199、AI -0.053と、現行検出器の仮説とは逆だった。

## 調査から得た実務的な判断

文章リズムを検査する発想は、先行研究のない新規な発見ではない。しかし、既存研究はそのまま編集ツールの仕様を与えてもいない。文長・読点・文末・反復などが文体を記述することは、広く確認されている。句読点や一文一内容が読解処理に影響するとの実験結果もある。AI生成文との統計差は、条件を限定した場合に観察されている。

「疑いを機械で提示し、直すかどうかを文脈で判断する」というワークフローには、実装・運用上の貢献がある。理論上の新発見を主張するものではない。次の作業では、`low_burstiness` の名称と説明を実際の算出式に合わせ、文長の均質さを品質やAI生成の確定判定に使わないことを明記する。その後、文長系列だけを操作した読者実験で、単調さの評定との対応を確かめるのがよい。

## 主要文献

- Altmann, E. G., Pierrehumbert, J. B., & Motter, A. E. (2009). [Beyond Word Frequency: Bursts, Lulls, and Scaling in the Temporal Distributions of Words](https://doi.org/10.1371/journal.pone.0007678). *PLOS ONE*, 4(11), e7678.
- Bothwell, S. et al. (2023). [Introducing Rhetorical Parallelism Detection](https://aclanthology.org/2023.emnlp-main.305/). *EMNLP 2023*, 5007–5039.
- Drury, J. E. et al. (2016). [Punctuation and Implicit Prosody in Silent Reading](https://doi.org/10.3389/fpsyg.2016.01375). *Frontiers in Psychology*, 7, 1375.
- Dugan, L. et al. (2024). [RAID: A Shared Benchmark for Robust Evaluation of Machine-Generated Text Detectors](https://aclanthology.org/2024.acl-long.674/). *ACL 2024*.
- Fredrick, A. J., & Craven, L. (2025). [Lexical diversity, syntactic complexity, and readability: a corpus-based analysis of ChatGPT and L2 student essays](https://doi.org/10.3389/feduc.2025.1616935). *Frontiers in Education*, 10.
- Grabska-Gradzińska, I. et al. (2012). [Multifractal analysis of sentence lengths in English literary texts](https://arxiv.org/abs/1212.3171).
- Hirotani, M., Frazier, L., & Rayner, K. (2006). [Punctuation and intonation effects on clause and sentence wrap-up](https://doi.org/10.1016/j.jml.2005.12.001). *Journal of Memory and Language*, 54, 425–443.
- Liang, W. et al. (2023). [GPT detectors are biased against non-native English writers](https://doi.org/10.1016/j.patter.2023.100779). *Patterns*, 4(7), 100779.
- Macko, D. et al. (2023). [MULTITuDE: Large-Scale Multilingual Machine-Generated Text Detection Benchmark](https://aclanthology.org/2023.emnlp-main.616/). *EMNLP 2023*, 9960–9987.
- Marinho, V. Q. et al. (2018). [Robustness of sentence length measures in written texts](https://doi.org/10.1016/j.physa.2018.05.125). *Physica A*.
- Mitchell, E. et al. (2023). [DetectGPT: Zero-Shot Machine-Generated Text Detection using Probability Curvature](https://proceedings.mlr.press/v202/mitchell23a.html). *ICML 2023*.
- Muñoz-Ortiz, A., Gómez-Rodríguez, C., & Vilares, D. (2024). [Contrasting Linguistic Patterns in Human and LLM-Generated News Text](https://doi.org/10.1007/s10462-024-10903-2). *Artificial Intelligence Review*, 57, 265.
- Patterson, W. M. (1917). [The Rhythm of Prose](https://archive.org/details/rhythmofproseexp00pattiala). Columbia University Press.
- Roberts, A. (1996). [Rhythm in Prose and the Serial Correlation of Sentence Lengths](https://doi.org/10.1093/llc/11.1.33). *Literary and Linguistic Computing*, 11(1), 33–39.
- Sadasivan, V. S. et al. (2023). [Can AI-Generated Text be Reliably Detected?](https://arxiv.org/abs/2303.11156).
- Sato, S., Matsuyoshi, S., & Kondoh, Y. (2008). [Automatic Assessment of Japanese Text Readability Based on a Textbook Corpus](https://aclanthology.org/L08-1230/). *LREC 2008*.
- Sichel, H. S. (1974). [On a Distribution Representing Sentence-Length in Written Prose](https://doi.org/10.2307/2345142). *Journal of the Royal Statistical Society, Series A*, 137(1), 25–34.
- Steinhauer, K., & Friederici, A. D. (2001). [Prosodic boundaries, comma rules, and brain responses](https://doi.org/10.1023/A:1010443001646). *Journal of Psycholinguistic Research*, 30(3), 267–295.
- Tateisi, Y., Ono, Y., & Yamada, H. (1988). [A Computer Readability Formula of Japanese Texts for Machine Scoring](https://aclanthology.org/C88-2135/). *COLING 1988*.
- Wang, Y. et al. (2024). [M4: Multi-generator, Multi-domain, and Multi-lingual Black-Box Machine-Generated Text Detection](https://aclanthology.org/2024.eacl-long.83/). *EACL 2024*, 1369–1407.
- Yule, G. U. (1939). [On Sentence-Length as a Statistical Characteristic of Style in Prose](https://doi.org/10.1093/biomet/30.3-4.363). *Biometrika*, 30(3/4), 363–390.
- Zaitsu, W., & Jin, M. (2023). [Distinguishing ChatGPT(-3.5, -4)-generated and human-written papers through Japanese stylometric analysis](https://doi.org/10.1371/journal.pone.0288453). *PLOS ONE*, 18(8), e0288453.
- 岩崎拓也（2018）[「読点が接続詞の直後に打たれる要因」](https://www.jstage.jst.go.jp/article/mathling/31/6/31_426/_article/-char/ja/)『計量国語学』31(6), 426–442.
- 黄善玉・金明哲（2020）[「日本語における機能フレーズを特徴量とした著者識別」](https://doi.org/10.2964/jsik_2020_035)『情報知識学会誌』30(3), 389–399.
- 金明哲（2013）[「文節パターンに基づいた文章の書き手の識別」](https://doi.org/10.2333/jbhmk.40.17)『行動計量学』40(1), 17–28.
- 金明哲・樺島忠夫・村上征勝（1993）[「読点と書き手の個性」](https://ndlsearch.ndl.go.jp/books/R000000004-I3534546)『計量国語学』18(8), 382–391.
- 柴崎秀子（2014）[「リーダビリティー研究と『やさしい日本語』」](https://www.jstage.jst.go.jp/article/nihongokyoiku/158/0/158_49/_article/-char/ja/)『日本語教育』158, 49–65.
- 張玉潔・尾関和彦（1997）[「文節間係り受け距離の統計的性質を用いた日本語文の係り受け解析」](https://doi.org/10.5715/jnlp.4.2_3)『自然言語処理』4(2), 3–19.
- 李広微・金明哲（2019）[「統計分析からみた水村美苗著『続明暗』の文体模倣」](https://www.jstage.jst.go.jp/article/mathling/32/1/32_19/_article/-char/ja/)『計量国語学』32(1), 19–32.
- 孟令冲（2022）[「夏目漱石の小説における文体の継時的変化について」](https://www.jstage.jst.go.jp/article/mathling/33/7/33_481/_article/-char/ja/)『計量国語学』33(7), 481–493.
- 吉田直人・中山実・清水康敬（2002）[「わかりやすい文章表現と文章理解に関する一検討」](https://doi.org/10.15077/jmet.25.4_217)『日本教育工学会論文誌』25(4), 217–224.
