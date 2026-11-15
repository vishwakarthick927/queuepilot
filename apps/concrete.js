const D=DATA,$=s=>document.querySelector(s);let mode='both',T=String(D.temps[1]),t=0,playing=false,last=0;
const css=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const fmt=n=>'₹'+Math.round(n).toLocaleString('en-IN');
$('#temp').innerHTML=D.temps.map(x=>`<button data-t="${x}" class="${String(x)===T?'on':''}">${x} °C</button>`).join('');
function views(){const list=mode==='both'?['today','queuepilot']:[mode];const v=$('#views');v.style.gridTemplateRows=list.map(()=>'1fr').join(' ');
  v.innerHTML=list.map(p=>`<div class="view" data-p="${p}" style="border-right:0;border-bottom:1px solid var(--line)"><div class="vlabel">${p==='today'?'Today':'QueuePilot'}<b>${p==='today'?'A truck every '+D.pump_plan_min+' min, first come first served':'Plant paced by the pump, least slack first'}</b></div><div class="vstat"><div class="num" id="rej_${p}">0</div><span>loads rejected so far</span></div><canvas></canvas></div>`).join('');
  const fin=Math.max(...['today','queuepilot'].map(p=>D.demo[T][p].finish));$('#scrub').max=Math.ceil(fin+10);kpis();draw();}
function fit(c){const r=c.getBoundingClientRect(),d=window.devicePixelRatio||1;c.width=r.width*d;c.height=r.height*d;const x=c.getContext('2d');x.setTransform(d,0,0,d,0,0);return[x,r.width,r.height];}
function truck(x,px,py,frac,dead,label){const w=44,h=20;x.fillStyle=dead?'#3a2022':css('--panel');x.strokeStyle=dead?css('--bad'):css('--ink2');x.lineWidth=1;x.beginPath();x.roundRect(px-w/2,py-h/2,w,h,4);x.fill();x.stroke();
  x.fillStyle=dead?css('--bad'):frac>.4?css('--good'):frac>.15?css('--warn'):css('--bad');x.fillRect(px-w/2+3,py+h/2-6,Math.max(0,(w-6)*frac),3);
  x.fillStyle=dead?css('--bad'):css('--ink');x.font='600 10px "JetBrains Mono"';x.textAlign='center';x.fillText(dead?'×':label,px,py+1);}
function draw(){document.querySelectorAll('.view').forEach(v=>{const p=v.dataset.p,[x,w,h]=fit(v.querySelector('canvas'));const R=D.demo[T][p],L=R.limit_min;x.clearRect(0,0,w,h);
  const y=h*.62,x0=70,x1=w-150,road=x1-x0-200;x.strokeStyle=css('--line');x.lineWidth=14;x.lineCap='round';x.beginPath();x.moveTo(x0+30,y);x.lineTo(x0+30+road,y);x.stroke();
  x.fillStyle=css('--ink2');x.font='12px "Space Grotesk"';x.textAlign='center';x.fillText('BATCHING PLANT',x0,y+44);x.fillText('WAITING AT SITE',x0+road+110,y+44);x.fillText('PUMP',x1+70,y+44);
  x.strokeStyle=css('--ink2');x.lineWidth=1;x.strokeRect(x0-26,y-22,52,44);x.strokeRect(x1+44,y-22,52,44);
  let rej=0,q=0;R.trucks.forEach(k=>{const lim=k.limit,frac=Math.max(0,(lim-t)/L);if(k.rejected&&t>=lim){rej++;return;}if(t<k.batch)return;
    if(t<k.arrive){const f=(t-k.batch)/(k.arrive-k.batch);truck(x,x0+30+road*f,y,frac,false,Math.max(0,Math.round(lim-t)));}
    else if(k.start===null||t<k.start){truck(x,x0+road+52+(q%4)*50,y-28*Math.floor(q/4),frac,false,Math.max(0,Math.round(lim-t)));q++;}
    else if(t<k.end){truck(x,x1+70,y,Math.max(0,(lim-k.start)/L),false,'pour');}});
  const placed=R.trucks.filter(k=>!k.rejected&&k.end<=t).length;x.textAlign='left';x.fillStyle=css('--ink2');x.font='12px "Space Grotesk"';x.fillText('placed',x1+44,y-58);x.fillStyle=css('--ink');x.font='600 20px "JetBrains Mono"';x.fillText(placed+' / '+D.trucks,x1+44,y-34);
  for(let i=0;i<rej;i++){truck(x,x0+road+52+(i%10)*50,h-34-26*Math.floor(i/10),0,true,'');}
  if(rej){x.fillStyle=css('--bad');x.font='12px "Space Grotesk"';x.textAlign='left';x.fillText('DUMPED: SET BEFORE THE PUMP WAS FREE',x0+road+30,h-52-26*Math.floor((rej-1)/10));}
  const el=document.getElementById('rej_'+p);el.textContent=rej;el.style.color=rej?css('--bad'):css('--ink');});
  $('#clock').textContent=Math.floor(t/60)+':'+String(Math.floor(t%60)).padStart(2,'0');$('#scrub').value=Math.floor(t);$('#phase').textContent='The number on each truck is its minutes of life left';}
