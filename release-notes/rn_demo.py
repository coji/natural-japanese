"""実演の部品(数字のタイル、工程の横並び、字数の棒、構成の図、主な変更、左右に並べて読む)の CSS と JS。
値は rn_style.py と同じ DADS のトークンを使う。"""

CSS2 = """
.eye{margin:0 0 calc(8 / 16 * 1rem);font-weight:bold;color:var(--color-key-900)}
/* 数字のタイル */
.tiles{display:grid;grid-template-columns:1fr;gap:calc(16 / 16 * 1rem);margin:calc(16 / 16 * 1rem) 0 calc(24 / 16 * 1rem)}
@media (min-width:48rem){.tiles{grid-template-columns:repeat(2,1fr)}}
@media (min-width:60rem){.tiles{grid-template-columns:repeat(4,1fr)}}
.tile{border:1px solid var(--color-neutral-solid-gray-420);border-radius:calc(8 / 16 * 1rem);padding:calc(16 / 16 * 1rem)}
.tile .l{margin:0 0 calc(8 / 16 * 1rem);font-weight:bold}
.tile .v{font-weight:bold;font-size:calc(32 / 16 * 1rem);line-height:1.5;letter-spacing:.01em;color:var(--color-key-900);font-variant-numeric:tabular-nums}
@media (min-width:48rem){.tile .v{font-size:calc(36 / 16 * 1rem);line-height:1.4}}
.tile .v small{font-size:calc(16 / 16 * 1rem);font-weight:bold;color:var(--color-neutral-solid-gray-800);margin-left:calc(6 / 16 * 1rem)}
.tile .d{margin:calc(4 / 16 * 1rem) 0 0}
/* 工程の横並び */
.flow{list-style:none;margin:calc(16 / 16 * 1rem) 0 calc(24 / 16 * 1rem);padding:calc(16 / 16 * 1rem) 0 0;border-top:calc(4 / 16 * 1rem) solid var(--color-key-900);display:grid;grid-template-columns:1fr;gap:calc(12 / 16 * 1rem)}
@media (min-width:48rem){.flow{grid-template-columns:repeat(3,1fr);gap:calc(16 / 16 * 1rem)}}
@media (min-width:75rem){.flow{grid-template-columns:repeat(6,1fr)}}
.flow li{position:relative;padding-right:calc(20 / 16 * 1rem)}
.flow li b{display:block;margin-bottom:calc(4 / 16 * 1rem)}
.flow li .chip{min-height:calc(24 / 16 * 1rem);padding:calc(1 / 16 * 1rem) calc(6 / 16 * 1rem);margin-left:calc(4 / 16 * 1rem);font-size:calc(14 / 16 * 1rem)}
@media (min-width:75rem){.flow li+li::before{content:"";position:absolute;left:calc(-14 / 16 * 1rem);top:calc(6 / 16 * 1rem);width:calc(8 / 16 * 1rem);height:calc(8 / 16 * 1rem);border-top:2px solid var(--color-neutral-solid-gray-536);border-right:2px solid var(--color-neutral-solid-gray-536);transform:rotate(45deg)}}
.twoc{display:grid;grid-template-columns:1fr;gap:calc(24 / 16 * 1rem)}
@media (min-width:60rem){.twoc{grid-template-columns:1fr 1fr;gap:calc(32 / 16 * 1rem)}}
.twoc h4{margin-top:0}
.twoc>div{min-width:0}
/* 字数の棒 */
.cbars{display:grid;gap:calc(8 / 16 * 1rem)}
.bar{display:grid;grid-template-columns:minmax(5em,9em) minmax(4em,1fr) 4.5em;align-items:center;gap:calc(8 / 16 * 1rem)}
.bar .bl{font-size:calc(16 / 16 * 1rem)}
.bar .tr{display:block;height:calc(20 / 16 * 1rem);background:var(--color-neutral-solid-gray-50);border-radius:calc(4 / 16 * 1rem);overflow:hidden}
.bar .f{display:block;height:100%;background:var(--color-key-400)}
.bar .f.k{background:var(--color-key-900)}
.bar .bv{text-align:right;font-variant-numeric:tabular-nums}
table.tbl caption{text-align:left;font-weight:bold;padding:calc(8 / 16 * 1rem) 0}
/* 主な変更 */
.changes{list-style:none;margin:calc(16 / 16 * 1rem) 0 calc(24 / 16 * 1rem);padding:0;display:grid;grid-template-columns:1fr;gap:0}
@media (min-width:60rem){.changes{grid-template-columns:1fr 1fr;column-gap:calc(48 / 16 * 1rem)}}
.chg{appearance:none;background:none;border:0;border-bottom:1px solid var(--color-neutral-solid-gray-420);width:100%;text-align:left;padding:calc(12 / 16 * 1rem) 0;display:grid;grid-template-columns:auto 10em 1fr;gap:calc(12 / 16 * 1rem);align-items:start;font:inherit;color:inherit;cursor:pointer}
.chg .num{display:inline-grid;place-items:center;width:calc(28 / 16 * 1rem);height:calc(28 / 16 * 1rem);border-radius:calc(624.9375rem);background:var(--color-key-900);color:var(--color-neutral-white);font-weight:bold;font-variant-numeric:tabular-nums}
@media (hover:hover){.chg:hover b{text-decoration:underline;text-underline-offset:calc(3 / 16 * 1rem)}}
/* 左右に並べて読む */
.viewer{display:grid;grid-template-columns:1fr;gap:calc(16 / 16 * 1rem)}
@media (min-width:48rem){.viewer{grid-template-columns:1fr 1fr}}
.pane .cap .ln{font-weight:normal;margin-left:calc(8 / 16 * 1rem)}
.doc mark.chg-b{background:none;box-shadow:none;text-decoration:underline dashed;text-decoration-color:var(--color-neutral-solid-gray-536);text-decoration-thickness:2px;text-underline-offset:calc(3 / 16 * 1rem)}
.doc mark.chg-a{background:none;box-shadow:none;text-decoration:underline solid;text-decoration-color:var(--color-key-900);text-decoration-thickness:2px;text-underline-offset:calc(3 / 16 * 1rem)}
.doc mark.on{background:var(--color-primitive-yellow-300)}
.map .mv.dashed{stroke:var(--color-neutral-solid-gray-420);stroke-dasharray:6 5}
.map .dst.body .mr{fill:var(--color-key-50);stroke:var(--color-key-900);stroke-width:1.5}
.map .dst.app .mr{fill:var(--color-neutral-white);stroke:var(--color-key-900);stroke-dasharray:4 3}
.map .ml{font-weight:bold}
"""

