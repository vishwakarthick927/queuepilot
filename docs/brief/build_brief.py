"""Builds docs/brief/QueuePilot_Brief.html (then printed to PDF with Edge). Run from repo root:
    python docs/brief/build_brief.py
"""
import base64
from pathlib import Path

HERE = Path(__file__).parent
img = lambda name: "data:image/png;base64," + base64.b64encode((HERE / name).read_bytes()).decode()

FLOW = """
<svg viewBox="0 0 760 170" class="fig" role="img" aria-label="How QueuePilot works">
  <defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#555"/></marker></defs>
  <g font-family="Space Grotesk, Arial" font-size="13" fill="#111">
    <rect x="10" y="40" width="150" height="80" rx="6" fill="#f3f4f6" stroke="#bbb"/>
    <text x="85" y="70" text-anchor="middle" font-weight="700">1. SEE</text>
    <text x="85" y="90" text-anchor="middle">calls, ambulances,</text><text x="85" y="106" text-anchor="middle">ER queues, doctors</text>
    <rect x="200" y="40" width="170" height="80" rx="6" fill="#e9f9ef" stroke="#2fa866"/>
    <text x="285" y="70" text-anchor="middle" font-weight="700">2. PREDICT</text>
    <text x="285" y="90" text-anchor="middle">physics + AI forecast</text><text x="285" y="106" text-anchor="middle">wait at every hospital</text>
    <rect x="410" y="40" width="160" height="80" rx="6" fill="#f3f4f6" stroke="#bbb"/>
    <text x="490" y="70" text-anchor="middle" font-weight="700">3. DECIDE</text>
    <text x="490" y="90" text-anchor="middle">drive time + wait</text><text x="490" y="106" text-anchor="middle">→ best hospital</text>
    <rect x="610" y="40" width="140" height="80" rx="6" fill="#f3f4f6" stroke="#bbb"/>
    <text x="680" y="70" text-anchor="middle" font-weight="700">4. LEARN</text>
    <text x="680" y="90" text-anchor="middle">compare forecast</text><text x="680" y="106" text-anchor="middle">with what happened</text>
    <path d="M160,80 H198" stroke="#555" stroke-width="2" marker-end="url(#a)"/>
    <path d="M370,80 H408" stroke="#555" stroke-width="2" marker-end="url(#a)"/>
    <path d="M570,80 H608" stroke="#555" stroke-width="2" marker-end="url(#a)"/>
    <path d="M680,120 V150 H285 V122" fill="none" stroke="#2fa866" stroke-width="2" stroke-dasharray="5 4" marker-end="url(#a)"/>
    <text x="480" y="164" text-anchor="middle" fill="#2fa866" font-size="12">gets better every day</text>
  </g>
</svg>"""

MODEL = """
<svg viewBox="0 0 760 150" class="fig" role="img" aria-label="Physics plus AI model">
  <g font-family="Space Grotesk, Arial" font-size="13" fill="#111">
    <rect x="10" y="20" width="230" height="110" rx="6" fill="#fff7ea" stroke="#e0a14a"/>
    <text x="125" y="46" text-anchor="middle" font-weight="700">PHYSICS (the rule)</text>
    <text x="125" y="72" text-anchor="middle">people waiting next minute =</text>
    <text x="125" y="90" text-anchor="middle">now + arrived − treated</text>
    <text x="125" y="114" text-anchor="middle" fill="#777" font-size="12">always true, never breaks</text>
    <text x="270" y="82" text-anchor="middle" font-size="28" fill="#555">+</text>
    <rect x="300" y="20" width="230" height="110" rx="6" fill="#eef3ff" stroke="#5a7fd6"/>
    <text x="415" y="46" text-anchor="middle" font-weight="700">AI (what the rule misses)</text>
    <text x="415" y="72" text-anchor="middle">people giving up, slow doctors,</text>
    <text x="415" y="90" text-anchor="middle">surges, each place's habits</text>
    <text x="415" y="114" text-anchor="middle" fill="#777" font-size="12">learned from data</text>
    <text x="560" y="82" text-anchor="middle" font-size="28" fill="#555">=</text>
    <rect x="590" y="20" width="160" height="110" rx="6" fill="#e9f9ef" stroke="#2fa866"/>
    <text x="670" y="52" text-anchor="middle" font-weight="700">Forecast you</text>
    <text x="670" y="72" text-anchor="middle" font-weight="700">can trust</text>
    <text x="670" y="98" text-anchor="middle" font-size="12">accurate + explainable</text>
    <text x="670" y="114" text-anchor="middle" font-size="12">+ never impossible</text>
  </g>
</svg>"""

