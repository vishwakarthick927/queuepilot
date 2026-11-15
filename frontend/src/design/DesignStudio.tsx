import { useEffect, useMemo, useState } from 'react'
import { Guard } from '../components/Guard'
import Curve from './Curve'
import { design, labelList, nameScenario, plan, recommend, results, type Design, type Plan, type Recommend, type Score } from './data'
import ModelDrawer from './ModelDrawer'
import PlanView, { DENSITY_STOPS, densityColor } from './PlanView'
import { Head, Stat, Tag, fmt, mmss } from './ui'

// QueuePilot Design Studio: where should the fire exits go? (docs/BUILD.md "The MVP screen")
// Every number is read from data/design/*.json (MAIN) or research/design/*.json (WIN). Nothing typed by hand.

const FRAME_MS = 70                                   // one 2-second simulation step per 70 ms on screen
const PANIC_NAME: Record<string, string> = { '0': 'Calm', '0.4': 'Uneasy', '0.8': 'Panic' }

export default function DesignStudio() {
  if (!plan) return <Empty text="No floor plan yet: waiting for data/design/demo_plan.json." />
  if (!design) return <Empty text="No design results yet: waiting for data/design/design.json." />
  return <Studio P={plan.data} D={design.data} />
}

// The best scored layout with exactly n exits (smallest worst case; never-cleared counts as worst).
function bestWith(layouts: Score[], n: number) {
  const w = (s: Score) => s.worst_case_s ?? Infinity
  return layouts.filter(l => l.exits.length === n).sort((a, b) => w(a) - w(b))[0]
}

