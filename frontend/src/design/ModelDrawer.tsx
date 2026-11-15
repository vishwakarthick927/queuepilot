import { Fragment, useEffect } from 'react'
import type { Plan, Recommend, Results } from './data'
import { Head, Tag, fmt } from './ui'

// The "how it works" drawer: the plan as a graph, the three models on unseen plans, conservation.
const NAMES = { physics: 'Physics only', gnn: 'GNN only', pggnn: 'PG-GNN (ours)' } as const

export default function ModelDrawer({ open, onClose, plan, results, recommend, stub }: {
  open: boolean; onClose: () => void; plan: Plan; results: Results | null; recommend: Recommend | null; stub: boolean
}) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [onClose])
  if (!open) return null
  const worst = results ? Math.max(...Object.values(results.models).map(m => m.clearance_err_s + m.ci95)) : 1
  return (
    <div className="fixed inset-0 z-20 flex justify-end bg-bg/70" onClick={onClose}>
      <aside className="flex h-full w-[600px] flex-col gap-4 overflow-y-auto border-l border-line-strong bg-panel p-7" onClick={e => e.stopPropagation()}
        role="dialog" aria-label="How the model works">
        <div className="flex items-start justify-between">
          <div>
            <div className="text-[13px] uppercase tracking-[0.14em] text-dim">The model</div>
            <h2 className="mt-1 text-[26px] font-semibold">Physics-guided graph neural network</h2>
          </div>
          <button onClick={onClose} className="rounded-sm border border-line-strong px-3 py-1.5 text-[14px] text-dim hover:text-ink">Close</button>
        </div>

        <PlanGraph plan={plan} />

        <section className="space-y-1.5 text-[14px] leading-snug text-dim">
          <p><span className="text-ink">Physics, hard-coded:</span> people are conserved, a door passes at most width × {plan.flow_per_m_s} people/m/s, a space holds at most {plan.max_density} people/m².</p>
          <p><span className="text-ink">Learned, bounded:</span> door efficiency in [0, 1] (sigmoid) and the share of people taking each door (softmax, sums to 1). So the network cannot create or lose a person.</p>
          <p className="num rounded-sm border border-line bg-raised px-3 py-2 text-[14px] text-ink">flow = min(people × share × walk, width × capacity × efficiency, free space)</p>
        </section>

        <section className="space-y-3">
          <Head n="A" title="Clearance-time error, floor plans never seen in training" tag={<Tag>{stub ? 'stub' : 'simulated'}</Tag>} />
          {!results ? <p className="text-dim">Model results not produced yet.</p> : (Object.keys(NAMES) as (keyof typeof NAMES)[]).map(k => {
            const m = results.models[k]
            return (
              <div key={k} className="grid grid-cols-[140px_1fr_140px] items-center gap-3">
                <div className={`text-[15px] ${k === 'pggnn' ? 'text-qp' : 'text-ink'}`}>{NAMES[k]}</div>
                <div className="relative h-3 bg-raised">
                  <div className={`absolute inset-y-0 left-0 ${k === 'pggnn' ? 'bg-qp' : 'bg-line-strong'}`} style={{ width: `${(m.clearance_err_s / worst) * 100}%` }} />
                  <div className="absolute inset-y-[-3px] w-px bg-dim" style={{ left: `${((m.clearance_err_s + m.ci95) / worst) * 100}%` }} />
                </div>
                <div className="num whitespace-nowrap text-right text-[15px]">{m.clearance_err_s} ± {m.ci95} s</div>
              </div>
            )
          })}
        </section>

        {results?.ablation && (
          <div className="num grid grid-cols-[1fr_140px] gap-y-0.5 text-[13px] text-dim">
            {results.ablation.map(r => <Fragment key={r.label}><span>{r.label}</span><span className="text-right">{r.clearance_err_s} ± {r.ci95} s</span></Fragment>)}
          </div>
        )}
        {results && (
          <section className="grid grid-cols-2 gap-4">
            <div className="border border-line bg-raised px-4 py-3">
              <div className="text-[12px] uppercase tracking-[0.12em] text-dim">People created or lost per run</div>
              <div className="num mt-2 text-[15px]">GNN only <span className="ml-2 text-[24px] text-alert">{fmt(Math.round(results.models.gnn.people_error))}</span></div>
              <div className="num mt-1 text-[15px]">PG-GNN <span className="ml-2 text-[24px] text-qp">{fmt(Math.round(results.models.pggnn.people_error))}</span></div>
            </div>
            <div className="border border-line bg-raised px-4 py-3">
              <div className="text-[12px] uppercase tracking-[0.12em] text-dim">Layouts scored per second</div>
              <div className="num mt-2 text-[15px]">PG-GNN <span className="ml-2 text-[24px] text-qp">{fmt(results.speed.pggnn_per_s)}</span></div>
              <div className="num mt-1 text-[15px]">Detailed simulator <span className="ml-2 text-[24px]">{fmt(results.speed.simulator_per_s)}</span></div>
            </div>
          </section>
        )}
        {recommend?.agreement && (
          <section className="space-y-2">
            <Head n="B" title="Does the screen pick the simulator's best layout?" tag={<Tag>simulated</Tag>} />
            <div className="num grid grid-cols-[150px_1fr_1fr] gap-y-1 text-[15px]">
              <span className="text-faint" /><span className="text-faint">best = its pick</span><span className="text-faint">best in its top 5</span>
              {recommend.agreement_physics_only && <><span>Physics only</span><span>{Math.round(recommend.agreement_physics_only.top1 * 100)}%</span><span>{Math.round(recommend.agreement_physics_only.top5 * 100)}%</span></>}
              <span className="text-qp">PG-GNN (ours)</span><span>{Math.round(recommend.agreement.top1 * 100)}%</span><span>{Math.round(recommend.agreement.top5 * 100)}%</span>
            </div>
            <p className="text-[13px] text-faint">Demo plan, panic 0.8, one check per exit count {recommend.agreement.exit_counts ? `(${recommend.agreement.exit_counts.join(', ')} exits)` : ''}, against MAIN's full simulator ranking.</p>
          </section>
        )}
        <p className="mt-auto pt-2 text-[12px] leading-snug text-faint">Method: Yu &amp; Wang, "Learning dynamical systems from data: an introduction to physics-guided deep learning", PNAS 2024, §3A (constrained hybrid), §4A (generalisation). Training data: our detailed evacuation simulator with hidden panic and exit familiarity. All results simulated.</p>
      </aside>
    </div>
  )
}