MAP = """
<svg viewBox="0 0 760 210" class="fig" role="img" aria-label="One engine, many sectors">
  <g font-family="Space Grotesk, Arial" font-size="13" fill="#111" text-anchor="middle">
    <circle cx="380" cy="105" r="62" fill="#111"/><text x="380" y="100" fill="#fff" font-weight="700">QueuePilot</text>
    <text x="380" y="118" fill="#9fe7bd" font-size="11">predict · plan · route</text>
    <g stroke="#bbb" stroke-width="1.5">
      <line x1="320" y1="80" x2="170" y2="35"/><line x1="320" y1="130" x2="170" y2="175"/><line x1="318" y1="105" x2="150" y2="105"/>
      <line x1="440" y1="80" x2="590" y2="35"/><line x1="440" y1="130" x2="590" y2="175"/><line x1="442" y1="105" x2="610" y2="105"/>
    </g>
    <g font-size="12">
      <rect x="40" y="16" width="160" height="38" rx="5" fill="#e9f9ef" stroke="#2fa866"/><text x="120" y="33" font-weight="700">Emergency care</text><text x="120" y="48">lives (our demo)</text>
      <rect x="20" y="86" width="140" height="38" rx="5" fill="#f3f4f6" stroke="#bbb"/><text x="90" y="103" font-weight="700">Hospital OPD / ER</text><text x="90" y="118">waiting patients</text>
      <rect x="40" y="156" width="160" height="38" rx="5" fill="#f3f4f6" stroke="#bbb"/><text x="120" y="173" font-weight="700">Crowds &amp; temples</text><text x="120" y="188">token counters, gates</text>
      <rect x="560" y="16" width="160" height="38" rx="5" fill="#f3f4f6" stroke="#bbb"/><text x="640" y="33" font-weight="700">EV charging hubs</text><text x="640" y="48">energy, battery physics</text>
      <rect x="600" y="86" width="140" height="38" rx="5" fill="#f3f4f6" stroke="#bbb"/><text x="670" y="103" font-weight="700">Perishable goods</text><text x="670" y="118">milk, concrete, cane</text>
      <rect x="560" y="156" width="160" height="38" rx="5" fill="#f3f4f6" stroke="#bbb"/><text x="640" y="173" font-weight="700">Banks, call centres</text><text x="640" y="188">tested on real data</text>
    </g>
  </g>
</svg>"""