function Studio({ P, D }: { P: Plan; D: Design }) {
  const q = new URLSearchParams(window.location.search)
  const stub = [plan, design, results, recommend].some(f => f?.stub)
  const [panic, setPanic] = useState(D.design_panic)
  const R = Object.values(D.by_panic).find(r => r.panic === panic) ?? D.by_panic[String(D.design_panic)]
  const chosenN = R.chosen_n_exits, ruleN = R.rule_n_exits
  const [n, setN] = useState(chosenN ?? 3)
  // ?compare=1&t=45 opens the side-by-side evacuation at step 45; ?rec=1 skips the Recommend press
  const [step, setStep] = useState(Number(q.get('t')) || 0)
  const [playing, setPlaying] = useState(false)
  const [compare, setCompare] = useState(q.get('compare') === '1')
  const [revealed, setRevealed] = useState(q.get('rec') === '1' || compare)
  const [drawer, setDrawer] = useState(q.get('model') === '1')     // ?model=1 opens the model drawer
  const F = D.frames
  const last = Math.max(F.chosen.people.length, F.rule_of_thumb.people.length) - 1

  // the animation clock: one step per tick, stop at the end
  useEffect(() => {
    if (!playing) return
    const id = setInterval(() => setStep(s => (s >= last ? (setPlaying(false), s) : s + 1)), FRAME_MS)
    return () => clearInterval(id)
  }, [playing, last])

  const layout = bestWith(R.layouts, n)
  const value = useMemo(() => Object.fromEntries((recommend?.data.candidate_value ?? []).map(v => [v.id, v.score])), [])
  const limit = P.safe_limit_s
  const total = P.nodes.reduce((s, x) => s + x.people0, 0)
  const nodeName = (i: number) => P.nodes[i]?.name || `#${i}`
  const play = () => { setCompare(true); if (step >= last) setStep(0); setPlaying(p => !p) }
  const across = D.across_plans

  return (
    <div className="grid h-screen grid-rows-[60px_1fr] overflow-hidden">
      {/* top bar */}
      <header className="flex items-center gap-5 border-b border-line bg-panel/90 px-6">
        <div className="flex items-baseline gap-3">
          <span className="text-[20px] font-semibold tracking-tight">QueuePilot <span className="text-qp">Design</span></span>
          <span className="text-[14px] text-faint">fire exit placement for architects</span>
        </div>
        <div className="ml-6 text-[15px] text-dim">{P.name}</div>
        <div className="ml-auto flex items-center gap-3">
          {stub && <Tag tone="alert">stub data, not final</Tag>}
          <Tag>all results simulated</Tag>
          <button onClick={() => setDrawer(true)} className="rounded-sm border border-line-strong px-4 py-2 text-[14px] text-ink hover:border-qp">How the model works</button>
        </div>
      </header>

      <main className="grid min-h-0 grid-cols-[300px_1fr_380px] grid-rows-[1fr_220px] gap-px bg-line">
        {/* LEFT: the brief */}
        <section className="row-span-2 flex min-h-0 flex-col gap-5 bg-panel p-6">
          <Head n="01" title="The brief" />
          <div className="space-y-3.5">
            <Stat label="Occupancy" value={fmt(total)} unit="people" />
            <Stat label="Floor area" value={fmt(Math.round(P.nodes.reduce((s, x) => s + (x.kind === 'exit' ? 0 : x.area_m2), 0)))} unit="m²" />
            <Stat label="Safe limit to empty" value={limit} unit="s" />
            <Stat label="Possible exit positions" value={P.candidates.length}
              sub={`every layout tested: no fire, ${P.fires.length} corridor fires, and a fire blocking each exit`} />
          </div>
          <fieldset className="space-y-2">
            <legend className="text-[12px] uppercase tracking-[0.12em] text-dim">Crowd behaviour</legend>
            <div className="grid grid-cols-3 gap-px bg-line-strong p-px">
              {D.panic_levels.map(v => (
                <button key={v} onClick={() => setPanic(v)} aria-pressed={panic === v}
                  className={`py-2 text-[15px] ${panic === v ? 'bg-qp font-semibold text-bg' : 'bg-panel text-dim hover:text-ink'}`}>{PANIC_NAME[String(v)] ?? v}</button>
              ))}
            </div>
            <div className="num text-[12px] text-faint">panic level {panic.toFixed(1)}</div>
          </fieldset>
          <label className="block space-y-2">
            <span className="flex justify-between text-[12px] uppercase tracking-[0.12em] text-dim">Number of exits <span className="num text-[15px] text-ink">{revealed ? n : '–'}</span></span>
            <input type="range" disabled={!revealed} min={R.curve[0].n_exits} max={R.curve[R.curve.length - 1].n_exits} value={n}
              onChange={e => setN(Number(e.target.value))} className="w-full" aria-label="Number of exits" />
            <span className="num flex justify-between text-[13px] text-faint"><span>{R.curve[0].n_exits}</span><span>code minimum 2</span><span>{R.curve[R.curve.length - 1].n_exits}</span></span>
          </label>
          <div className="mt-auto text-[13px] leading-snug text-faint">Never below the building-code minimum (2 exits, {P.max_travel_m} m travel). The fire authority approves.</div>
        </section>

        {/* CENTRE: the plan, or the side-by-side evacuation */}
        <section className="flex min-h-0 flex-col bg-bg">
          <div className="flex items-center gap-4 border-b border-line px-5 py-3">
            <Head n="02" title={compare ? `Evacuation, panic: ${nameScenario(D.frames_scenario) ?? 'worst case'}` : revealed ? `QueuePilot, ${n} exits` : `Rule of thumb, ${ruleN} exits spread out`} />
            <div className="ml-auto flex items-center gap-3">
              {compare && <span className="num text-[15px] text-dim">t = <span className="text-ink">{mmss(step * P.dt_s)}</span></span>}
              <button onClick={play} className="rounded-sm bg-qp px-5 py-2 text-[15px] font-semibold text-bg hover:brightness-110">
                {playing ? 'Pause' : step > 0 && step < last ? 'Resume' : 'Play evacuation'}
              </button>
              {compare && <button onClick={() => { setCompare(false); setPlaying(false); setStep(0) }} className="rounded-sm border border-line-strong px-4 py-2 text-[14px] text-dim hover:text-ink">Back to plan</button>}
            </div>
          </div>
          <Guard name="Floor plan">
            {compare ? <SideBySide P={P} D={D} step={step} total={total} limit={limit} /> : (
              <div className="min-h-0 flex-1 px-6 py-4">
                {revealed
                  ? <PlanView plan={P} exits={layout?.exits ?? []} minCut={D.min_cut} value={value} />
                  : <PlanView plan={P} exits={R.rule_of_thumb?.exits ?? []} ours={false} />}
              </div>
            )}
          </Guard>
          <div className="flex items-center gap-6 border-t border-line px-5 py-2 text-[13px] text-dim">
            {compare ? (
              <>
                <span>Density</span>
                {DENSITY_STOPS.map(d => <span key={d} className="num flex items-center gap-1.5"><i className="inline-block h-3 w-5" style={{ background: densityColor(d) }} />{d}{d === 4 ? '+' : ''}</span>)}
                <span>people/m²</span>
                <input type="range" min={0} max={last} value={step} onChange={e => { setPlaying(false); setStep(Number(e.target.value)) }} className="ml-auto w-72" aria-label="Scrub the evacuation" />
              </>
            ) : (
              <>
                <span className="flex items-center gap-2"><i className={`inline-block h-3.5 w-3.5 rounded-full ${revealed ? 'bg-qp' : 'bg-ink'}`} />exit built</span>
                <span className="flex items-center gap-2"><i className="inline-block h-3.5 w-3.5 rounded-full border border-dashed border-faint" />possible position{recommend ? ' (size = value)' : ''}</span>
                {revealed && <span className="flex items-center gap-2"><i className="inline-block h-2 w-4 bg-qp" />bottleneck (min-cut)</span>}
                <span className="ml-auto">room labels: floor area</span>
              </>
            )}
          </div>
        </section>

        {/* RIGHT: the verdict */}
        <section className="row-span-2 flex min-h-0 flex-col gap-4 overflow-hidden bg-panel p-6">
          <Head n="03" title="Verdict" tag={<Tag>simulated</Tag>} />
          {!revealed ? (
            <Before ruleN={ruleN} ruleS={R.rule_of_thumb?.worst_case_s ?? null} limit={limit} screened={recommend?.data.screened}
              onGo={() => { setRevealed(true); setN(chosenN ?? 3) }} />
          ) : (
            <>
              <div>
                <div className="text-[13px] uppercase tracking-[0.12em] text-dim">Fewest exits that pass</div>
                <div className="mt-1 flex items-baseline gap-3">
                  <span className="num text-[60px] font-semibold leading-none text-qp">{chosenN ?? '–'}</span>
                  <span className="text-[17px] text-dim">vs <span className="num text-ink">{ruleN ?? 'none'}</span> by rule of thumb</span>
                </div>
                <div className="mt-2 text-[14px] text-dim">{PANIC_NAME[String(panic)]?.toLowerCase()} crowd, every fire scenario, limit {limit} s
                  {R.rule_same_count && <> · rule of thumb with {chosenN}: <span className={`num ${R.rule_same_count.passes ? 'text-ink' : 'text-alert'}`}>{R.rule_same_count.worst_case_s ?? 'never clears'}{R.rule_same_count.worst_case_s ? ' s' : ''}</span></>}</div>
              </div>
              {R.chosen?.worst_case_s != null && <Gauge value={R.chosen.worst_case_s} limit={limit} bound={panic === D.design_panic ? D.bound_maxflow_s : null} />}
              <div className="grid grid-cols-2 gap-x-5 gap-y-4">
                <Stat label="Exits saved" value={R.exits_saved ?? '–'} tone="qp" />
                <Stat label="Floor area freed" value={R.area_freed_m2 ?? '–'} unit="m²" sub={`at ${D.exit_core_m2} m² per exit core`} />
                <Stat label="Cost of panic" value={D.cost_of_panic.panic_s != null && D.cost_of_panic.calm_s != null ? `+${D.cost_of_panic.panic_s - D.cost_of_panic.calm_s}` : '–'} unit="s"
                  sub={`our layout: ${D.cost_of_panic.calm_s} s calm → ${D.cost_of_panic.panic_s} s panic`} />
              </div>
              {across && <Across a={across} />}
              {panic === D.design_panic && D.min_cut.length > 0 && (
                <div className="border-l-2 border-qp bg-raised px-4 py-2.5">
                  <div className="text-[12px] uppercase tracking-[0.12em] text-dim">Bottleneck (min-cut): widen first</div>
                  <div className="mt-1 text-[15px] leading-snug">{D.min_cut.map(i => P.edges[i]).filter(Boolean).map(e => `${nodeName(e.a)} → ${nodeName(e.b)} ${e.width_m} m`).join(' · ')}</div>
                </div>
              )}
              {recommend ? <AiCheck rec={recommend.data} limit={limit} /> : (
                <div className="mt-auto text-[13px] text-faint">PG-GNN screening results not produced yet (research/design/recommend.json).</div>
              )}
            </>
          )}
        </section>

        {/* BOTTOM: the curve */}
        <section className="flex min-h-0 flex-col bg-panel px-5 pb-3 pt-4">
          <Head n="04" title="Exits vs worst-case clearance" tag={
            <span className="flex items-center gap-4 text-[13px] text-dim">
              {revealed && <span className="flex items-center gap-2"><i className="inline-block h-0.5 w-5 bg-qp" />QueuePilot</span>}
              <span className="flex items-center gap-2"><i className="inline-block h-0.5 w-5 bg-dim" />Rule of thumb</span>
              <Tag>simulated</Tag>
            </span>} />
          <div className="min-h-0 flex-1"><Guard name="Curve"><Curve curve={R.curve} limit={limit} selected={revealed ? n : ruleN ?? 0} onPick={setN} ours={revealed} /></Guard></div>
        </section>
      </main>
      <ModelDrawer open={drawer} onClose={() => setDrawer(false)} plan={P} results={results?.data ?? null} recommend={recommend?.data ?? null} stub={!!results?.stub} />
    </div>
  )
}

