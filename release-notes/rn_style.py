"""ビジュアルリリースノートの見た目。デジタル庁デザインシステム(DADS)の HTML 実装例(MIT、© デジタル庁)の
global.css・prose.css・各コンポーネントの CSS から、このページで使う分を写したもの。値は変えていない。
出典: https://github.com/digital-go-jp/design-system-example-components-html(2026-11 時点の main)
"""

FONT = '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;700&family=Noto+Sans+Mono:wght@400&display=swap" rel="stylesheet">'

TOKENS = """
:root{
  --color-primitive-blue-50:#e8f1fe;--color-primitive-blue-100:#d9e6ff;--color-primitive-blue-200:#c5d7fb;--color-primitive-blue-300:#9db7f9;--color-primitive-blue-400:#7096f8;--color-primitive-blue-500:#4979f5;--color-primitive-blue-600:#3460fb;--color-primitive-blue-700:#264af4;--color-primitive-blue-800:#0031d8;--color-primitive-blue-900:#0017c1;--color-primitive-blue-1000:#00118f;--color-primitive-blue-1100:#000071;--color-primitive-blue-1200:#000060;
  --color-primitive-green-50:#e6f5ec;--color-primitive-green-600:#259d63;--color-primitive-green-800:#197a4b;--color-primitive-green-900:#115a36;
  --color-primitive-yellow-300:#ffd43d;
  --color-primitive-orange-800:#c74700;
  --color-primitive-magenta-900:#8b008b;
  --color-neutral-white:#ffffff;--color-neutral-black:#000000;
  --color-neutral-solid-gray-50:#f2f2f2;--color-neutral-solid-gray-100:#e6e6e6;--color-neutral-solid-gray-200:#cccccc;--color-neutral-solid-gray-300:#b3b3b3;--color-neutral-solid-gray-400:#999999;--color-neutral-solid-gray-420:#949494;--color-neutral-solid-gray-500:#7f7f7f;--color-neutral-solid-gray-536:#767676;--color-neutral-solid-gray-600:#666666;--color-neutral-solid-gray-700:#4d4d4d;--color-neutral-solid-gray-800:#333333;--color-neutral-solid-gray-900:#1a1a1a;
  --font-family-sans:"Noto Sans JP",-apple-system,BlinkMacSystemFont,sans-serif;--font-family-mono:"Noto Sans Mono",monospace;
  --elevation-1:0 2px 8px 1px rgba(0,0,0,.1),0 1px 5px 0 rgba(0,0,0,.3);
  --color-key-50:var(--color-primitive-blue-50);--color-key-100:var(--color-primitive-blue-100);--color-key-200:var(--color-primitive-blue-200);--color-key-400:var(--color-primitive-blue-400);--color-key-900:var(--color-primitive-blue-900);--color-key-1000:var(--color-primitive-blue-1000);
}
"""

