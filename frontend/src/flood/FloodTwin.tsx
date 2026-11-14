import { useEffect, useMemo, useRef, useState } from 'react'
import twin from './twin.json'
import evac from './evac_results.json'

// Everything here was computed by research/flood/twin.py (physics + the trained CNN) and is played back.
type Group = {
  zone: number; depart: number | null; path: number[][]; times: number[]
  shelter: number | null; arrive: number | null; start: number | null
  trapped: { t: number; x: number; y: number; where: string } | null
}
type Mode = 'today' | 'queuepilot'
const T = twin as unknown as {
  nx: number; ny: number; steps: number; step_min: number; flood_m: number; group: number
  z: number[][]; river: number[][]; eff_true: number[][]; eff_learned: number[][]
  depth_cm: number[][][]; rain_mmh: number[][][]; ai_soon: number[][]; physics_soon: number[][]
  nodes: number[][]; edges: number[][]; edge_flood_step: (number | null)[]
  zones: { x: number; y: number; name: string; groups: number }[]
  shelters: { x: number; y: number; name: string; capacity: number }[]
  runs: Record<Mode, { groups: Group[]; metrics: Record<string, number | null> }>
  water_results: Record<string, Record<string, { flooded_cells_caught_pct: number; false_alarm_pct: number; depth_error_cm: number }>>
}
const EVAC = evac as unknown as Record<string, { people_trapped: number; needless_evacuations: number; worst_shelter_wait_min: number; first_departure_after_min: number; people_in_flooding_areas: number }>

