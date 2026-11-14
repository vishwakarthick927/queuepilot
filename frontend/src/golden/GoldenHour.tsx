import { useEffect, useMemo, useState } from 'react'
import { CITY, CRASH, GOLDEN, MINUTES, clock, simulate, snapshot, summary, type Policy } from './sim'

const SCALE = 46                       // px per km on the map
const W = CITY.w * SCALE, H = CITY.h * SCALE
const TICK_MS = 120                    // real ms per simulated minute while playing

// Major roads, drawn only for orientation.
const ROADS = [
  'M0,322 L920,322', 'M460,0 L460,644', 'M0,140 C250,170 620,90 920,230', 'M120,644 C260,420 640,420 820,0',
  'M60,60 C300,40 760,60 860,380 C900,520 700,620 380,610 C150,600 40,480 60,60',
]

export default function GoldenHour() {
  // ?policy=queuepilot&t=180 opens a given moment (handy for demos and screenshots)
  const q = new URLSearchParams(window.location.search)
  const [policy, setPolicy] = useState<Policy>(q.get('policy') === 'queuepilot' ? 'queuepilot' : 'nearest')
  const [t, setT] = useState(() => Math.min(MINUTES - 1, Number(q.get('t')) || CRASH.t - 20))
  const [playing, setPlaying] = useState(false)

  // Both worlds are simulated once, from the same calls.
  const runs = useMemo(() => ({ nearest: simulate('nearest'), queuepilot: simulate('queuepilot') }), [])
  const finals = useMemo(() => ({ nearest: summary(runs.nearest), queuepilot: summary(runs.queuepilot) }), [runs])
  const snap = snapshot(runs[policy], t)
  const other = snapshot(runs[policy === 'nearest' ? 'queuepilot' : 'nearest'], t)

  useEffect(() => {
    if (!playing) return
    const id = setInterval(() => setT((x) => (x >= MINUTES - 1 ? (setPlaying(false), x) : x + 1)), TICK_MS)
    return () => clearInterval(id)
  }, [playing])

  const crashOn = t >= CRASH.t
  const ours = policy === 'queuepilot'
  const accent = ours ? 'var(--color-qp)' : 'var(--color-base)'
  const near = policy === 'nearest' ? snap : other, qp = ours ? snap : other

  return (
    <div className="mx-auto flex min-h-screen max-w-[1440px] flex-col px-4 py-5 md:px-8">
      {/* ---------- header ---------- */}
      <header className="flex flex-wrap items-center justify-between gap-4 pb-5">
        <div>
          <div className="num text-[11px] tracking-[0.2em] text-faint">QUEUEPILOT · GOLDEN HOUR</div>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight md:text-3xl">
            Send every patient where they'll be <span style={{ color: 'var(--color-qp)' }}>treated</span> first, not where's closest.
          </h1>
        </div>
        <div className="flex items-center gap-2 border border-line-strong p-1" role="tablist" aria-label="Routing policy">
          {(['nearest', 'queuepilot'] as Policy[]).map((p) => (
            <button key={p} role="tab" aria-selected={policy === p} onClick={() => setPolicy(p)}
              className={`cursor-pointer px-4 py-2 text-sm transition-colors duration-150 ${policy === p ? (p === 'queuepilot' ? 'bg-qp text-bg' : 'bg-ink text-bg') : 'text-dim hover:text-ink'}`}>
              {p === 'nearest' ? 'Today: nearest hospital' : 'With QueuePilot'}
            </button>
          ))}
        </div>
      </header>

      <div className="grid flex-1 gap-5 lg:grid-cols-[1fr_340px]">
        {/* ---------- the city ---------- */}
        <div className="relative border border-line bg-panel">
          <div className="num absolute left-4 top-3 z-10 flex items-baseline gap-3">
            <span className="text-3xl text-ink">{clock(t)}</span>
            <span className="text-xs text-faint">{snap.ambulances.length} ambulances on the road</span>
          </div>
          {crashOn && t < CRASH.t + 40 && (
            <div className="num absolute right-4 top-3 z-10 border border-alert/60 bg-alert/10 px-3 py-1.5 text-xs text-alert">
              {clock(CRASH.t)} · {CRASH.label} · {CRASH.n} injured
            </div>
          )}
          <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img" aria-label="City map with hospitals and ambulances">
            {ROADS.map((d) => <path key={d} d={d} fill="none" stroke="var(--color-line-strong)" strokeWidth="6" strokeLinecap="round" opacity="0.55" />)}

            {/* crash site */}
            {crashOn && (
              <g transform={`translate(${CRASH.x * SCALE},${CRASH.y * SCALE})`}>
                <circle r="30" fill="var(--color-alert)" opacity="0.12" />
                <circle r="9" fill="none" stroke="var(--color-alert)" strokeWidth="2" />
                <path d="M-4,-4 L4,4 M4,-4 L-4,4" stroke="var(--color-alert)" strokeWidth="2" />
              </g>
            )}

            {/* ambulances: line to their hospital + dot */}
            {snap.ambulances.map((a) => (
              <g key={a.id}>
                <line x1={a.x * SCALE} y1={a.y * SCALE} x2={a.to.x * SCALE} y2={a.to.y * SCALE} stroke={accent} strokeOpacity="0.22" strokeDasharray="3 4" />
                <circle cx={a.x * SCALE} cy={a.y * SCALE} r={a.surge ? 5 : 4} fill={a.loading ? 'var(--color-ink)' : accent} />
              </g>
            ))}

            {/* hospitals */}
            {snap.hospitals.map((h) => {
              const risk = h.forecastWait >= GOLDEN / 2 ? 'alert' : h.forecastWait >= 15 ? 'base' : 'line-strong'
              const x = h.x * SCALE, y = h.y * SCALE
              return (
                <g key={h.id} transform={`translate(${x},${y})`}>
                  {risk === 'alert' && <circle r="44" fill="var(--color-alert)" opacity="0.14"><animate attributeName="r" values="38;48;38" dur="1.6s" repeatCount="indefinite" /></circle>}
                  <rect x="-22" y="-22" width="44" height="44" fill="var(--color-bg)" stroke={`var(--color-${risk})`} strokeWidth="2" />
                  <path d="M-6,0 H6 M0,-6 V6" stroke="var(--color-ink)" strokeWidth="2.5" />
                  {/* one tick per doctor: lit = treating someone */}
                  {Array.from({ length: h.doctors }, (_, k) => (
                    <rect key={k} x={-22 + k * (44 / h.doctors) + 2} y="26" width={44 / h.doctors - 4} height="4"
                      fill={k < h.busy ? 'var(--color-ink)' : 'var(--color-line-strong)'} />
                  ))}
                  <text y="-30" textAnchor="middle" className="num" fontSize="12" fill="var(--color-dim)">{h.name}</text>
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
          <Legend accent={accent} />
        </div>

        {/* ---------- what it means ---------- */}
        <aside className="flex flex-col gap-5">
          <div className="border border-line bg-panel p-5">
            <div className="text-sm text-dim">Patients waiting 30+ min for a doctor <span className="text-faint">right now</span></div>
            <div className="mt-4 grid grid-cols-2 gap-4">
              <Big label="Nearest hospital" value={near.atRisk} color="var(--color-base)" active={policy === 'nearest'} />
              <Big label="QueuePilot" value={qp.atRisk} color="var(--color-qp)" active={ours} />
            </div>
            <div className="num mt-3 text-xs text-faint">Missed the golden hour so far: <span className="text-base">{near.lateSoFar}</span> vs <span className="text-qp">{qp.lateSoFar}</span></div>
            <p className="mt-4 border-t border-line pt-3 text-xs leading-relaxed text-dim">
              Full afternoon, {finals.nearest.patients} emergencies: <span className="text-base">{finals.nearest.late}</span> late today vs{' '}
              <span className="text-qp">{finals.queuepilot.late}</span> with QueuePilot. Of the {CRASH.n} crash victims:{' '}
              <span className="text-base">{finals.nearest.surgeLate}</span> vs <span className="text-qp">{finals.queuepilot.surgeLate}</span>.
            </p>
          </div>

          <div className="border border-line bg-panel p-5">
            <div className="text-sm text-dim">Forecast wait for the next patient</div>
            <div className="mt-3 space-y-2.5">
              {snap.hospitals.map((h) => {
                const pct = Math.min(1, h.forecastWait / GOLDEN)
                const c = h.forecastWait >= GOLDEN / 2 ? 'var(--color-alert)' : h.forecastWait >= 15 ? 'var(--color-base)' : 'var(--color-dim)'
                return (
                  <div key={h.id} className="grid grid-cols-[80px_1fr_52px] items-center gap-3">
                    <span className="text-sm">{h.name}</span>
                    <div className="h-1.5 bg-line"><div className="h-full transition-[width] duration-200" style={{ width: `${pct * 100}%`, background: c }} /></div>
                    <span className="num text-right text-xs" style={{ color: c }}>{Math.round(h.forecastWait)} min</span>
                  </div>
                )
              })}
            </div>
            <p className="mt-3 text-[11px] leading-relaxed text-faint">
              Forecast = everyone waiting or on the way ÷ doctors × treatment time. Red = the golden hour is at risk.
            </p>
          </div>

          <div className="border border-line bg-panel p-5 text-xs leading-relaxed text-dim">
            <span className="text-ink">{ours ? 'QueuePilot' : 'Today'}:</span>{' '}
            {ours
              ? 'every ambulance is sent to the hospital where treatment starts soonest = drive time + forecast wait. The crash victims are spread across Central, Ring Road and North.'
              : 'every ambulance goes to the closest hospital. After the crash, East gets every victim while hospitals 10 minutes away sit half empty.'}
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
          <span className="pointer-events-none absolute -top-3 h-3 w-px bg-alert" style={{ left: `${(CRASH.t / MINUTES) * 100}%` }} />
        </div>
        <span className="num text-xs text-faint">{clock(MINUTES)}</span>
        <button onClick={() => { setPlaying(false); setT(CRASH.t - 5) }}
          className="num cursor-pointer border border-alert/50 px-3 py-2 text-xs tracking-widest text-alert transition-colors duration-150 hover:bg-alert/10">
          JUMP TO CRASH
        </button>
      </div>
      <footer className="num mt-4 flex flex-wrap justify-between gap-2 text-[11px] text-faint">
        <span>Same calls in both worlds · simulated city · physics-guided forecasting after Yu &amp; Wang, PNAS 2024</span>
        <a href="?view=engine" className="hover:text-ink">Engine room →</a>
      </footer>
    </div>
  )
}

function Big({ label, value, color, active }: { label: string; value: number; color: string; active: boolean }) {
  return (
    <div className={`border p-3 ${active ? 'border-line-strong' : 'border-transparent'}`}>
      <div className="num text-5xl leading-none" style={{ color }}>{value}</div>
      <div className="mt-2 text-xs text-dim">{label}</div>
    </div>
  )
}

function Legend({ accent }: { accent: string }) {
  return (
    <div className="num flex flex-wrap gap-x-5 gap-y-1 border-t border-line px-4 py-2.5 text-[11px] text-faint">
      <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full" style={{ background: accent }} />ambulance with patient</span>
      <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-ink" />picking up</span>
      <span>▮ doctor busy</span>
      <span className="flex items-center gap-1.5"><span className="inline-block h-3 w-4 bg-raised text-center text-[9px] leading-3 text-ink">3</span>waiting in ER</span>
      <span className="text-alert">red ring = golden hour at risk</span>
    </div>
  )
}
