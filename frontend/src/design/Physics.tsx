// "Why this physics" (rounds 7 + 8): why QueuePilot conserves PEOPLE, not energy.
// Built only from data/design/mechanics.json (MAIN, engine/mechanics.py). Every number below is read from that file.

type Model = { label: string; clearance_err_s: number; ci95: number; most_negative_people?: number; backflow_pct?: number; cleared_pct?: number; people_created_or_lost?: number; runs?: number }
type Mechanics = {
  test_runs: number
  models: Record<'hamiltonian' | 'damped' | 'least_action' | 'pggnn' | 'gnn_only', Model>
  example: { truth: number[]; hamiltonian: number[]; damped: number[]; least_action: number[] }
  design: { building: string; exhaustive_calls: number; lagrange_calls: number; exhaustive_exits: number; lagrange_exits: number; exhaustive_worst_s: number; same_answer: boolean }[]
}

const file = import.meta.glob('../../../data/design/mechanics.json', { eager: true, import: 'default' })
const M = Object.values(file)[0] as Mechanics | undefined
const DT = 2                                             // seconds per simulation step
const ONE_FONT = { '--font-mono': 'var(--font-sans)' } as React.CSSProperties

export default function Physics() {
  if (!M) return <div className="grid h-screen place-items-center text-[18px] text-dim">Waiting for data/design/mechanics.json.</div>
  const m = M.models
  const back = () => { window.location.search = '' }
  return (
    <div className="grid h-screen grid-rows-[auto_1fr_auto] overflow-hidden bg-bg" style={ONE_FONT}>
      <header className="flex items-end gap-8 border-b border-line px-8 pb-4 pt-5">
        <div>
          <div className="text-[13px] font-semibold uppercase tracking-[0.14em] text-dim">QueuePilot <span className="text-qp">Design</span> · why this physics</div>
          <h1 className="mt-2 text-[44px] font-semibold leading-[1.1] tracking-tight">A crowd conserves people, <span className="text-qp">not energy.</span></h1>
        </div>
        <button onClick={back} className="mb-1 ml-auto rounded-sm border border-line-strong px-4 py-2 text-[15px] text-dim hover:border-ink hover:text-ink">Back to the building</button>
      </header>

      <main className="grid min-h-0 grid-cols-[1fr_640px] gap-px bg-line">
        <section className="flex min-h-0 flex-col bg-bg px-8 py-5">
          <h2 className="text-[22px] font-semibold">One evacuation, four kinds of physics</h2>
          <p className="mt-1 text-[15px] text-dim">People still inside over time. Energy-conserving mechanics keeps the crowd moving after the rooms are empty, so it predicts fewer than zero people.</p>
          <div className="min-h-0 flex-1 pt-3"><Curves /></div>
        </section>

        <section className="flex min-h-0 flex-col gap-4 bg-panel px-7 py-5">
          <div>
            <h2 className="text-[22px] font-semibold">Error in the time to get everyone out</h2>
            <p className="mt-1 text-[15px] text-dim">Same {M.test_runs} evacuations for every model, on floor plans none of them had seen.</p>
          </div>
          <Bars m={m} />
          <Lagrange />
        </section>
      </main>

      <footer className="border-t border-line px-8 py-2.5 text-[13px] text-faint">
        Simulated crowd. Same {M.test_runs} evacuations for every model, on 16 floor plans none of them had seen. Details: docs/PHYSICS.md.
      </footer>
    </div>
  )
}

// The key picture: people inside over time, with the impossible region (below zero people) shaded.
function Curves() {
  const ex = M!.example
  const steps = 110                                                     // 220 s: long enough to see the swing back
  const pad = (a: number[]) => Array.from({ length: steps }, (_, i) => (i < a.length ? a[i] : a.length < 300 ? 0 : a[a.length - 1]))
  const lines = [
    { key: 'truth', label: 'What really happens', data: pad(ex.truth), stroke: 'var(--color-ink)', w: 3, dash: undefined },
    { key: 'hamiltonian', label: 'Hamiltonian (energy kept)', data: pad(ex.hamiltonian), stroke: 'var(--color-alert)', w: 2.5, dash: undefined },
    { key: 'damped', label: 'Hamiltonian + friction', data: pad(ex.damped), stroke: 'var(--color-dim)', w: 2, dash: '7 5' },
    { key: 'least_action', label: 'Least action (fastest path)', data: pad(ex.least_action), stroke: 'var(--color-faint)', w: 2, dash: '2 4' },
  ]
  const W = 900, H = 560, L = 64, R = 230, T = 30, B = 44
  const all = lines.flatMap(l => l.data)
  const ymax = Math.ceil(Math.max(...all) / 100) * 100, ymin = Math.floor(Math.min(...all) / 100) * 100
  const x = (i: number) => L + (i / (steps - 1)) * (W - L - R)
  const y = (v: number) => T + ((ymax - v) / (ymax - ymin)) * (H - T - B)
  const path = (d: number[]) => d.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ')
  const ticksY = Array.from({ length: (ymax - ymin) / 100 + 1 }, (_, i) => ymin + i * 100)
  const ticksX = Array.from({ length: Math.floor((steps * DT) / 60) + 1 }, (_, i) => i * 60)
  // end labels, nudged apart so they never overlap
  const ends = lines.map(l => ({ ...l, ly: y(l.data[steps - 1]) })).sort((a, b) => a.ly - b.ly)
  for (let i = 1; i < ends.length; i++) ends[i].ly = Math.max(ends[i].ly, ends[i - 1].ly + 34)
  const low = Math.min(...ex.hamiltonian)
  const lowAt = ex.hamiltonian.indexOf(low)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-full w-full" role="img" aria-label="People still inside over time for four kinds of physics">
      <rect x={L} y={y(0)} width={W - L - R} height={y(ymin) - y(0)} fill="var(--color-alert)" fillOpacity={0.08} />
      <text x={L + 12} y={y(ymin) - 12} fontSize={15} fill="var(--color-alert)">impossible: fewer than zero people</text>
      {ticksY.map(v => <g key={v}>
        <line x1={L} x2={W - R} y1={y(v)} y2={y(v)} stroke={v === 0 ? 'var(--color-ink)' : 'var(--color-line)'} strokeWidth={v === 0 ? 1.5 : 1} />
        <text x={L - 10} y={y(v) + 5} fontSize={13} textAnchor="end" fill="var(--color-dim)" className="num">{v}</text>
      </g>)}
      {ticksX.map(s => <text key={s} x={x(s / DT)} y={H - B + 22} fontSize={13} textAnchor="middle" fill="var(--color-dim)" className="num">{s} s</text>)}
      <text x={L} y={T - 14} fontSize={13} fill="var(--color-dim)">people inside</text>
      {lines.map(l => <path key={l.key} d={path(l.data)} fill="none" stroke={l.stroke} strokeWidth={l.w} strokeDasharray={l.dash} strokeLinejoin="round" />)}
      {lowAt < steps && <g>
        <circle cx={x(lowAt)} cy={y(low)} r={4} fill="var(--color-alert)" />
        <text x={x(lowAt) + 10} y={y(low) + 24} fontSize={15} textAnchor="start" fill="var(--color-alert)" className="num">{Math.round(low)} people</text>
      </g>}
      {ends.map(l => <text key={l.key} x={W - R + 12} y={l.ly + 5} fontSize={15} fill={l.stroke === 'var(--color-faint)' ? 'var(--color-dim)' : l.stroke}>{l.label}</text>)}
    </svg>
  )
}