JS2 = r"""
// 左右に並べて読む: 文書ごとに、右の文書の切り替え、節の対応でのスクロール同期、主な変更の下線と移動
(function(){
  const views=[...document.querySelectorAll('.viewer[data-doc]')];
  const caps={after:'決裁者の目で見て直した後',short:'もっと端的にした後',rebuild:'構成から組み直した後'};
  views.forEach(v=>{
    const key=v.dataset.doc, maps=JSON.parse(v.dataset.maps), L=v.querySelector('.doc.L'), R=v.querySelector('.doc.R'), cap=v.querySelector('.R-cap');
    const seg=v.previousElementSibling;
    function load(d,k){d.replaceChildren(document.getElementById('t-'+key+'-'+k).content.cloneNode(true));d.dataset.key=k;d.scrollTop=0;}
    function mark(d,texts,cls){texts.forEach(t=>{const walker=document.createTreeWalker(d,NodeFilter.SHOW_TEXT);let n;while((n=walker.nextNode())){const i=n.nodeValue.indexOf(t);if(i>=0){const r=document.createRange();r.setStart(n,i);r.setEnd(n,i+t.length);const m=document.createElement('mark');m.className=cls;m.dataset.t=t;r.surroundContents(m);return;}}});}
    const chgs=[...document.querySelectorAll('.chg[data-doc="'+key+'"]')];
    function markAll(){mark(L,chgs.map(b=>b.dataset.b),'chg-b');mark(R,chgs.map(b=>b.dataset.a),'chg-a');}
    load(L,'before');load(R,'after');markAll();
    let right='after';
    seg.querySelectorAll('button[data-r]').forEach(b=>b.addEventListener('click',()=>{right=b.dataset.r;seg.querySelectorAll('button').forEach(x=>x.setAttribute('aria-pressed',x===b));load(R,right);cap.textContent=caps[right];markAll();}));
    // 節の対応でスクロール同期
    let lock=false;
    function heads(d){return [...d.querySelectorAll('article h2')];}
    function sync(from,to,map){if(lock)return;const hs=heads(from);const top=from.getBoundingClientRect().top;let i=-1;for(let k=0;k<hs.length;k++){if(hs[k].getBoundingClientRect().top-top<=8)i=k;}
      if(i<0){lock=true;to.scrollTop=0;requestAnimationFrame(()=>lock=false);return;}
      const j=map[i];if(j==null||j<0)return;const th=heads(to)[j];if(!th)return;lock=true;to.scrollTop=th.offsetTop-to.querySelector('article').offsetTop;requestAnimationFrame(()=>lock=false);}
    function inv(map,n){const m=new Array(n).fill(-1);map.forEach((j,i)=>{if(j>=0&&m[j]<0)m[j]=i;});return m;}
    L.addEventListener('scroll',()=>sync(L,R,maps[right]),{passive:true});
    R.addEventListener('scroll',()=>sync(R,L,inv(maps[right],heads(R).length)),{passive:true});
    // 主な変更を押すと移動
    chgs.forEach(b=>b.addEventListener('click',()=>{v.scrollIntoView({block:'start'});const mb=[...L.querySelectorAll('mark.chg-b')].find(m=>m.dataset.t===b.dataset.b);const ma=[...R.querySelectorAll('mark.chg-a')].find(m=>m.dataset.t===b.dataset.a);
      document.querySelectorAll('.doc mark.on').forEach(m=>m.classList.remove('on'));
      lock=true;if(mb){mb.classList.add('on');L.scrollTop=mb.offsetTop-L.querySelector('article').offsetTop-40;}if(ma){ma.classList.add('on');R.scrollTop=ma.offsetTop-R.querySelector('article').offsetTop-40;}setTimeout(()=>lock=false,50);}));
  });
})();
"""
