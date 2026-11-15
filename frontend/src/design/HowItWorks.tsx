import { useEffect } from 'react'
import type { Design, Plan, Recommend, Results } from './data'

// "How it works", for judges' questions: three blocks, each one picture and two sentences.
// (a) the physics we know, (b) what the AI learns (the PG-GNN and its real numbers), (c) how we check.

export default function HowItWorks({ open, onClose, plan, design, results, recommend }: {
  open: boolean; onClose: () => void; plan: Plan; design: Design; results: Results | null; recommend: Recommend | null
}) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [onClose])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-20 flex justify-end bg-bg/80" onClick={onClose}>
      <aside role="dialog" aria-label="How it works" onClick={e => e.stopPropagation()}
        className="flex h-full w-[640px] flex-col gap-6 overflow-y-auto border-l border-line-strong bg-panel px-8 py-7">
        <div className="flex items-start justify-between">
          <h2 className="text-[22px] font-semibold">How it works</h2>
          <button onClick={onClose} className="rounded-sm border border-line-strong px-3 py-1 text-[15px] text-dim hover:text-ink">Close</button>
        </div>
        <Block title="1. Physics we know" picture={<PlanGraph plan={plan} />}
          text={`People can't appear or vanish, and a door only lets so many through: ${plan.flow_per_m_s} people per metre of width per second. The building is a network of rooms and doors, and these rules are written into the model, never learned.`} />
        <Block title="2. What the AI learns" picture={results ? <Models r={results} /> : <Missing />}
          text="Which exit a panicked crowd actually runs to, and how badly doors jam when people push. It is a physics-guided graph neural network: it predicts how long a building takes to empty, on floor plans it has never seen." />
        <Block title="3. How we check" picture={<Checks design={design} recommend={recommend} />}
          text="The AI screens every possible layout in seconds; the best ones are re-run in a detailed crowd simulation before anything is recommended. We also compared against spreading exits evenly on random floor plans." />
        <p className="mt-auto text-[15px] leading-snug text-faint">Method: Yu &amp; Wang, "Learning dynamical systems from data: an introduction to physics-guided deep learning", PNAS 2024. Every crowd result here is simulated.</p>
      </aside>
    </div>
  )
}

function Block({ title, picture, text }: { title: string; picture: React.ReactNode; text: string }) {
  return (
    <section className="grid grid-cols-[250px_1fr] gap-5 border-t border-line pt-5">
      <div>{picture}</div>
      <div>
        <h3 className="text-[15px] font-semibold uppercase tracking-[0.12em] text-dim">{title}</h3>
        <p className="mt-2 text-[15px] leading-relaxed">{text}</p>
      </div>
    </section>
  )
}

const Missing = () => <p className="text-[15px] text-faint">Model results not produced yet.</p>

// (a) the floor plan as the model sees it: rooms and corridors are nodes, doors are lines.
function PlanGraph({ plan }: { plan: Plan }) {
  const xs = plan.nodes.map(n => n.x), ys = plan.nodes.map(n => n.y)
  const vb = `${Math.min(...xs) - 3} ${Math.min(...ys) - 3} ${Math.max(...xs) - Math.min(...xs) + 6} ${Math.max(...ys) - Math.min(...ys) + 6}`
  return (
    <figure>
      <svg viewBox={vb} className="h-[130px] w-full" role="img" aria-label="The floor plan as a network of rooms and doors">
        {plan.edges.map((e, i) => {
          const a = plan.nodes[e.a], b = plan.nodes[e.b]
          return <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="var(--color-line-strong)" strokeWidth={0.3 + e.width_m * 0.2} strokeDasharray={e.candidate != null ? '0.8 0.6' : undefined} />
        })}
        {plan.nodes.map(n => <circle key={n.id} cx={n.x} cy={n.y} r={n.kind === 'room' ? 1.3 : 0.9} fill={n.kind === 'exit' ? 'var(--color-qp)' : 'var(--color-dim)'} />)}
      </svg>
      <figcaption className="mt-1 text-[15px] text-faint">{plan.nodes.length} spaces, {plan.edges.length} doors</figcaption>
    </figure>
  )
}

// (b) three models, same test on floor plans never seen in training: error in the time to empty.
function Models({ r }: { r: Results }) {
  const rows = [['Physics alone', r.models.physics, 'bg-dim'], ['AI alone', r.models.gnn, 'bg-dim'], ['Physics-guided AI, ours', r.models.pggnn, 'bg-qp']] as const
  const max = Math.max(...rows.map(([, m]) => m.clearance_err_s))
  return (
    <figure className="space-y-2">
      {rows.map(([name, m, c]) => (
        <div key={name}>
          <div className="flex justify-between text-[15px]"><span className={c === 'bg-qp' ? 'text-qp' : 'text-dim'}>{name}</span><span className="num whitespace-nowrap">±{m.clearance_err_s} s</span></div>
          <div className="mt-0.5 h-1.5 bg-raised"><div className={`h-full ${c}`} style={{ width: `${(m.clearance_err_s / max) * 100}%` }} /></div>
        </div>
      ))}
      <figcaption className="text-[15px] leading-snug text-faint">
        Typical error in time to empty, {r.models.pggnn.runs ?? ''} runs on unseen plans. People made up or lost per run: AI alone {Math.round(r.models.gnn.people_error)}, ours {Math.round(r.models.pggnn.people_error)}.
      </figcaption>
    </figure>
  )
}

// (c) the AI's top picks re-run in the detailed simulation, and the random-plan comparison.
function Checks({ design, recommend }: { design: Design; recommend: Recommend | null }) {
  const a = design.across_plans
  return (
    <figure className="space-y-2 text-[15px]">
      {recommend && (
        <table className="num w-full">
          <thead><tr className="text-left text-faint"><th className="font-normal">AI's top picks</th><th className="text-right font-normal">AI</th><th className="text-right font-normal">checked</th></tr></thead>
          <tbody>{recommend.top5.map((t, i) => (
            <tr key={i} className="border-t border-line"><td>{t.exits.length} exits</td><td className="text-right">{t.predicted_s} s</td>
              <td className={`text-right ${t.verified_s != null && t.verified_s <= design.safe_limit_s ? 'text-ink' : 'text-alert'}`}>{t.verified_s ?? 'fails'}{t.verified_s != null && ' s'}</td></tr>
          ))}</tbody>
        </table>
      )}
      {recommend?.fewest_exits != null && design.by_panic[String(design.design_panic)]?.chosen_n_exits != null && recommend.fewest_exits !== design.by_panic[String(design.design_panic)].chosen_n_exits && (
        <p className="leading-snug text-faint">The AI's quick screen asks for {recommend.fewest_exits} exits; the full simulation shows {design.by_panic[String(design.design_panic)].chosen_n_exits} are enough. It errs on the cautious side, and the simulation has the final word.</p>
      )}
      {a && <p className="leading-snug text-faint">{a.solved_both} random floor plans: {a.mean_exits_ours} exits on average with QueuePilot, {a.mean_exits_rule} spread evenly.</p>}
    </figure>
  )
}
