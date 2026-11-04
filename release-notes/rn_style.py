"""ビジュアルリリースノートの見た目(デジタル庁デザインシステムのトークン、CSS、JS)。build-v1.7.0.py が読む。"""
TOKENS = """
:root{
  --sans:'Noto Sans JP',sans-serif;--mono:ui-monospace,'SF Mono',Menlo,monospace;
  --fs-13:.8125rem;--fs-14:.875rem;--fs-16:1rem;--fs-17:1.0625rem;--fs-18:1.125rem;--fs-20:1.25rem;--fs-24:1.5rem;--fs-28:1.75rem;--fs-32:2rem;--fs-36:2.25rem;
  --r-4:.25rem;--r-8:.5rem;--r-12:.75rem;--r-full:624.9375rem;
  --key-50:#e8f1fe;--key-100:#d9e6ff;--key-200:#c5d7fb;--key-400:#7096f8;--key-800:#0031d8;--key-900:#0017c1;--key-1000:#00118f;
  --ok:#197a4b;--ok-50:#e6f5ec;--ng:#ce0000;--ng-50:#fdeeee;--warn:#b78f00;--warn-50:#fbf5e0;--warn-100:#fff0b3;--orange:#c74700;--orange-50:#ffeee2;
  --g-50:#f2f2f2;--g-100:#e6e6e6;--g-200:#cccccc;--g-300:#b3b3b3;--g-700:#4d4d4d;--g-800:#333333;--g-900:#1a1a1a;
  --elev:0 2px 8px 1px rgba(0,0,0,.1),0 1px 5px 0 rgba(0,0,0,.3);
}
"""
JA = 'font-feature-settings:"palt" 1;line-break:strict;word-break:auto-phrase;text-autospace:normal;-webkit-text-size-adjust:100%;'
FONT = '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;700;900&display=swap" rel="stylesheet">'

DOC_CSS = """
.doc{padding:24px clamp(16px,3vw,32px) 64px;color:var(--g-900);font:400 var(--fs-16)/1.75 var(--sans)}
.doc article{max-width:40em}
.doc h1{font-size:var(--fs-24);line-height:1.4;margin:0 0 24px;text-wrap:balance}
.doc h2{font-size:var(--fs-20);line-height:1.4;margin:48px 0 12px;padding-top:16px;border-top:1px solid var(--g-200);text-wrap:balance}
.doc h3{font-size:var(--fs-17);line-height:1.5;margin:28px 0 8px}
.doc h4{font-size:var(--fs-16);margin:20px 0 6px}
.doc p{margin:0 0 1em}
.doc ul,.doc ol{padding-left:1.6em;margin:0 0 1em}
.doc li{margin:.3em 0}
.doc hr{border:0;border-top:1px solid var(--g-200);margin:32px 0}
.doc table{border-collapse:collapse;width:100%;margin:0 0 1.2em;font-size:var(--fs-14);line-height:1.6;font-variant-numeric:tabular-nums}
.doc th,.doc td{border:1px solid var(--g-200);padding:8px 10px;text-align:left;vertical-align:top}
.doc th{background:var(--g-50);font-weight:700}
.doc code{font-family:var(--mono);font-size:.92em;background:var(--g-50);padding:1px 4px;border-radius:var(--r-4)}
"""