const C = 22                                   // px per cell (500 m)
const W = T.nx * C, H = T.ny * C
const TICK_MS = 260
const clock = (min: number) => { const m = 14 * 60 + Math.floor(min); return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}` }
const px = (cell: number) => cell * C + C / 2

export default function FloodTwin() {
  const q = new URLSearchParams(window.location.search)
  const [mode, setMode] = useState<Mode>(q.get('mode') === 'queuepilot' ? 'queuepilot' : 'today')
  const [step, setStep] = useState(() => Math.min(T.steps - 1, Number(q.get('t')) || 18))
  const [playing, setPlaying] = useState(false)
  const [layer, setLayer] = useState<'water' | 'drains'>(q.get('layer') === 'drains' ? 'drains' : 'water')
  const canvas = useRef<HTMLCanvasElement>(null)
  const tm = step * T.step_min
  const run = T.runs[mode]

  useEffect(() => {
    if (!playing) return
    const id = setInterval(() => setStep((s) => (s >= T.steps - 1 ? (setPlaying(false), s) : s + 1)), TICK_MS)
    return () => clearInterval(id)
  }, [playing])

  // ---- draw terrain + water (+ AI forecast) on a canvas, cell by cell
  useEffect(() => {
    const ctx = canvas.current?.getContext('2d')
    if (!ctx) return
    const zmax = Math.max(...T.z.flat())
    const soon = new Set(mode === 'queuepilot' ? T.ai_soon[step] : [])
    for (let y = 0; y < T.ny; y++) for (let x = 0; x < T.nx; x++) {
      const shade = 14 + Math.round((T.z[y][x] / zmax) * 26)
      ctx.fillStyle = `rgb(${shade},${shade + 3},${shade + 8})`
      ctx.fillRect(x * C, y * C, C, C)
      if (layer === 'drains') {
        const e = T.eff_learned[y][x]
        if (!T.river[y][x] && e < 0.6) { ctx.fillStyle = `rgba(242,165,65,${0.75 * (1 - e)})`; ctx.fillRect(x * C, y * C, C, C) }
        continue
      }
      const d = T.depth_cm[step][y][x]
      if (T.river[y][x]) { ctx.fillStyle = 'rgba(70,130,220,0.55)'; ctx.fillRect(x * C, y * C, C, C) }
      if (d >= 3) {
        const a = Math.min(0.9, 0.15 + d / 120)
        ctx.fillStyle = d >= T.flood_m * 100 ? `rgba(80,160,255,${a})` : `rgba(80,160,255,${a * 0.6})`
        ctx.fillRect(x * C, y * C, C, C)
      }
      const rain = T.rain_mmh[step][y][x]
      if (rain > 20) { ctx.fillStyle = `rgba(200,220,255,${Math.min(0.12, rain / 900)})`; ctx.fillRect(x * C, y * C, C, C) }
      if (soon.has(y * T.nx + x)) {
        ctx.strokeStyle = 'rgba(242,165,65,0.95)'; ctx.lineWidth = 1.5
        ctx.strokeRect(x * C + 2, y * C + 2, C - 4, C - 4)
      }
    }
  }, [step, mode, layer])

  // ---- people
  const live = useMemo(() => {
    const groups = run.groups
    const safe = groups.filter((g) => g.start != null && g.start <= tm).length
    const trapped = groups.filter((g) => g.trapped && g.trapped.t * T.step_min <= tm)
    const moving = groups.filter((g) => g.depart != null && g.depart * T.step_min <= tm && !(g.trapped && g.trapped.t * T.step_min <= tm) && !(g.arrive != null && g.arrive <= tm))
    const queue = T.shelters.map((_, i) => groups.filter((g) => g.shelter === i && g.arrive! <= tm && g.start! > tm).length)
    const inside = T.shelters.map((_, i) => groups.filter((g) => g.shelter === i && g.start! <= tm).length)
    return { safe, trapped, moving, queue, inside }
  }, [run, tm])
  const other = T.runs[mode === 'today' ? 'queuepilot' : 'today'].groups
  const trappedOther = other.filter((g) => g.trapped && g.trapped.t * T.step_min <= tm).length

  const pos = (g: Group) => {             // where a moving convoy is right now
    const ts = g.times
    if (!ts.length) return null
    let k = 0
    while (k < ts.length - 1 && ts[k + 1] <= tm) k++
    if (k >= g.path.length - 1) return g.path[g.path.length - 1]
    const f = Math.min(1, Math.max(0, (tm - ts[k]) / ((ts[k + 1] ?? ts[k] + 8) - ts[k])))
    return [g.path[k][0] + (g.path[k + 1][0] - g.path[k][0]) * f, g.path[k][1] + (g.path[k + 1][1] - g.path[k][1]) * f]
  }

  // ---- what happened, as a feed
  const feed = useMemo(() => {
    const ev: { m: number; text: string; tone: 'qp' | 'base' | 'alert' }[] = []
    T.zones.forEach((z, zi) => {
      const gs = run.groups.filter((g) => g.zone === zi && g.depart != null)
      if (!gs.length) return
      const m = Math.min(...gs.map((g) => g.depart!)) * T.step_min
      ev.push({ m, tone: mode === 'queuepilot' ? 'qp' : 'base', text: mode === 'queuepilot' ? `AI: ${z.name} will flood within 2 h. Evacuation starts now.` : `Water in ${z.name}'s streets. Evacuation starts.` })
      const tr = run.groups.filter((g) => g.zone === zi && g.trapped)
      if (tr.length) ev.push({ m: Math.min(...tr.map((g) => g.trapped!.t)) * T.step_min, tone: 'alert', text: `${z.name}: convoys cut off by flooded roads (${tr.length * T.group} people).` })
    })
    return ev.sort((a, b) => a.m - b.m)
  }, [run, mode])
  const feedNow = feed.filter((e) => e.m <= tm).slice(-4).reverse()

  const flooded = (e: number) => T.edge_flood_step[e] != null && T.edge_flood_step[e]! <= step
  const wr = T.water_results
  const evacKeys = Object.keys(EVAC).filter((k) => k !== 'setup')

  return (
    <div className="mx-auto flex min-h-screen max-w-[1440px] flex-col px-4 py-5 md:px-8">
      <header className="pb-4">
        <div className="num text-[11px] tracking-[0.2em] text-faint">QUEUEPILOT · FLOOD TWIN</div>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight md:text-3xl">
          Know which streets go under <span className="text-base">2 hours early</span>. Get everyone out <span className="text-qp">before the water does</span>.
        </h1>
        <div className="num mt-3 flex flex-wrap gap-x-6 gap-y-1 text-[11px] tracking-wider text-dim">
          <span><span className="text-route">01 WATER</span> physics + deep learning forecast every street, 2 h ahead</span>
          <span><span className="text-qp">02 PEOPLE</span> evacuation routes that will still be dry</span>
          <span><span className="text-base">03 QUEUES</span> shelters that never overflow</span>
        </div>
      </header>

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-1 border border-line-strong p-1" role="tablist" aria-label="Map layer">
          {([['water', 'Water now'], ['drains', 'Clogged drains the AI found']] as const).map(([k, l]) => (
            <button key={k} role="tab" aria-selected={layer === k} onClick={() => setLayer(k)}
              className={`num cursor-pointer px-3 py-1.5 text-xs transition-colors duration-150 ${layer === k ? 'bg-ink text-bg' : 'text-dim hover:text-ink'}`}>{l}</button>
          ))}
        </div>
        <div className="flex gap-1 border border-line-strong p-1" role="tablist" aria-label="How the city responds">
          {([['today', 'Today: react when water arrives'], ['queuepilot', 'QueuePilot: act on the forecast']] as const).map(([k, l]) => (
            <button key={k} role="tab" aria-selected={mode === k} onClick={() => setMode(k)}
              className="cursor-pointer px-3.5 py-2 text-sm transition-colors duration-150"
              style={mode === k ? { background: k === 'queuepilot' ? 'var(--color-qp)' : 'var(--color-ink)', color: 'var(--color-bg)' } : { color: 'var(--color-dim)' }}>{l}</button>
          ))}
        </div>
      </div>

      <div className="grid flex-1 gap-5 lg:grid-cols-[1fr_360px]">
        {/* ---------- the city ---------- */}
        <div className="relative self-start border border-line bg-panel">
          <div className="num flex items-baseline gap-3 border-b border-line px-4 py-2.5">
            <span className="text-3xl text-ink">{clock(tm)}</span>
            <span className="text-xs text-faint">{Math.max(...T.rain_mmh[step].flat())} mm/h at the storm's core</span>
          </div>
          <div className="relative">
            <canvas ref={canvas} width={W} height={H} className="block h-auto w-full" />
            <svg viewBox={`0 0 ${W} ${H}`} className="absolute inset-0 h-full w-full" role="img" aria-label="Roads, neighbourhoods, shelters and evacuation convoys">
              {T.edges.map(([a, b], e) => (
                <line key={e} x1={px(T.nodes[a][0])} y1={px(T.nodes[a][1])} x2={px(T.nodes[b][0])} y2={px(T.nodes[b][1])}
                  stroke={flooded(e) ? 'var(--color-alert)' : 'var(--color-dim)'} strokeOpacity={flooded(e) ? 0.9 : 0.35} strokeWidth={flooded(e) ? 3 : 2} />
              ))}
              {T.zones.map((z, zi) => {
                const atRisk = run.groups.some((g) => g.zone === zi && g.depart != null)
                return (
                  <g key={z.name} transform={`translate(${px(z.x)},${px(z.y)})`}>
                    <circle r="9" fill="var(--color-bg)" stroke={atRisk ? 'var(--color-base)' : 'var(--color-dim)'} strokeWidth="2" />
                    <text y="-14" textAnchor="middle" fontSize="11" className="num" fill="var(--color-ink)" stroke="var(--color-bg)" strokeWidth="3" paintOrder="stroke">{z.name}</text>
                  </g>
                )
              })}
              {T.shelters.map((s, i) => (
                <g key={s.name} transform={`translate(${px(s.x)},${px(s.y)})`}>
                  <rect x="-13" y="-13" width="26" height="26" fill="var(--color-bg)" stroke="var(--color-qp)" strokeWidth="2" />
                  <path d="M-6,3 L0,-5 L6,3 Z" fill="var(--color-qp)" />
                  <text y="26" textAnchor={s.x > T.nx - 6 ? 'end' : s.x < 5 ? 'start' : 'middle'} x={s.x > T.nx - 6 ? 13 : s.x < 5 ? -13 : 0} fontSize="10" className="num" fill="var(--color-qp)" stroke="var(--color-bg)" strokeWidth="3" paintOrder="stroke">{s.name} · {live.inside[i] * T.group}</text>
                  {live.queue[i] > 0 && (
                    <g transform={`translate(${s.x > T.nx - 6 ? -50 : 16},-16)`}><rect width="34" height="16" fill="var(--color-base)" /><text x="17" y="12" textAnchor="middle" fontSize="10" className="num" fill="var(--color-bg)">{live.queue[i] * T.group} wait</text></g>
                  )}
                </g>
              ))}
              {live.moving.map((g, i) => { const p = pos(g); return p && <circle key={i} cx={px(p[0])} cy={px(p[1])} r="4" fill={mode === 'queuepilot' ? 'var(--color-qp)' : 'var(--color-ink)'} /> })}
              {live.trapped.map((g, i) => (
                <g key={`t${i}`} transform={`translate(${px(g.trapped!.x) + ((i % 3) - 1) * 6},${px(g.trapped!.y) + (Math.floor(i / 3) % 3 - 1) * 6})`}>
                  <path d="M-4,-4 L4,4 M4,-4 L-4,4" stroke="var(--color-alert)" strokeWidth="2.2" />
                </g>
              ))}
            </svg>
          </div>
          <div className="num flex flex-wrap gap-x-5 gap-y-1 border-t border-line px-4 py-2.5 text-[11px] text-faint">
            {layer === 'water'
              ? <><span className="text-route">■ water (bright = 30 cm+, cars stall)</span>{mode === 'queuepilot' && <span className="text-base">▢ AI: floods within 2 h</span>}<span className="text-alert">— flooded road · ✕ people cut off</span><span>● convoy (100 people)</span><span className="text-qp">▲ shelter</span></>
              : <span className="text-base">■ drains the neural network learned are clogged, from height, building density and drain age. Nobody told it where.</span>}
          </div>
        </div>

        {/* ---------- side panel ---------- */}
        <aside className="flex flex-col gap-4">
          <div className="border border-line bg-panel p-5">
            <div className="text-sm text-dim">People cut off by water, so far</div>
            <div className="mt-3 grid grid-cols-2 gap-3">
              <Big value={(mode === 'today' ? live.trapped.length : trappedOther) * T.group} label="Today" color="var(--color-base)" active={mode === 'today'} />
              <Big value={(mode === 'queuepilot' ? live.trapped.length : trappedOther) * T.group} label="QueuePilot" color="var(--color-qp)" active={mode === 'queuepilot'} />
            </div>
            <div className="num mt-3 border-t border-line pt-3 text-xs text-dim">
              Safe in shelters now: <span className="text-ink">{live.safe * T.group}</span> · on the move: <span className="text-ink">{live.moving.length * T.group}</span>
            </div>
          </div>

          <div className="border border-line bg-panel p-5">
            <div className="text-sm text-dim">What's happening</div>
            <ul className="mt-3 space-y-2.5">
              {feedNow.length === 0 && <li className="text-xs text-faint">Rain building. {mode === 'queuepilot' ? 'The AI is watching every street.' : 'Nobody acts until water arrives.'}</li>}
              {feedNow.map((e, i) => (
                <li key={i} className="text-xs leading-relaxed"><span className="num text-faint">{clock(e.m)}</span>{' '}
                  <span className={e.tone === 'qp' ? 'text-qp' : e.tone === 'alert' ? 'text-alert' : 'text-base'}>{e.text}</span></li>
              ))}
            </ul>
          </div>

          <div className="border border-line bg-panel p-5 text-xs text-dim">
            <div className="num mb-2 text-[11px] tracking-wider text-faint">12 STORMS · 66,400 PEOPLE IN FLOOD ZONES</div>
            <table className="w-full">
              <thead><tr className="text-left text-faint"><th className="pb-1 font-normal" /><th className="pb-1 font-normal">cut off</th><th className="pb-1 font-normal">moved for nothing</th></tr></thead>
              <tbody>
                {evacKeys.map((k, i) => (
                  <tr key={k} className="border-t border-line">
                    <td className="py-1.5 pr-2">{['Today', 'Physics forecast', 'Physics + AI (ours)'][i]}</td>
                    <td className={`num ${i === 2 ? 'text-qp' : 'text-base'}`}>{EVAC[k].people_trapped.toLocaleString()}</td>
                    <td className={`num ${i === 2 ? 'text-qp' : 'text-dim'}`}>{EVAC[k].needless_evacuations.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 leading-relaxed">A forecast alone isn't enough: physics thinks the drains work. The neural network learned which ones are clogged, and that is what gets everyone out.</p>
          </div>

          <div className="border border-line bg-panel p-5 text-xs leading-relaxed text-dim">
            <div className="num mb-2 text-[11px] tracking-wider text-faint">THE AI · STREETS THAT FLOOD 2 H LATER</div>
            {(['Unseen storms, 2 h ahead', 'District never seen in training (east), 2 h ahead'] as const).map((k) => (
              <div key={k} className="mb-2">
                <div className="text-faint">{k.startsWith('Unseen') ? 'New storms' : 'A district it never saw'}</div>
                <div className="num">caught: physics <span className="text-base">{wr[k]['Physics only'].flooded_cells_caught_pct}%</span> · AI only <span className="text-route">{wr[k]['AI only (CNN)'].flooded_cells_caught_pct}%</span> · ours <span className="text-qp">{wr[k]['Physics + AI (ours)'].flooded_cells_caught_pct}%</span></div>
                <div className="num">false alarms: AI only <span className="text-route">{wr[k]['AI only (CNN)'].false_alarm_pct}%</span> · ours <span className="text-qp">{wr[k]['Physics + AI (ours)'].false_alarm_pct}%</span></div>
              </div>
            ))}
          </div>
        </aside>
      </div>

      <div className="mt-5 flex items-center gap-4 border border-line bg-panel px-5 py-4">
        <button onClick={() => { if (step >= T.steps - 1) setStep(0); setPlaying((p) => !p) }}
          className="num w-24 cursor-pointer border border-qp/60 py-2 text-xs tracking-widest text-qp transition-colors duration-150 hover:bg-qp/10">{playing ? 'PAUSE' : 'PLAY'}</button>
        <span className="num text-xs text-faint">{clock(0)}</span>
        <input type="range" aria-label="Time" className="flex-1 cursor-pointer" min={0} max={T.steps - 1} value={step}
          onChange={(e) => { setPlaying(false); setStep(Number(e.target.value)) }} />
        <span className="num text-xs text-faint">{clock(T.steps * T.step_min)}</span>
      </div>
      <footer className="num mt-4 flex flex-wrap justify-between gap-2 text-[11px] text-faint">
        <span>Simulated city, 20 × 14 km · physics-guided deep learning after Yu &amp; Wang, PNAS 2024 · rain for the next 3 h assumed known (radar nowcast)</span>
        <span className="flex gap-4"><a href="?view=golden" className="hover:text-ink">Golden Hour →</a><a href="?view=engine" className="hover:text-ink">Engine room →</a></span>
      </footer>
    </div>
  )
}

function Big({ value, label, color, active }: { value: number; label: string; color: string; active: boolean }) {
  return (
    <div className={`border p-3 ${active ? 'border-line-strong' : 'border-transparent'}`}>
      <div className="num text-4xl leading-none" style={{ color }}>{value.toLocaleString()}</div>
      <div className="mt-2 text-xs text-dim">{label}</div>
    </div>
  )
}