function kpis(){const a=D.across_pours[T].today,b=D.across_pours[T].queuepilot,s=D.across_pours[T].smart_queue;
  $('#k1a').textContent=a.rejected_mean;$('#k1b').textContent=b.rejected_mean;$('#k1s').textContent='average of '+a.seeds+' simulated pours · ±'+b.rejected_ci95;
  $('#k2a').textContent=fmt(a.lost_rs_mean);$('#k2b').textContent=fmt(b.lost_rs_mean);$('#k3b').textContent=D.limits[T]+' min';$('#k3s').textContent='from batching to discharge · the drive alone takes about '+D.travel_mean_min+' min';
  $('#say').innerHTML='At '+T+' °C, <b>'+(a.rejected_mean-b.rejected_mean).toFixed(1)+' fewer truckloads</b> are dumped per pour: '+fmt(a.lost_rs_mean-b.lost_rs_mean)+' of concrete saved.';
  $('#honest').innerHTML='<span><b style="color:var(--ink)">Measured, not assumed.</b> Re-ordering the queue alone barely helps ('+a.rejected_mean+' → '+s.rejected_mean+' rejected): when trucks arrive faster than the pump works, some load must expire. Pacing the plant is what works. The cost: the pour takes longer ('+a.finish_min+' → '+b.finish_min+' min) because every truck is actually placed. '+(+T>=38?'At 38 °C the limit is close to the drive time, so some loads are lost under any schedule: that calls for a retarder or a closer plant.':'')+'</span>';
  $('#foot').textContent=D.trucks+' trucks · '+D.load_m3+' m³ each · pump planned at '+D.pump_plan_min+' min per truck, really '+D.pump_real_min+' min';}
function tick(ts){if(!playing)return;const dt=(ts-last)/1000;last=ts;const mx=+$('#scrub').max;t=Math.min(mx,t+dt*14);draw();if(t>=mx){playing=false;$('#play').textContent='Replay';return;}requestAnimationFrame(tick);}
$('#play').onclick=()=>{if(playing){playing=false;$('#play').textContent='Play';return;}if(t>=+$('#scrub').max)t=0;playing=true;$('#play').textContent='Pause';last=performance.now();requestAnimationFrame(tick);};
$('#scrub').oninput=e=>{t=+e.target.value;draw();};
$('#mode').onclick=e=>{const b=e.target.closest('button');if(!b)return;mode=b.dataset.m;document.querySelectorAll('#mode button').forEach(k=>k.classList.toggle('on',k===b));views();};
$('#temp').onclick=e=>{const b=e.target.closest('button');if(!b)return;T=b.dataset.t;t=0;document.querySelectorAll('#temp button').forEach(k=>k.classList.toggle('on',k===b));views();};
addEventListener("resize",draw);views();if(document.fonts&&document.fonts.ready)document.fonts.ready.then(draw);
