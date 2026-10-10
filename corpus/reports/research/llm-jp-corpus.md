# LLM-jp コーパス 調査メモ

- 調査日: 2026-10-07
- 目的: 国立情報学研究所(NII)の LLM-jp が公開している「LLM-jp コーパス」を、natural-japanese の基準データ(生成AI以前の人間の説明的・実務的な日本語)として使えるかを確かめる。あわせて、他のスキル作者にも配れる公開資源にできるかを調べる
- 関連: `exemplar-sources.md`(お手本の文章源。本文はコミットせずメタデータだけ持つ方針)、`business-corpus-sources.md`、`../genre-feasibility.md`、`../../ROADMAP.md`(F13〜F15: 誤検知の率は、どの人間の文章を基準に選ぶかで大きく変わる)
- 実地確認: v4 の各サブセットの先頭だけを HTTP の範囲指定で取得した(合計で約10MB の圧縮データ。ファイル全体はダウンロードしていない)。手元の作業ファイルはスクラッチ領域に置き、リポジトリには入れていない

## 1. 結論

**条件付きで使える。** 使いどころは「無作為に近い、生成AI以前の人間の Web 文章」の基準データ。お手本(読みやすさの手本)には向かない。

理由は次のとおり。

1. **誰でも申請なしでダウンロードできる。** GitLab から認証なしで取れ、範囲指定(Accept-Ranges)にも対応していた。ファイル単位で必要な分だけ取れる
2. **文書ごとに URL と日付が付いている(ja_cc・nwc2010・warp_html)。** ただし日付は収集(クロール)の時刻と見られ、書かれた日ではない。そのため「クロール日が 2022-10 以前なら生成AI以前に書かれた」とは言える。逆に「2023年以降のクロールだから AI 時代の文章」とは言えない
3. **ジャンルの分類は付いていない。** 文書の種類で絞るには、URL・ドメインと本文の特徴から自分で推定するしかない
4. **実務的・説明的な文章は少数派。** サンプルを目で見た範囲では、地の文が十分ある文書は全体の約3割で、そのうち説明的・実務的なものは3割弱だった(全体の1割弱と見積もる。精度は低い)。技術記事はサンプルにほぼなかった
5. **ライセンスはデータセットとしての許諾で、文書の著作権は書いた人に残る。** README 自身がそう明記している。LLM-jp は「大規模言語モデルの事前学習のため」に日本国内のサーバから配っている。抜き出した本文を「人が読む手本集」として公開し直すのは目的が違い、同じ根拠で許されるかは未確認

公開資源としては、**本文は配らず、文書 ID・URL・日付・判定ラベルの一覧(manifest)と抽出スクリプトを配る**のが安全。利用者は LLM-jp のサーバから同じ文書を自分で取り出す。これは `exemplar-sources.md` の方針(本文は gitignore、manifest だけコミット)と同じ形になる。

## 2. 版と構成