HTML = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>QueuePilot Brief</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
  @page {{ size: A4; margin: 14mm 14mm 14mm 14mm; }}
  body {{ font-family: 'Space Grotesk', Arial, sans-serif; color:#111; font-size: 11.5pt; line-height: 1.5; margin:0; }}
  h1 {{ font-size: 26pt; margin: 0 0 2mm; letter-spacing:-0.5px; }}
  h2 {{ font-size: 14pt; margin: 6mm 0 2mm; border-bottom: 2px solid #111; padding-bottom: 1mm; }}
  .tag {{ font-family:'JetBrains Mono', monospace; font-size: 8.5pt; letter-spacing: 2px; color:#2fa866; }}
  .lead {{ font-size: 13pt; color:#333; margin: 0 0 3mm; }}
  .box {{ background:#f6f7f8; border-left: 4px solid #2fa866; padding: 3mm 4mm; margin: 3mm 0; }}
  .warn {{ border-left-color:#e0a14a; }}
  .fig {{ width:100%; height:auto; margin: 2mm 0; }}
  .shots {{ display:grid; grid-template-columns: 1fr 1fr; gap: 3mm; }}
  .shots figure {{ margin:0; }} .shots img {{ width:100%; border:1px solid #ccc; }}
  figcaption {{ font-size: 9pt; color:#555; margin-top:1mm; }}
  table {{ width:100%; border-collapse: collapse; font-size: 10.5pt; margin: 2mm 0; }}
  th, td {{ text-align:left; padding: 1.6mm 2mm; border-bottom: 1px solid #ddd; vertical-align: top; }}
  th {{ background:#111; color:#fff; font-weight:500; }}
  .num {{ font-family:'JetBrains Mono', monospace; }}
  .big {{ font-size: 22pt; font-weight:700; }}
  .g {{ color:#1f8f50; }} .o {{ color:#c27a12; }}
  .kpis {{ display:grid; grid-template-columns: repeat(3, 1fr); gap: 3mm; margin: 3mm 0; }}
  .kpis div {{ border:1px solid #ddd; padding: 3mm; }}
  .page {{ page-break-after: always; }}
  .qa p {{ margin: 0 0 2.5mm; }} .qa b {{ display:block; }}
  ul {{ margin: 1mm 0 1mm 5mm; padding:0; }} li {{ margin: 0.6mm 0; }}
</style></head><body>

<div class="page">
  <div class="tag">ZEROHOUR 2026 · TEAM COUNTER INTELLIGENCE · TRACK 3</div>
  <h1>QueuePilot: the City Emergency Brain</h1>
  <p class="lead">An AI that sees an emergency room overflowing <b>30 minutes before it happens</b>, and sends every patient to the hospital where a doctor will see them <b>first</b>, not just the one that is <b>closest</b>.</p>
  <div class="kpis">
    <div><b>01 ROUTE</b><br>every ambulance to the fastest treatment: drive time + waiting time</div>
    <div><b>02 RADAR</b><br>a physics-guided neural network predicts each ER 30 minutes ahead</div>
    <div><b>03 AUTOPILOT</b><br>acts on the radar: calls in off-duty doctors before the wave hits</div>
  </div>

  <h2>The problem, in one minute</h2>
  <ul>
    <li>A badly injured person has about <b>one hour</b> to get treatment. Doctors call this the <b>golden hour</b>.</li>
    <li>Today an ambulance drives to the <b>nearest</b> hospital. Nobody checks if that hospital is already full.</li>
    <li>When a bus crashes, every victim goes to the same hospital. It overflows. Hospitals ten minutes away sit half empty.</li>
    <li>In COVID's second wave, families drove from hospital to hospital looking for a bed. Some died on the way.</li>
  </ul>
  <div class="box"><b>Our idea:</b> before the ambulance leaves, predict the waiting time at every hospital.
  Send the patient where <b>drive time + waiting time</b> is shortest.</div>

  <h2>What the demo shows (same city, same emergency calls, three ways)</h2>
  <div class="shots">
    <figure><img src="{img('radar.png')}"><figcaption><b>Five minutes after a bus crash.</b> Nobody is waiting at East yet, but the AI radar already warns: <b>"18 waiting in 30 min"</b>. Today, nobody acts on that.</figcaption></figure>
    <figure><img src="{img('autopilot.png')}"><figcaption><b>Festival crowd crush, Routing + AI Autopilot.</b> As soon as the radar saw the wave coming, it called in 2 off-duty doctors at each hospital in its path (green ticks).</figcaption></figure>
  </div>
  <table>
    <tr><th>Patients who missed the golden hour<br>(one afternoon, ~150-190 emergencies)</th><th>Today:<br>nearest hospital</th><th>Smart<br>routing</th><th>Routing +<br>AI Autopilot</th></tr>
    <tr><td><b>Festival crowd crush</b> (45 hurt)</td><td class="num">43-46</td><td class="num">15-32</td><td class="num"><b>1-3</b></td></tr>
    <tr><td>Building collapse (40 hurt)</td><td class="num">48-59</td><td class="num">4-7</td><td class="num"><b>1-5</b></td></tr>
    <tr><td>Bus crash (28 hurt)</td><td class="num">26-37</td><td class="num">0</td><td class="num"><b>0</b></td></tr>
    <tr><td>Normal day</td><td class="num">0</td><td class="num">0</td><td class="num"><b>0, no false alarms</b></td></tr>
  </table>
  <p style="font-size:9.5pt;color:#555">Ranges = 3 different random days per scenario. Simulated city with 6 hospitals; nothing is tuned per scenario.
  In the worst disaster, smart routing alone is not enough. The AI radar sees the wave 30 minutes early and calls in doctors, which saves almost everyone else.
  Fair note: Autopilot uses extra staff (2 called-in doctors per alert; 8-12 in the crowd crush, 0 on a normal day).</p>
</div>

<div class="page">
  <h2>How it works</h2>
  {FLOW}
  <h2>The brain: physics + AI together</h2>
  {MODEL}
  <table>
    <tr><th>Radar test (150 days it never saw)</th><th>Error when an ER is filling up<br>(people, 30 min ahead)</th><th>On a hospital it never saw</th><th>Explains its answer?</th></tr>
    <tr><td>Physics only</td><td class="num">3.95</td><td class="num">4.43</td><td>yes, but too simple</td></tr>
    <tr><td>AI only (neural network)</td><td class="num">3.17</td><td class="num">3.68</td><td>no, black box</td></tr>
    <tr><td><b>Physics + AI (ours)</b></td><td class="num"><b>3.21</b></td><td class="num"><b>3.59 (best)</b></td><td><b>yes: "I expect N new patients"</b></td></tr>
  </table>
  <p style="font-size:9.5pt;color:#555">Trained on 900 simulated days (223,200 snapshots), tested on 150 new days. The same trained network runs live inside the demo.
  Honest reading: AI cuts the physics error by about a fifth; ours matches pure AI on known hospitals, is best on a new one, and can explain itself ("I expect N new patients").</p>
  <p>Pure AI can make impossible predictions (like a negative queue) and breaks when something new happens.
  Pure physics is too simple: it does not know people give up and leave, or that every hospital behaves differently.
  We use <b>both</b>, the way the research paper suggests. The AI part is <b>only allowed</b> to do things that are physically possible:
  it can slow service down or let waiting people leave, but it can never invent or delete patients.</p>

  <h2>The research paper and the gap we fill</h2>
  <p><b>Paper:</b> Rose Yu &amp; Rui Wang, <i>"Learning dynamical systems from data: An introduction to physics-guided deep learning"</i>, PNAS 2024.
  It shows how to mix physics with deep learning. At the end it lists problems that are still <b>open</b>:</p>
  <table>
    <tr><th>Open problem in the paper</th><th>In simple words</th><th>What we do</th></tr>
    <tr><td>Generalisation (§4A)</td><td>AI fails on situations it never saw</td><td>Tested on days with fewer staff and 50% more patients than training. A new place is learned from <b>one day</b> of data.</td></tr>
    <tr><td>Stability (§4B)</td><td>No guarantee the AI's answers make sense</td><td>The AI is boxed in by physics, so every prediction is physically possible <b>by design</b>.</td></tr>
    <tr><td>Uncertainty (§4C)</td><td>AI is over-confident</td><td>We give a range, and check that reality falls inside it about 90% of the time.</td></tr>
    <tr><td>Explainability (§3A)</td><td>The AI part is a black box</td><td>Our AI outputs real things: "chance a waiting person gives up per minute".</td></tr>
  </table>
  <div class="box"><b>The big gap:</b> every example in the paper is about <b>nature</b>: fluids, climate, lakes, drones, epidemics.
  Nobody has used physics-guided deep learning for <b>systems run by people</b>: hospitals, queues, crowds. That is what we do.</div>
  <div class="box"><b>Something new we found:</b> from queue lengths alone, "people gave up" and "service got slower" look exactly the same.
  The paper does not mention this. Fix: also learn from records of who left (call-centre hang-ups, "left without being seen" in hospitals).</div>
  <div class="box warn"><b>Tested on real data:</b> 300,000 real calls from a bank call centre (Technion SEE "Anonymous Bank" dataset).
  Our model learned that callers hang up at <b class="num">0.14–0.15 per minute</b>. The real, measured rate is <b class="num">0.156</b>.
  The AI learned real human patience, and we can read it. <i>Honest note:</i> a pure data model is still slightly more accurate on raw queue length (2.7 vs 3.1); our edge is trust and explainability.</div>
</div>

<div>
  <h2>One engine, many sectors</h2>
  {MAP}
  <p>Anything where things <b>arrive, wait and get served</b> is the same problem: patients and doctors, cars and chargers, trucks of milk and factories.
  Waiting destroys something every time: <b>lives</b>, <b>energy</b> or <b>money</b>. QueuePilot only needs one simple table to start:
  <span class="num">arrived · started · finished (or left) · who served</span>.</p>

  <h2>Cheat sheet for judges' questions</h2>
  <div class="qa">
    <p><b>What is the use case?</b> City emergency care. Send each ambulance to the hospital where treatment starts soonest. Same idea works for hospitals, crowds, EV hubs, perishable goods.</p>
    <p><b>What is the research gap?</b> Physics-guided deep learning has only been used for nature. We bring it to systems run by people, and tackle four problems the paper itself calls open: new situations, stability, uncertainty and explainability.</p>
    <p><b>Why not just use AI?</b> Plain AI can predict impossible things and breaks on new situations. In an emergency you need answers that always make sense. Physics guarantees that.</p>
    <p><b>Why not just use physics?</b> Physics does not know people give up, or that each hospital is different. The AI learns that.</p>
    <p><b>Where is the graph theory?</b> The city is a graph of incidents, roads and hospitals. Each patient is matched to a hospital by the shortest "drive + wait" time. Next step: min-cut on this graph to show the city's real bottleneck.</p>
    <p><b>Is it real?</b> The demo city is simulated so we can measure everything. The forecasting method is tested on 300,000 real bank calls.</p>
    <p><b>Who pays?</b> State ambulance services (108), hospital chains, smart-city control rooms. Every other day, the same engine cuts waiting in OPDs, banks and offices.</p>
  </div>
</div>
</body></html>"""

(HERE / "QueuePilot_Brief.html").write_text(HTML, encoding="utf-8")
print("wrote", HERE / "QueuePilot_Brief.html")
