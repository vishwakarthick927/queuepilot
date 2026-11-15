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
          <div className="text-[13px] font-semibold uppercase tracking-[0.14em] text-dim">QueuePilot <span className="text-qp">Design</span></div>
          <h1 className="mt-2 text-[44px] font-semibold leading-[1.1] tracking-tight">Why not Hamiltonian?</h1>
        </div>
        <button onClick={back} className="mb-1 ml-auto rounded-sm border border-line-strong px-4 py-2 text-[15px] text-dim hover:border-ink hover:text-ink">Back to the building</button>
      </header>

      <main className="grid min-h-0 grid-cols-[1fr_600px] gap-px bg-line">
        <section className="flex min-h-0 flex-col bg-bg px-8 py-5">
          <h2 className="text-[22px] font-semibold">People still inside, one evacuation</h2>
          <div className="min-h-0 flex-1 pt-2"><Curves /></div>
        </section>

        <section className="flex min-h-0 flex-col gap-5 bg-panel px-7 py-5">
          <div>
            <h2 className="text-[22px] font-semibold">Seconds of error in the time to get everyone out</h2>
            <div className="mt-3"><Bars m={m} /></div>
          </div>
          <Reason m={m} />
        </section>
      </main>

      <footer className="border-t border-line px-8 py-2.5 text-[13px] text-faint">
        Simulated crowd. Same {M.test_runs} evacuations for every model, on 16 floor plans none of them had seen.
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
    { key: 'hamiltonian', label: 'Hamiltonian / Lagrangian', data: pad(ex.hamiltonian), stroke: 'var(--color-alert)', w: 2.5, dash: undefined },
    { key: 'damped', label: 'Hamiltonian + friction', data: pad(ex.damped), stroke: 'var(--color-dim)', w: 2, dash: '7 5' },
    { key: 'least_action', label: 'Our physics', data: pad(ex.least_action), stroke: 'var(--color-faint)', w: 2, dash: '2 4' },
  ]
  const W = 900, H = 720, L = 64, R = 230, T = 30, B = 44
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
      <rect x={L} y={y(0)} width={W - L - R} height={y(ymin) - y(0)} fill="var(--color-alert)" fillOpacity={0.14} />
      <text x={L + 12} y={y(ymin) - 12} fontSize={17} fontWeight={600} fill="var(--color-alert)">Impossible: fewer than zero people</text>
      {ticksY.map(v => <g key={v}>
        <line x1={L} x2={W - R} y1={y(v)} y2={y(v)} stroke={v === 0 ? 'var(--color-ink)' : 'var(--color-line)'} strokeWidth={v === 0 ? 3 : 1} />
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

// Five models, worst at the top, best at the bottom, value at the end of each bar. Nothing else.
function Bars({ m }: { m: Mechanics['models'] }) {
  const rows: [keyof Mechanics['models'], string][] = [
    ['damped', 'Hamiltonian + friction'], ['hamiltonian', 'Hamiltonian / Lagrangian'], ['gnn_only', 'GNN only'],
    ['least_action', 'Our physics only'], ['pggnn', 'PG-GNN, ours'],
  ]
  rows.sort((a, b) => m[b[0]].clearance_err_s - m[a[0]].clearance_err_s)
  const max = Math.max(...rows.map(([k]) => m[k].clearance_err_s))
  return (
    <div className="space-y-2.5">
      {rows.map(([k, name]) => {
        const ours = k === 'pggnn', v = m[k].clearance_err_s
        return (
          <div key={k} className="grid grid-cols-[190px_1fr] items-center gap-3">
            <span className={`text-[15px] ${ours ? 'font-semibold text-qp' : 'text-ink'}`}>{name}</span>
            <div className="flex items-center gap-2">
              <div className={`h-5 ${ours ? 'bg-qp' : 'bg-dim'}`} style={{ width: `${Math.max(1.5, (v / max) * 82)}%` }} />
              <span className={`num text-[15px] font-semibold ${ours ? 'text-qp' : 'text-ink'}`}>{v} s</span>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// The reason, in four short lines, every number from the file.
function Reason({ m }: { m: Mechanics['models'] }) {
  return (
    <div className="mt-auto border-t border-line pt-4">
      <h3 className="text-[22px] font-semibold">Why Hamiltonian doesn't work for a crowd</h3>
      <ul className="mt-3 space-y-2 text-[17px] leading-snug">
        <li>It conserves energy. A crowd doesn't: people stop, push and slow down.</li>
        <li>Its flow has momentum that never dies, so it keeps emptying rooms that are already empty: down to <span className="num font-semibold text-alert">{Math.round(m.hamiltonian.most_negative_people ?? 0)}</span> people in one room.</li>
        <li>Then it swings back, like a pendulum: <span className="num font-semibold text-alert">{m.hamiltonian.backflow_pct}%</span> of all movement is away from the exits.</li>
        <li>Adding friction stops the swinging but the crowd creeps: only <span className="num font-semibold">{m.damped.cleared_pct}%</span> of buildings ever empty.</li>
      </ul>
      <p className="mt-3 text-[17px] font-semibold leading-snug text-qp">What we use instead: people are conserved, doors have limits, and the PG-GNN learns how a panicked crowd behaves.</p>
    </div>
  )
}
