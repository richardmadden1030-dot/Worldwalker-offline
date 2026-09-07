/* Political atlas: one projection for coast, hex ownership, routes and pieces.
   SVG stays sharp at every zoom; merged edge paths remove same-owner borders. */
window.WorldAtlas = (() => {
  const ns = 'http://www.w3.org/2000/svg';
  const views = new Map(), histories = new Map();
  let active = null, observer = null;
  const escape = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const palette = ['#81a56d','#d5ad68','#74aab2','#c58678','#ae99b7','#c3bc82','#8babc2','#b49772','#90bda2','#d8b29a','#a9b0ca','#c3a652'];
  const fixed = {'Konohagakure':'#76a36a','Sunagakure':'#d8b36e','Iwagakure':'#b38361','Kumogakure':'#d8c479','Kirigakure':'#7bacbb','Amegakure':'#9586a5','Iron Country':'#bfc5c8','Japan':'#95b1a1','World Government':'#adc3ce','Saharan Empire':'#b4827b','Eternal Kingdom':'#83a8be'};
  Object.assign(fixed, {'Land of Fire':'#76a36a','Land of Wind':'#d8b36e','Land of Earth':'#b38361','Land of Lightning':'#d8c479','Land of Water':'#7bacbb','Land of Rain':'#9586a5','Jura Forest communities':'#84a56e','Jura Tempest Federation':'#6dad98','Hollow dominions':'#b8b6a5','Soul Society':'#c6c5af','Belto Kingdom':'#c3bc82'});
  function hash(s) { let h=2166136261; for(const c of s) h=Math.imul(h^c.charCodeAt(0),16777619); return h>>>0; }
  function color(name) { return fixed[name] || palette[hash(String(name))%palette.length]; }
  function vertices(c) {
    const r=1.5/Math.sqrt(3);
    return Array.from({length:6},(_,i)=>[+(c.x+r*Math.cos((30+i*60)*Math.PI/180)).toFixed(2),+(c.y+r*Math.sin((30+i*60)*Math.PI/180)).toFixed(2)]);
  }
  const point = p => `${(p[0]*16).toFixed(2)},${(p[1]*10).toFixed(2)}`;
  const path = poly => 'M'+poly.map(point).join('L')+'Z';
  const edgeKey = (a,b) => [a.join(','),b.join(',')].sort().join('|');
  function render(plane, atlas, key) {
    const diagram = String(atlas.context?.extent || '').includes('diagram');
    const previous=histories.get(key), owners=new Map(), edges=new Map(), changed=[];
    const ownerAt=new Map();
    for(const c of atlas.cells) {
      const poly=vertices(c), record=owners.get(c.owner)||{paths:[],cells:[]};
      record.paths.push(path(poly)); record.cells.push(c); owners.set(c.owner,record); ownerAt.set(c.id,c.owner);
      if(previous && previous.get(c.id)!==c.owner) changed.push(path(poly));
      for(let i=0;i<6;i++) {
        const a=poly[i],b=poly[(i+1)%6], id=edgeKey(a,b);
        if(edges.has(id)) { const e=edges.get(id); e.internal=e.owner===c.owner; }
        else edges.set(id,{a,b,owner:c.owner,internal:false});
      }
    }
    histories.set(key,ownerAt);
    const coast=atlas.land.map(l=>path(l.polygon)).join('');
    const borders=[...edges.values()].filter(e=>!e.internal).map(e=>'M'+point(e.a)+'L'+point(e.b)).join('');
    let terrain='';
    let ridges='';
    for(const range of atlas.relief || []) {
      for(let i=0;i<range.length-1;i++) {
        const a=range[i],b=range[i+1],steps=Math.ceil(Math.hypot((a[0]-b[0])*1.6,a[1]-b[1])*1.8);
        for(let n=0;n<steps;n++) {
          const x=(a[0]+(b[0]-a[0])*n/steps)*16+(n%3-1)*9,y=(a[1]+(b[1]-a[1])*n/steps)*10;
          const h=11+(n*7%12),w=10+(n*3%8);
          ridges+=`<path d="M${x-w},${y+7}l${w},-${h} ${w+5},${h}Z" fill="#435a4e" fill-opacity=".28"/><path d="M${x-w},${y+7}l${w},-${h} -2,${h-4}Z" fill="#f0edd0" fill-opacity=".4"/><path d="M${x-w},${y+7}l${w},-${h} ${w+5},${h}" fill="none" stroke="#3a5144" stroke-opacity=".38" stroke-width="1"/>`;
        }
      }
    }
    // Deterministic engraved relief. Never changes with saves, starts or zoom.
    for(const c of atlas.cells) {
      const h=hash(atlas.id+c.id), x=c.x*16, y=c.y*10;
      const ground = atlas.land[c.land]?.terrain || 'green';
      if(h%29===0) terrain+=`<path d="M${x-8},${y+4}l8,-13 9,13 -9,-6z" fill="#253b36" fill-opacity=".18" stroke="#29372d" stroke-opacity=".25" stroke-width=".7"/>`;
      else if(h%13===0 && ground==='green') terrain+=`<path d="M${x-4},${y+2}l4,-9 4,9M${x},${y+2}v3" fill="#264c3d" fill-opacity=".2" stroke="#294a37" stroke-opacity=".25" stroke-width=".6"/>`;
      else if(h%7===0) terrain+=`<path d="M${x-8},${y}q6,-3 12,0" fill="none" stroke="#283f32" stroke-opacity=".13" stroke-width=".8"/>`;
    }
    const structures=(atlas.structures || []).map(s=>s.kind==='enclosure'
      ? `<ellipse cx="${s.x*16}" cy="${s.y*10}" rx="${s.rx*16}" ry="${s.ry*10}" fill="#e1d9bd" fill-opacity=".15" stroke="#363632" stroke-width="8"/><ellipse cx="${s.x*16}" cy="${s.y*10}" rx="${s.rx*16-8}" ry="${s.ry*10-8}" fill="none" stroke="#e8dfbe" stroke-width="3"/>`
      : s.kind==='river' ? `<path d="M${s.points.map(point).join('L')}" fill="none" stroke="#5598ab" stroke-width="14" stroke-linejoin="round"/>` : '').join('');
    plane.querySelector('#map-territory-canvas')?.remove();
    plane.querySelector('#map-faction-labels')?.remove();
    plane.querySelector('#map-ambient')?.remove();
    const svg=document.createElementNS(ns,'svg');
    svg.classList.add('atlas-geography'); svg.setAttribute('viewBox','0 0 1600 1000'); svg.setAttribute('aria-label',atlas.id+' political map');
    svg.innerHTML=`<defs><clipPath id="atlas-land-clip"><path d="${coast}"/></clipPath><pattern id="atlas-sea" width="100" height="80" patternUnits="userSpaceOnUse"><path d="M0,40h100M50,0v80" stroke="#acd3d4" stroke-opacity=".055" fill="none"/><path d="M12,16q6,-3 12,0t12,0M65,61q6,-3 12,0t12,0" fill="none" stroke="#bed8d6" stroke-opacity=".12"/></pattern><linearGradient id="atlas-ocean" x2="0" y2="1"><stop stop-color="#17343b"/><stop offset="1" stop-color="#294d53"/></linearGradient><pattern id="atlas-paper" width="7" height="7" patternUnits="userSpaceOnUse"><path d="M0,1h7M0,4h7" stroke="#fff" stroke-opacity=".04"/></pattern></defs>
      <rect width="1600" height="1000" fill="${diagram?'#242b32':'url(#atlas-ocean)'}"/><rect width="1600" height="1000" fill="${diagram?'none':'url(#atlas-sea)'}"/>
      <path d="${coast}" fill="none" stroke="#739b96" stroke-opacity=".15" stroke-width="22"/><path d="${coast}" fill="none" stroke="#91b3a5" stroke-opacity=".3" stroke-width="9"/>
      <g clip-path="url(#atlas-land-clip)"><path d="${coast}" fill="#a9ac80"/>${[...owners].map(([name,o])=>`<path class="atlas-country" data-owner="${escape(name)}" d="${o.paths.join('')}" fill="${color(name)}" stroke="${color(name)}" stroke-width=".45"><title>${escape(name)}</title></path>`).join('')}${terrain}${ridges}<path d="${borders}" fill="none" stroke="#f6e7b4" stroke-opacity=".62" stroke-width="3.4"/><path d="${borders}" fill="none" stroke="#343e36" stroke-opacity=".85" stroke-width="1.3"/><rect width="1600" height="1000" fill="url(#atlas-paper)"/>${changed.length?`<path class="atlas-control-change" d="${changed.join('')}" fill="#fff2b7"/>`:''}</g>
      <path d="${coast}" fill="none" stroke="#162f32" stroke-width="2.2"/>
      <g fill="#b6ccbf" fill-opacity=".65" font-family="Georgia,serif" font-size="17" letter-spacing="4" text-anchor="middle">${atlas.labels.map(([s,x,y])=>`<text x="${x*16}" y="${y*10}">${escape(s)}</text>`).join('')}</g>
      <g transform="translate(1450 870)" stroke="#b7c8b1" fill="none" opacity=".6"><circle r="32"/><path d="M0,-45V45M-45,0H45M-15,20L0,-37 15,20 0,12Z"/><text y="-52" text-anchor="middle" stroke="none" fill="#ced9c6" font-family="Georgia" font-size="18">N</text></g>`;
    plane.prepend(svg); plane.classList.add('atlas-plane');
    if (structures) {
      const features=document.createElementNS(ns,'g');
      features.setAttribute('clip-path','url(#atlas-land-clip)');
      features.innerHTML=structures;
      svg.append(features);
    }
    const labelLayer=document.createElement('div'); labelLayer.className='atlas-polity-labels';
    for(const [name,o] of owners) {
      if(o.cells.length<20) continue;
      const cx=o.cells.reduce((a,c)=>a+c.x,0)/o.cells.length,cy=o.cells.reduce((a,c)=>a+c.y,0)/o.cells.length;
      // Snap centroid to owned land rather than placing the name in the sea.
      const c=o.cells.reduce((a,c)=>(c.x-cx)**2+(c.y-cy)**2<(a.x-cx)**2+(a.y-cy)**2?c:a);
      const label=document.createElement('span'); label.className='atlas-polity-label'; label.textContent=name; label.style.left=c.x+'%';label.style.top=c.y+'%';label.title=name;label.dataset.weight=o.cells.length; labelLayer.append(label);
    }
    plane.append(labelLayer);
    return {owners:[...owners.keys()],changed:changed.length};
  }
  let bindingController;
  function usableCamera(a) {
    return a && [a.w, a.h, a.wrap.clientWidth, a.wrap.clientHeight].every(n => Number.isFinite(n) && n > 0);
  }
  function bind(wrap,plane,key,onZoom=()=>{}) {
    observer?.disconnect();
    bindingController?.abort();
    bindingController = new AbortController();
    const listen = (type, fn, options = {}) => wrap.addEventListener(type, fn, { ...options, signal: bindingController.signal });
    const candidate=views.get(key);
    const saved=candidate && [candidate.z,candidate.px,candidate.py].every(Number.isFinite)
      ? {...candidate,z:Math.max(1,Math.min(8,candidate.z))} : {z:1,px:.5,py:.5};
    active={wrap,plane,key,z:saved.z,px:saved.px,py:saved.py,w:0,h:0,onZoom};
    const pointers=new Map(); let last=null, moved=false;
    function measure() {
      if (active?.wrap !== wrap || !wrap.clientWidth || !wrap.clientHeight) return;
      const s=Math.min(wrap.clientWidth/1600,wrap.clientHeight/1000);
      active.w=1600*s;active.h=1000*s;
      plane.style.width=active.w+'px';plane.style.height=active.h+'px';
      apply();
    }
    function pose(){ const p=[...pointers.values()];return p.length>1?{x:(p[0].x+p[1].x)/2,y:(p[0].y+p[1].y)/2,d:Math.hypot(p[0].x-p[1].x,p[0].y-p[1].y)}:p[0]; }
    listen('pointerdown',e=>{if(e.target.closest('.map-zoom-controls'))return; pointers.set(e.pointerId,{x:e.clientX,y:e.clientY,d:0});last=pose();moved=false;});
    listen('pointermove',e=>{
      if(!pointers.has(e.pointerId) || !usableCamera(active))return;
      pointers.set(e.pointerId,{x:e.clientX,y:e.clientY,d:0});const p=pose();
      if(last){const dx=p.x-last.x,dy=p.y-last.y;
        if(Math.abs(dx)+Math.abs(dy)>2||p.d) {moved=true;wrap.setPointerCapture(e.pointerId);}
        active.px-=dx/(active.w*active.z);active.py-=dy/(active.h*active.z);
        if(p.d&&last.d)active.z=Math.max(1,Math.min(8,active.z*p.d/last.d));apply();}
      last=p;
    });
    const end=e=>{pointers.delete(e.pointerId);last=pose();};
    listen('pointerup',end);listen('pointercancel',end);
    listen('click',e=>{if(moved){e.preventDefault();e.stopImmediatePropagation();moved=false;}},{capture:true});
    listen('wheel',e=>{e.preventDefault();const r=wrap.getBoundingClientRect();zoom(e.deltaY<0?1.15:1/1.15,e.clientX-r.left,e.clientY-r.top);},{passive:false});
    observer=new ResizeObserver(measure);observer.observe(wrap);measure();
  }
  function apply(){
    if(!usableCamera(active))return;
    const a=active,w=a.wrap.clientWidth,h=a.wrap.clientHeight;
    if (![a.z,a.px,a.py].every(Number.isFinite)) Object.assign(a,{z:1,px:.5,py:.5});
    const bx=Math.min(.5,w/(2*a.w*a.z)),by=Math.min(.5,h/(2*a.h*a.z));
    a.px=Math.max(bx,Math.min(1-bx,a.px));a.py=Math.max(by,Math.min(1-by,a.py));
    a.plane.style.transform=`translate(${w/2-a.px*a.w*a.z}px,${h/2-a.py*a.h*a.z}px) scale(${a.z})`;
    a.plane.style.setProperty('--atlas-inverse',1/a.z);
    views.set(a.key,{z:a.z,px:a.px,py:a.py});a.onZoom(a.z);labels();
  }
  function labels(){
    const a=active;if(!a)return;
    const placed=[];
    const viewport=a.wrap.getBoundingClientRect();
    const landmarks=[...a.plane.querySelectorAll('.map-node .map-label')].sort((x,y)=>Number(y.parentElement.classList.contains('here'))-Number(x.parentElement.classList.contains('here')));
    const countries=[...a.plane.querySelectorAll('.atlas-polity-label')].sort((x,y)=>Number(y.dataset.weight)-Number(x.dataset.weight));
    const labels=a.z<1.8 ? [...landmarks.filter(x=>x.parentElement.classList.contains('here')), ...countries, ...landmarks.filter(x=>!x.parentElement.classList.contains('here'))] : [...landmarks,...countries];
    for(const el of labels){
      el.classList.remove('atlas-collided');
      const hidden=getComputedStyle(el.parentElement).opacity==='0';
      if(hidden)continue;
      const r=el.getBoundingClientRect(),v=viewport;
      const overlap=placed.some(p=>r.left<p.right+5&&r.right>p.left-5&&r.top<p.bottom+4&&r.bottom>p.top-4);
      if(overlap||r.left<v.left||r.right>v.right||r.top<v.top||r.bottom>v.bottom)el.classList.add('atlas-collided');else placed.push(r);
    }
  }
  function zoom(factor,x,y){if(!usableCamera(active)||!Number.isFinite(factor)||factor<=0)return;const a=active,old=a.z,next=Math.max(1,Math.min(8,old*factor));x??=a.wrap.clientWidth/2;y??=a.wrap.clientHeight/2;a.px+=(x-a.wrap.clientWidth/2)/a.w*(1/old-1/next);a.py+=(y-a.wrap.clientHeight/2)/a.h*(1/old-1/next);a.z=next;apply();}
  function focus(x,y){if(!active||![x,y].every(Number.isFinite))return;active.z=Math.max(2.4,active.z);active.px=x/100;active.py=y/100;apply();}
  function reset(){if(!active)return;Object.assign(active,{z:1,px:.5,py:.5});apply();}
  return {render,bind,color,zoom,focus,reset,labels,refresh:apply};
})();

// Optional workspace presentation, loaded independently of the atlas renderer.
// This entry point is already shipped by both desktop and browser shells.
(() => {
  if (!document.querySelector('.col-center #living-map-main') || document.getElementById('workspace-tabs-script')) return;
  const script = document.createElement('script');
  script.id = 'workspace-tabs-script';
  script.src = '/js/workspace-tabs.js?v=3.64.0-membership-truth-1';
  script.async = true;
  script.addEventListener('error', () => {
    script.remove();
    console.warn('Workspace tabs could not load; retaining the original layout.');
  }, { once: true });
  document.head.append(script);
})();
