import { useEffect, useMemo, useState } from 'react'
import { CITY, GOLDEN, MINUTES, clock, simulate, snapshot, summary, type Crash, type Extra, type Patient } from './sim'
import { CALL_IN, RADAR_ALERT, hospitalName, radarAlerts, simulateAutopilot } from './autopilot'
import { RADAR_RESULTS, radar } from './radar'

const SCALE = 46                       // px per km on the map
const W = CITY.w * SCALE, H = CITY.h * SCALE
const TICK_MS = 120                    // real ms per simulated minute while playing
const SEED = 7

// Major roads, drawn only for orientation.
const ROADS = [
  'M0,322 L920,322', 'M460,0 L460,644', 'M0,140 C250,170 620,90 920,230', 'M120,644 C260,420 640,420 820,0',
  'M60,60 C300,40 760,60 860,380 C900,520 700,620 380,610 C150,600 40,480 60,60',
]

// Four afternoons. Same engine, nothing tuned per scenario.
const SCENARIOS: Record<string, { name: string; crash: Crash | null; rate: number }> = {
  festival: { name: 'Festival crowd crush', rate: 2.0, crash: { t: 200, x: 9.6, y: 11.4, n: 45, label: 'Crowd crush at festival grounds, South' } },
  collapse: { name: 'Building collapse', rate: 2.4, crash: { t: 120, x: 10.6, y: 7.6, n: 40, label: 'Building collapse, Old City' } },
  bus: { name: 'Bus crash', rate: 2.4, crash: { t: 150, x: 15.6, y: 4.6, n: 28, label: 'Bus crash, Outer Ring Road' } },
  normal: { name: 'Normal day', rate: 2.4, crash: null },
}

// The three ways to run the city.
const MODES = {
  nearest: { label: 'Today: nearest hospital', short: 'Today', color: 'var(--color-base)' },
  route: { label: 'Smart routing', short: 'Routing', color: 'var(--color-route)' },
  autopilot: { label: 'Routing + AI Autopilot', short: 'Autopilot', color: 'var(--color-qp)' },
} as const
type Mode = keyof typeof MODES
const MODE_KEYS = Object.keys(MODES) as Mode[]

