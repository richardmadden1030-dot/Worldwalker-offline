/* Ground-only cast receipt. The resolved cells, never the projectile art, own the area. */
(function(root){
'use strict';
const colors={fire:'#ffb348',water:'#80dff7',lightning:'#b0eaff',wind:'#c7efd7',ice:'#d3f4ff',earth:'#d9b287',sand:'#edcc87',wood:'#aad48b',metal:'#d6e1f0',poison:'#d1acef',acid:'#c9ed84',magma:'#ff9c66',light:'#ffedb0',shadow:'#b5a5e2',spirit:'#a5efff',cursed:'#bf9bf0',sound:'#a7e5e4',gravity:'#c7b3e6',blood:'#ec9ca3',barrier:'#a4f3d9'};
const clamp=x=>Math.max(0,Math.min(1,x));
colors.energy='#d3c6ff';
function geometry(outcome,{columns=8,rows=8}={}){
 const cells=[],keys=new Set(),edges=[];
 for(const key of Array.isArray(outcome?.cells)?outcome.cells:[]){
  if(typeof key!=='string'||!/^\d+,\d+$/.test(key))continue;
  const [x,y]=key.split(',').map(Number),normal=x+','+y;
  if(x>=columns||y>=rows||keys.has(normal))continue;
  keys.add(normal);cells.push({x,y});
 }
 for(const {x,y} of cells){
  if(!keys.has(x+','+(y-1)))edges.push([x,y,x+1,y]);
  if(!keys.has((x+1)+','+y))edges.push([x+1,y,x+1,y+1]);
  if(!keys.has(x+','+(y+1)))edges.push([x+1,y+1,x,y+1]);
  if(!keys.has((x-1)+','+y))edges.push([x,y+1,x,y]);
 }
 return {cells,edges};
}
function envelope(t,{impact=.48,end=.94,reduced=false}={}){
 if(!Number.isFinite(t)||!Number.isFinite(impact)||!Number.isFinite(end)||end<=impact)return 0;
 const start=impact-.035;if(t<=start||t>=end)return 0;
 // One short rise, hold, fade. No strobe, repeated pulse or permanent terrain mark.
 if(reduced)return .75;
 const rise=clamp((t-start)/.06),fade=clamp((end-t)/Math.min(.18,(end-impact)/2));
 return Math.min(rise,fade);
}
function draw(ctx,outcome,t,options={}){
 const alpha=envelope(t,options);if(!alpha)return;
 const {cells,edges}=geometry(outcome,options);if(!cells.length)return;
 const size=options.cellSize||100,color=colors[outcome.element]||'#f2d49e';
 ctx.save();
 try{
  // Clip even the thick contour inward: no light bleed onto a non-hit tile.
  ctx.beginPath();for(const {x,y} of cells)ctx.rect(x*size,y*size,size,size);ctx.clip();
  ctx.fillStyle=color;ctx.globalAlpha=alpha*.27;
  for(const {x,y} of cells)ctx.fillRect(x*size,y*size,size,size);
  ctx.globalAlpha=alpha*.35;ctx.strokeStyle=color;ctx.lineWidth=1.5;
  for(const {x,y} of cells)ctx.strokeRect(x*size+2,y*size+2,size-4,size-4);
  ctx.beginPath();for(const [x,y,ex,ey] of edges){ctx.moveTo(x*size,y*size);ctx.lineTo(ex*size,ey*size);}
  ctx.globalAlpha=alpha*.8;ctx.strokeStyle=color;ctx.lineWidth=10;ctx.lineJoin='miter';ctx.lineCap='butt';ctx.stroke();
  ctx.globalAlpha=alpha;ctx.strokeStyle='#fff3d5';ctx.lineWidth=3;ctx.stroke();
 }finally{ctx.restore();}
}
const api=Object.freeze({geometry,envelope,draw});
if(typeof module==='object'&&module.exports)module.exports=api;else root.GroundAOE=api;
})(typeof window==='object'?window:globalThis);