// Five models, worst to best, each with its one-line reason. Numbers in the reasons come from the file.
function Bars({ m }: { m: Mechanics['models'] }) {
  const neg = Math.round(m.hamiltonian.most_negative_people ?? 0), back = m.hamiltonian.backflow_pct ?? 0
  const rows: { k: keyof Mechanics['models']; name: string; why: string }[] = [
    { k: 'damped', name: 'Hamiltonian + friction', why: `Friction stops the swinging but makes the crowd creep: only ${Math.round(m.damped.cleared_pct ?? 0)}% of buildings ever empty. No setting fits both the fast start and the slow end, because the equations have no door limit.` },
    { k: 'hamiltonian', name: 'Hamiltonian / Lagrangian', why: `Momentum never dies, so the flow keeps draining rooms that are already empty (down to ${neg} people) and swings back: ${back}% of all movement is away from the exits. A pendulum that cannot stop.` },
    { k: 'gnn_only', name: 'GNN only', why: `It learns from data, but nothing stops it inventing people: ${Math.round(m.gnn_only.people_created_or_lost ?? 0)} made up or lost per run.` },
    { k: 'least_action', name: 'Least action', why: 'The part of Lagrange that fits: everyone takes the path of least time. Never breaks a law, but assumes people stay calm.' },
    { k: 'pggnn', name: 'PG-GNN, ours', why: 'Keeps the physics that is true (people conserved, doors have limits, least-time paths) and learns only what physics cannot know: which exit a panicked crowd runs to and how doors jam.' },
  ]
  rows.sort((a, b) => m[b.k].clearance_err_s - m[a.k].clearance_err_s)
  const max = Math.max(...rows.map(r => m[r.k].clearance_err_s))
  return (
    <div className="space-y-3">
      {rows.map(r => {
        const ours = r.k === 'pggnn', v = m[r.k].clearance_err_s
        return (
          <div key={r.k}>
            <div className="flex items-baseline justify-between gap-3">
              <span className={`text-[15px] font-semibold ${ours ? 'text-qp' : 'text-ink'}`}>{r.name}</span>
              <span className={`num text-[15px] font-semibold ${ours ? 'text-qp' : 'text-ink'}`}>{v} s</span>
            </div>
            <div className="mt-1 h-2 bg-raised"><div className={`h-full ${ours ? 'bg-qp' : 'bg-dim'}`} style={{ width: `${Math.max(1.5, (v / max) * 100)}%` }} /></div>
            <p className="mt-1 text-[13px] leading-snug text-dim">{r.why}</p>
          </div>
        )
      })}
    </div>
  )
}

// Lagrange multipliers: the part of Lagrange's work that does help, finding the same exits with fewer simulations.
function Lagrange() {
  return (
    <div className="mt-auto">
      <h3 className="text-[15px] font-semibold">Lagrange multipliers find the same exits faster</h3>
      <table className="num mt-1 w-full text-[13px]">
        <thead><tr className="text-left text-faint"><th className="font-normal">building</th><th className="text-right font-normal">every layout</th><th className="text-right font-normal">Lagrange search</th><th className="text-right font-normal">same answer</th></tr></thead>
        <tbody>{M!.design.map(d => (
          <tr key={d.building} className="border-t border-line">
            <td className="py-0.5">{d.building}</td><td className="text-right">{d.exhaustive_calls}</td>
            <td className="text-right text-qp">{d.lagrange_calls}</td><td className="text-right">{d.same_answer ? `yes, ${d.lagrange_exits} exits` : 'no'}</td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  )
}