公開リポジトリは GitLab(https://gitlab.llm-jp.nii.ac.jp/datasets/)にある。GitLab の API で一覧を取ると、次のプロジェクトがすべて public だった。

| 版 | 公開日 | 総量 | 日本語の構成 | 出典 |
|---|---|---|---|---|
| v1 | 2024-04-29 | 273GB(gzip) | ja_mc4(mC4 を絞ったもの)、ja_wiki | [README](https://gitlab.llm-jp.nii.ac.jp/datasets/llm-jp-corpus-v1/-/blob/main/README.md) |
| v2 | 2024-05-22 | 624GB(gzip) | ja_cc(Common Crawl 全量から Uzushio で抽出。level0・level1)、ja_wiki | [README](https://gitlab.llm-jp.nii.ac.jp/datasets/llm-jp-corpus-v2/-/blob/main/README.md) |
| v2 ja_cc_all | ― | 4.5TB | v2 の ja_cc で、各フィルタが落とした文書をフィルタ別に収録 | [README](https://gitlab.llm-jp.nii.ac.jp/datasets/llm-jp-corpus-v2-ja_cc_all/-/blob/main/README.md) |
| v3 | 2024-09-28 | 2.7TB、1.7T トークン | ja_cc(381B)、ja_warp_html(1.3B)、ja_warp_pdf(207B)、ja_wiki(1.3B)、kaken(0.9B) | [README](https://gitlab.llm-jp.nii.ac.jp/datasets/llm-jp-corpus-v3/-/blob/main/README.md) |
| v4 | 2025-06-30 | 33TB、19.5T トークン(日本語 688B) | 下の表 | [README](https://gitlab.llm-jp.nii.ac.jp/datasets/llm-jp-corpus-v4/-/blob/main/README.md)、[NII の告知](https://llmc.nii.ac.jp/topics/llm-jp-corpus-v4/) |
| v4.1 | 2026-03-31 | 英語とコードのみ | 日本語なし | [README](https://gitlab.llm-jp.nii.ac.jp/datasets/llm-jp-corpus-v4.1/-/blob/main/README.md) |
| midtraining v1 / v2 | ― | 115GB / 858GB | 合成データ(LLM が生成した指示・応答)を含む | [v1](https://gitlab.llm-jp.nii.ac.jp/datasets/llm-jp-corpus-midtraining-v1)、[v2](https://gitlab.llm-jp.nii.ac.jp/datasets/llm-jp-corpus-midtraining-v2) |

括弧内のトークン数は llm-jp-tokenizer v3 で数えた値(README の記載)。

### 2.1 v4 の日本語サブセット

規模は README の値。メタデータの列は、各サブセットの先頭ファイルを実際に開いて確かめた。

| サブセット | 中身 | 規模 | ライセンス(README) | URL | 日付 | 実務文の見込み |
|---|---|---|---|---|---|---|
| ja_cc(level0/1/2) | Common Crawl 全量から Uzushio で抽出・フィルタ | 223B | ODC-BY + Common Crawl 利用規約 | あり | あり | 低い割合だが絶対数は多い |
| ja_fineweb-2 | FineWeb 2 の日本語部分(再配布) | 236B | ODC-BY + Common Crawl 利用規約 | あり | あり(`dump` 付き) | ja_cc と同程度 |
| ja_nwc2010 | 日本語ウェブコーパス2010 の HTML から抽出 | 16B | CC BY 4.0 | あり | あり | ja_cc と同程度。2010年前後の文体 |
| ja_warp_html | 国立国会図書館 WARP の URL を LLM-jp がクロール | 0.8B | CC BY 4.0 | あり(`<...>` で囲まれている) | あり | 官公庁・自治体のお知らせ・議事要旨が多い |
| ja_warp_pdf(e0 / e0.2) | 同じく PDF から抽出。e0 は Word・TeX・一太郎、e0.2 は PowerPoint・Excel など | 58B | CC BY 4.0 | **なし** | **なし** | 報告書に最も近いが、時期で分けられない |
| ja_sip_comprehensive_html / pdf | SIP 第3期で作られた一般 Web コーパス | 11B / 30B | CC BY 4.0 | あり | あり(2024年のクロールが中心) | ja_cc と同程度 |
| ja_kaken | 科研費データベースの研究課題の概要 | 0.9B | CC BY 4.0 | なし | なし | 研究計画の説明文。学術寄り |
| ja_kokkai_giji | 国会会議録(国会会議録検索システムの API) | 0.8B | CC BY 4.0 | 会議録の URL | 会議の日付 | 話し言葉の書き起こし。議事録の手本ではない |
| ja_patent | 特許庁の公開データ | 68B | CC BY 4.0 | 未確認 | 未確認 | 特許文体。対象外 |
| ja_e-gov | e-Gov の法令 | 0.08B | CC BY 4.0 | ― | ― | 法令文。対象外 |
| ja_aozorabunko | 青空文庫 | 0.1B | CC BY 4.0 | ― | ― | 文学。対象外 |
| ja_wiki | 日本語版 Wikipedia(2023-07-20 版) | 1B | CC BY-SA 3.0 | ― | ― | 百科事典の説明文 |

v4 には本来、国語研日本語ウェブコーパス(NWJC)と Ceek.jp News から作ったサブセットも含まれるが、再配布できないため公開版にはない(README)。

## 3. ライセンスと配布条件

- **ダウンロード**: 申請・ログインは不要。`https://gitlab.llm-jp.nii.ac.jp/datasets/llm-jp-corpus-v4/-/raw/main/<パス>` で取れた。HEAD で `Content-Length` と `Accept-Ranges: bytes` が返る
- **アクセス制限**: 2026-09-28 から、GitLab に「アクセスが集中しているため、同一アドレスからの同時接続数を制限している」というお知らせが出ている(`/api/v4/broadcast_messages` で確認)。並列で大量に取らない
- **ライセンス**: サブセットごとに ODC-BY、CC BY 4.0、CC BY-SA 3.0 など(2.1 の表)
- **著作権の扱い**(v4 の日本語 README から引用): 「本データセットにおける各文書の著作権は、原則としてその文書の著作者に帰属します。本データセットは大規模言語モデルを事前学習するためのものであり、日本国著作権法を適用するため、日本国内のサーバから配布しています。ライセンスの範囲内で再配布を含む利用が可能ですが、日本国外のサーバから再配布する場合には日本国著作権法が適用されませんので、ご注意ください。」
  - つまり ODC-BY や CC BY 4.0 は「LLM-jp がまとめたデータセット」への許諾で、個々の文書の著作権を手放させるものではない。ja_nwc2010 のように中身が一般の Web ページでも CC BY 4.0 と表示されているのは、このためと読める(推測)
  - 再配布は「ライセンスの範囲内で」可能とされる。ただし、本文を人が読む手本として公開し直すことが、事前学習(情報解析)と同じ根拠で許されるかは、このメモでは確かめていない(未確認)
- **Common Crawl 利用規約**(2024-03-07 更新、https://commoncrawl.org/terms-of-use): 「BY USING THE CRAWLED CONTENT, YOU AGREE TO RESPECT THE COPYRIGHTS AND OTHER APPLICABLE RIGHTS OF THIRD PARTIES IN AND TO THE MATERIAL CONTAINED THEREIN.」とある。AI・機械学習への言及は補償(indemnify)の条項の中にあり、利用者が第三者からの請求の責任を負う、という趣旨。AI 利用を禁止する条項ではない
- **削除依頼**: llm-jp-corpus (at) nii.ac.jp。文書が後から消える可能性がある。manifest で配るなら、取り出せなくなった文書を飛ばす作りにする

## 4. 文書の時期

### 4.1 収集時期

- v2 の ja_cc: 論文に「2013年から2023年半ばまでの Common Crawl のダンプ」とある([LLM-jp 論文 arXiv:2407.03963](https://arxiv.org/html/2407.03963v1))
- v4 の ja_cc: 公式の収集範囲は見つからなかった(未確認)。実地では 2024-11 の日付の文書があった(level0/0060)
- ja_fineweb-2: FineWeb 2 は Common Crawl の96スナップショット、2013年夏〜2024年4月([データセットカード](https://huggingface.co/datasets/HuggingFaceFW/fineweb-2))
- ja_nwc2010: 2010年に収集([日本語ウェブコーパス 2010](https://www.s-yata.jp/corpus/nwc2010/))。構造上、すべて生成AI以前
- ja_warp_html / pdf: WARP が集めた URL を、LLM-jp が自分でクロールし直したもの(河原「日本語に強い大規模言語モデルの開発のためのコーパス構築」LLMシンポジウム2024 の資料、https://llmc.nii.ac.jp/wp-content/uploads/2024/10/20240925_t1_kawahara.pdf)。warp_html の日付は 2024年が大半だった

### 4.2 `date` は書かれた日ではない

ja_cc の各ファイルの先頭を見ると、1ファイルの日付がほぼ1つの時期に集まっていた。

- level0/0000: 625件中608件が 2019-08-17〜26
- level0/0060: 173件中171件が 2024年
- level0/0110: 64件中58件が 2017年

1ファイルがほぼ1回のクロールに当たる、と読める。少数の古い日付(2005年など)も混じる。Common Crawl に 2005年のクロールはないので、HTTP の `Last-Modified` を使っている文書もあると推測する(未確認)。裏付けになりそうな例が一つある。warp_html の青森県の報道発表(`pref.aomori.lg.jp/release/2016/55537.html`)は、`date` が 2016-04-26 で、本文の「公開日:2016年4月26日」と一致していた。一方で、2006年に作られた厚労省のページが 2018年の日付になっている例もあった。

ここから言えるのは次の2点。

- **日付が 2022-10 以前なら、そのページは生成AI以前に存在した。** 基準データを作るには十分な条件になる(安全側)
- **日付が 2022-11 以降でも、AI 時代に書かれたとは限らない。** 古いページを後から収集したものが多く混じる。AI 時代の比較用には、本文や URL に公開日が出ている文書だけを使う必要がある

ja_fineweb-2 は `dump`(例: `CC-MAIN-2018-34`)と `file_path` を持つので、どのクロールかが曖昧さなく分かる。ja_cc にはスナップショットの欄がない。

### 4.3 生成AI以前のファイルの割合(探り)

level0 は1,000ファイルある。先頭を見た11ファイルのうち、主な日付が 2022-10 以前のものは5(2017年が2、2019年が3)、2022-11 以降のものは6だった。後者のうち1本(0170)は 2022-11〜12 で、年だけ見ると「2022年」になり、境目をまたぐ。年ではなく月まで見て分ける必要がある。ファイル単位で時期を選べそうだが、これは探りで、計測ではない。

## 5. メタデータ

実地で確かめた `meta` の中身。

| サブセット | 欄 |
|---|---|
| ja_cc | `docId`(UUID)、`url`、`date`、`charset`(ある文書のみ)、`dedup_meta`(MinHash のクラスタ ID と大きさ) |
| ja_fineweb-2 | `dump`、`url`、`date`、`language`、`language_score`、`language_script`、`top_langs`、`dedup_meta`(元の WARC のパスを含む) |
| ja_nwc2010 / ja_sip_comprehensive_html | ja_cc と同じ形 |
| ja_warp_html | ja_cc と同じ形。ただし `url` が `<https://...>` と山括弧で囲まれている |
| ja_warp_pdf | `docId`(9桁の数字)、`line_break_or_white_space_ratio`、`short_line_ratio`、`dedup_meta`。**URL も日付もない** |
| ja_kaken | `dedup_meta` だけ |
| ja_kokkai_giji | 国会会議録 API のメタデータ一式(`nameOfHouse`、`nameOfMeeting`、`date`、`meetingURL` など) |

- **品質スコアはない。** 段落ごとの perplexity などの値は残っていない。level0/1/2 の区別は重複の度合いで、品質の段階ではない
- **ジャンル分類はない。** どのサブセットにも文書の種類のラベルは付いていない。絞るには URL・ドメイン・本文の特徴から推定する
- ja_warp_pdf の `docId` から元の URL を引けるかは未確認

## 6. 品質フィルタ

ja_cc は Uzushio(Works Applications、Apache 2.0)で処理されている。使われた設定は [pipeline_03a.conf](https://github.com/WorksApplications/uzushio/blob/main/scripts/pipeline_03a.conf) で公開されている。順に次のフィルタがかかる。

1. 文書長(50字未満を除く。最後に200字未満も除く)
2. 重複文書の間引き(SimHash による。何段階か)
3. ひらがなの割合(0.1 未満、0.15 未満を除く)
4. リンク文字の割合(0.8 超、0.4 超を除く)
5. ナビゲーションのような DOM の除去、見出しの Markdown 化
6. 多くの文書に出る段落の除去(定型文の除去)
7. KenLM の perplexity(段落ごと・文書の平均。外れ値の上位1割は無視)
8. 圧縮率(0.4〜0.75、0.5〜0.75 の範囲外を除く。繰り返しの多い文書を落とす)
9. アダルト・差別の語のリスト

偏りについて分かったこと。

- **フィルタで落ちた文書が公開されている。** v2 の ja_cc_all に、フィルタ別に落ちた文書がある。偏りを自分で確かめられる
- **perplexity のフィルタは話題を偏らせる。** 関連論文では、perplexity で強く絞るほど「ファッション・通販」が 15.6% から 1.3% に減り、ニュース・ブログの話題が増えた([Enomoto et al., NAACL SRW 2024](https://aclanthology.org/2024.naacl-srw.18.pdf) 5.2節)。この論文の実験では BCCWJ で KenLM を学習している。ただし、本番の ja_cc に使った KenLM が何で学習されたかは、設定ファイルでは変数(`${kenlm}`)になっていて分からなかった(未確認)
- **「読みやすい文章」への偏りは小さいと見る。** 閾値はゆるく、明らかなゴミ(記号の羅列、リンク集、定型文)を落とす設計に見える。ただし、読みやすさの指標への影響は計っていない(未検証)
- 箇条書きや表が多い文書は、ひらがなの割合とリンクの割合で落ちやすいと推測する(未検証)。手順書・仕様の説明のような文書が減っている可能性がある
- FineWeb 2 は、Wikipedia などの「お手本」との類似度で選ぶ機械学習フィルタを意図的に使っていない、と書いている。句読点のフィルタが詩を多く落とすことも認めている(データセットカード)

## 7. 実務的・説明的な文章の割合(小さなサンプル)

各サブセットの先頭の文書を集計した。「地の文あり」は、800字以上で、20字以上かつ「。」などで終わる行が文字数の6割以上ある文書とした。URL による分類は正規表現の粗い推定。

| サンプル | 件数 | 地の文あり | ブログ系の URL | go.jp・lg.jp・ac.jp |
|---|---|---|---|---|
| ja_cc level0(11ファイルの先頭) | 1,367 | 25〜41% | 9〜61% | 0〜4% |
| ja_cc level1 / level2 | 176 / 185 | 26% / 23% | 29% / 22% | 0〜1% |
| ja_fineweb-2(2ファイル) | 575 | 26〜27% | 18〜22% | 1% |
| ja_nwc2010 | 169 | 23% | 14% | 2% |
| ja_warp_html | 265 | 25% | ― | 71% |
| ja_warp_pdf/e0 | 161 | 19% | ― | ― |
| ja_kaken | 400 | 65% | ― | ― |

ja_cc level0/0000 のうち、2022-10 以前で「地の文あり」の文書から30件を無作為に選び、目で見た。

- 説明的・実務的と言えるもの: 8件程度。企業のお知らせ・プレスリリース、支援機関の紹介、製品の技術的な説明、健康相談への助言、催しの報告、コラムなど
- 個人の日記・趣味のブログ、レビュー、Q&A サイト、小説の紹介: 約半数
- SEO 目的の自動生成と見られる文(意味の通らない語の並び、`.xyz` ドメインなど): 数件

ここから、ja_cc 全体のうち実務的・説明的な文書は1割弱と見積もる(n が小さく、精度は低い)。技術記事(Qiita・Zenn など)は約2,000件のサンプルにほぼなかった。これはサンプルが小さいためで、コーパスにないとは言えない。ただ、技術記事はすでに Qiita から直接集めている(`collect_qiita.py`)ので、LLM-jp に頼る必要は薄い。

規模の概算: level0 の1ファイルは圧縮で約2.5〜3.5億バイト、展開で約26億バイトあり、約15万件の文書が入っている(先頭の文書数からの外挿)。level0 全体で1億件を超える計算になる。1割弱でも数百万件の説明的な文書があることになる(概算)。

ja_warp_html は官公庁・自治体の報道発表、検討会の議事要旨、制度の説明が中心だった。仕事の文書に近いが、行政の文体に偏る。

## 8. AI 生成文の混入

- **2022-10 以前のクロール分には、ChatGPT 型の生成文はまず入っていない。** 公開前なので
- **ただし「生成AI以前 = 人間が書いた」ではない。** 2019年のクロールに、SEO 目的の自動生成(文をつぎはぎした意味の通らない文)が混じっていた。基準データに入れると、読みにくさの分布がゆがむ。ドメインの除外と、本文の特徴による除外が要る
- **2023年以降のクロール分(ja_cc の一部、ja_fineweb-2 の 2023〜2024年4月、ja_sip)には、生成文が混じりうる。** 割合は調べていない(未確認)
- **midtraining v1 / v2 は、LLM が生成した日本語を大量に含む。** calm3-22b、Mixtral 8x22B、gpt-oss-120b などの生成。AI 側の比較材料には使えるが、指示・応答の形式で、仕事の文書の形ではない

## 9. 似た公開資源との比較

「本文のサブセットを作って公開できるか」の観点で並べた。どれも Web 由来のものは、文書の著作権が書いた人に残る点は同じ。

| 資源 | 時期 | 日本語の規模 | 入手 | ライセンス | 時期で分けられるか | サブセット公開の見込み |
|---|---|---|---|---|---|---|
| LLM-jp v4 ja_cc | 2013〜2024(推定) | 223B トークン | GitLab、申請なし | ODC-BY + CC 規約。著作権は著作者 | クロール日で一方向だけ | 本文は未確認。manifest は可 |
| FineWeb 2 jpn_Jpan | 2013夏〜2024-04 | 約4億文書(カードの表) | Hugging Face、申請なし。ストリーミングで読める | ODC-BY + CC 規約 | `dump` で明確 | 同上。フィルタで落ちた分(`_removed`)も公開。個人情報の除去依頼フォームあり |
| LLM-jp v4 ja_nwc2010 | 2010 | 16B トークン | GitLab | CC BY 4.0(データセットとして) | すべて AI 以前 | 同上。元の配布元のページに利用条件の記載は見当たらなかった(未確認) |
| mC4 日本語(allenai/c4) | mT5 の構築時点まで | 未計測 | Hugging Face、申請なし | ODC-BY | すべて AI 以前(2020〜2021年の公開) | 同上 |
| CC-100 日本語 | 2018年のクロール(未確認) | 未計測 | statmt のサイト・Hugging Face | Hugging Face では license: unknown | すべて AI 以前 | 条件が不明確 |
| OSCAR 23.01 | 2022年末のクロール(未確認) | 未計測 | Hugging Face、手動承認の申請が要る | CC0(まとめ方への許諾) | 一部は AI 以後 | 申請制で配りにくい |
| HPLT 2.0 | 未確認 | 未計測 | Hugging Face、申請なし | CC0(まとめ方への許諾) | クロール日 | manifest は可(未確認) |
| Swallow コーパス v1 / v2 | 2013〜2023 | 未計測 | 本文の公開配布は確認できなかった(未確認) | ― | ― | 使えない見込み |
| BCCWJ | 〜2008 | 約1億語 | 有償の利用契約。中納言は登録制で無償 | 契約で第三者への貸与は不可 | すべて AI 以前 | 不可(`exemplar-sources.md` #16) |
| 日本語版 Wikipedia | 随時 | ― | ダンプを自由に入手 | CC BY-SA | 版の履歴で分けられる | 本文も公開できる。ただし百科事典の文体だけ |

FineWeb 2 の日本語は、LLM-jp の ja_fineweb-2 と同じデータを Hugging Face から読めるもの。`load_dataset(..., streaming=True)` で少しずつ読め、`dump` で時期を選べる。再現できる形でサブセットを作るなら、こちらのほうが扱いやすい可能性がある。

## 10. サブセットの作り方の案

狙いは「生成AI以前の、人間が書いた説明的・実務的な Web 文章」の基準データ。誤検知の率を測るときの母集団にする。ROADMAP の F14・F15 のとおり、基準の選び方で誤検知の率が変わるので、「選び方」も一緒に記録する。

1. **元にするサブセット**
   - 主: ja_cc level0(または ja_fineweb-2)。量が多く、URL と日付がある
   - 補: ja_warp_html(行政の文書の枠)、ja_nwc2010(2010年の文体との比較用)
   - 使わない: ja_warp_pdf(時期で分けられない)、ja_kokkai_giji(話し言葉)、ja_patent・ja_e-gov・ja_aozorabunko(対象外の文体)
2. **時期で絞る**: `date < 2022-11-01`。ja_fineweb-2 なら `dump` が `CC-MAIN-2022-40` 以前
3. **ドメインで絞る**
   - 除く: EC・通販、求人・不動産の一覧、Q&A サイト、掲示板、`.xyz` などスパムの多いドメイン
   - 種類の推定に使う: `.go.jp`・`.lg.jp`(行政)、`.co.jp` のうち `/news/`・`/press/`・`/release/`(企業の発信)、`/blog/`・ブログサービス(ブログ)、`/column/`・`/topics/`(コラム)
4. **本文で絞る**: 800字以上、地の文の割合6割以上、繰り返しの少なさ。lint.py の素の結果は、この段階では絞り込みに使わない(誤検知の基準を測る対象そのものなので)
5. **種類のラベルを付ける**: URL の規則で一次分類し、各枠から数十件を人が見て、分類の精度を記録する。必要なら LLM で種類を判定する。ただし判定のプロンプトとモデルを manifest に記録する
6. **出力**: 文書ごとに `source`(サブセットとファイル名)、`docId`、`url`、`date`、推定した種類、本文の SHA-256、選んだ規則の版。本文は `corpus/private/` に置き、コミットしない

## 11. 公開資源として配れるか

- **manifest と抽出スクリプトは配れる。** docId・URL・日付・ラベル・ハッシュは、本文の複製ではない。抽出スクリプトは利用者自身が LLM-jp のサーバから同じ文書を取り出す。日本語の文章を直す他のスキルや道具の作者も、同じ母集団で誤検知を測れる
- **本文そのものの公開は勧めない。** ライセンス表示上は「ライセンスの範囲内で再配布可」だが、各文書の著作権は著作者にあり、LLM-jp は事前学習の目的と日本の著作権法を前提に配っている。手本集として本文を公開し直すのは目的が違い、法的に整理できているかは未確認。Hugging Face など国外のサーバに置くと、README の注意書きにも当たる
- **例外として本文ごと配れる可能性があるもの**: 日本語版 Wikipedia(CC BY-SA)。政府標準利用規約が明示されている官公庁のページ(WARP 由来の一部)。ただし後者はページごとに規約を確かめる必要がある(未確認)
- **配るときに付けるもの**: 出典(LLM-jp Corpus v4、サブセット名、ODC-BY / CC BY 4.0 の表示)、Common Crawl 利用規約への言及、文書が削除される可能性があること、選び方の規則

## 12. 最初に試す最小手順

1. **ファイルと時期の対応表を作る**: ja_cc level0 の1,000ファイルそれぞれの先頭 100KB だけを範囲指定で取り、主な日付を記録する(合計約100MB)。同時接続は1本にする。ja_fineweb-2 で代えるなら、Hugging Face のストリーミングで `dump` を見るだけでよい
2. **2022年以前のファイルを2〜3本だけ丸ごと取る**(1本あたり圧縮で約3億バイト)
3. **10章の2〜4の規則で絞り、種類を推定する**。各枠から30件ずつ目で見て、規則の精度を記録する
4. **lint.py を当てる**: 各検出器の反応率を、既存の基準(Qiita の無作為抽出 H、ストック数で選んだ H'、Zenn quality:high)と並べる。F14・F15 の「基準の選び方で率が変わる」を、もう一つの母集団で確かめる
5. **manifest と抽出スクリプトをコミットする**。本文は `corpus/private/` に置く

ここまでで、LLM-jp 由来の基準が既存の基準と比べてどれだけ違うか、続ける価値があるかを判断できる。

## 13. 未確認の事項

- v4 の ja_cc がどの Common Crawl のスナップショットを使ったか(v2 は 2013〜2023年半ば)
- `date` の正確な定義(クロール時刻か、`Last-Modified` か、その混在か)
- ja_cc の KenLM が何で学習されたか
- ja_warp_html / pdf の LLM-jp によるクロールの期間と、ja_warp_pdf の `docId` から URL を引けるか
- ja_patent のメタデータ
- NWJC・Ceek.jp News の入手条件
- 日本語ウェブコーパス2010 の元の配布条件
- 抜き出した本文を手本集として公開し直すことの法的な可否
- 2023年以降のクロール分に含まれる生成文の割合
- Swallow コーパスの本文が公開配布されているか
- フィルタが手順書・箇条書きの多い文書を落としているか(v2 ja_cc_all で確かめられる)

## 14. 出典

- LLM-jp Corpus v1〜v4.1、midtraining v1 / v2、v2 ja_cc_all の README: https://gitlab.llm-jp.nii.ac.jp/datasets/
- v4 の日本語 README(著作権の扱い): https://gitlab.llm-jp.nii.ac.jp/datasets/llm-jp-corpus-v4/-/blob/main/README-ja.md
- NII 大規模言語モデル研究開発センター「LLM-jp Corpus v4 の公開」: https://llmc.nii.ac.jp/topics/llm-jp-corpus-v4/
- LLM-jp 論文: https://arxiv.org/html/2407.03963v1
- 河原大輔「日本語に強い大規模言語モデルの開発のためのコーパス構築」(LLMシンポジウム2024): https://llmc.nii.ac.jp/wp-content/uploads/2024/10/20240925_t1_kawahara.pdf
- Uzushio の設定: https://github.com/WorksApplications/uzushio/blob/main/scripts/pipeline_03a.conf
- Enomoto et al. "Investigating Web Corpus Filtering Methods for Language Model Development in Japanese" (NAACL SRW 2024): https://aclanthology.org/2024.naacl-srw.18.pdf
- FineWeb 2 データセットカード: https://huggingface.co/datasets/HuggingFaceFW/fineweb-2
- Common Crawl 利用規約(2024-03-07 更新): https://commoncrawl.org/terms-of-use
- 日本語ウェブコーパス 2010: https://www.s-yata.jp/corpus/nwc2010/
- Hugging Face の各データセットのメタデータ(gated・license の欄): allenai/c4、oscar-corpus/OSCAR-2301、statmt/cc100、HPLT/HPLT2.0_cleaned
- Swallow コーパス v2 の論文(言語処理学会 2025): https://www.anlp.jp/proceedings/annual_meeting/2025/pdf_dir/C1-5.pdf