CSS = TOKENS + """
*{box-sizing:border-box}
html{scrollbar-gutter:stable;font-family:var(--font-family-sans);scroll-behavior:smooth;scroll-padding-top:72px}
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}*{transition:none!important}}
body{margin:0;background:var(--color-neutral-white);color:var(--color-neutral-solid-gray-800);font-weight:normal;font-size:calc(16 / 16 * 1rem);line-height:1.7;letter-spacing:.02em;overflow-wrap:anywhere;line-break:strict;text-autospace:normal;text-spacing-trim:trim-start}
@media (min-width:48rem){body{font-size:calc(17 / 16 * 1rem)}}
p{margin:0}

/* リンク(global.css) */
a:any-link{color:var(--color-primitive-blue-1000);text-decoration:underline;text-decoration-thickness:calc(1 / 16 * 1rem);text-underline-offset:calc(3 / 16 * 1rem)}
a:visited{color:var(--color-primitive-magenta-900)}
@media (hover:hover){a:hover{color:var(--color-primitive-blue-900);text-decoration-thickness:calc(3 / 16 * 1rem)}}
a:active{color:var(--color-primitive-orange-800);text-decoration-thickness:calc(1 / 16 * 1rem)}
:focus-visible{outline:calc(4 / 16 * 1rem) solid var(--color-neutral-black);outline-offset:calc(2 / 16 * 1rem);border-radius:calc(4 / 16 * 1rem);box-shadow:0 0 0 calc(2 / 16 * 1rem) var(--color-primitive-yellow-300)}

/* 幅と余白。ブレークポイントは 768px の1つ */
.wrap{max-width:calc(960 / 16 * 1rem);margin:0 auto;padding:0 calc(16 / 16 * 1rem)}
@media (min-width:48rem){.wrap{padding:0 calc(32 / 16 * 1rem)}}

/* 目次 */
.toc{position:sticky;top:0;z-index:5;background:var(--color-neutral-white);border-bottom:1px solid var(--color-neutral-solid-gray-420)}
.toc-inner{max-width:calc(960 / 16 * 1rem);margin:0 auto;padding:0 calc(16 / 16 * 1rem);display:flex;align-items:center;gap:calc(16 / 16 * 1rem)}
@media (min-width:48rem){.toc-inner{padding:0 calc(32 / 16 * 1rem)}}
.toc-h{margin:0;font-weight:bold;font-size:calc(16 / 16 * 1rem);flex:none}
.toc-list{list-style:none;margin:0;padding:0;display:flex;gap:calc(4 / 16 * 1rem);overflow-x:auto;scrollbar-width:none}
.toc-list::-webkit-scrollbar{display:none}
.toc-list li{flex:none}
.toc-list a{display:block;padding:calc(12 / 16 * 1rem) calc(8 / 16 * 1rem);border-bottom:calc(4 / 16 * 1rem) solid transparent;color:var(--color-neutral-solid-gray-800);text-decoration:none;font-size:calc(16 / 16 * 1rem);white-space:nowrap;line-height:1.2}
.toc-list a[aria-current=location]{font-weight:bold;border-bottom-color:var(--color-key-900)}
@media (hover:hover){.toc-list a:hover{text-decoration:underline;text-underline-offset:calc(3 / 16 * 1rem)}}

/* 見出し(prose.css) */
h1,h2,h3,h4{color:var(--color-neutral-solid-gray-800);text-wrap:pretty}
h1{margin:0 0 calc(32 / 16 * 1rem);font-weight:bold;font-size:calc(28 / 16 * 1rem);line-height:1.5;letter-spacing:.01em}
@media (min-width:48rem){h1{margin-bottom:calc(48 / 16 * 1rem);font-size:calc(45 / 16 * 1rem);line-height:1.4;letter-spacing:0}}
h2{margin:calc(40 / 16 * 1rem) 0 calc(24 / 16 * 1rem);font-weight:bold;font-size:calc(24 / 16 * 1rem);line-height:1.5;letter-spacing:.02em}
@media (min-width:48rem){h2{margin-top:calc(64 / 16 * 1rem);font-size:calc(32 / 16 * 1rem)}}
h3{margin:calc(32 / 16 * 1rem) 0 calc(16 / 16 * 1rem);font-weight:bold;font-size:calc(22 / 16 * 1rem);line-height:1.5;letter-spacing:.02em}
@media (min-width:48rem){h3{margin:calc(48 / 16 * 1rem) 0 calc(24 / 16 * 1rem);font-size:calc(24 / 16 * 1rem)}}
h4{margin:calc(24 / 16 * 1rem) 0 calc(16 / 16 * 1rem);font-weight:bold;font-size:calc(18 / 16 * 1rem);line-height:1.6;letter-spacing:.02em}
@media (min-width:48rem){h4{margin-top:calc(40 / 16 * 1rem);font-size:calc(20 / 16 * 1rem);line-height:1.5}}
/* 見出しのチップ(heading.css data-chip) */
h2[data-chip]{position:relative;padding-left:calc(1em / 3 + .5em)}
h2[data-chip]::before{position:absolute;top:.2em;bottom:.1em;left:0;width:calc(1em / 3);background-color:var(--color-key-900);content:""}
@supports (top:1lh){h2[data-chip]::before{top:calc(.5lh - .45em);bottom:calc(.5lh - .55em)}}

/* 段落・リスト(prose.css) */
.p{margin:calc(16 / 16 * 1rem) 0}
@media (min-width:48rem){.p{margin-bottom:calc(24 / 16 * 1rem)}}
.prose-max{max-width:40em}
ul.list,ol.list{margin:calc(16 / 16 * 1rem) 0;padding-left:calc(32 / 16 * 1rem)}
@media (min-width:48rem){ul.list,ol.list{margin:calc(24 / 16 * 1rem) 0}}
.list>li+li{margin-top:calc(8 / 16 * 1rem)}

/* 引用(prose.css blockquote) */
blockquote{margin:calc(16 / 16 * 1rem) 0 calc(24 / 16 * 1rem);border-left:calc(8 / 16 * 1rem) solid var(--color-neutral-solid-gray-536);padding:calc(8 / 16 * 1rem) 0 calc(8 / 16 * 1rem) calc(24 / 16 * 1rem)}
blockquote>*:first-child{margin-top:0}blockquote>*:last-child{margin-bottom:0}
blockquote.key{border-left-color:var(--color-key-900)}
blockquote em{font-style:normal;font-weight:bold;text-decoration:underline;text-decoration-color:var(--color-primitive-green-800);text-decoration-thickness:calc(3 / 16 * 1rem);text-underline-offset:calc(3 / 16 * 1rem)}
.ln{color:var(--color-neutral-solid-gray-700);font-variant-numeric:tabular-nums}

/* チップラベル(chip-label.css) */
.chip{display:inline-grid;grid-template-columns:auto auto;align-items:baseline;align-content:center;min-height:calc(32 / 16 * 1rem);border-radius:calc(8 / 16 * 1rem);padding:calc(3 / 16 * 1rem) calc(7 / 16 * 1rem);font-weight:normal;font-size:calc(16 / 16 * 1rem);line-height:1;letter-spacing:.02em;border:1px solid var(--_non-text);background:var(--color-neutral-white);color:var(--_text);vertical-align:middle;white-space:nowrap}
.chip[data-color=gray]{--_non-text:var(--color-neutral-solid-gray-700);--_text:var(--color-neutral-solid-gray-800)}
.chip[data-color=blue]{--_non-text:var(--color-primitive-blue-700);--_text:var(--color-primitive-blue-700)}
.chip[data-color=green]{--_non-text:var(--color-primitive-green-800);--_text:var(--color-primitive-green-800)}
.chip[data-fill]{background:var(--_non-text);color:var(--color-neutral-white)}

/* 表(prose.css table) */
table.tbl{margin:calc(16 / 16 * 1rem) 0;width:100%;border-collapse:collapse;font-size:calc(14 / 16 * 1rem);line-height:1.7;letter-spacing:.02em}
@media (min-width:48rem){table.tbl{margin:calc(24 / 16 * 1rem) 0;font-size:calc(16 / 16 * 1rem)}}
table.tbl thead{background:var(--color-neutral-solid-gray-100)}
table.tbl th{border-bottom:1px solid var(--color-neutral-black);background:var(--color-neutral-solid-gray-100);padding:calc(12 / 16 * 1rem) calc(8 / 16 * 1rem);vertical-align:baseline;text-align:left;font-weight:bold}
table.tbl td{border-bottom:1px solid var(--color-neutral-solid-gray-420);padding:calc(12 / 16 * 1rem) calc(8 / 16 * 1rem);vertical-align:baseline;text-align:left}
@media (min-width:48rem){table.tbl th,table.tbl td{padding:calc(20 / 16 * 1rem) calc(16 / 16 * 1rem)}}
.tbl-wrap{overflow-x:auto}

/* 区切り(divider.css) */
section.block{padding:0 0 calc(40 / 16 * 1rem);border-bottom:1px solid var(--color-neutral-solid-gray-420)}
@media (min-width:48rem){section.block{padding-bottom:calc(64 / 16 * 1rem)}}

/* ディスクロージャー(disclosure.css)と、ブロックの details(prose.css) */
.dsc{margin:calc(16 / 16 * 1rem) 0}
.dsc summary{display:flex;align-items:start;justify-content:start;gap:calc(8 / 16 * 1rem);width:fit-content;cursor:default;list-style-type:none;font-weight:bold}
.dsc summary::marker{content:""}.dsc summary::-webkit-details-marker{display:none}
@media (hover:hover){.dsc summary:hover{text-decoration:underline;text-underline-offset:calc(3 / 16 * 1rem)}}
.dsc summary svg{flex-shrink:0;margin-top:calc((1lh - 24px) / 2);color:var(--color-key-1000)}
.dsc[open] summary svg{rotate:180deg}
.dsc-body{padding-left:calc(32 / 16 * 1rem);margin:calc(16 / 16 * 1rem) 0}
details.box{margin:calc(16 / 16 * 1rem) 0;border:1px solid var(--color-neutral-solid-gray-420);border-radius:calc(8 / 16 * 1rem);padding:calc(16 / 16 * 1rem)}
details.box>summary{cursor:default;font-weight:bold}
details.box[open]>summary{margin-bottom:calc(16 / 16 * 1rem)}

/* タブ(tab.css) */
.dads-tab{position:relative;z-index:0;display:flex;flex-direction:column;margin:calc(24 / 16 * 1rem) 0}
.dads-tab__list{position:relative;z-index:0;margin:calc(-6 / 16 * 1rem);overflow:hidden;display:flex;flex-wrap:wrap;padding:calc(7 / 16 * 1rem) calc(6 / 16 * 1rem) calc(6 / 16 * 1rem) calc(7 / 16 * 1rem);list-style:none}
.dads-tab__list>li{margin:0;display:contents}
.dads-tab__list::after{position:relative;flex-grow:1;border:0 solid var(--color-neutral-solid-gray-420);content:"";margin-left:-1px;width:1px;border-bottom-width:1px}
.dads-tab__tab{isolation:isolate;appearance:none;margin:-1px 0 0 -1px;display:flex;border:1px solid var(--color-neutral-solid-gray-420);background:var(--color-neutral-white);padding:0;color:inherit;font:inherit;letter-spacing:inherit;text-align:left;cursor:default;position:relative}
.dads-tab__tab::before{content:"";position:absolute;bottom:6px;width:100%;border:0 solid var(--color-neutral-white)}
.dads-tab__tab>span{position:relative;display:flex;flex-grow:1;align-items:center;border:0 solid var(--color-neutral-solid-gray-50);border-top-width:5px;padding:calc(16 / 16 * 1rem);font-size:calc(16 / 16 * 1rem);line-height:1.2;letter-spacing:0}
.dads-tab__tab>span::before{content:"";position:absolute;top:-6px;right:0;left:0;height:6px}
.dads-tab__tab[aria-selected=true]>span{font-weight:bold}
.dads-tab__tab[aria-selected=true]:not(:focus-visible)::before{border-bottom-width:1px}
.dads-tab__tab[aria-selected=true]>span::before{background:var(--color-key-900)}
@media (hover:hover){.dads-tab__tab:not([aria-selected=true]):hover{background:var(--color-neutral-solid-gray-50)}.dads-tab__tab:not([aria-selected=true]):hover>span{text-decoration:underline;text-underline-offset:calc(3 / 16 * 1rem)}.dads-tab__tab:not([aria-selected=true]):hover>span::before{background:var(--color-neutral-solid-gray-420)}}
.dads-tab__tab:focus-visible{overflow:hidden;z-index:1}
.dads-tab__panels{flex-grow:1;display:flex;flex-direction:column}
.dads-tab__panel{border:solid var(--color-neutral-solid-gray-420);border-width:0 1px 1px;background:var(--color-neutral-white);padding:calc(16 / 16 * 1rem)}
@media (min-width:48rem){.dads-tab__panel{padding:calc(24 / 16 * 1rem)}}
.dads-tab__panel>:first-child{margin-top:0}

/* ファーストビュー */
.hero{padding:calc(32 / 16 * 1rem) 0 calc(40 / 16 * 1rem);border-bottom:1px solid var(--color-neutral-solid-gray-420)}
.hero .ver{margin:0;font-weight:bold;font-size:calc(48 / 16 * 1rem);line-height:1.4;letter-spacing:0;color:var(--color-key-900);font-variant-numeric:tabular-nums}
@media (min-width:48rem){.hero .ver{font-size:calc(64 / 16 * 1rem)}}
.hero .ver small{font-size:.5em;font-weight:bold;margin-right:.1em}
.hero .meta{margin:calc(8 / 16 * 1rem) 0 calc(32 / 16 * 1rem)}
.hero h1{margin-bottom:calc(24 / 16 * 1rem);max-width:24em}
.lead{max-width:40em}
mark{background:var(--color-key-50);color:inherit;padding:0 .1em;box-shadow:inset 0 calc(-2 / 16 * 1rem) 0 var(--color-key-900)}
.cmp{display:grid;grid-template-columns:1fr;gap:calc(16 / 16 * 1rem);margin:calc(24 / 16 * 1rem) 0 0}
@media (min-width:60rem){.cmp{grid-template-columns:1fr 1fr 1fr;gap:calc(24 / 16 * 1rem)}}
.cmp h4{margin:0 0 calc(8 / 16 * 1rem)}
.cmp blockquote{margin:0}
.cmp .ans{margin-top:calc(12 / 16 * 1rem)}

/* 数字の並び */
.stats{display:grid;grid-template-columns:1fr;gap:calc(16 / 16 * 1rem);margin:calc(24 / 16 * 1rem) 0}
@media (min-width:48rem){.stats{grid-template-columns:repeat(2,1fr)}}
.stat{border:1px solid var(--color-neutral-solid-gray-420);border-radius:calc(8 / 16 * 1rem);padding:calc(16 / 16 * 1rem)}
.stat b{display:block;margin-bottom:calc(4 / 16 * 1rem)}
.stat .n{font-weight:bold;font-size:calc(32 / 16 * 1rem);line-height:1.5;letter-spacing:.01em;color:var(--color-key-900);font-variant-numeric:tabular-nums}
.stat .n small{font-size:calc(16 / 16 * 1rem);font-weight:normal;color:var(--color-neutral-solid-gray-800);margin-left:calc(4 / 16 * 1rem)}

/* 前後の対比 */
.ba{display:grid;grid-template-columns:1fr;gap:calc(16 / 16 * 1rem);margin:calc(16 / 16 * 1rem) 0}
@media (min-width:48rem){.ba{grid-template-columns:1fr 1fr;gap:calc(24 / 16 * 1rem)}}
.ba h5{margin:0 0 calc(8 / 16 * 1rem);font-weight:bold;font-size:calc(16 / 16 * 1rem);line-height:1.7;letter-spacing:.02em}
.ba blockquote{margin:0 0 calc(8 / 16 * 1rem)}

/* 保つ/替えてよい */
.keep{display:grid;grid-template-columns:1fr;gap:calc(16 / 16 * 1rem);margin:calc(16 / 16 * 1rem) 0}
@media (min-width:48rem){.keep{grid-template-columns:1fr 1fr;gap:calc(24 / 16 * 1rem)}}
.keep>div{border:1px solid var(--color-neutral-solid-gray-420);border-radius:calc(8 / 16 * 1rem);padding:calc(16 / 16 * 1rem)}
.keep h4{margin:0 0 calc(8 / 16 * 1rem)}
.keep ul{margin:0;padding-left:calc(24 / 16 * 1rem)}

/* 流れ図 */
.fig{width:100%;height:auto;display:block;font-family:var(--font-family-sans)}
.fig text{fill:var(--color-neutral-solid-gray-800);font-size:16px}
.flow .bx{fill:var(--color-neutral-white);stroke:var(--color-neutral-solid-gray-420);stroke-width:1.5}
.flow .k .bx{stroke:var(--color-key-900);stroke-width:2}
.flow .q .bx,.flow .src .bx{fill:var(--color-neutral-solid-gray-50);stroke:var(--color-neutral-solid-gray-800)}
.flow .bt{font-size:20px;font-weight:bold}
.flow .bs{font-size:14px;fill:var(--color-neutral-solid-gray-700)}
.flow .ar{fill:none;stroke:var(--color-neutral-solid-gray-700);stroke-width:1.5}.flow .ar.dashed{stroke-dasharray:6 5}
.flow .node{cursor:pointer}
@media (hover:hover){.flow .node:hover .bx{fill:var(--color-key-50)}}
.flow .node[aria-pressed=true] .bx{fill:var(--color-key-900);stroke:var(--color-key-900)}
.flow .node[aria-pressed=true] text{fill:var(--color-neutral-white)}
.nd{margin-top:calc(16 / 16 * 1rem);border-left:calc(8 / 16 * 1rem) solid var(--color-key-900);padding:calc(8 / 16 * 1rem) 0 calc(8 / 16 * 1rem) calc(24 / 16 * 1rem);max-width:44em}
.nd b{display:block;margin-bottom:calc(4 / 16 * 1rem)}
.flow-list{display:none;list-style:none;margin:0;padding:0}
.flow-list li{margin:0 0 calc(8 / 16 * 1rem)}
@media (max-width:47.99rem){.flow-wrap,.nd-wrap{display:none}.flow-list{display:block}}
.bars .s-body{fill:var(--color-key-900)}.bars .s-app{fill:var(--color-key-400)}
.bars .bl{font-size:14px;font-variant-numeric:tabular-nums}.bars .bl.inv{fill:var(--color-neutral-white)}
.bars .mn{font-size:14px;fill:var(--color-neutral-solid-gray-700);font-variant-numeric:tabular-nums}.bars .ml{font-size:16px}
.bars-wrap,.map-wrap{overflow-x:auto}
.map .mh{font-size:16px;font-weight:bold}
.map .mr{fill:var(--color-neutral-white);stroke:var(--color-neutral-solid-gray-420)}
.map .mr.body{stroke:var(--color-key-900);stroke-width:1.5}
.map .mr.app{fill:var(--color-neutral-solid-gray-50)}
.map .mr.new{stroke:var(--color-key-900);stroke-dasharray:4 3}
.map .ml{font-size:15px}.map .mn{font-size:14px;fill:var(--color-neutral-solid-gray-700);font-variant-numeric:tabular-nums}
.map .mv{fill:none;stroke:var(--color-key-400);stroke-width:1.5;opacity:.8}
.map.hl .mv{opacity:.12}.map.hl .mv.on{opacity:1;stroke:var(--color-key-900);stroke-width:2.5}
.map.hl .dst .mr,.map.hl .dst text{opacity:.35}.map.hl .dst.on .mr,.map.hl .dst.on text{opacity:1}
.map .src:hover .mr,.map .src.on .mr{fill:var(--color-key-50);stroke:var(--color-key-900)}
@media (max-width:47.99rem){.map{min-width:720px}.bars{min-width:640px}}

/* コマンド */
.cmd{display:flex;align-items:center;gap:calc(12 / 16 * 1rem);background:var(--color-neutral-solid-gray-800);color:var(--color-neutral-solid-gray-50);border-radius:calc(8 / 16 * 1rem);padding:calc(12 / 16 * 1rem) calc(16 / 16 * 1rem);font-family:var(--font-family-mono);font-size:calc(14 / 16 * 1rem);line-height:1.5;letter-spacing:0;margin:calc(8 / 16 * 1rem) 0 calc(16 / 16 * 1rem);max-width:44em}
@media (min-width:48rem){.cmd{font-size:calc(16 / 16 * 1rem)}}
.cmd code{flex:1;overflow:auto;white-space:nowrap;font-family:inherit}
.cmd button{appearance:none;border:1px solid var(--color-neutral-white);background:transparent;color:var(--color-neutral-white);border-radius:calc(4 / 16 * 1rem);padding:calc(4 / 16 * 1rem) calc(12 / 16 * 1rem);font:inherit;font-family:var(--font-family-sans);cursor:pointer;min-height:calc(32 / 16 * 1rem)}
.steps{margin:calc(8 / 16 * 1rem) 0 calc(16 / 16 * 1rem);padding-left:calc(32 / 16 * 1rem);max-width:44em}

/* 文書ビューア */
.seg{display:flex;flex-wrap:wrap;gap:calc(8 / 16 * 1rem);margin:0 0 calc(16 / 16 * 1rem)}
.seg button{appearance:none;border:1px solid var(--color-neutral-solid-gray-420);background:var(--color-neutral-white);color:var(--color-neutral-solid-gray-800);font:inherit;font-size:calc(16 / 16 * 1rem);line-height:1;padding:calc(10 / 16 * 1rem) calc(16 / 16 * 1rem);border-radius:calc(8 / 16 * 1rem);cursor:pointer;min-height:calc(44 / 16 * 1rem)}
.seg button[aria-pressed=true]{background:var(--color-key-900);border-color:var(--color-key-900);color:var(--color-neutral-white);font-weight:bold}
@media (hover:hover){.seg button:hover:not([aria-pressed=true]){background:var(--color-neutral-solid-gray-50);text-decoration:underline}}
.sync{display:inline-flex;align-items:center;gap:calc(6 / 16 * 1rem);margin-bottom:calc(16 / 16 * 1rem)}
.viewer{display:grid;grid-template-columns:1fr;gap:calc(16 / 16 * 1rem)}
@media (min-width:48rem){.viewer{grid-template-columns:1fr 1fr}.viewer.single{grid-template-columns:1fr}}
.pane{border:1px solid var(--color-neutral-solid-gray-420);border-radius:calc(8 / 16 * 1rem);overflow:hidden;background:var(--color-neutral-white)}
.pane .cap{font-weight:bold;padding:calc(8 / 16 * 1rem) calc(16 / 16 * 1rem);border-bottom:1px solid var(--color-neutral-solid-gray-420);background:var(--color-neutral-solid-gray-100);margin:0}
.pane .doc{height:min(80vh,900px);overflow:auto;overscroll-behavior:contain}
[hidden]{display:none!important}
footer{padding:calc(32 / 16 * 1rem) 0 calc(64 / 16 * 1rem)}
footer p{margin:0 0 calc(8 / 16 * 1rem)}
"""