CSS = TOKENS + """
:root{--yellow-300:#ffd43d;--g-420:#949494;--key-1200:#000060;--key-300:#9db7f9}
*{box-sizing:border-box}
html{scroll-behavior:smooth;scroll-padding-top:24px}
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}*{transition:none!important}}
body{margin:0;background:#fff;color:var(--g-900);font:400 var(--fs-16)/1.75 var(--sans);""" + JA + """}
::selection{background:var(--key-100)}
a{color:var(--key-900);text-decoration-thickness:1px;text-underline-offset:.2em}
a:hover{text-decoration-thickness:3px;color:var(--key-1000)}
a:active{color:var(--orange)}
:focus-visible{outline:4px solid #000;outline-offset:2px;border-radius:4px;box-shadow:0 0 0 2px var(--yellow-300)}
p{margin:0}
.wrap{max-width:1120px;margin:0 auto;padding:0 clamp(16px,4vw,40px)}
.band{background:var(--key-900);color:#fff;font-size:var(--fs-14);padding:10px 0}
.band .wrap{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap}
.band a{color:#fff}

/* 目次(DADS の toc を土台に、現在地をスクロールで追う) */
.toc{position:sticky;top:0;z-index:5;background:#fff;border-bottom:1px solid var(--g-200)}
.toc-inner{max-width:1120px;margin:0 auto;padding:0 clamp(16px,4vw,40px);display:flex;align-items:center;gap:16px}
.toc-h{margin:0;font-size:var(--fs-14);font-weight:700;color:var(--g-800);flex:none}
.toc-list{list-style:none;margin:0;padding:0;display:flex;gap:4px;overflow-x:auto;scrollbar-width:none;-webkit-overflow-scrolling:touch}
.toc-list::-webkit-scrollbar{display:none}
.toc-list li{flex:none}
.toc-list a{display:block;padding:10px 10px 8px;border-bottom:3px solid transparent;color:var(--g-800);text-decoration:none;font-size:var(--fs-14);white-space:nowrap;line-height:1.4}
.toc-list a:hover{text-decoration:underline;text-underline-offset:3px;color:var(--key-1000)}
.toc-list a[aria-current=location]{color:var(--g-900);font-weight:700;border-bottom-color:var(--key-900)}
@media (min-width:1560px){
  .toc{position:fixed;top:120px;left:calc((100vw - 1120px)/2 - 220px);width:200px;background:transparent;border:0;z-index:5}
  .toc-inner{display:block;padding:0}
  .toc-h{margin-bottom:8px;font-size:var(--fs-16)}
  .toc-list{display:block;overflow:visible;border-left:1px solid var(--g-200)}
  .toc-list a{padding:6px 12px;border-bottom:0;border-left:3px solid transparent;margin-left:-1px;white-space:normal}
  .toc-list a[aria-current=location]{border-left-color:var(--key-900)}
}
html{scroll-padding-top:56px}
@media (min-width:1560px){html{scroll-padding-top:24px}}
.hero{padding:48px 0 40px;border-bottom:1px solid var(--g-200)}
.hero .ver{font-size:clamp(3.5rem,9vw,6.5rem);font-weight:900;line-height:1;letter-spacing:-.03em;margin:0;color:var(--key-900);font-variant-numeric:tabular-nums}
.hero .ver small{font-size:.35em;font-weight:700;letter-spacing:0;margin-right:.15em}
.hero .meta{color:var(--g-700);font-size:var(--fs-14);margin:8px 0 28px}
.hero h1{font-size:clamp(var(--fs-24),3.2vw,var(--fs-36));line-height:1.4;margin:0 0 16px;text-wrap:balance;letter-spacing:-.01em;max-width:24em}
.hero .lead{font-size:var(--fs-17);max-width:40em;text-wrap:pretty;margin-bottom:12px}
.sk{font-family:var(--mono);font-size:.9em;background:var(--g-50);border:1px solid var(--g-200);border-radius:var(--r-4);padding:0 .35em;white-space:nowrap;color:var(--g-900)}
mark{background:var(--warn-100);color:inherit;padding:0 .1em;border-radius:2px}
mark.ok{background:var(--ok-50);box-shadow:inset 0 -2px 0 var(--ok)}
mark.key{background:var(--key-50);box-shadow:inset 0 -2px 0 var(--key-900)}
.cap{font-size:var(--fs-14);color:var(--g-700);margin:28px 0 8px}
.hero4{display:grid;grid-template-columns:1fr auto 1.1fr auto 1.1fr auto 1fr;gap:10px;align-items:start;margin-top:8px}
.hero4>div{font-size:var(--fs-14);line-height:1.7}
.hero4 h4{font-size:var(--fs-14);font-weight:700;margin:0 0 8px;padding-bottom:6px;border-bottom:1px solid var(--g-900);display:flex;justify-content:space-between;align-items:center;gap:8px}
.hero4 .arrow{align-self:center;color:var(--g-700);font-size:var(--fs-24);font-weight:700;padding-top:20px}
.hero4 .arrow::before{content:'→'}
.hero4 .tag{display:inline-block;font-weight:700;font-size:var(--fs-13);padding:0 8px;border-radius:var(--r-4);line-height:1.6}
.hero4 .tag-ask{background:var(--key-900);color:#fff}
blockquote.q-ask{background:var(--key-50);border:1px solid var(--key-200)}
blockquote.q-ans{background:var(--warn-50);border:1px solid var(--warn)}
.hero3{display:grid;grid-template-columns:1fr auto 1.2fr auto 1fr;gap:12px;align-items:start;margin-top:8px}
.hero3>div{font-size:var(--fs-14);line-height:1.7}
.hero3 h4{font-size:var(--fs-14);font-weight:700;margin:0 0 8px;padding-bottom:6px;border-bottom:1px solid var(--g-900);display:flex;justify-content:space-between;align-items:center;gap:8px}
.hero3 .arrow{align-self:center;color:var(--g-700);font-size:var(--fs-24);font-weight:700;padding-top:20px}
.hero3 .arrow::before{content:'→'}
.hero3 blockquote.q-somo{background:var(--orange-50);border:1px solid #ffc199}
.hero3 blockquote em{font-style:normal;background:var(--ok-50);box-shadow:inset 0 -2px 0 var(--ok)}
.hero3 .tag{display:inline-block;font-weight:700;font-size:var(--fs-13);padding:0 8px;border-radius:var(--r-4);line-height:1.6}
.hero3 .tag-somo{background:var(--orange);color:#fff}
.ba{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.ba h4{font-size:var(--fs-14);font-weight:700;margin:0 0 8px;padding-bottom:6px;border-bottom:1px solid var(--g-900);display:flex;justify-content:space-between;align-items:center;gap:8px}
blockquote{margin:0 0 10px;padding:12px 14px;background:var(--g-50);border-radius:var(--r-8);font-size:var(--fs-14);line-height:1.7}
blockquote p{margin:2px 0 0}
blockquote em{font-style:normal;background:var(--ok-50);box-shadow:inset 0 -2px 0 var(--ok);padding:0 .1em}
.ba>div:first-child blockquote em{background:var(--warn-100);box-shadow:none}
blockquote em.same{background:var(--ng-50);box-shadow:inset 0 -2px 0 var(--ng)}
.gone{font-size:var(--fs-14);color:var(--g-700);margin:0 0 10px;padding:0 14px}
.ln{display:inline-block;font-size:var(--fs-14);color:var(--g-700);font-variant-numeric:tabular-nums}
.legend{font-size:var(--fs-13);color:var(--g-700);margin:6px 0 0}
.legend i{display:inline-block;width:12px;height:12px;vertical-align:-1px;margin:0 4px 0 10px;border-radius:2px}

main section.block{padding:44px 0;border-bottom:1px solid var(--g-200)}
main h2{font-size:var(--fs-24);line-height:1.4;margin:0 0 8px;text-wrap:balance}
main .sub{max-width:40em;color:var(--g-800);margin-bottom:20px;text-wrap:pretty}
main h3.sec{font-size:var(--fs-18);margin:36px 0 8px}

/* ディスクロージャー(DADS) */
.dsc summary{display:flex;width:fit-content;align-items:flex-start;gap:8px;cursor:default;list-style:none;font-weight:700;font-size:var(--fs-16);color:var(--g-900)}
.dsc summary::-webkit-details-marker{display:none}
.dsc summary svg{flex:none;color:var(--key-1000);margin-top:calc((1lh - 24px)/2);transition:transform .15s}
.dsc[open]>summary svg{transform:rotate(180deg)}
.dsc summary:hover{text-decoration:underline;text-underline-offset:3px}
.dsc-body{padding:12px 0 4px 32px;font-size:var(--fs-14);line-height:1.7}
.dsc{margin:12px 0 0}

/* タブ(DADS) */
.dads-tab{position:relative;z-index:0;display:flex;flex-direction:column;font-size:var(--fs-16);line-height:1.7}
.dads-tab__list{position:relative;z-index:0;margin:-6px;overflow:hidden;display:flex;flex-wrap:wrap;padding:7px 6px 6px 7px;list-style:none}
.dads-tab__list>li{margin:0;display:contents}
.dads-tab__list::after{position:relative;flex-grow:1;border:0 solid var(--g-420);content:"";margin-left:-1px;width:1px;border-bottom-width:1px}
.dads-tab__tab{isolation:isolate;appearance:none;margin:-1px 0 0 -1px;display:flex;border:1px solid var(--g-420);background:#fff;padding:0;color:inherit;font:inherit;text-align:left;cursor:default;position:relative}
.dads-tab__tab::before{content:"";position:absolute;bottom:6px;width:100%;border:0 solid #fff}
.dads-tab__tab>span{position:relative;display:flex;flex-grow:1;align-items:center;gap:8px;border:0 solid var(--g-50);border-top-width:5px;padding:14px 16px;font-size:var(--fs-16);line-height:1.2}
.dads-tab__tab>span::before{content:"";position:absolute;top:-6px;right:0;left:0;height:6px}
.dads-tab__tab[aria-selected=true]>span{font-weight:700}
.dads-tab__tab[aria-selected=true]:not(:focus-visible)::before{border-bottom-width:1px}
.dads-tab__tab[aria-selected=true]>span::before{background:var(--key-900)}
.dads-tab__tab:not([aria-selected=true]):hover{background:var(--g-50)}
.dads-tab__tab:not([aria-selected=true]):hover>span{text-decoration:underline;text-underline-offset:3px}
.dads-tab__tab:not([aria-selected=true]):hover>span::before{background:var(--g-420)}
.dads-tab__tab:focus-visible{overflow:hidden;z-index:1}
.dads-tab__panels{flex-grow:1;display:flex;flex-direction:column}
.dads-tab__panel{border:solid var(--g-420);border-width:0 1px 1px;background:#fff;padding:20px clamp(16px,2.5vw,28px) 24px}
.tnum{display:inline-grid;place-items:center;width:24px;height:24px;border-radius:var(--r-full);background:var(--key-900);color:#fff;font-size:var(--fs-14);font-variant-numeric:tabular-nums}
.pick .desc{font-size:var(--fs-14);color:var(--g-800);margin:0 0 4px;max-width:44em}
.pick .nums{font-size:var(--fs-13);color:var(--g-700);margin:0 0 20px;font-variant-numeric:tabular-nums}
.ex{padding:16px 0 4px;border-top:1px solid var(--g-100)}
.ex-t{font-size:var(--fs-17);line-height:1.4;margin:0 0 12px;text-wrap:balance}
.ex-t .st{margin-left:8px;vertical-align:middle}
.ba h5{font-size:var(--fs-14);font-weight:700;margin:0 0 8px;padding-bottom:6px;border-bottom:1px solid var(--g-900)}
.spine{margin:8px 0 28px}
.spine td.n{white-space:nowrap}
.spine small{display:block;color:var(--g-700)}
.pick h3{font-size:var(--fs-18);line-height:1.4;margin:0 0 16px;text-wrap:balance}
.pick h3 .st{margin-left:8px;vertical-align:middle}
.q{margin:0 0 12px;padding:12px 14px;border:1px solid var(--g-200);border-radius:var(--r-8);font-size:var(--fs-14);line-height:1.7}
.q .tag{display:inline-block;font-weight:700;font-size:var(--fs-13);padding:0 8px;border-radius:var(--r-4);margin-right:8px;line-height:1.6}
.q-logic{border-color:var(--key-200);background:var(--key-50)}
.q-logic .tag{background:var(--key-900);color:#fff}
.q-somo{border-color:#ffc199;background:var(--orange-50)}
.q-somo .tag{background:var(--orange);color:#fff}
.q p{margin:4px 0 0}
.st{font-weight:700;font-size:var(--fs-13);padding:1px 10px;border-radius:var(--r-full);white-space:nowrap;display:inline-block}
.st-fixed{background:var(--ok);color:#fff}
.st-deferred{background:var(--warn-100);color:var(--g-900);border:1px solid var(--warn)}
.st-remains{background:var(--ng);color:#fff}
.st-ask{background:var(--key-900);color:#fff}
.st-doc{background:var(--g-100);color:var(--g-900);border:1px solid var(--g-700)}
.q-ask{border-color:var(--key-200);background:var(--key-50)}.q-ask .tag{background:var(--key-900);color:#fff}
.q-ans{border-color:var(--warn);background:var(--warn-50)}.q-ans .tag{background:var(--warn);color:var(--g-900)}
.qa-list{padding-left:1.6em;margin:0 0 16px;max-width:48em}.qa-list li{margin:0 0 12px}.qa-list .qq{margin:0;font-weight:700;font-size:var(--fs-14);line-height:1.7}.qa-list .qa{margin:4px 0 0;font-size:var(--fs-14);line-height:1.7}.qa-list .qa .tag{display:inline-block;font-weight:700;font-size:var(--fs-13);padding:0 8px;border-radius:var(--r-4);margin-right:6px;background:var(--warn);color:var(--g-900)}
.kak-rest{list-style:disc}
.st-shrink{background:var(--orange-50);color:var(--orange);border:1px solid var(--orange)}
.plan.shrink{border:2px dashed var(--orange)}
.plan .lbl{font-weight:700;margin:8px 0 2px}
.plan.shrink ul{margin:0 0 8px;padding-left:1.4em;color:var(--g-800)}
.hero3 blockquote.q-shrink{background:var(--orange-50);border:1px dashed var(--orange)}
.spine td.sh{color:var(--g-900)}
.note{font-size:var(--fs-14);line-height:1.7;color:var(--g-800);text-wrap:pretty;margin-top:8px}

/* 流れ図 */
.fig{width:100%;height:auto;display:block;font-family:var(--sans)}
.fig text{fill:var(--g-900);font-size:15px}
.flow .bx{fill:#fff;stroke:var(--g-300);stroke-width:1.5;transition:fill .15s}
.flow .k .bx{stroke:var(--key-900);stroke-width:2}
.flow .o .bx{stroke:var(--orange);stroke-width:2}
.flow .q .bx,.flow .src .bx{fill:var(--g-50);stroke:var(--g-900)}
.flow .bt{font-size:19px;font-weight:700}
.flow .bs{font-size:13px;fill:var(--g-700)}
.flow .ar.dashed{stroke-dasharray:6 5}.flow .ar{fill:none;stroke:var(--g-700);stroke-width:1.5}
.flow .node{cursor:pointer}
.flow .node:hover .bx{fill:var(--key-50)}
.flow .node[aria-pressed=true] .bx{fill:var(--key-900);stroke:var(--key-900)}
.flow .node[aria-pressed=true] text{fill:#fff}
.flow .node:focus-visible{outline:4px solid #000;outline-offset:2px;border-radius:8px}
.flow-hint{font-size:var(--fs-14);color:var(--g-700);margin:6px 0 0}
.nd{margin-top:12px;padding:16px 20px;border-left:4px solid var(--key-900);background:var(--key-50);border-radius:0 var(--r-8) var(--r-8) 0;max-width:44em}
.nd b{display:block;margin-bottom:4px}
.nd p{font-size:var(--fs-14);line-height:1.7}
.flow-list{display:none;list-style:none;margin:0;padding:0;font-size:var(--fs-14)}
.flow-list li{padding:6px 14px;border:1px solid var(--g-200);border-radius:var(--r-8);margin:0 0 8px}
.flow-list .dsc{margin:0}
.flow-list .dsc-body p{color:var(--g-800);margin-top:4px}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:28px}.stats.four{grid-template-columns:repeat(2,1fr)}
.stat{border:1px solid var(--g-200);border-radius:var(--r-8);padding:16px 18px}
.stat b{display:block;font-size:var(--fs-16);margin-bottom:2px}
.stat .n{font-size:var(--fs-32);font-weight:900;color:var(--key-900);line-height:1.1;font-variant-numeric:tabular-nums}
.stat .n small{font-size:var(--fs-14);font-weight:400;color:var(--g-700);margin-left:4px}
.stat .dsc summary{font-weight:400;font-size:var(--fs-14);color:var(--key-900)}
.stat .dsc-body{color:var(--g-800)}

/* 組み直す */
.keep{display:grid;grid-template-columns:1fr auto 1fr;gap:16px;align-items:stretch;margin:8px 0 8px}
.keep>div{border-radius:var(--r-8);padding:16px 20px;font-size:var(--fs-14);line-height:1.7}
.keep .k{border:2px solid var(--key-900)}
.keep .c{border:2px dashed var(--orange)}
.keep h4{margin:0 0 8px;font-size:var(--fs-16)}
.keep ul{margin:0;padding-left:1.3em}
.keep .mid::before{content:'→'}
.keep .mid{align-self:center;font-weight:700;color:var(--g-700);font-size:var(--fs-28);text-align:center;padding:0}
.plan{border:1px solid var(--key-900);box-shadow:inset 0 0 0 1px var(--key-900);border-radius:var(--r-8);padding:16px 18px;font-size:var(--fs-14);line-height:1.7;margin-bottom:8px}
.plan h4{font-size:var(--fs-16);margin:0 0 8px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.plan .claim,.dsc-body .claim{margin:0 0 10px;text-wrap:pretty}
.plan ol,.dsc-body ol{margin:0 0 10px;padding-left:1.6em;color:var(--g-800)}
.plan li,.dsc-body li{margin:1px 0}
.plan .weak,.dsc-body .weak{margin:0;color:var(--g-800)}
.plan-alt{margin:4px 0 0}
.map .mh{font-size:15px;font-weight:700}
.map .mr{fill:#fff;stroke:var(--g-300)}
.map .mr.body{stroke:var(--key-900);stroke-width:1.5}
.map .mr.app{fill:var(--g-50)}
.map .mr.new{fill:var(--warn-50);stroke:var(--warn)}
.map .ml{font-size:15px}
.map .mn{font-size:13px;fill:var(--g-700);font-variant-numeric:tabular-nums}
.map .mv{fill:none;stroke:var(--key-400);stroke-width:1.5;opacity:.8;transition:opacity .15s,stroke-width .15s}
.map .src{cursor:default}
.map.hl .mv{opacity:.12}
.map.hl .mv.on{opacity:1;stroke:var(--key-900);stroke-width:2.5}
.map.hl .dst .mr{opacity:.35}
.map.hl .dst.on .mr{opacity:1;stroke:var(--key-900);stroke-width:2}
.map.hl .dst text{opacity:.35}.map.hl .dst.on text{opacity:1}
.map .src:hover .mr,.map .src.on .mr{fill:var(--key-50);stroke:var(--key-900)}
.map .src:focus-visible{outline:4px solid #000;outline-offset:2px}
.bars .s-body{fill:var(--key-900)}.bars .s-app{fill:var(--key-400)}.bars .s-kak{fill:var(--key-200)}
.bars .bl{font-size:13px;font-variant-numeric:tabular-nums}.bars .bl.inv{fill:#fff}
.bars .mn{font-size:13px;fill:var(--g-700);font-variant-numeric:tabular-nums}.bars .ml{font-size:15px}

.kak{padding-left:1.6em;margin:0;font-size:var(--fs-14);line-height:1.7;max-width:44em}
.kak li{margin:0 0 10px;padding-left:4px}
.kak li::marker{color:var(--key-900);font-weight:700;font-variant-numeric:tabular-nums}
.kak li:target{background:var(--warn-50);border-radius:var(--r-4)}
.dsc-body .kak{padding-left:1.6em}

.tbl{border-collapse:collapse;width:100%;font-size:var(--fs-14);line-height:1.6;font-variant-numeric:tabular-nums;margin:8px 0 16px}
.tbl th,.tbl td{padding:10px 12px;border-top:1px solid var(--g-200);text-align:left;vertical-align:top}
.tbl thead th{border-top:0;border-bottom:2px solid var(--g-900);font-weight:700}
.tbl tbody th{font-weight:700;white-space:nowrap}
.tbl small{color:var(--g-700)}
.limits{max-width:40em;text-wrap:pretty;padding-left:1.3em;margin:0}
.limits li{margin:8px 0}
.cmd{display:flex;align-items:center;gap:12px;background:var(--g-900);color:#fff;border-radius:var(--r-8);padding:12px 16px;font-family:var(--mono);font-size:var(--fs-14);margin:8px 0 20px;max-width:44em}
.cmd code{flex:1;overflow:auto;white-space:nowrap}
.cmd button{appearance:none;border:1px solid #fff;background:transparent;color:#fff;border-radius:var(--r-4);padding:4px 12px;font:inherit;font-family:var(--sans);cursor:pointer;min-height:28px}
.cmd button:hover{background:#fff;color:var(--g-900);text-decoration:underline}
.env .desc{font-size:var(--fs-14);color:var(--g-800);margin:0 0 12px;max-width:44em}
.steps{margin:0 0 12px;padding-left:1.6em;font-size:var(--fs-14);line-height:1.7;max-width:44em}
.steps li{margin:4px 0}
.env .cmd{margin:4px 0 12px}
.asks{list-style:none;padding:0;margin:0;display:grid;grid-template-columns:repeat(2,1fr);gap:8px 24px;max-width:44em;font-size:var(--fs-14)}
.asks li{padding:8px 12px;background:var(--g-50);border-radius:var(--r-8)}
.asks li span{display:block;color:var(--g-700);font-size:var(--fs-13)}

.seg{display:inline-flex;border:1px solid var(--g-420);border-radius:var(--r-8);overflow:hidden;margin:0 16px 16px 0;flex-wrap:wrap}
.seg button{appearance:none;border:0;background:#fff;color:var(--key-900);font:inherit;font-size:var(--fs-14);padding:8px 16px;cursor:pointer;border-right:1px solid var(--g-420);min-height:36px}
.seg button:last-child{border-right:0}
.seg button[aria-pressed=true]{background:var(--key-900);color:#fff}
.seg button:hover:not([aria-pressed=true]){background:var(--key-200);color:var(--key-1000);text-decoration:underline}
.sync{font-size:var(--fs-14);display:inline-flex;align-items:center;gap:6px;vertical-align:top;padding-top:8px}
.viewer{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.viewer.single{grid-template-columns:1fr}
.pane{border:1px solid var(--g-200);border-radius:var(--r-8);overflow:hidden;background:#fff;box-shadow:var(--elev)}
.pane .cap{font-size:var(--fs-14);font-weight:700;padding:8px 14px;border-bottom:1px solid var(--g-200);background:var(--g-50);margin:0;color:var(--g-900)}
.pane .doc{height:min(80vh,900px);overflow:auto;overscroll-behavior:contain}
[hidden]{display:none!important}
footer{padding:32px 0 64px;font-size:var(--fs-14);color:var(--g-700)}
footer p{margin:0 0 8px}

@media (max-width:900px){
  .ba,.stats,.asks,.hero3{grid-template-columns:1fr}
  .hero3 .arrow{padding:0;text-align:center}.hero3 .arrow::before{content:'↓'}
  .keep{grid-template-columns:1fr}.keep .mid{padding:4px 0}.keep .mid::before{content:'↓'}
  .viewer{grid-template-columns:1fr}
  .flow-wrap,.nd-wrap{display:none}.flow-list{display:block}
  .map{min-width:720px}.map-wrap{overflow:auto}
  .bars{min-width:640px}.bars-wrap{overflow:auto}
  .spine{min-width:600px}.spine-wrap{overflow:auto}
}
""" + DOC_CSS