// The same floor plan as the network sees it: nodes (rooms, corridors, exits) and edges (doors).
function PlanGraph({ plan }: { plan: Plan }) {
  const xs = plan.nodes.map(n => n.x), ys = plan.nodes.map(n => n.y)
  const vb = `${Math.min(...xs) - 3} ${Math.min(...ys) - 3} ${Math.max(...xs) - Math.min(...xs) + 6} ${Math.max(...ys) - Math.min(...ys) + 6}`
  const color = { room: 'var(--color-dim)', corridor: 'var(--color-faint)', stair: 'var(--color-faint)', exit: 'var(--color-qp)' }
  return (
    <figure className="flex items-center gap-5 border border-line bg-raised p-3">
      <svg viewBox={vb} className="h-[120px] w-[190px] shrink-0" role="img" aria-label="The floor plan as a graph">
        {plan.edges.map((e, i) => {
          const a = plan.nodes[e.a], b = plan.nodes[e.b]
          return <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="var(--color-line-strong)" strokeWidth={0.25 + e.width_m * 0.2} strokeDasharray={e.candidate != null ? '0.8 0.6' : undefined} />
        })}
        {plan.nodes.map(n => <circle key={n.id} cx={n.x} cy={n.y} r={n.kind === 'room' ? 1.3 : 0.9} fill={color[n.kind]} />)}
      </svg>
      <figcaption className="num space-y-1 text-[14px] text-dim">
        <div><span className="text-ink">{plan.nodes.length}</span> nodes: rooms, corridor segments, exits</div>
        <div><span className="text-ink">{plan.edges.length}</span> edges: doors and passages (dashed = possible exit)</div>
        <div>3 rounds of message passing, 32 numbers per node</div>
      </figcaption>
    </figure>
  )
}
