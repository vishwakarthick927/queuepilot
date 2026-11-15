const D=DATA,H=D.hospitals,W=D.city_km[0],Hh=D.city_km[1],$=s=>document.querySelector(s);
let mode='both',t=0,playing=false,last=0;
const css=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
function views(){const v=$('#views');const list=mode==='both'?['nearest','learned']:[mode];v.className='views'+(list.length>1?' two':'');
  v.innerHTML=list.map(p=>`<div class="view" data-p="${p}"><div class="vlabel">${p==='nearest'?'Today':'QueuePilot'}<b>${p==='nearest'?'Nearest hospital':'Soonest treatment'}</b></div><div class="vstat"><div class="num" id="late_${p}">0</div><span>past the golden hour so far</span></div><canvas></canvas></div>`).join('');draw();}
function fit(c){const r=c.getBoundingClientRect(),d=window.devicePixelRatio||1;c.width=r.width*d;c.height=r.height*d;const x=c.getContext('2d');x.setTransform(d,0,0,d,0,0);return[x,r.width,r.height];}
function draw(){document.querySelectorAll('.view').forEach(v=>{const p=v.dataset.p,[x,w,h]=fit(v.querySelector('canvas'));const pad=26,sc=Math.min((w-2*pad)/W,(h-2*pad-90)/Hh),ox=(w-W*sc)/2,oy=(h-Hh*sc)/2+34,X=k=>ox+k*sc,Y=k=>oy+(Hh-k)*sc;
  x.clearRect(0,0,w,h);x.strokeStyle=css('--line');x.lineWidth=1;for(let i=0;i<=W;i+=2){x.beginPath();x.moveTo(X(i),Y(0));x.lineTo(X(i),Y(Hh));x.stroke();}for(let j=0;j<=Hh;j+=2){x.beginPath();x.moveTo(X(0),Y(j));x.lineTo(X(W),Y(j));x.stroke();}
  const ev=D.event;if(t>=ev.at_min){const a=Math.max(.15,1-(t-ev.at_min)/60);x.strokeStyle=css('--bad');x.globalAlpha=a;x.lineWidth=2;x.beginPath();x.arc(X(ev.x),Y(ev.y),14+((t-ev.at_min)%6)*3,0,7);x.stroke();x.globalAlpha=1;x.fillStyle=css('--bad');x.font='600 12px "Space Grotesk"';x.fillText(ev.name,X(ev.x)+22,Y(ev.y)+4);}
  const P=D.demo[p].patients;let late=0;
  P.forEach(q=>{if(q.start<=t&&q.wait>D.golden_min)late++;if(t<q.t||t>=q.start)return;const hh=H[q.h],f=Math.min(1,(t-q.t)/Math.max(1,q.arrive-q.t));const bad=q.wait>D.golden_min;
    if(t<q.arrive){const px=q.x+(hh.x-q.x)*f,py=q.y+(hh.y-q.y)*f;x.strokeStyle=bad?css('--bad'):css('--acc');x.globalAlpha=.35;x.beginPath();x.moveTo(X(q.x),Y(q.y));x.lineTo(X(px),Y(py));x.stroke();x.globalAlpha=1;x.fillStyle=bad?css('--bad'):css('--acc');x.beginPath();x.arc(X(px),Y(py),3.5,0,7);x.fill();}});
  const wq=D.demo[p].waiting[Math.min(239,Math.floor(t))];
  H.forEach((hh,i)=>{const n=wq[i],cx=X(hh.x),cy=Y(hh.y),full=n>=8;x.fillStyle=css('--panel');x.strokeStyle=full?css('--bad'):css('--ink2');x.lineWidth=full?2:1;x.beginPath();x.roundRect(cx-13,cy-13,26,26,4);x.fill();x.stroke();
    x.fillStyle=full?css('--bad'):css('--ink');x.font='600 13px "JetBrains Mono"';x.textAlign='center';x.fillText('+',cx,cy+5);
    const bh=Math.min(60,n*3);x.fillStyle=full?css('--bad'):css('--warn');x.fillRect(cx+18,cy+13-bh,7,bh);
    x.textAlign='left';x.fillStyle=css('--ink2');x.font='12px "Space Grotesk"';x.fillText(hh.name,cx-13,cy+30);x.fillStyle=full?css('--bad'):css('--ink');x.font='600 12px "JetBrains Mono"';x.fillText(n+' waiting',cx-13,cy+45);});
  const el=document.getElementById('late_'+p);el.textContent=late;el.style.color=late>0&&p==='nearest'?css('--bad'):css('--ink');});
  $('#clock').textContent=Math.floor(t/60)+':'+String(Math.floor(t%60)).padStart(2,'0');$('#scrub').value=Math.floor(t);
  $('#phase').textContent=t<D.event.at_min?'An ordinary evening':t<D.event.at_min+D.event.over_min?D.event.casualties+' casualties in '+D.event.over_min+' minutes':'Hospitals absorbing the surge';}
function tick(ts){if(!playing)return;const dt=(ts-last)/1000;last=ts;t=Math.min(239,t+dt*9);draw();if(t>=239){playing=false;$('#play').textContent='Replay';return;}requestAnimationFrame(tick);}
$('#play').onclick=()=>{if(playing){playing=false;$('#play').textContent='Play';return;}if(t>=239)t=0;playing=true;$('#play').textContent='Pause';last=performance.now();requestAnimationFrame(tick);};
$('#scrub').oninput=e=>{t=+e.target.value;draw();};
$('#mode').onclick=e=>{const b=e.target.closest('button');if(!b)return;mode=b.dataset.m;document.querySelectorAll('#mode button').forEach(k=>k.classList.toggle('on',k===b));views();};
const A=D.across_days,n=A.nearest,q=A.learned,pl=A.nameplate;
$('#k1a').textContent=n.late_mean;$('#k1b').textContent=q.late_mean;$('#k1s').textContent='of about 130 patients · average of '+n.seeds+' simulated nights · ±'+q.late_ci95;
$('#k2a').textContent=n.mean_min;$('#k2b').textContent=q.mean_min;$('#k3a').textContent=Math.round(n.worst_min);$('#k3b').textContent=Math.round(q.worst_min);
$('#say').innerHTML='On the same night, with the same calls, <b>'+Math.round(n.late_mean-q.late_mean)+' more patients</b> reach a doctor inside the golden hour.';
const R=D.load_forecast_model['hospital never seen (Ring Road)'];
$('#honest').innerHTML='<span><b style="color:var(--ink)">Measured, not assumed.</b> Routing on the plan-on-paper rates gives '+pl.late_mean+' late patients, on learned rates '+q.late_mean+': the same within the margin ('+'±'+q.late_ci95+'). The gain comes from routing by wait, not from the learning. Our physics-guided network that forecasts emergency-room load 30 minutes ahead: error '+R['Physics + AI (ours)'].ER_filling_up+' patients on a hospital it never saw, physics alone '+R['Physics only'].ER_filling_up+', AI alone '+R['AI only'].ER_filling_up+'.</span>';
$('#foot').textContent=H.length+' hospitals · ambulances at '+D.speed_kmh+' km/h · golden hour = '+D.golden_min+' min';
addEventListener("resize",draw);views();if(document.fonts&&document.fonts.ready)document.fonts.ready.then(draw);