JS = r"""
// タブ(DADS の矢印キー操作)
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
// 流れ図の箱
(function(){
  const nodes=[...document.querySelectorAll('.flow .node')];const descs=[...document.querySelectorAll('.nd')];
  function pick(key){nodes.forEach(n=>n.setAttribute('aria-pressed',n.dataset.node===key));descs.forEach(d=>d.hidden=d.dataset.for!==key);}
  nodes.forEach(n=>{n.addEventListener('click',()=>pick(n.dataset.node));n.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();pick(n.dataset.node);}});});
  pick('ask');
})();
// 節の移動図
(function(){
  document.querySelectorAll('.map').forEach(svg=>{
  const srcs=[...svg.querySelectorAll('.src')],paths=[...svg.querySelectorAll('.mv')],dsts=[...svg.querySelectorAll('.dst')];
  function on(i){svg.classList.add('hl');srcs.forEach(s=>s.classList.toggle('on',s.dataset.src===i));
    const hit=new Set();paths.forEach(p=>{const m=p.dataset.src===i;p.classList.toggle('on',m);if(m)hit.add(p.dataset.dst);});
    dsts.forEach(d=>d.classList.toggle('on',hit.has(d.dataset.dst)));}
  function off(){svg.classList.remove('hl');srcs.forEach(s=>s.classList.remove('on'));paths.forEach(p=>p.classList.remove('on'));dsts.forEach(d=>d.classList.remove('on'));}
  srcs.forEach(s=>{s.addEventListener('mouseenter',()=>on(s.dataset.src));s.addEventListener('mouseleave',off);s.addEventListener('focus',()=>on(s.dataset.src));s.addEventListener('blur',off);
  });
  });
})();
// 目次:いま読んでいる節を追う
(function(){
  const links=[...document.querySelectorAll('.toc-list a')];if(!links.length)return;
  const targets=links.map(a=>document.querySelector(a.getAttribute('href'))).filter(Boolean);
  function setCurrent(id){links.forEach(a=>{const on=a.getAttribute('href')==='#'+id;if(on)a.setAttribute('aria-current','location');else a.removeAttribute('aria-current');
    if(on&&window.innerWidth<1560){const l=a.closest('.toc-list');const r=a.getBoundingClientRect(),lr=l.getBoundingClientRect();l.scrollLeft+=(r.left+r.width/2)-(lr.left+lr.width/2);}});}
  function update(){const y=window.scrollY+window.innerHeight*0.3;let cur=targets[0];for(const t of targets){if(t.offsetTop<=y)cur=t;}setCurrent(cur.id);}
  let ticking=false;window.addEventListener('scroll',()=>{if(!ticking){requestAnimationFrame(()=>{update();ticking=false;});ticking=true;}},{passive:true});
  window.addEventListener('resize',update);update();
})();
// 確認事項へのリンク:折りたたみの中にある項目を開いてから移動
function openTarget(){const el=location.hash&&document.getElementById(decodeURIComponent(location.hash.slice(1)));if(!el)return;let d=el.closest('details');while(d){d.open=true;d=d.parentElement&&d.parentElement.closest('details');}el.scrollIntoView({block:'center'});}
window.addEventListener('hashchange',openTarget);openTarget();
// ビューア
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