export default function GoldenHour() {
  // URL presets for demos: ?scenario=festival&mode=autopilot&t=215
  const q = new URLSearchParams(window.location.search)
  const [scenarioKey, setScenarioKey] = useState(q.get('scenario') && SCENARIOS[q.get('scenario')!] ? q.get('scenario')! : 'festival')
  const [mode, setMode] = useState<Mode>(MODE_KEYS.includes(q.get('mode') as Mode) ? (q.get('mode') as Mode) : 'nearest')
  const sc = SCENARIOS[scenarioKey]
  const [t, setT] = useState(() => Math.min(MINUTES - 1, Number(q.get('t')) || (sc.crash ? sc.crash.t - 15 : 60)))
  const [playing, setPlaying] = useState(false)

  // All three worlds, same calls.
  const worlds = useMemo(() => {
    const ap = simulateAutopilot(SEED, sc.crash, sc.rate)
    const ps: Record<Mode, Patient[]> = { nearest: simulate('nearest', SEED, sc.crash, sc.rate), route: simulate('queuepilot', SEED, sc.crash, sc.rate), autopilot: ap.ps }
    const extra: Record<Mode, Extra[]> = { nearest: [], route: [], autopilot: ap.extra }
    // Autopilot's feed = the alerts that actually called doctors in; the others = what the radar saw in that world.
    const alerts = { nearest: radarAlerts(ps.nearest), route: radarAlerts(ps.route), autopilot: ap.alerts }
    const finals = Object.fromEntries(MODE_KEYS.map((m) => [m, summary(ps[m])])) as Record<Mode, ReturnType<typeof summary>>
    return { ps, extra, alerts, finals }
  }, [sc])

  useEffect(() => {
    if (!playing) return
    const id = setInterval(() => setT((x) => (x >= MINUTES - 1 ? (setPlaying(false), x) : x + 1)), TICK_MS)
    return () => clearInterval(id)
  }, [playing])

  const snaps = Object.fromEntries(MODE_KEYS.map((m) => [m, snapshot(worlds.ps[m], t, worlds.extra[m])])) as Record<Mode, ReturnType<typeof snapshot>>
  const snap = snaps[mode]
  const radars = snap.hospitals.map((h) => radar(h, snap.calls15, t))
  const accent = MODES[mode].color
  const crash = sc.crash
  const crashOn = !!crash && t >= crash.t
  const arrivedDocs = (id: string) => worlds.extra[mode].filter((e) => e.hospital === id && e.t <= t).length
  const feed = worlds.alerts[mode].filter((a) => a.t <= t).slice(-4).reverse()

  const pickScenario = (k: string) => {
    setPlaying(false); setScenarioKey(k)
    const c = SCENARIOS[k].crash
    setT(c ? c.t - 15 : 60)
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-[1440px] flex-col px-4 py-5 md:px-8">
      {/* ---------- header ---------- */}
      <header className="flex flex-wrap items-end justify-between gap-4 pb-4">
        <div>
          <div className="num text-[11px] tracking-[0.2em] text-faint">QUEUEPILOT · CITY EMERGENCY BRAIN</div>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight md:text-3xl">
            See the overflow <span className="text-route">30 minutes early</span>. Get every patient to a doctor <span className="text-qp">in the golden hour</span>.
          </h1>
          <div className="num mt-3 flex flex-wrap gap-x-6 gap-y-1 text-[11px] tracking-wider text-dim">
            <span><span className="text-qp">01 ROUTE</span> every ambulance to the fastest treatment</span>
            <span><span className="text-route">02 RADAR</span> physics-guided AI predicts each ER 30 min ahead</span>
            <span><span className="text-qp">03 AUTOPILOT</span> calls in doctors before the wave hits</span>
          </div>
        </div>
      </header>

      {/* ---------- scenario + mode ---------- */}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Scenario">
          {Object.entries(SCENARIOS).map(([k, s]) => (
            <button key={k} role="tab" aria-selected={k === scenarioKey} onClick={() => pickScenario(k)}
              className={`num cursor-pointer border px-3 py-1.5 text-xs transition-colors duration-150 ${k === scenarioKey ? 'border-ink text-ink' : 'border-line-strong text-dim hover:text-ink'}`}>
              {s.name}{s.crash ? ` · ${s.crash.n} hurt` : ''}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1 border border-line-strong p-1" role="tablist" aria-label="How the city is run">
          {MODE_KEYS.map((m) => (
            <button key={m} role="tab" aria-selected={mode === m} onClick={() => setMode(m)}
              className="cursor-pointer px-3.5 py-2 text-sm transition-colors duration-150"
              style={mode === m ? { background: MODES[m].color, color: 'var(--color-bg)' } : { color: 'var(--color-dim)' }}>
              {MODES[m].label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid flex-1 gap-5 lg:grid-cols-[1fr_350px]">
        {/* ---------- the city ---------- */}
        <div className="relative self-start border border-line bg-panel">
          <div className="num absolute left-4 top-3 z-10 flex items-baseline gap-3">
            <span className="text-3xl text-ink">{clock(t)}</span>
            <span className="text-xs text-faint">{snap.ambulances.length} ambulances on the road</span>
          </div>
          {crash && crashOn && t < crash.t + 45 && (
            <div className="num absolute right-4 top-3 z-10 border border-alert/60 bg-alert/10 px-3 py-1.5 text-xs text-alert">
              {clock(crash.t)} · {crash.label} · {crash.n} injured
            </div>
          )}
          <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img" aria-label="City map with hospitals and ambulances">
            {ROADS.map((d) => <path key={d} d={d} fill="none" stroke="var(--color-line-strong)" strokeWidth="6" strokeLinecap="round" opacity="0.55" />)}

            {crash && crashOn && (
              <g transform={`translate(${crash.x * SCALE},${crash.y * SCALE})`}>
                <circle r="30" fill="var(--color-alert)" opacity="0.12" />
                <circle r="9" fill="none" stroke="var(--color-alert)" strokeWidth="2" />
                <path d="M-4,-4 L4,4 M4,-4 L-4,4" stroke="var(--color-alert)" strokeWidth="2" />
              </g>
            )}

            {snap.ambulances.map((a) => (
              <g key={a.id}>
                <line x1={a.x * SCALE} y1={a.y * SCALE} x2={a.to.x * SCALE} y2={a.to.y * SCALE} stroke={accent} strokeOpacity="0.22" strokeDasharray="3 4" />
                <circle cx={a.x * SCALE} cy={a.y * SCALE} r={a.surge ? 5 : 4} fill={a.loading ? 'var(--color-ink)' : accent} />
              </g>
            ))}

            {snap.hospitals.map((h, i) => {
              const risk = h.forecastWait >= GOLDEN / 2 ? 'alert' : h.forecastWait >= 15 ? 'base' : 'line-strong'
              const extra = arrivedDocs(h.id)
              return (
                <g key={h.id} transform={`translate(${h.x * SCALE},${h.y * SCALE})`}>
                  {risk === 'alert' && <circle r="44" fill="var(--color-alert)" opacity="0.14"><animate attributeName="r" values="38;48;38" dur="1.6s" repeatCount="indefinite" /></circle>}
                  {radars[i].forecast >= RADAR_ALERT && (
                    <g>
                      <circle r="58" fill="none" stroke="var(--color-route)" strokeWidth="1.5" strokeDasharray="4 5">
                        <animateTransform attributeName="transform" type="rotate" from="0" to="360" dur="8s" repeatCount="indefinite" />
                      </circle>
                      <text y="74" textAnchor="middle" className="num" fontSize="11" fill="var(--color-route)">AI: {Math.round(radars[i].forecast)} waiting in 30 min</text>
                    </g>
                  )}
                  <rect x="-22" y="-22" width="44" height="44" fill="var(--color-bg)" stroke={`var(--color-${risk})`} strokeWidth="2" />
                  <path d="M-6,0 H6 M0,-6 V6" stroke="var(--color-ink)" strokeWidth="2.5" />
                  {/* one tick per doctor: lit = treating someone; green = called in by Autopilot */}
                  {Array.from({ length: h.doctors }, (_, k) => {
                    const w = 52 / h.doctors
                    return <rect key={k} x={-26 + k * w + 1.5} y="27" width={w - 3} height="4"
                      fill={k >= h.doctors - extra ? 'var(--color-qp)' : k < h.busy ? 'var(--color-ink)' : 'var(--color-line-strong)'} />
                  })}
                  <text y="-30" textAnchor="middle" className="num" fontSize="12" fill="var(--color-dim)">{h.name}</text>
                  {extra > 0 && <text y="44" textAnchor="middle" className="num" fontSize="10" fill="var(--color-qp)">+{extra} doctors</text>}
                  {h.waiting > 0 && (
                    <g transform="translate(26,-26)">
                      <rect x="0" y="-10" width={h.waiting > 9 ? 30 : 22} height="20" fill={`var(--color-${risk === 'line-strong' ? 'raised' : risk})`} />
                      <text x={h.waiting > 9 ? 15 : 11} y="4" textAnchor="middle" className="num" fontSize="12" fill={risk === 'line-strong' ? 'var(--color-ink)' : 'var(--color-bg)'}>{h.waiting}</text>
                    </g>
                  )}
                </g>
              )
            })}
          </svg>
          <div className="num flex flex-wrap gap-x-5 gap-y-1 border-t border-line px-4 py-2.5 text-[11px] text-faint">
            <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full" style={{ background: accent }} />ambulance with patient</span>
            <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-ink" />picking up</span>
            <span>▮ doctor busy · <span className="text-qp">▮ called in</span></span>
            <span className="text-route">blue ring = AI radar warning</span>
            <span className="text-alert">red = golden hour at risk</span>
          </div>
        </div>

        {/* ---------- side panel ---------- */}
        <aside className="flex flex-col gap-4">
          <div className="border border-line bg-panel p-5">
            <div className="text-sm text-dim">Patients waiting 30+ min for a doctor, <span className="text-ink">right now</span></div>
            <div className="mt-3 grid grid-cols-3 gap-2">
              {MODE_KEYS.map((m) => (
                <div key={m} className={`border p-2.5 ${m === mode ? 'border-line-strong' : 'border-transparent'}`}>
                  <div className="num text-4xl leading-none" style={{ color: MODES[m].color }}>{snaps[m].atRisk}</div>
                  <div className="mt-1.5 text-[11px] text-dim">{MODES[m].short}</div>
                </div>
              ))}
            </div>
            <div className="mt-3 border-t border-line pt-3 text-xs text-dim">
              Missed the golden hour, whole afternoon:
              <div className="num mt-1.5 flex gap-4 text-lg">
                {MODE_KEYS.map((m) => <span key={m} style={{ color: MODES[m].color }}>{worlds.finals[m].late}</span>)}
                <span className="self-end text-[11px] text-faint">of {worlds.finals.nearest.patients} emergencies</span>
              </div>
            </div>
          </div>

          <div className="border border-line bg-panel p-5">
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-sm text-dim"><span className="num text-route">RADAR</span> · waiting now → in 30 min</span>
              <span className="num shrink-0 text-[10px] text-faint">PHYSICS + AI</span>
            </div>
            <div className="mt-3 space-y-2.5">
              {snap.hospitals.map((h, i) => {
                const r = radars[i], max = 20
                return (
                  <div key={h.id} className="grid grid-cols-[76px_1fr_64px] items-center gap-3">
                    <span className="text-sm">{h.name}</span>
                    <div className="flex h-1.5 bg-line">
                      <div style={{ width: `${Math.min(100, ((r.forecast - r.newArrivals) / max) * 100)}%`, background: 'var(--color-dim)' }} />
                      <div style={{ width: `${Math.min(100, (r.newArrivals / max) * 100)}%`, background: 'var(--color-route)' }} />
                    </div>
                    <span className={`num text-right text-xs ${r.forecast >= RADAR_ALERT ? 'text-route' : 'text-dim'}`}>{h.waiting} → {Math.round(r.forecast)}</span>
                  </div>
                )
              })}
            </div>
            <p className="mt-3 text-[11px] leading-relaxed text-faint">
              Grey = what physics knows (waiting + ambulances on the way). <span className="text-route">Blue</span> = new patients the neural network expects who have not called yet.
            </p>
          </div>

          <div className="border border-line bg-panel p-5">
            <div className="text-sm text-dim"><span className="num text-qp">AUTOPILOT</span> · {mode === 'autopilot' ? 'acting on the radar' : mode === 'route' ? 'routing only, no staff changes' : 'today nobody acts'}</div>
            <ul className="mt-3 space-y-2.5">
              {feed.length === 0 && <li className="text-xs text-faint">Quiet. The radar sees no ER filling up.</li>}
              {feed.map((a) => (
                <li key={a.t + a.hospital} className="text-xs leading-relaxed">
                  <span className="num text-faint">{clock(a.t)}</span>{' '}
                  <span className="text-route">{hospitalName(a.hospital)}</span> <span className="text-dim">will have {a.n} waiting.</span>{' '}
                  {mode === 'autopilot' && <span className="text-qp">Called in {CALL_IN.doctors} off-duty doctors, on duty at {clock(a.t + CALL_IN.delay)}.</span>}
                  {mode === 'route' && <span className="text-route">New ambulances steered away.</span>}
                  {mode === 'nearest' && <span className="text-base">No action. Ambulances keep arriving.</span>}
                </li>
              ))}
            </ul>
          </div>

          <div className="border border-line bg-panel p-5 text-xs leading-relaxed text-dim">
            <div className="num mb-2 text-[11px] tracking-wider text-faint">THE AI, TESTED ON 150 UNSEEN DAYS</div>
            When an ER is filling up, physics alone is off by <span className="num text-base">{RADAR_RESULTS['new days']['Physics only'].ER_filling_up}</span> people,
            physics + AI by <span className="num text-qp">{RADAR_RESULTS['new days']['Physics + AI (ours)'].ER_filling_up}</span>.
            On a hospital it never saw: <span className="num text-base">{RADAR_RESULTS['hospital never seen (Ring Road)']['Physics only'].ER_filling_up}</span> →{' '}
            <span className="num text-qp">{RADAR_RESULTS['hospital never seen (Ring Road)']['Physics + AI (ours)'].ER_filling_up}</span>.
            Unlike a black box, it explains itself: the blue part of each bar is how many new patients it expects.
          </div>
        </aside>
      </div>

      {/* ---------- timeline ---------- */}
      <div className="mt-5 flex items-center gap-4 border border-line bg-panel px-5 py-4">
        <button onClick={() => { if (t >= MINUTES - 1) setT(0); setPlaying((p) => !p) }}
          className="num w-24 cursor-pointer border border-qp/60 py-2 text-xs tracking-widest text-qp transition-colors duration-150 hover:bg-qp/10">
          {playing ? 'PAUSE' : 'PLAY'}
        </button>
        <span className="num text-xs text-faint">{clock(0)}</span>
        <div className="relative flex-1">
          <input type="range" aria-label="Time of day" className="w-full cursor-pointer" min={0} max={MINUTES - 1} value={t}
            onChange={(e) => { setPlaying(false); setT(Number(e.target.value)) }} />
          {crash && <span className="pointer-events-none absolute -top-3 h-3 w-px bg-alert" style={{ left: `${(crash.t / MINUTES) * 100}%` }} />}
        </div>
        <span className="num text-xs text-faint">{clock(MINUTES)}</span>
        {crash && (
          <button onClick={() => { setPlaying(false); setT(crash.t - 2) }}
            className="num cursor-pointer border border-alert/50 px-3 py-2 text-xs tracking-widest text-alert transition-colors duration-150 hover:bg-alert/10">
            JUMP TO DISASTER
          </button>
        )}
      </div>
      <footer className="num mt-4 flex flex-wrap justify-between gap-2 text-[11px] text-faint">
        <span>Same calls in all three worlds · simulated city · physics-guided deep learning after Yu &amp; Wang, PNAS 2024</span>
        <a href="?view=engine" className="hover:text-ink">Engine room →</a>
      </footer>
    </div>
  )
}
