import { useEffect, useRef } from 'react'
import { cnnDemo, cnnResults, smokeDemo, type Design, type Plan, type Recommend, type Results } from './data'

// "How it works", for judges' questions. One block per model, plus how we check:
// (1) where the smoke goes: the PG-CNN, the plan as a GRID; (2) where the people go: the PG-GNN, the plan as a GRAPH;
// (3) where the exits go: screen every layout, then re-check the best in the detailed simulation.
// Each block = one picture, two plain sentences (what physics fixes, what the network learns), the real numbers, small.

export default function HowItWorks({ open, at, onClose, plan, design, results, recommend }: {
  open: boolean; at?: string; onClose: () => void; plan: Plan; design: Design; results: Results | null; recommend: Recommend | null
}) {
  const box = useRef<HTMLElement>(null)
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [onClose])
  useEffect(() => { if (open && at) box.current?.querySelector(`#how-${at}`)?.scrollIntoView({ block: 'start' }) }, [open, at])
  if (!open) return null
  const c = cnnResults?.data
  return (
    <div className="fixed inset-0 z-20 flex justify-end bg-bg/80" onClick={onClose}>
      <aside ref={box} role="dialog" aria-label="How it works" onClick={e => e.stopPropagation()}
        className="flex h-full w-[680px] flex-col gap-5 overflow-y-auto border-l border-line-strong bg-panel px-8 py-6">
        <div className="flex items-start justify-between">
          <h2 className="text-[22px] font-semibold">How it works</h2>
          <button onClick={onClose} className="rounded-sm border border-line-strong px-3 py-1 text-[15px] text-dim hover:text-ink">Close</button>
        </div>

        <Block id="smoke" n="1" title="Where the smoke goes" model="PG-CNN" active={at === 'smoke'} picture={<SmokeGrid />}
          physics="Physics fixes the rules: smoke spreads from thick to thin through open doors, and a room can only clear smoke, never make it."
          learns="The network reads the floor plan as a grid and learns how fast each space clears smoke, mostly from its windows. That tells us when each corridor fills up."
          numbers={c ? <Compare unit="s" rows={[
            ['Textbook physics', c.models.physics.block_time_err_s], ['AI alone', c.models.cnn.block_time_err_s], ['Physics-guided AI, ours', c.models.pgcnn.block_time_err_s, true]]}
            caption={`Error in when a corridor fills with smoke, ${c.setup?.test_fires ?? ''} fires on plans never seen in training. Smoke made from nothing: AI alone ${c.models.cnn.smoke_created}, ours ${c.models.pgcnn.smoke_created}.`} /> : <Missing />} />

        <Block id="people" n="2" title="Where the people go" model="PG-GNN" active={at === 'people'} picture={<PlanGraph plan={plan} />}
          physics={`Physics fixes the rules: nobody appears or vanishes, a door lets at most ${plan.flow_per_m_s} people per metre of width through each second, a room only holds so many.`}
          learns="The network reads the floor plan as a graph of rooms and doors and learns which exit a panicked crowd runs to and how badly doors jam."
          numbers={results ? <Compare unit="s" rows={[
            ['Textbook physics', results.models.physics.clearance_err_s], ['AI alone', results.models.gnn.clearance_err_s], ['Physics-guided AI, ours', results.models.pggnn.clearance_err_s, true]]}
            caption={`Error in time to get everyone out, ${results.models.pggnn.runs ?? ''} runs on plans never seen in training. People made up or lost per run: AI alone ${Math.round(results.models.gnn.people_error)}, ours ${Math.round(results.models.pggnn.people_error)}.`} /> : <Missing />} />

        <Block id="exits" n="3" title="Where the exits go" model="QueuePilot" active={at === 'exits'} picture={<Checks design={design} recommend={recommend} />}
          physics="Every possible layout is tested with a panicked crowd: no fire, each fire from the smoke model, and a fire blocking each exit in turn."
          learns="The fastest layouts are re-run in a detailed crowd simulation before anything is recommended, and we never go below the building code."
          numbers={null} />

        <p className="mt-auto text-[13px] leading-snug text-faint">Method: Yu &amp; Wang, "Learning dynamical systems from data: an introduction to physics-guided deep learning", PNAS 2024. Every smoke and crowd result here is simulated.</p>
      </aside>
    </div>
  )
}