// Both layouts, same number of exits, same scenario, played side by side.
function SideBySide({ P, D, step, total, limit }: { P: Plan; D: Design; step: number; total: number; limit: number }) {
  const sides = [['rule_of_thumb', 'Rule of thumb'], ['chosen', 'QueuePilot']] as const
  return (
    <div className="grid min-h-0 flex-1 grid-cols-2 gap-px bg-line">
      {sides.map(([k, name]) => {
        const f = D.frames[k], s = Math.min(step, f.people.length - 1)
        const left = Math.max(0, Math.round(total - (f.evacuated[s] ?? 0)))
        const late = step * P.dt_s > limit && left > 0
        return (
          <div key={k} className="flex min-h-0 flex-col bg-bg px-4 pb-2 pt-3">
            <div className="flex items-baseline justify-between">
              <span className={`text-[17px] font-medium ${k === 'chosen' ? 'text-qp' : 'text-ink'}`}>{name}, {f.exits.length} exits</span>
              <span className="num text-[13px] text-faint">{labelList(f.exits)}</span>
            </div>
            <div className="num mt-1 flex items-baseline gap-2 text-[15px] text-dim">
              still inside <span className={`text-[26px] ${late ? 'text-alert' : 'text-ink'}`}>{left}</span>
              <span className="ml-auto">{f.clearance_s != null ? `empty at ${f.clearance_s} s` : 'not empty within the run'}</span>
            </div>
            <div className="min-h-0 flex-1 py-2">
              <PlanView plan={P} exits={f.exits} blocked={f.lost_exit ?? null} people={f.people[s]} compact ours={k === 'chosen'} />
            </div>
          </div>
        )
      })}
    </div>
  )
}

