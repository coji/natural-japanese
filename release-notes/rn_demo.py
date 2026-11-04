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
.twoc h4{margin-top:0}
.twoc>div{min-width:0}
/* 字数の棒 */
.cbars{display:grid;gap:calc(8 / 16 * 1rem)}
.bar{display:grid;grid-template-columns:minmax(5em,11em) minmax(4em,1fr) 4.5em;align-items:center;gap:calc(8 / 16 * 1rem)}
.bar .bl{font-size:calc(16 / 16 * 1rem)}
.bar .tr{display:block;height:calc(20 / 16 * 1rem);background:var(--color-neutral-solid-gray-50);border-radius:calc(4 / 16 * 1rem);overflow:hidden}
.bar .f{display:block;height:100%;background:var(--color-key-400)}
.bar .f.k{background:var(--color-key-900)}
.bar .bv{text-align:right;font-variant-numeric:tabular-nums}
table.tbl caption{text-align:left;font-weight:bold;padding:calc(8 / 16 * 1rem) 0}
/* 主な変更 */
.changes{list-style:none;margin:calc(16 / 16 * 1rem) 0 calc(24 / 16 * 1rem);padding:0;display:grid;grid-template-columns:1fr;gap:0}
.chg{appearance:none;background:none;border:0;border-bottom:1px solid var(--color-neutral-solid-gray-420);width:100%;text-align:left;padding:calc(12 / 16 * 1rem) 0;display:grid;grid-template-columns:auto 10em 1fr;gap:calc(12 / 16 * 1rem);align-items:start;font:inherit;color:inherit;cursor:pointer}
.chg .num{display:inline-grid;place-items:center;width:calc(28 / 16 * 1rem);height:calc(28 / 16 * 1rem);border-radius:calc(624.9375rem);background:var(--color-key-900);color:var(--color-neutral-white);font-weight:bold;font-variant-numeric:tabular-nums}
@media (hover:hover){.chg:hover b{text-decoration:underline;text-underline-offset:calc(3 / 16 * 1rem)}}
/* 左右に並べて読む */
.viewer{display:grid;grid-template-columns:1fr;gap:calc(16 / 16 * 1rem)}
@media (min-width:48rem){.viewer{grid-template-columns:1fr 1fr}}
.pane .cap .ln{font-weight:normal;margin-left:calc(8 / 16 * 1rem)}
.doc td:first-child,.doc th:first-child{min-width:4.5em}
.doc table+hr{display:none}
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
  views.forEach(v=>{
    const key=v.dataset.doc, maps=JSON.parse(v.dataset.maps), L=v.querySelector('.doc.L'), R=v.querySelector('.doc.R');
    function load(d,k){d.replaceChildren(document.getElementById('t-'+key+'-'+k).content.cloneNode(true));d.dataset.key=k;d.scrollTop=0;}
    function mark(d,texts,cls){texts.forEach(t=>{const walker=document.createTreeWalker(d,NodeFilter.SHOW_TEXT);let n;while((n=walker.nextNode())){const i=n.nodeValue.indexOf(t);if(i>=0){const r=document.createRange();r.setStart(n,i);r.setEnd(n,i+t.length);const m=document.createElement('mark');m.className=cls;m.dataset.t=t;r.surroundContents(m);return;}}});}
    const chgs=[...document.querySelectorAll('.chg[data-doc="'+key+'"]')];
    function markAll(){mark(L,chgs.map(b=>b.dataset.b),'chg-b');mark(R,chgs.map(b=>b.dataset.a),'chg-a');}
    load(L,'before');load(R,'after');markAll();
    const right='after';
    // 節の対応でスクロール同期。左右の見出しの対応のうち、順序を保つもの(付録へ移った節のように前後が入れ替わるものは除く)を
    // 目印にして、スクロール位置を目印のあいだで線形に補間する。自分が動かした側から返ってくる scroll イベントは、200ms のあいだ無視する
    const hold={L:0,R:0};
    function heads(d){return [...d.querySelectorAll('article h4')];}
    function pos(el,d){return el.getBoundingClientRect().top-d.getBoundingClientRect().top+d.scrollTop;}
    function lis(pairs){ // j が増える最長の並び(節の数は十数個なので O(n^2) でよい)
      const n=pairs.length, best=new Array(n).fill(1), prev=new Array(n).fill(-1); let end=0;
      for(let a=0;a<n;a++){for(let b=0;b<a;b++){if(pairs[b][1]<pairs[a][1]&&best[b]+1>best[a]){best[a]=best[b]+1;prev[a]=b;}} if(best[a]>best[end])end=a;}
      const out=[]; for(let k=end;k>=0&&n;k=prev[k]){out.unshift(pairs[k]); if(prev[k]<0)break;} return out;
    }
    function anchors(from,to,map){
      const hs=heads(from), ts=heads(to); const pairs=[]; map.forEach((j,i)=>{if(j>=0&&hs[i]&&ts[j])pairs.push([i,j]);});
      const kept=lis(pairs); const pts=[[0,0]]; kept.forEach(([i,j])=>pts.push([pos(hs[i],from),pos(ts[j],to)]));
      pts.push([from.scrollHeight-from.clientHeight, to.scrollHeight-to.clientHeight]); return pts;
    }
    function interp(pts,y){
      for(let k=1;k<pts.length;k++){const [a,ta]=pts[k-1],[b,tb]=pts[k]; if(y<=b){return b>a?ta+(y-a)/(b-a)*(tb-ta):tb;}}
      return pts[pts.length-1][1];
    }
    function sync(from,to,map,name){
      if(Date.now()<hold[name])return;
      const pts=anchors(from,to,map); let target=interp(pts,from.scrollTop);
      target=Math.max(0,Math.min(target,to.scrollHeight-to.clientHeight));
      if(Math.abs(to.scrollTop-target)<1)return;
      hold[name==='L'?'R':'L']=Date.now()+200; to.scrollTop=target;
    }
    function inv(map,n){const m=new Array(n).fill(-1);map.forEach((j,i)=>{if(j>=0&&m[j]<0)m[j]=i;});return m;}
    L.addEventListener('scroll',()=>sync(L,R,maps[right],'L'),{passive:true});
    R.addEventListener('scroll',()=>sync(R,L,inv(maps[right],heads(R).length),'R'),{passive:true});
    // 主な変更を押すと移動
    chgs.forEach(b=>b.addEventListener('click',()=>{v.scrollIntoView({block:'start'});const mb=[...L.querySelectorAll('mark.chg-b')].find(m=>m.dataset.t===b.dataset.b);const ma=[...R.querySelectorAll('mark.chg-a')].find(m=>m.dataset.t===b.dataset.a);
      document.querySelectorAll('.doc mark.on').forEach(m=>m.classList.remove('on'));
      hold.L=hold.R=Date.now()+300;if(mb){mb.classList.add('on');L.scrollTop=pos(mb,L)-40;}if(ma){ma.classList.add('on');R.scrollTop=pos(ma,R)-40;}}));
  });
})();
"""