DOC_CSS = """
.doc{padding:calc(24 / 16 * 1rem) calc(16 / 16 * 1rem) calc(64 / 16 * 1rem);color:var(--color-neutral-solid-gray-800)}
@media (min-width:48rem){.doc{padding:calc(24 / 16 * 1rem) calc(32 / 16 * 1rem) calc(64 / 16 * 1rem)}}
.doc article{max-width:40em}
.doc h1{font-size:calc(24 / 16 * 1rem);line-height:1.5;margin:0 0 calc(24 / 16 * 1rem)}
.doc h2{font-size:calc(20 / 16 * 1rem);line-height:1.5;margin:calc(48 / 16 * 1rem) 0 calc(12 / 16 * 1rem);padding-top:calc(16 / 16 * 1rem);border-top:1px solid var(--color-neutral-solid-gray-420)}
.doc h3{font-size:calc(18 / 16 * 1rem);line-height:1.6;margin:calc(28 / 16 * 1rem) 0 calc(8 / 16 * 1rem)}
.doc h4{font-size:calc(16 / 16 * 1rem);margin:calc(20 / 16 * 1rem) 0 calc(6 / 16 * 1rem)}
.doc p{margin:0 0 1em}
.doc ul,.doc ol{padding-left:calc(32 / 16 * 1rem);margin:0 0 1em}
.doc li{margin:.3em 0}
.doc hr{border:0;border-top:1px solid var(--color-neutral-solid-gray-420);margin:calc(32 / 16 * 1rem) 0}
.doc table{border-collapse:collapse;width:100%;margin:0 0 1.2em;font-size:calc(14 / 16 * 1rem);line-height:1.6;font-variant-numeric:tabular-nums}
@media (min-width:48rem){.doc table{font-size:calc(16 / 16 * 1rem)}}
.doc th,.doc td{border-bottom:1px solid var(--color-neutral-solid-gray-420);padding:calc(8 / 16 * 1rem) calc(10 / 16 * 1rem);text-align:left;vertical-align:top}
.doc th{background:var(--color-neutral-solid-gray-100);font-weight:bold;border-bottom-color:var(--color-neutral-black)}
.doc code{font-family:var(--font-family-mono);font-size:.92em;background:var(--color-neutral-solid-gray-50);padding:1px 4px;border-radius:calc(4 / 16 * 1rem)}
"""
CSS = CSS + DOC_CSS