// What the PG-GNN screened, and how the simulator re-checked its top 5.
function AiCheck({ rec, limit }: { rec: Recommend; limit: number }) {
  return (
    <div className="mt-auto">
      <div className="text-[12px] uppercase tracking-[0.12em] text-dim">AI proposes, simulator verifies</div>
      <div className="mt-1 text-[14px] text-dim"><span className="num text-ink">{fmt(rec.screened)}</span> layouts screened by the PG-GNN; top 5 re-checked</div>
      <table className="num mt-1.5 w-full text-[13px]">
        <thead><tr className="text-left text-faint"><th className="font-normal">exits</th><th className="font-normal">PG-GNN</th><th className="font-normal">simulator</th></tr></thead>
        <tbody>{rec.top5.map((t, i) => (
          <tr key={i} className="border-t border-line"><td className="py-0.5">{labelList(t.exits)}</td><td>{t.predicted_s ?? '–'} s</td>
            <td className={t.verified_s == null || t.verified_s > limit ? 'text-alert' : 'text-ink'}>{t.verified_s ?? 'fails'}{t.verified_s != null && ' s'}</td></tr>
        ))}</tbody>
      </table>
    </div>
  )
}

// Before the architect presses Recommend: what the rule of thumb gives them.
function Before({ ruleN, ruleS, limit, screened, onGo }: { ruleN: number | null; ruleS: number | null; limit: number; screened?: number; onGo: () => void }) {
  return (
    <div className="flex flex-1 flex-col gap-5">
      <div>
        <div className="text-[13px] uppercase tracking-[0.12em] text-dim">Rule of thumb</div>
        <div className="mt-1 flex items-baseline gap-3">
          <span className="num text-[60px] font-semibold leading-none">{ruleN ?? '–'}</span><span className="text-[17px] text-dim">exits, spread as far apart as possible</span>
        </div>
      </div>
      {ruleS != null && <Gauge value={ruleS} limit={limit} bound={null} neutral />}
      <p className="text-[15px] leading-relaxed text-dim">The fewest spread-out exits that clear the building within {limit} s in every fire scenario.</p>
      <button onClick={onGo} className="mt-auto rounded-sm bg-qp py-4 text-[18px] font-semibold text-bg hover:brightness-110">Recommend exits</button>
      {screened !== undefined && <p className="text-center text-[13px] text-faint">screens {fmt(screened)} layouts with the PG-GNN, then the simulator verifies the top 5</p>}
    </div>
  )
}