function Block({ id, n, title, model, active, picture, physics, learns, numbers }: {
  id: string; n: string; title: string; model: string; active: boolean; picture: React.ReactNode; physics: string; learns: string; numbers: React.ReactNode
}) {
  return (
    <section id={`how-${id}`} className={`grid grid-cols-[230px_1fr] gap-5 border-t pt-4 ${active ? 'border-qp' : 'border-line'}`}>
      <div>{picture}</div>
      <div>
        <h3 className="text-[15px] font-semibold"><span className="num mr-2 text-faint">{n}</span>{title} <span className="text-qp">· {model}</span></h3>
        <p className="mt-2 text-[15px] leading-snug">{physics}</p>
        <p className="mt-2 text-[15px] leading-snug text-dim">{learns}</p>
        {numbers && <div className="mt-3">{numbers}</div>}
      </div>
    </section>
  )
}

const Missing = () => <p className="text-[13px] text-faint">Model results not produced yet.</p>

// Three models, same test: small bars, ours in the accent.
function Compare({ rows, unit, caption }: { rows: (readonly [string, number, boolean?])[]; unit: string; caption: string }) {
  const max = Math.max(...rows.map(r => r[1]))
  return (
    <figure className="space-y-1.5">
      {rows.map(([name, v, ours]) => (
        <div key={name} className="grid grid-cols-[170px_1fr_64px] items-center gap-2 text-[13px]">
          <span className={ours ? 'text-qp' : 'text-dim'}>{name}</span>
          <span className="h-1.5 bg-raised"><span className={`block h-full ${ours ? 'bg-qp' : 'bg-dim'}`} style={{ width: `${(v / max) * 100}%` }} /></span>
          <span className="num text-right">±{v} {unit}</span>
        </div>
      ))}
      <figcaption className="text-[13px] leading-snug text-faint">{caption}</figcaption>
    </figure>
  )
}

// (1) the plan as a GRID: one smoke frame from the PG-CNN's prediction for the demo fire, cell by cell.
function SmokeGrid() {
  const fire = cnnDemo?.data.fires[0] ?? smokeDemo?.data.fires[0]
  if (!fire || !smokeDemo) return <Missing />
  const k = Math.min(12, fire.smoke.length - 1)
  const frame = fire.smoke[k]
  const H = frame.length, W = frame[0].length
  const node = (smokeDemo.data as unknown as { node?: number[][] }).node
  return (
    <figure>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="The floor plan as a grid with predicted smoke">
        {frame.map((row, r) => row.map((v, c) => {
          const inside = node ? node[r][c] >= 0 : true
          return <rect key={`${r}-${c}`} x={c + 0.05} y={r + 0.05} width={0.9} height={0.9}
            fill={v > 0.04 ? '#c7ccd4' : inside ? 'var(--color-raised)' : 'transparent'} fillOpacity={v > 0.04 ? Math.min(0.9, v * 1.1) : 1} />
        }))}
      </svg>
      <figcaption className="mt-1 text-[13px] text-faint">{W} × {H} cells of 2 m, predicted smoke after {(3 * k + 1) * 2} s</figcaption>
    </figure>
  )
}

// (2) the plan as a GRAPH: rooms and corridors are nodes, doors are lines.
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
      <figcaption className="mt-1 text-[13px] text-faint">{plan.nodes.length} spaces, {plan.edges.length} doors</figcaption>
    </figure>
  )
}

// (3) the AI's top picks re-run in the detailed simulation, and the random-plan comparison.
function Checks({ design, recommend }: { design: Design; recommend: Recommend | null }) {
  const a = design.across_plans
  const n = design.by_panic[String(design.design_panic)]?.chosen_n_exits
  return (
    <figure className="space-y-2 text-[13px]">
      {recommend && (
        <table className="num w-full">
          <thead><tr className="text-left text-faint"><th className="font-normal">AI's top picks</th><th className="text-right font-normal">AI</th><th className="text-right font-normal">checked</th></tr></thead>
          <tbody>{recommend.top5.map((t, i) => (
            <tr key={i} className="border-t border-line"><td>{t.exits.length} exits</td><td className="text-right">{t.predicted_s} s</td>
              <td className={`text-right ${t.verified_s != null && t.verified_s <= design.safe_limit_s ? 'text-ink' : 'text-alert'}`}>{t.verified_s ?? 'fails'}{t.verified_s != null && ' s'}</td></tr>
          ))}</tbody>
        </table>
      )}
      {recommend?.fewest_exits != null && n != null && recommend.fewest_exits !== n && (
        <p className="leading-snug text-faint">The AI's quick screen asks for {recommend.fewest_exits} exits; the detailed simulation shows {n} are enough. It errs on the cautious side, and the simulation has the final word.</p>
      )}
      {a && <p className="leading-snug text-faint">{a.solved_both} random floor plans: {a.mean_exits_ours} exits on average with QueuePilot, {a.mean_exits_rule} spread evenly.</p>}
    </figure>
  )
}
