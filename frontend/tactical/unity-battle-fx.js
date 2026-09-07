/* Unity-authored sprites over the browser board. Frozen outcomes remain authoritative. */
(function(root){
'use strict';
const clamp=x=>Math.max(0,Math.min(1,x));
const travel=t=>{const q=clamp((t-.2)/.42);return q*q*(3-2*q);};
const angle=facing=>({e:0,s:Math.PI/2,w:Math.PI,n:-Math.PI/2})[facing]||0;
const center=p=>({x:p.x*100+50,y:p.y*100+50});
function profile(o){
 if(o.effect)return o.effect;
 if(o.visual_effect?.family)return null;
 // Neutral energy has its own procedural geometry, never a borrowed Rasengan.
 if(o.element==='energy')return null;
 if(o.mode==='sweep')return {asset:'clone-barrage',delivery:'area',scale:1};
 const support=o.visual==='barrier'?'chakra-guard':o.visual==='heal'?'healing':o.visual==='binding'?(o.element==='wood'?'wood-bind':o.element==='shadow'?'shadow-bind':'water-prison'):null;
 if(support)return {asset:support,delivery:o.shape==='self'?'self':'target',scale:1};
 const asset={fire:['line','cone','wave'].includes(o.shape)?'fire-breath':'fireball',water:'water-wave',lightning:'lightning-bolt',wind:'wind-blade',earth:'earth-spikes',sand:'sand-wave',wood:'wood-bind',shadow:'shadow-bind',spirit:'rasengan',physical:o.mode==='kunai'?'kunai':'taijutsu-hit',impact:o.mode==='kunai'?'kunai':'taijutsu-hit'}[o.element];
 return asset?{asset,delivery:o.shape==='self'?'self':o.shape==='line'?'line':['wave','cone','pulse','ring'].includes(o.shape)?'area':o.shape==='single'&&asset==='taijutsu-hit'?'contact':'projectile',scale:1}:null;
}
function placement(o,t){const start=center(o.origin),end=center(o.aim||o.origin),q=travel(t);return {start,end,q,point:{x:start.x+(end.x-start.x)*q,y:start.y+(end.y-start.y)*q}};}
class AtlasCache{
 constructor(fetcher=(...args)=>fetch(...args),decoder=(...args)=>createImageBitmap(...args)){this.fetcher=fetcher;this.decoder=decoder;this.items=new Map();this.manifest=null;}
 async json(){if(!this.manifest){const res=await this.fetcher('../assets/unity-attack-library/manifest.json',{cache:'no-store',signal:AbortSignal.timeout(8000)});if(!res.ok)throw Error('Unity library manifest unavailable');const m=await res.json();if(!m.renderer.startsWith('Unity ')||m.frameSize!==256||m.frames!==48||m.columns!==8||m.rows!==6||!Array.isArray(m.effects))throw Error('Unexpected Unity library format');this.manifest=m;}return this.manifest;}
 async get(id){if(this.items.has(id)){const hit=this.items.get(id);this.items.delete(id);this.items.set(id,hit);return hit;}
  const m=await this.json(),meta=m.effects.find(e=>e.id===id);if(!meta)throw Error('No Unity asset for '+id);
  if(!/^[a-z0-9-]+$/.test(id))throw Error('Invalid effect asset identifier');
  const response=await this.fetcher('../assets/unity-attack-library/'+id+'.png?v='+m.revision,{signal:AbortSignal.timeout(8000)});if(!response.ok)throw Error('Unity effect download unavailable');
  const image=await this.decoder(await response.blob());if(image.width!==2048||image.height!==1536){image.close();throw Error('Incomplete Unity sprite atlas');}
  const entry={image,meta,manifest:m};this.items.set(id,entry);
  while(this.items.size>2){const oldest=this.items.keys().next().value;this.items.get(oldest).image.close();this.items.delete(oldest);}
  return entry;
 }
 clear(){for(const entry of this.items.values())entry.image.close();this.items.clear();}
}
const Base=root.BattleFX||class{};
class UnityBattleFX extends Base{
 constructor(canvas,groundCanvas){super(canvas,groundCanvas);this.cache=new AtlasCache();this.active=null;this.request=0;this.portraits=new Map();}
 cancel(){this.request=(this.request||0)+1;super.cancel();}
 async loadPortraits(o){for(const art of (o.art||[]).filter(a=>a.id!=='you').slice(0,2)){
  const p=art.portrait;if(!p?.url||this.portraits.has(p.url))continue;
  const url=new URL(p.url,location.href);if(url.origin!==location.origin||!url.pathname.includes('/assets/'))continue;
  try{const response=await fetch(url,{signal:AbortSignal.timeout(4000)});if(response.ok){const img=await createImageBitmap(await response.blob());this.portraits.set(p.url,img);}}catch{}
  while(this.portraits.size>2){const key=this.portraits.keys().next().value;this.portraits.get(key).close();this.portraits.delete(key);}
 }}
 async play(outcome,options={}){
  this.cancel();const request=this.request,spec=profile(outcome);this.active=null;this.canvas.dataset.renderer='browser';
  if(spec&&!this.reduced())try{this.active=await this.cache.get(spec.asset);if(spec.asset==='clone-barrage')await this.loadPortraits(outcome);this.canvas.dataset.renderer='Unity';delete this.canvas.dataset.assetError;delete this.canvas.dataset.assetFailure;}catch(error){this.canvas.dataset.assetFailure=error.name+': '+error.message;this.canvas.dataset.assetError='Unity asset unavailable; browser effect used. Combat result unchanged.';}
  if(request!==this.request||document.hidden){this.active=null;options.onImpact?.();return;}
  this.durationMs=this.active?2000:1750;this.impactTime=this.active ? .62 : .48;
  try{await super.play(outcome,options);}finally{this.active=null;}
 }
 stamp(ctx,entry,t,p,width,rotation=0){const m=entry.manifest,f=Math.min(m.frames-1,Math.floor(clamp(t)*(m.frames-1)));ctx.save();ctx.translate(p.x,p.y);ctx.rotate(rotation);ctx.drawImage(entry.image,(f%m.columns)*m.frameSize,Math.floor(f/m.columns)*m.frameSize,m.frameSize,m.frameSize,-width/2,-width/2,width,width);ctx.restore();}
 cloneImages(ctx,o,t){if(t<.2||t>.72)return;const q=travel(t),p=placement(o,t);for(const [i,a] of (o.art||[]).filter(a=>a.id!=='you'&&a.id.match(/^(a|b)$/)).entries()){
  const art=a.portrait,img=this.portraits.get(art?.url);if(!img)continue;const atlas=art.atlas||{columns:1,rows:1,column:0,row:0},sw=img.width/atlas.columns,sh=img.height/atlas.rows;
  const x=p.start.x+(p.end.x-p.start.x)*q+(i%2?1:-1)*Math.sin(q*Math.PI)*40,y=p.start.y+(p.end.y-p.start.y)*q-16;
  ctx.save();ctx.globalAlpha=Math.sin(clamp((t-.2)/.52)*Math.PI)*.8;ctx.drawImage(img,atlas.column*sw,atlas.row*sh,sw,sh,x-20,y-28,40,48);ctx.restore();
 }}
 draw(o,t,reduced){
  if(!this.active||reduced)return super.draw(o,t,reduced);
  this.clear();if(this.ground)root.GroundAOE.draw(this.ground,o,t,{impact:.62,end:.96,reduced});
  const c=this.ctx,spec=profile(o),entry=this.active,{start,end,q,point}=placement(o,t),width=entry.meta.worldSize*100*(spec.scale||1);
  c.save();try{
   if(spec.delivery==='area'){
    this.cellClip(o.cells);
    if(['shuriken','kunai','fireball','clone-barrage'].includes(spec.asset)){for(const cell of o.cells){const [x,y]=cell.split(',').map(Number);this.stamp(c,entry,t,center({x,y}),Math.min(width,190),angle(o.facing));}}
    else{const coords=o.cells.map(v=>v.split(',').map(Number)),xs=coords.map(v=>v[0]),ys=coords.map(v=>v[1]);if(coords.length){const x=(Math.min(...xs)+Math.max(...xs)+1)*50,y=(Math.min(...ys)+Math.max(...ys)+1)*50,span=(Math.max(Math.max(...xs)-Math.min(...xs),Math.max(...ys)-Math.min(...ys))+1)*100;this.stamp(c,entry,t,{x,y},Math.max(160,span*1.55),angle(o.facing));}}
   }else if(spec.delivery==='line'){
    const [dx,dy]=({n:[0,-1],e:[1,0],s:[0,1],w:[-1,0]})[o.facing]||[1,0];
    const length=Math.max(1,...o.cells.map(k=>{const[x,y]=k.split(',').map(Number);return (x-o.origin.x)*dx+(y-o.origin.y)*dy;}))*100;
    this.stamp(c,entry,t,{x:start.x+dx*length*q/2,y:start.y+dy*length*q/2},Math.max(100,length*q+90)*(spec.asset==='water-dragon'?1.68:1.25),angle(o.facing));
   }else if(spec.delivery==='self')this.stamp(c,entry,t,start,width);
   else if(spec.delivery==='target')this.stamp(c,entry,t,end,width);
   else this.stamp(c,entry,t,point,width,Math.atan2(end.y-start.y,end.x-start.x));
   if(spec.asset==='clone-barrage')this.cloneImages(c,o,t);
  }finally{c.restore();}
  this.labels(o,clamp((t-.62)*4),clamp((1-t)*5));
 }
}
const api={profile,placement,AtlasCache,UnityBattleFX};if(typeof module==='object'&&module.exports)module.exports=api;else{root.UnityBattleFX=UnityBattleFX;root.UnityEffects=api;}
})(typeof window==='object'?window:globalThis);