// Worst-case clearance on a machined scale: ticks every 30 s, the safe limit, the max-flow bound.
function Gauge({ value, limit, bound, neutral }: { value: number; limit: number; bound: number | null; neutral?: boolean }) {
  const max = Math.ceil(Math.max(value, limit) * 1.25 / 60) * 60
  const pct = (v: number) => `${(v / max) * 100}%`
  const bar = value > limit ? 'bg-alert' : neutral ? 'bg-ink/70' : 'bg-qp'
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span className="text-[12px] uppercase tracking-[0.12em] text-dim">Worst-case clearance</span>
        <span className={`num text-[28px] ${value > limit ? 'text-alert' : 'text-ink'}`}>{value}<span className="ml-1 text-[15px] text-dim">s</span></span>
      </div>
      <div className="relative mt-3 h-4 bg-raised">
        <div className={`absolute inset-y-0 left-0 ${bar}`} style={{ width: pct(Math.min(value, max)) }} />
        <div className="absolute -inset-y-1.5 w-0.5 bg-alert" style={{ left: pct(limit) }} />
        {bound != null && <div className="absolute -inset-y-1 w-px bg-ink/70" style={{ left: pct(bound) }} />}
      </div>
      <div className="relative mt-1 h-4">
        {Array.from({ length: max / 30 + 1 }, (_, i) => i * 30).map(t => (
          <span key={t} className="num absolute -translate-x-1/2 text-[11px] text-faint" style={{ left: pct(t) }}>{t % 60 === 0 ? t : '·'}</span>
        ))}
      </div>
      <div className="mt-1 flex gap-4 whitespace-nowrap text-[13px] text-dim">
        <span><i className="mr-1.5 inline-block h-3 w-0.5 bg-alert align-middle" />limit {limit} s</span>
        {bound != null && <span><i className="mr-1.5 inline-block h-3 w-px bg-ink/70 align-middle" />max-flow bound {bound} s</span>}
      </div>
    </div>
  )
}

// The honest version of the hero number: not just the demo plan, random plans too.
function Across({ a }: { a: NonNullable<Design['across_plans']> }) {
  const rows = (a as { rows?: { ours: number | null; rule: number | null }[] }).rows ?? []
  const both = rows.filter(r => r.ours != null && r.rule != null)
  const more = both.filter(r => (r.ours as number) > (r.rule as number)).length
  return (
    <div className="border-t border-line pt-3">
      <div className="text-[12px] uppercase tracking-[0.12em] text-dim">Across {a.solved_both} random floor plans</div>
      <div className="num mt-1 text-[22px]"><span className="text-qp">{a.mean_exits_ours}</span> <span className="text-[15px] text-dim">vs</span> {a.mean_exits_rule} <span className="text-[15px] text-dim">exits on average</span></div>
      <div className="mt-0.5 text-[13px] text-dim">fewer on {a.plans_where_ours_needs_fewer}, the same on {both.length - a.plans_where_ours_needs_fewer - more}, more on {more}</div>
    </div>
  )
}

function Empty({ text }: { text: string }) {
  return <div className="grid h-screen place-items-center"><p className="num text-[16px] text-dim">{text}</p></div>
}
