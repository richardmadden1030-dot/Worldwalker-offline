/* Phase-one reusable tactical animation families. Pure canvas, offline safe. */
(function(root){
'use strict';
const FAMILIES=[
 ['spirit-bolt','Spirit Bolt','projectile','bolt',['#d9fbff','#60c9df','#284b61']],
 ['piercing-lance','Piercing Lance','projectile','beam',['#fff5c7','#8edbe5','#31536d']],
 ['spirit-volley','Spirit Volley','projectile','volley',['#f7ffff','#77d5e8','#29495e']],
 ['homing-arc','Homing Arc','projectile','homing',['#fce7bb','#8bcfe4','#395067']],
 ['crescent-wave','Crescent Wave','projectile','crescent',['#f7f3e7','#9ed8e3','#334b59']],
 ['horizon-ray','Horizon Ray','projectile','ray',['#ffffff','#78cfe4','#273d53']],
 ['blade-trail','Blade Trail','melee','slash',['#fffdf2','#b5dbe0','#59666b']],
 ['impact-burst','Impact Burst','melee','impact',['#fff0bd','#e18b4c','#63382d']],
 ['multi-slash','Multi Slash','melee','multi-slash',['#ffffff','#aacbd2','#495c65']],
 ['chain-whip','Chain or Whip','melee','chain',['#f6e7bd','#a6b5b9','#4e5558']],
 ['living-flame','Living Flame','element','flame',['#fff0a8','#ff8b35','#9e271f']],
 ['tidal-surge','Tidal Surge','element','water',['#e9ffff','#62cadd','#17648d']],
 ['frost-bloom','Frost Bloom','element','ice',['#ffffff','#b7ecf2','#4d87a4']],
 ['storm-vein','Storm Vein','element','lightning',['#f6ffff','#8adff0','#315da0']],
 ['wind-shear','Wind Shear','element','wind',['#f3fff7','#a4e0cc','#497f78']],
 ['stone-crystal','Stone and Crystal','element','crystal',['#fff1d4','#c5a884','#6a5260']],
 ['shadow-ink','Shadow Ink','element','ink',['#c6c5d5','#56546b','#171a22']],
 ['poison-mist','Poison Mist','element','mist',['#e5f2ad','#91ad5e','#493b61']],
 ['binding-bands','Binding Bands','control','bands',['#fff4c5','#dcbd68','#5d4933']],
 ['seal-glyph','Seal Glyph','control','glyph',['#fff7d6','#d0954e','#6a3028']],
 ['illusion-glass','Illusion Glass','control','glass',['#f2ffff','#94c8d0','#56526b']],
 ['spirit-barrier','Spirit Barrier','support','barrier',['#f0ffff','#78d6ce','#335d68']],
 ['restoration-pulse','Restoration Pulse','support','heal',['#f7ffe5','#9ad7a4','#42705a']],
 ['soul-siphon','Soul Siphon','support','siphon',['#efe2ff','#a17cc0','#403451']],
 ['flash-step','Flash Step','spatial','blink',['#ffffff','#c3e7e8','#64747a']],
 ['rift-swap','Rift and Swap','spatial','rift',['#e7f9ff','#79aec0','#353b55']],
 ['spirit-construct','Spirit Construct','summon','construct',['#fff6d7','#76c8d5','#304d60']],
 ['persistent-zone','Persistent Zone','field','zone',['#f6edcf','#93cbd0','#445965']],
 ['reiatsu-pressure','Reiatsu Pressure','release','pressure',['#ffffff','#8acbd5','#253747']],
 ['release-transformation','Release Transformation','release','release',['#fff9e8','#e1b467','#553c32']]
].map(([id,label,category,style,colors])=>Object.freeze({id,label,category,style,colors}));
const BY_ID=new Map(FAMILIES.map(v=>[v.id,v]));
const clamp=v=>Math.max(0,Math.min(1,v));
const ease=v=>1-Math.pow(1-clamp(v),3);
const center=p=>({x:p.x*100+50,y:p.y*100+50});
const hash=s=>[...String(s)].reduce((n,c)=>(n*31+c.charCodeAt(0))>>>0,2166136261);
function line(ctx,a,b,color,width,alpha=1){ctx.globalAlpha=alpha;ctx.strokeStyle=color;ctx.lineWidth=width;ctx.lineCap='round';ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke();}
function ring(ctx,p,r,color,width,alpha=1,start=0,end=Math.PI*2){ctx.globalAlpha=alpha;ctx.strokeStyle=color;ctx.lineWidth=width;ctx.beginPath();ctx.arc(p.x,p.y,r,start,end);ctx.stroke();}
function polygon(ctx,p,r,sides,color,alpha,rotation=0){ctx.globalAlpha=alpha;ctx.strokeStyle=color;ctx.lineWidth=3;ctx.beginPath();for(let i=0;i<=sides;i++){const a=rotation+i*Math.PI*2/sides,x=p.x+Math.cos(a)*r,y=p.y+Math.sin(a)*r;i?ctx.lineTo(x,y):ctx.moveTo(x,y);}ctx.stroke();}
function clipCells(ctx,o){ctx.beginPath();for(const key of o.cells||[]){const [x,y]=key.split(',').map(Number);ctx.rect(x*100,y*100,100,100);}ctx.clip();}
function path(o){const a=center(o.origin),b=center(o.aim||o.origin);return {a,b,dx:b.x-a.x,dy:b.y-a.y,angle:Math.atan2(b.y-a.y,b.x-a.x)};}
function target(o){return center(o.aim||o.origin);}
function draw(ctx,o,t,{reduced=false}={}){
 const family=BY_ID.get(o?.visual_effect?.family||o?.family);if(!family)return false;
 const [hi,mid,deep]=family.colors,fade=clamp((1-t)*5),seed=hash((o.id||'effect')+family.id),p=path(o),q=ease(t/.58),head={x:p.a.x+p.dx*q,y:p.a.y+p.dy*q};
 ctx.save();
 if(reduced){ctx.globalAlpha=.28*fade;ctx.fillStyle=mid;for(const key of o.cells||[]){const [x,y]=key.split(',').map(Number);ctx.fillRect(x*100+4,y*100+4,92,92);}ctx.restore();return true;}
 try{
  if(['bolt','beam','ray','volley','homing','crescent'].includes(family.style)){
   if(family.style==='volley'||family.style==='homing')for(let i=-2;i<=2;i++){const wobble=family.style==='homing'?Math.sin(q*Math.PI+i)*34:i*12,perp={x:-Math.sin(p.angle)*wobble,y:Math.cos(p.angle)*wobble};line(ctx,{x:p.a.x+perp.x,y:p.a.y+perp.y},{x:head.x+perp.x,y:head.y+perp.y},i?mid:hi,i?4:7,fade*.72);ring(ctx,{x:head.x+perp.x,y:head.y+perp.y},5,hi,3,fade);}
   else if(family.style==='crescent'){ctx.translate(head.x,head.y);ctx.rotate(p.angle);ctx.globalAlpha=fade;ctx.strokeStyle=hi;ctx.lineWidth=10;ctx.beginPath();ctx.arc(0,0,42,-1.15,1.15);ctx.stroke();ctx.strokeStyle=mid;ctx.lineWidth=20;ctx.globalAlpha=fade*.5;ctx.stroke();}
   else{line(ctx,p.a,head,deep,family.style==='ray'?34:family.style==='beam'?24:12,fade*.55);line(ctx,p.a,head,mid,family.style==='ray'?19:family.style==='beam'?13:7,fade*.9);line(ctx,p.a,head,hi,family.style==='ray'?6:3,fade);ring(ctx,head,family.style==='bolt'?13:8,hi,4,fade);}
  }else if(['slash','multi-slash','impact','chain'].includes(family.style)){
   const c=target(o),impact=clamp((t-.22)/.5);clipCells(ctx,o);
   if(family.style==='impact'){ring(ctx,c,18+impact*68,mid,14,fade*(1-impact));for(let i=0;i<10;i++){const a=i*Math.PI/5;line(ctx,{x:c.x+Math.cos(a)*15,y:c.y+Math.sin(a)*15},{x:c.x+Math.cos(a)*(35+impact*70),y:c.y+Math.sin(a)*(35+impact*70)},hi,4,fade*(1-impact));}}
   else if(family.style==='chain'){ctx.strokeStyle=mid;ctx.lineWidth=7;ctx.globalAlpha=fade;ctx.beginPath();for(let i=0;i<=12;i++){const x=p.a.x+p.dx*i/12,y=p.a.y+p.dy*i/12+Math.sin(i*1.8+t*13)*17;i?ctx.lineTo(x,y):ctx.moveTo(x,y);}ctx.stroke();for(let i=2;i<=12;i+=2)ring(ctx,{x:p.a.x+p.dx*i/12,y:p.a.y+p.dy*i/12+Math.sin(i*1.8+t*13)*17},9,hi,3,fade);}
   else for(let i=0;i<(family.style==='multi-slash'?5:1);i++){const off=(i-2)*17,a=p.angle+(i%2?.52:-.52);ctx.strokeStyle=i%2?mid:hi;ctx.lineWidth=family.style==='slash'?12:6;ctx.globalAlpha=fade;ctx.beginPath();ctx.arc(c.x+Math.cos(p.angle+Math.PI/2)*off,c.y+Math.sin(p.angle+Math.PI/2)*off,48+impact*25,a-1.2,a+1.2);ctx.stroke();}
  }else if(['flame','water','ice','lightning','wind','crystal','ink','mist'].includes(family.style)){
   clipCells(ctx,o);ctx.globalAlpha=fade*.18;ctx.fillStyle=mid;for(const key of o.cells||[]){const [x,y]=key.split(',').map(Number);ctx.fillRect(x*100,y*100,100,100);}ctx.globalAlpha=fade;
   for(const [index,key] of (o.cells||[]).entries()){const [x,y]=key.split(',').map(Number),c={x:x*100+50,y:y*100+50},phase=t*8+index+seed%7;
    if(family.style==='flame')for(let i=0;i<4;i++){ctx.fillStyle=i%2?mid:hi;ctx.beginPath();ctx.moveTo(c.x-30+i*18,c.y+36);ctx.quadraticCurveTo(c.x-42+i*22,c.y,c.x-18+i*18+Math.sin(phase+i)*9,c.y-45-(i%2)*18);ctx.quadraticCurveTo(c.x+4+i*17,c.y,c.x-30+i*18,c.y+36);ctx.fill();}
    else if(family.style==='water'){for(let i=0;i<3;i++){ctx.strokeStyle=i?mid:hi;ctx.lineWidth=5-i;ctx.beginPath();ctx.arc(c.x,c.y+10-i*13,24+i*8,Math.PI+phase*.1,Math.PI*2+phase*.1);ctx.stroke();}}
    else if(family.style==='ice')for(let i=0;i<5;i++){const a=i*Math.PI*2/5+phase*.04;ctx.fillStyle=i%2?mid:hi;ctx.beginPath();ctx.moveTo(c.x+Math.cos(a)*8,c.y+Math.sin(a)*8);ctx.lineTo(c.x+Math.cos(a-.14)*(42+i%2*18),c.y+Math.sin(a-.14)*(42+i%2*18));ctx.lineTo(c.x+Math.cos(a+.14)*(42+i%2*18),c.y+Math.sin(a+.14)*(42+i%2*18));ctx.fill();}
    else if(family.style==='lightning')for(let i=0;i<3;i++){let pts=[],sx=c.x-35+i*35;for(let j=0;j<6;j++)pts.push({x:sx+Math.sin(seed+i*13+j*7)*13,y:c.y-50+j*20});for(let j=1;j<pts.length;j++)line(ctx,pts[j-1],pts[j],i===1?hi:mid,i===1?4:7,fade);}
    else if(family.style==='wind')for(let i=0;i<3;i++){ctx.strokeStyle=i?mid:hi;ctx.lineWidth=5-i;ctx.beginPath();ctx.ellipse(c.x,c.y,20+i*13,8+i*6,phase*.15,0,Math.PI*1.7);ctx.stroke();}
    else if(family.style==='crystal')for(let i=0;i<4;i++)polygon(ctx,{x:c.x+(i-1.5)*17,y:c.y+12},20+i%2*16,4,i%2?mid:hi,fade,Math.PI/4);
    else if(family.style==='ink'){ctx.fillStyle=deep;for(let i=0;i<8;i++){ctx.beginPath();ctx.arc(c.x+Math.sin(seed+i*17)*42,c.y+Math.cos(seed+i*11)*35,5+(i%3)*5,0,Math.PI*2);ctx.fill();}ring(ctx,c,18+q*35,mid,6,fade);}
    else {ctx.fillStyle=mid;for(let i=0;i<9;i++){ctx.globalAlpha=fade*(.16+(i%3)*.08);ctx.beginPath();ctx.arc(c.x+Math.sin(seed+i*14+t)*38,c.y+Math.cos(seed+i*9-t)*33,18+(i%4)*6,0,Math.PI*2);ctx.fill();}}
   }
  }else{
   const c=target(o),impact=ease(clamp((t-.08)/.7));
   if(family.style==='bands'){for(let i=0;i<4;i++){ctx.strokeStyle=i%2?mid:hi;ctx.lineWidth=5;ctx.globalAlpha=fade;ctx.beginPath();ctx.ellipse(c.x,c.y,(18+i*9)*impact,10+i*8,t*2+i*.6,0,Math.PI*2);ctx.stroke();}}
   else if(family.style==='glyph'){for(let i=0;i<3;i++)polygon(ctx,c,(24+i*16)*impact,6+i, i===1?mid:hi,fade,t*(i%2?1:-1));for(let i=0;i<8;i++){const a=i*Math.PI/4;line(ctx,{x:c.x+Math.cos(a)*18,y:c.y+Math.sin(a)*18},{x:c.x+Math.cos(a)*58*impact,y:c.y+Math.sin(a)*58*impact},mid,3,fade);}}
   else if(family.style==='glass'){for(let i=0;i<7;i++){const a=i*Math.PI*2/7+t*.3,r=18+impact*45;polygon(ctx,{x:c.x+Math.cos(a)*r*.45,y:c.y+Math.sin(a)*r*.45},13+(i%2)*7,3, i%2?mid:hi,fade*.7,a);}}
   else if(family.style==='barrier'){ctx.fillStyle=mid;ctx.globalAlpha=fade*.16;ctx.beginPath();ctx.arc(c.x,c.y,68*impact,Math.PI,Math.PI*2);ctx.fill();ring(ctx,c,68*impact,hi,6,fade,Math.PI,Math.PI*2);}
   else if(family.style==='heal'){for(let i=0;i<4;i++)ring(ctx,c,12+impact*(24+i*14),i%2?mid:hi,4,fade*(1-i*.16));line(ctx,{x:c.x-22,y:c.y},{x:c.x+22,y:c.y},hi,8,fade);line(ctx,{x:c.x,y:c.y-22},{x:c.x,y:c.y+22},hi,8,fade);}
   else if(family.style==='siphon'){for(let i=0;i<5;i++){const a=t*4+i*Math.PI*2/5,r=(1-impact)*85+12;ring(ctx,{x:c.x+Math.cos(a)*r,y:c.y+Math.sin(a)*r},8,mid,4,fade);line(ctx,{x:c.x+Math.cos(a)*r,y:c.y+Math.sin(a)*r},c,deep,4,fade*.55);}}
   else if(family.style==='blink'){for(let i=0;i<6;i++){const x=p.a.x+(p.dx*i/5),y=p.a.y+(p.dy*i/5);ctx.fillStyle=i===5?hi:mid;ctx.globalAlpha=fade*i/5;ctx.fillRect(x-7,y-28,14,56);}}
   else if(family.style==='rift'){ring(ctx,p.a,38*impact,mid,8,fade);ring(ctx,p.b,38*impact,hi,8,fade);line(ctx,p.a,p.b,mid,3,fade*.45);}
   else if(family.style==='construct'){polygon(ctx,c,55*impact,6,mid,fade,t*.4);polygon(ctx,c,35*impact,4,hi,fade,-t*.6);ring(ctx,c,12+impact*18,hi,5,fade);}
   else if(family.style==='zone'){clipCells(ctx,o);ctx.fillStyle=deep;ctx.globalAlpha=fade*.28;for(const key of o.cells||[]){const [x,y]=key.split(',').map(Number);ctx.fillRect(x*100,y*100,100,100);}for(const key of o.cells||[]){const [x,y]=key.split(',').map(Number);ring(ctx,{x:x*100+50,y:y*100+50},20+Math.sin(t*7+x+y)*8,mid,3,fade*.75);}}
   else if(family.style==='pressure'){for(let i=0;i<5;i++)ring(ctx,p.a,20+impact*(25+i*27),i%2?mid:hi,7-i,fade*(1-i*.12));}
   else if(family.style==='release'){for(let i=0;i<12;i++){const a=i*Math.PI/6,r=18+impact*(55+(i%3)*18);line(ctx,{x:p.a.x+Math.cos(a)*12,y:p.a.y+Math.sin(a)*12},{x:p.a.x+Math.cos(a)*r,y:p.a.y+Math.sin(a)*r},i%3?mid:hi,5,fade);}ring(ctx,p.a,22+impact*62,hi,4,fade);}
  }
 }finally{ctx.restore();}
 return true;
}
function resolve(id){return BY_ID.get(id)||null;}
const api=Object.freeze({families:Object.freeze(FAMILIES),resolve,draw});
if(typeof module==='object'&&module.exports)module.exports=api;else root.EffectFamilies=api;
})(typeof window==='object'?window:globalThis);
