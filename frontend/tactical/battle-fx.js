/* Browser-native, bounded canvas animation. Receives a frozen outcome; never changes battle state. */
(function(root){
'use strict';
const palettes={fire:['#e73e24','#ff9434','#fff0a6'],water:['#176eae','#65d3eb','#e6fdff'],binding:['#176eae','#65d3eb','#e6fdff'],lightning:['#346ec9','#8ee9ff','#f0fcff'],wind:['#75a9ad','#bbf0d8','#efffe6'],barrier:['#428d9e','#76e7d4','#defdf0'],impact:['#b66c36','#f5c976','#fff2cc']};
Object.assign(palettes,{ice:['#42738e','#b6e4eb','#ffffff'],earth:['#795739','#c6a57b','#f1d9a1'],sand:['#8e6d36','#e1c478','#fff3bc'],wood:['#42633b','#8eae6b','#e4e9b0'],metal:['#556375','#b5c3cf','#ffffff'],poison:['#5b3869','#b68ada','#ddef9a'],acid:['#49712e','#a7d753','#e6ffaa'],magma:['#562420','#ea6637','#ffce61'],light:['#a88d36','#fff09a','#ffffff'],shadow:['#393447','#8b7fba','#d3c9e9'],spirit:['#396377','#87d7e0','#ebfcff'],cursed:['#312b60','#8c66b9','#c7b3ed'],sound:['#427985','#acd9d7','#e7ffff'],gravity:['#38334a','#9d91b8','#e1d4f5'],blood:['#702d35','#c46164','#f9c6b6']});
const ease=t=>1-Math.pow(1-t,3),clamp=t=>Math.max(0,Math.min(1,t));
palettes.energy=['#635a93','#c5b5fa','#fffaff'];
class BattleFX{
 constructor(canvas,groundCanvas=null){this.canvas=canvas;this.ctx=canvas.getContext('2d');this.ground=groundCanvas?.getContext('2d');this.frame=0;this.complete=null;this.forcedReduced=false;this.media=matchMedia('(prefers-reduced-motion: reduce)');this.media.addEventListener('change',()=>this.cancel());document.addEventListener('visibilitychange',()=>{if(document.hidden)this.cancel();});}
 clear(){this.ctx.clearRect(0,0,800,800);this.ground?.clearRect(0,0,800,800);}
 reduced(){return this.forcedReduced||this.media.matches;}
 cancel(){if(this.frame)cancelAnimationFrame(this.frame);this.frame=0;this.clear();this.canvas.dataset.phase='idle';if(this.complete){const done=this.complete;this.complete=null;done();}}
 play(outcome,{onImpact=()=>{},replay=false}={}){this.cancel();let impacted=false,done=false;const impact=()=>{if(!impacted){impacted=true;onImpact();}};return new Promise(resolve=>{const finish=()=>{if(done)return;done=true;try{impact();}finally{this.clear();this.canvas.dataset.phase='idle';this.complete=null;resolve();}};this.complete=finish;this.canvas.dataset.outcome=outcome.id;this.canvas.dataset.replay=String(replay);let start=null;const duration=this.reduced()?520:(this.durationMs||1750),impactAt=this.impactTime||.48;const tick=now=>{if(start===null)start=now;const t=clamp((now-start)/duration);this.canvas.dataset.phase=t<.42?'travel':t<.82?'impact':'fade';try{this.draw(outcome,t,this.reduced());if(t>=impactAt)impact();}catch(error){this.canvas.dataset.error='Effect rendering interrupted; result preserved';this.frame=0;finish();return;}if(t<1)this.frame=requestAnimationFrame(tick);else{this.frame=0;finish();}};this.frame=requestAnimationFrame(tick);});}
 cellClip(cells){const c=this.ctx;c.beginPath();for(const cell of cells){let [x,y]=cell.split(',').map(Number);c.rect(x*100,y*100,100,100);}c.clip();}
 stroke(points,color,width){const c=this.ctx;c.beginPath();points.forEach(([x,y],i)=>i?c.lineTo(x,y):c.moveTo(x,y));c.strokeStyle=color;c.lineWidth=width;c.lineCap='round';c.lineJoin='round';c.stroke();}
 flame(x,y,r,phase,color){const c=this.ctx;c.fillStyle=color;c.beginPath();c.moveTo(x-r*.65,y+r*.5);c.bezierCurveTo(x-r,y-r*.1,x-r*.14,y-r*.6,x+r*.1*Math.sin(phase),y-r*1.45);c.bezierCurveTo(x+r*.1,y-r*.8,x+r*.62,y-r*.45,x+r*.56,y+r*.1);c.bezierCurveTo(x+r*.4,y+r*.8,x-r*.3,y+r*.85,x-r*.65,y+r*.5);c.fill();}
 draw(o,t,reduced){const c=this.ctx,pal=palettes[o.visual==='binding'||o.mode==='binding'?'binding':o.element]||palettes.impact,origin={x:o.origin.x*100+50,y:o.origin.y*100+50},fade=clamp((1-t)*5),progress=clamp(t/.55);this.clear();if(this.ground)root.GroundAOE.draw(this.ground,o,t,{reduced});c.save();
  if(root.EffectFamilies?.draw(c,o,t,{reduced})){c.restore();this.labels(o,clamp((t-.4)*2.5),fade);return;}
  if(reduced){c.globalAlpha=.25*fade;c.fillStyle=pal[1];for(const cell of o.cells){const [x,y]=cell.split(',').map(Number);c.fillRect(x*100+3,y*100+3,94,94);}c.restore();this.labels(o,clamp((t-.2)*2),fade);return;}
  if(o.element==='energy'&&!['binding','barrier','heal','buff'].includes(o.visual)){
   const end={x:(o.aim?.x??o.origin.x)*100+50,y:(o.aim?.y??o.origin.y)*100+50},q=ease(clamp(t/.48));
   const head={x:origin.x+(end.x-origin.x)*q,y:origin.y+(end.y-origin.y)*q};
   if(['single','burst'].includes(o.shape)&&t<.48){
    c.globalAlpha=fade;this.stroke([[origin.x,origin.y],[head.x,head.y]],pal[0],10);
    c.fillStyle=pal[1];c.beginPath();c.arc(head.x,head.y,16,0,Math.PI*2);c.fill();
    c.fillStyle=pal[2];c.beginPath();c.arc(head.x,head.y,8,0,Math.PI*2);c.fill();
   }
   if(t>=.48){c.save();this.cellClip(o.cells);const impact=clamp((t-.48)/.4);c.globalAlpha=fade;
    if(o.shape==='line'){
     const [dx,dy]=({n:[0,-1],e:[1,0],s:[0,1],w:[-1,0]})[o.facing]||[1,0];
     const target=[origin.x+dx*800,origin.y+dy*800];
     this.stroke([[origin.x,origin.y],target],pal[0],42);this.stroke([[origin.x,origin.y],target],pal[1],26);this.stroke([[origin.x,origin.y],target],pal[2],9);
    }else{
     const center=['burst','single'].includes(o.shape)?end:origin;
     const radius=Math.max(35,...o.cells.map(k=>{const[x,y]=k.split(',').map(Number);return Math.hypot(x*100+50-center.x,y*100+50-center.y)+70;}));
     c.fillStyle=pal[0];c.globalAlpha=fade*.24;for(const k of o.cells){const[x,y]=k.split(',').map(Number);c.fillRect(x*100,y*100,100,100);}
     c.globalAlpha=fade;for(let i=0;i<2;i++){c.strokeStyle=pal[i+1];c.lineWidth=i?4:14;c.beginPath();c.arc(center.x,center.y,12+radius*clamp(impact-i*.13),0,Math.PI*2);c.stroke();}
    }c.restore();
   }
   c.restore();this.labels(o,clamp((t-.48)*3),fade);return;
  }
  // The filled attack is clipped to the very same footprint used by the resolver.
  c.save();this.cellClip(o.cells);c.globalAlpha=fade;
  for(const [i,cell] of o.cells.entries()){const [gx,gy]=cell.split(',').map(Number),x=gx*100+50,y=gy*100+50,dist=Math.hypot(x-origin.x,y-origin.y)/600,local=clamp((t-dist*.13-.12)*3.4);if(local<=0)continue;
   if(o.element==='fire'){c.globalAlpha=local*fade*.32;c.fillStyle=pal[0];c.fillRect(gx*100,gy*100,100,100);c.globalAlpha=local*fade;for(let j=0;j<4;j++){let fx=x-36+j*24+Math.sin(t*10+j+i)*6,fy=y+23+Math.cos(t*9+i+j)*10,r=27+Math.sin(t*12+i)*8;this.flame(fx,fy,r,t*15+i+j,pal[0]);this.flame(fx+3,fy+2,r*.72,t*15+i+j,pal[1]);this.flame(fx+5,fy+5,r*.35,t*15+i+j,pal[2]);}for(let j=0;j<3;j++){c.fillStyle=pal[2];c.beginPath();c.arc(x+Math.sin(i*17+j*9)*35,y-((t*130+j*23)%85),2,0,Math.PI*2);c.fill();}}
   else if(o.element==='water'&&o.mode!=='binding'&&o.visual!=='binding'){c.globalAlpha=local*fade*.14;c.fillStyle=pal[1];c.fillRect(gx*100,gy*100,100,100);}
   else if(o.element==='wind'){c.globalAlpha=local*fade*.2;c.fillStyle=pal[1];c.fillRect(gx*100,gy*100,100,100);c.globalAlpha=local*fade;c.strokeStyle=pal[2];for(let j=0;j<3;j++){c.lineWidth=4-j;c.beginPath();c.ellipse(x,y,38+j*8,14+j*9,t*1.5+i,Math.PI*.15,Math.PI*1.5);c.stroke();}}
   else if(o.element==='lightning'){c.globalAlpha=local*fade*.2;c.fillStyle=pal[1];c.fillRect(gx*100,gy*100,100,100);}
   else{c.globalAlpha=local*fade*.28;c.fillStyle=pal[0];c.fillRect(gx*100,gy*100,100,100);c.globalAlpha=local*fade;c.strokeStyle=pal[1];c.lineWidth=4;c.beginPath();c.arc(x,y,15+local*25,t*2,t*2+Math.PI*1.7);c.stroke();c.fillStyle=pal[2];for(let j=0;j<4;j++){const a=j*Math.PI/2+t;c.fillRect(x+Math.cos(a)*28-3,y+Math.sin(a)*28-3,6,6);}}
  }
  if(o.element==='water'&&o.mode!=='binding'&&o.visual!=='binding'){const [dx,dy]=({n:[0,-1],e:[1,0],s:[0,1],w:[-1,0]})[o.facing]||[1,0];c.save();c.translate(origin.x,origin.y);c.rotate(Math.atan2(dy,dx));const maxDepth=Math.max(1,...o.cells.map(cell=>{const [x,y]=cell.split(',').map(Number);return (x-o.origin.x)*dx+(y-o.origin.y)*dy;}))*100+50,front=50+(maxDepth-50)*ease(progress);c.globalAlpha=fade*.86;const gradient=c.createLinearGradient(50,0,front,0);gradient.addColorStop(0,'#237bab88');gradient.addColorStop(.72,'#2198bd');gradient.addColorStop(1,'#b2f8ff');c.fillStyle=gradient;c.beginPath();c.moveTo(50,-155);c.lineTo(front-25,-155);c.bezierCurveTo(front+45,-90,front-35,-35,front+15,0);c.bezierCurveTo(front+50,55,front-25,115,front-15,155);c.lineTo(50,155);c.closePath();c.fill();c.strokeStyle=pal[2];c.lineWidth=6;c.beginPath();c.moveTo(front-23,-155);c.bezierCurveTo(front+45,-90,front-35,-35,front+15,0);c.bezierCurveTo(front+50,55,front-25,115,front-15,155);c.stroke();for(let i=0;i<7;i++){let y=-135+i*44;c.strokeStyle=i%2?pal[1]:pal[2];c.lineWidth=3;c.beginPath();c.arc(front-23+Math.sin(i*7+t*5)*12,y,16+i%3*5,-Math.PI*.65,Math.PI*.75);c.stroke();}c.restore();}
  c.restore();
  // Trails identify direction, not extra collision/hit tiles.
  if(o.element==='fire'||o.element==='water'||o.element==='wind'){let target=['single','burst'].includes(o.shape)?{x:o.aim.x*100+50,y:o.aim.y*100+50}:(()=>{const [dx,dy]=({n:[0,-1],e:[1,0],s:[0,1],w:[-1,0]})[o.facing]||[0,0];const depth=Math.max(0,...o.cells.map(cell=>{const [x,y]=cell.split(',').map(Number);return (x-o.origin.x)*dx+(y-o.origin.y)*dy;}));return {x:origin.x+dx*depth*100,y:origin.y+dy*depth*100};})();const head={x:origin.x+(target.x-origin.x)*ease(progress),y:origin.y+(target.y-origin.y)*ease(progress)};c.globalAlpha=clamp((.62-t)*3)*.75;if(o.mode!=='binding'&&o.visual!=='binding'){this.stroke([[origin.x,origin.y],[head.x,head.y]],pal[1],o.element==='water'?16:9);this.stroke([[origin.x,origin.y],[head.x,head.y]],pal[2],3);}}
  if(o.element==='lightning'){let cells=o.cells.map(v=>v.split(',').map(Number));const end=cells.length?{x:cells.at(-1)[0]*100+50,y:cells.at(-1)[1]*100+50}:origin;let dx=end.x-origin.x,dy=end.y-origin.y,len=Math.hypot(dx,dy)||1,points=[[origin.x,origin.y]];for(let i=1;i<=16;i++){let q=i/16*Math.min(1,progress*1.6),j=Math.sin(i*19+Math.floor(t*7))*(i===16?0:15);points.push([origin.x+dx*q-dy/len*j,origin.y+dy*q+dx/len*j]);}c.globalAlpha=Math.sin(Math.min(1,t*2)*Math.PI/2)*fade;this.stroke(points,pal[0],14);this.stroke(points,pal[1],7);this.stroke(points,pal[2],2);}
  if(o.mode==='binding'||o.visual==='binding'||o.visual==='barrier'||o.element==='barrier'){const targets=o.hits;for(const h of targets){const x=h.x*100+50,y=h.y*100+50,r=45*ease(clamp(t*3));c.globalAlpha=.85*fade;c.fillStyle=pal[0]+'44';c.beginPath();c.arc(x,y,r,0,Math.PI*2);c.fill();c.strokeStyle=pal[1];c.lineWidth=4;c.stroke();c.strokeStyle=pal[2];c.lineWidth=2;for(let i=0;i<3;i++){c.beginPath();c.ellipse(x,y,r,12+i*7,t*3+i*Math.PI/3,0,Math.PI*2);c.stroke();}}}
  if(t>.35&&o.element!=='barrier'){for(const h of o.hits){let q=clamp((t-.35)*3),x=h.x*100+50,y=h.y*100+50;c.globalAlpha=(1-q)*fade;c.strokeStyle=h.immune?'#dfded1':pal[2];c.lineWidth=3;c.beginPath();c.arc(x,y,10+q*45,0,Math.PI*2);c.stroke();if(o.element==='impact'){for(let i=0;i<7;i++){let a=i*Math.PI*2/7;this.stroke([[x+Math.cos(a)*12,y+Math.sin(a)*12],[x+Math.cos(a)*(20+q*35),y+Math.sin(a)*(20+q*35)]],pal[2],3);}}}}
  c.restore();this.labels(o,clamp((t-.4)*2.5),fade);
 }
 labels(o,q,fade){if(q<=0)return;const c=this.ctx;c.save();c.globalAlpha=fade;c.font='bold 21px Segoe UI';c.textAlign='center';for(const h of o.hits){let text=h.immune?'IMMUNE':h.blocked?'BLOCKED':h.healed!==undefined?'HEAL +'+h.healed:h.shieldAfter>h.shieldBefore?'SHIELD '+h.shieldAfter:h.damage?'-'+h.damage:h.statusBlocked?'BLOCKED':(h.statusesApplied?.[0]?.kind?.toUpperCase()||(h.statusesRemoved?.length?'CLEANSED':'NO DAMAGE'));let x=Math.max(60,Math.min(740,h.x*100+50)),y=Math.max(26,h.y*100+15-q*28);c.lineWidth=5;c.strokeStyle='#172a25';c.strokeText(text,x,y);c.fillStyle='#fff4d6';c.fillText(text,x,y);}c.restore();}
}
root.BattleFX=BattleFX;
})(window);