JS = r"""
(function(){
  document.querySelectorAll('[role=tablist]').forEach(list=>{
  const tabs=[...list.querySelectorAll('[role=tab]')];
  function select(i,focus){tabs.forEach((t,j)=>{const on=i===j;t.setAttribute('aria-selected',on);t.tabIndex=on?0:-1;document.getElementById(t.getAttribute('aria-controls')).hidden=!on;});if(focus)tabs[i].focus();}
  tabs.forEach((t,i)=>{t.addEventListener('click',()=>select(i,false));
    t.addEventListener('keydown',e=>{const n=tabs.length;let j=null;
      if(e.key==='ArrowRight')j=(i+1)%n;else if(e.key==='ArrowLeft')j=(i-1+n)%n;else if(e.key==='Home')j=0;else if(e.key==='End')j=n-1;
      if(j!==null){e.preventDefault();select(j,true);}});});
  });
})();
(function(){
  const nodes=[...document.querySelectorAll('.flow .node')];const descs=[...document.querySelectorAll('.nd')];
  function pick(key){nodes.forEach(n=>n.setAttribute('aria-pressed',n.dataset.node===key));descs.forEach(d=>d.hidden=d.dataset.for!==key);}
  nodes.forEach(n=>{n.addEventListener('click',()=>pick(n.dataset.node));n.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();pick(n.dataset.node);}});});
  pick('ask');
})();
(function(){
  document.querySelectorAll('.map').forEach(svg=>{
  const srcs=[...svg.querySelectorAll('.src')],paths=[...svg.querySelectorAll('.mv')],dsts=[...svg.querySelectorAll('.dst')];
  function on(i){svg.classList.add('hl');srcs.forEach(s=>s.classList.toggle('on',s.dataset.src===i));
    const hit=new Set();paths.forEach(p=>{const m=p.dataset.src===i;p.classList.toggle('on',m);if(m)hit.add(p.dataset.dst);});
    dsts.forEach(d=>d.classList.toggle('on',hit.has(d.dataset.dst)));}
  function off(){svg.classList.remove('hl');srcs.forEach(s=>s.classList.remove('on'));paths.forEach(p=>p.classList.remove('on'));dsts.forEach(d=>d.classList.remove('on'));}
  srcs.forEach(s=>{s.addEventListener('mouseenter',()=>on(s.dataset.src));s.addEventListener('mouseleave',off);s.addEventListener('focus',()=>on(s.dataset.src));s.addEventListener('blur',off);
    s.addEventListener('click',()=>{if(s.classList.contains('on')&&svg.classList.contains('hl')){off();}else{on(s.dataset.src);}});});
  });
})();
(function(){
  const links=[...document.querySelectorAll('.toc-list a')];const secs=links.map(a=>document.querySelector(a.getAttribute('href'))).filter(Boolean);
  function update(){let cur=secs[0];for(const s of secs){if(s.getBoundingClientRect().top<=96)cur=s;}links.forEach(a=>{const on=a.getAttribute('href')==='#'+cur.id;if(on)a.setAttribute('aria-current','location');else a.removeAttribute('aria-current');});}
  window.addEventListener('scroll',update,{passive:true});update();
})();
function openTarget(){const el=location.hash&&document.getElementById(decodeURIComponent(location.hash.slice(1)));if(!el)return;let d=el.closest('details');while(d){d.open=true;d=d.parentElement&&d.parentElement.closest('details');}el.scrollIntoView({block:'center'});}
window.addEventListener('hashchange',openTarget);openTarget();
const caps={before:'元の稟議書',after:'直した後',concise:'端的にした後',kak:'別ファイルの確認事項',redesign:'組み直した後',logic:'筋を見る(検査の報告)',somosomo:'前提を疑う(検査の報告)'};
const viewer=document.getElementById('viewer');
const pL=document.getElementById('paneL'),pR=document.getElementById('paneR');
const dL=pL.querySelector('.doc'),dR=pR.querySelector('.doc');
function load(d,key){if(d.dataset.key!==key){d.replaceChildren(document.getElementById('t-'+key).content.cloneNode(true));d.dataset.key=key;d.scrollTop=0;}}
function mode(m){
  document.querySelectorAll('.seg button').forEach(b=>b.setAttribute('aria-pressed',b.dataset.m===m));
  const side=m==='side'||m==='side2'||m==='side3';
  viewer.classList.toggle('single',!side);pR.hidden=!side;document.getElementById('syncbox').hidden=!side;
  if(side){const r={side:'after',side2:'redesign',side3:'concise'}[m];load(dL,'before');load(dR,r);pL.querySelector('.cap').textContent=caps.before;pR.querySelector('.cap').textContent=caps[r];}
  else{load(dL,m);pL.querySelector('.cap').textContent=caps[m];}
}
document.querySelectorAll('.seg button').forEach(b=>b.addEventListener('click',()=>mode(b.dataset.m)));
let lock=false;
function bind(a,b){a.addEventListener('scroll',()=>{if(lock||!document.getElementById('sync').checked||pR.hidden)return;
  const r=a.scrollTop/Math.max(1,a.scrollHeight-a.clientHeight);lock=true;b.scrollTop=r*(b.scrollHeight-b.clientHeight);requestAnimationFrame(()=>lock=false);});}
bind(dL,dR);bind(dR,dL);
mode('side');
document.querySelectorAll('[data-copy]').forEach(b=>b.addEventListener('click',async()=>{await navigator.clipboard.writeText(document.getElementById(b.dataset.copy).textContent);b.textContent='コピーした';setTimeout(()=>b.textContent='コピー',1500);}));
"""
