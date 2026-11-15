import { useCallback, useEffect, useMemo, useState } from 'react'
import { Guard } from '../components/Guard'
import Curve from './Curve'
import { design, labelList, nameScenario, plan, recommend, results, type Design, type Frames, type Plan, type Recommend, type Score } from './data'
import ModelDrawer from './ModelDrawer'
import PlanView, { DENSITY_STOPS, densityColor } from './PlanView'
import { Head, Key, Row, Tag, fmt, mmss } from './ui'

// QueuePilot Design Studio: where should the fire exits go? (docs/BUILD.md "The MVP screen")
// Every number is read from data/design/*.json (MAIN) or research/design/*.json (WIN). Nothing typed by hand.
// Demo path, one key each: R recommend · Space play · M model · 1 2 3 crowd behaviour · ← → exits · Esc back.

const FRAME_MS = 70                                   // one 2-second simulation step per 70 ms on screen
const PANIC_NAME: Record<string, string> = { '0': 'Calm', '0.4': 'Uneasy', '0.8': 'Panic' }
const ONE_FONT = { '--font-mono': 'var(--font-sans)' } as React.CSSProperties   // one family on this page

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

// People per node at clock step s (step 0 = the starting crowd; the files hold people AFTER each step).
function frameAt(f: Frames, s: number, start: number[]) {
  if (s <= 0) return { people: start, out: 0 }
  const i = Math.min(s, f.people.length) - 1
  return { people: f.people[i], out: f.evacuated[i] ?? 0 }
}

function Studio({ P, D }: { P: Plan; D: Design }) {
  const q = new URLSearchParams(window.location.search)
  const stub = [plan, design, results, recommend].some(f => f?.stub)
  const [panic, setPanic] = useState(D.design_panic)
  const R = Object.values(D.by_panic).find(r => r.panic === panic) ?? D.by_panic[String(D.design_panic)]
  const chosenN = R.chosen_n_exits, ruleN = R.rule_n_exits
  const [n, setN] = useState(chosenN ?? 3)
  // ?compare=1&t=60 opens the side-by-side at step 60 · ?rec=1 skips the Recommend press · ?model=1 opens the drawer
  const [step, setStep] = useState(Number(q.get('t')) || 0)
  const [playing, setPlaying] = useState(false)
  const [compare, setCompare] = useState(q.get('compare') === '1')
  const [revealed, setRevealed] = useState(q.get('rec') === '1' || compare)
  const [drawer, setDrawer] = useState(q.get('model') === '1')
  const F = D.frames
  const last = Math.max(F.chosen.people.length, F.rule_of_thumb.people.length)
  const start = useMemo(() => P.nodes.map(x => x.people0), [P])
  const total = start.reduce((a, b) => a + b, 0)
  const limit = P.safe_limit_s
  const curve = R.curve
  const layout = bestWith(R.layouts, n)
  const value = useMemo(() => Object.fromEntries((recommend?.data.candidate_value ?? []).map(v => [v.id, v.score])), [])

  // the animation clock: one step per tick, stop at the end
  useEffect(() => {
    if (!playing) return
    const id = setInterval(() => setStep(s => (s >= last ? (setPlaying(false), s) : s + 1)), FRAME_MS)
    return () => clearInterval(id)
  }, [playing, last])

  const recommendNow = useCallback(() => { setRevealed(true); setN(chosenN ?? 3) }, [chosenN])
  const play = useCallback(() => { setRevealed(true); setCompare(true); setStep(s => (s >= last ? 0 : s)); setPlaying(p => !p) }, [last])
  const back = useCallback(() => { setCompare(false); setPlaying(false); setStep(0) }, [])

  // keyboard: one key per demo step
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement && e.key !== 'Escape') return
      const lo = curve[0].n_exits, hi = curve[curve.length - 1].n_exits
      if (e.key === 'r' || e.key === 'R') recommendNow()
      else if (e.key === ' ' || e.key === 'p') { e.preventDefault(); play() }
      else if (e.key === 'm' || e.key === 'M') setDrawer(d => !d)
      else if (e.key === 'Escape') { if (drawer) setDrawer(false); else back() }
      else if (['1', '2', '3'].includes(e.key)) setPanic(D.panic_levels[Number(e.key) - 1] ?? panic)
      else if (e.key === 'ArrowLeft' && revealed) setN(v => Math.max(lo, v - 1))
      else if (e.key === 'ArrowRight' && revealed) setN(v => Math.min(hi, v + 1))
    }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [recommendNow, play, back, drawer, revealed, curve, D.panic_levels, panic])

  return (
    <div className="grid h-screen grid-rows-[56px_1fr] overflow-hidden" style={ONE_FONT}>
      <header className="flex items-center gap-6 border-b border-line bg-panel px-6">
        <span className="text-[18px] font-semibold">QueuePilot <span className="text-qp">Design</span></span>
        <span className="text-[13px] text-dim">{P.name}</span>
        <div className="ml-auto flex items-center gap-3">
          {stub && <Tag tone="alert">stub data, not final</Tag>}
          <Tag>all results simulated</Tag>
          <button onClick={() => setDrawer(true)} className="rounded-sm border border-line-strong px-3 py-1.5 text-[13px] text-ink hover:border-ink">How the model works<Key k="M" /></button>
        </div>
      </header>

      <main className="grid min-h-0 grid-cols-[280px_1fr_360px] grid-rows-[1fr_200px] gap-px bg-line">
        <Brief P={P} D={D} total={total} panic={panic} setPanic={setPanic} n={n} setN={setN} revealed={revealed} curve={curve} />

        {/* CENTRE: the floor plan is the hero */}
        <section className="flex min-h-0 flex-col bg-bg">
          <div className="flex items-center gap-4 border-b border-line px-5 py-2.5">
            <h1 className="text-[18px] font-semibold">
              {compare ? <>Evacuation under panic: {nameScenario(D.frames_scenario) ?? 'worst case'}</>
                : revealed ? <span className="text-qp">QueuePilot layout, {n} exits</span>
                  : <>Rule of thumb layout, {ruleN} exits spread out</>}
            </h1>
            <div className="ml-auto flex items-center gap-2">
              {compare && <button onClick={back} className="rounded-sm border border-line-strong px-3 py-1.5 text-[13px] text-dim hover:text-ink">Back to plan<Key k="Esc" /></button>}
              <button onClick={play} className="rounded-sm bg-qp px-4 py-1.5 text-[13px] font-semibold text-bg hover:brightness-110">
                {playing ? 'Pause' : compare && step > 0 && step < last ? 'Resume' : 'Play side by side'}<Key k="Space" />
              </button>
            </div>
          </div>
          <Guard name="Floor plan">
            {compare ? <SideBySide P={P} D={D} step={step} total={total} limit={limit} start={start} /> : (
              <div className="min-h-0 flex-1 px-6 py-3">
                {revealed
                  ? <PlanView plan={P} exits={layout?.exits ?? []} minCut={D.min_cut} value={value} />
                  : <PlanView plan={P} exits={R.rule_of_thumb?.exits ?? []} ours={false} />}
              </div>
            )}
          </Guard>
          {compare
            ? <Timeline D={D} step={step} last={last} dt={P.dt_s} limit={limit} onScrub={s => { setPlaying(false); setStep(s) }} />
            : <PlanLegend revealed={revealed} />}
        </section>

        {/* RIGHT: the verdict */}
        <section className="row-span-2 flex min-h-0 flex-col gap-3 overflow-hidden bg-panel p-5">
          <Head n="03" title="Verdict" tag={<Tag>simulated</Tag>} />
          {!revealed
            ? <Before ruleN={ruleN} ruleS={R.rule_of_thumb?.worst_case_s ?? null} limit={limit} screened={recommend?.data.screened} onGo={recommendNow} />
            : <Verdict P={P} D={D} panic={panic} />}
        </section>

        {/* BOTTOM: the curve */}
        <section className="flex min-h-0 flex-col bg-panel px-5 pb-2 pt-3">
          <Head n="04" title="Exits vs worst-case time to empty" tag={<Tag>simulated</Tag>} />
          <div className="min-h-0 flex-1"><Guard name="Curve"><Curve curve={curve} limit={limit} selected={revealed ? n : ruleN ?? 0} onPick={v => revealed && setN(v)} ours={revealed} /></Guard></div>
        </section>
      </main>
      <ModelDrawer open={drawer} onClose={() => setDrawer(false)} plan={P} results={results?.data ?? null} recommend={recommend?.data ?? null} stub={!!results?.stub} />
    </div>
  )
}

// LEFT: the architect's brief and the two controls.
function Brief({ P, D, total, panic, setPanic, n, setN, revealed, curve }: {
  P: Plan; D: Design; total: number; panic: number; setPanic: (v: number) => void; n: number; setN: (v: number) => void; revealed: boolean; curve: Design['by_panic'][string]['curve']
}) {
  return (
    <section className="row-span-2 flex min-h-0 flex-col gap-5 bg-panel p-5">
      <div>
        <Head n="01" title="The brief" />
        <Row label="Occupancy" value={fmt(total)} unit="people" />
        <Row label="Floor area" value={fmt(Math.round(P.nodes.reduce((s, x) => s + (x.kind === 'exit' ? 0 : x.area_m2), 0)))} unit="m²" />
        <Row label="Safe limit to empty" value={P.safe_limit_s} unit="s" />
        <Row label="Possible exit positions" value={P.candidates.length} />
        <Row label="Fire scenarios per layout" value={1 + P.fires.length + '+'} note="no fire, each corridor fire, a fire blocking each exit" />
      </div>
      <fieldset>
        <legend className="mb-2 text-[13px] text-dim">Crowd behaviour</legend>
        <div className="grid grid-cols-3 gap-px border border-line-strong bg-line-strong">
          {D.panic_levels.map((v, i) => (
            <button key={v} onClick={() => setPanic(v)} aria-pressed={panic === v}
              className={`py-2 text-[13px] ${panic === v ? 'bg-ink font-semibold text-bg' : 'bg-panel text-dim hover:text-ink'}`}>{PANIC_NAME[String(v)] ?? v}<Key k={String(i + 1)} /></button>
          ))}
        </div>
        <div className="num mt-1.5 text-[13px] text-faint">panic level {panic.toFixed(1)} of 1</div>
      </fieldset>
      <label className="block">
        <span className="flex items-baseline justify-between text-[13px] text-dim">Number of exits<span className="num text-[18px] font-semibold text-ink">{revealed ? n : '–'}</span></span>
        <input type="range" disabled={!revealed} min={curve[0].n_exits} max={curve[curve.length - 1].n_exits} value={n}
          onChange={e => setN(Number(e.target.value))} className="mt-2 w-full" aria-label="Number of exits" />
        <span className="num flex justify-between text-[13px] text-faint"><span>{curve[0].n_exits}</span><span>← →</span><span>{curve[curve.length - 1].n_exits}</span></span>
      </label>
      <p className="mt-auto text-[13px] leading-snug text-faint">Never below the code minimum: 2 exits, {P.max_travel_m} m travel. We place exits and prove it by simulation; the fire authority approves.</p>
    </section>
  )
}

// RIGHT, after Recommend.
function Verdict({ P, D, panic }: { P: Plan; D: Design; panic: number }) {
  const R = Object.values(D.by_panic).find(r => r.panic === panic)!
  const name = (i: number) => P.nodes[i]?.name || `#${i}`
  const same = R.rule_same_count
  return (
    <>
      <div>
        <div className="text-[13px] text-dim">Fewest exits that pass, {PANIC_NAME[String(panic)]?.toLowerCase()} crowd</div>
        <div className="mt-1 flex items-baseline gap-3">
          <span className="num text-[44px] font-semibold leading-none text-qp">{R.chosen_n_exits ?? '–'}</span>
          <span className="text-[13px] text-dim">QueuePilot</span>
          <span className="num ml-auto text-[44px] font-semibold leading-none text-ink">{R.rule_n_exits ?? '–'}</span>
          <span className="text-[13px] text-dim">rule of thumb</span>
        </div>
      </div>
      {R.chosen?.worst_case_s != null && <Gauge value={R.chosen.worst_case_s} limit={P.safe_limit_s} bound={panic === D.design_panic ? D.bound_maxflow_s : null} rule={same?.worst_case_s ?? null} n={R.chosen_n_exits} />}
      <div>
        <Row label="Exits saved" value={R.exits_saved ?? '–'} tone="qp" />
        <Row label="Floor area freed" value={R.area_freed_m2 ?? '–'} unit="m²" note={`at ${D.exit_core_m2} m² per exit core (assumption)`} />
        <Row label="Cost of panic, our layout" value={D.cost_of_panic.panic_s != null && D.cost_of_panic.calm_s != null ? `+${D.cost_of_panic.panic_s - D.cost_of_panic.calm_s}` : '–'} unit="s"
          note={`${D.cost_of_panic.calm_s} s calm → ${D.cost_of_panic.panic_s} s panic`} />
        {D.across_plans && <Across a={D.across_plans} />}
        {panic === D.design_panic && D.min_cut.length > 0 && (
          <Row label="Bottleneck (min-cut)" value={D.min_cut.map(i => P.edges[i]).filter(Boolean).map(e => name(e.b).replace('Exit ', '')).join(' ')}
            note={`exit doors ${D.min_cut.map(i => P.edges[i]?.width_m).join(' / ')} m: widen first`} />
        )}
      </div>
      {recommend ? <AiCheck rec={recommend.data} limit={P.safe_limit_s} /> : <p className="mt-auto text-[13px] text-faint">PG-GNN screening not produced yet (research/design/recommend.json).</p>}
    </>
  )
}

// The honest version of the hero number: random plans, not just the demo plan.
function Across({ a }: { a: NonNullable<Design['across_plans']> }) {
  const rows = (a as { rows?: { ours: number | null; rule: number | null }[] }).rows ?? []
  const both = rows.filter(r => r.ours != null && r.rule != null)
  const more = both.filter(r => (r.ours as number) > (r.rule as number)).length
  return <Row label={`Average exits, ${a.solved_both} random plans`} value={<><span className="text-qp">{a.mean_exits_ours}</span> vs {a.mean_exits_rule}</>}
    note={`fewer on ${a.plans_where_ours_needs_fewer}, same on ${both.length - a.plans_where_ours_needs_fewer - more}, more on ${more}`} />
}

// Both layouts, same number of exits, same scenario, same clock.
function SideBySide({ P, D, step, total, limit, start }: { P: Plan; D: Design; step: number; total: number; limit: number; start: number[] }) {
  const sides = [['rule_of_thumb', 'Rule of thumb', 'text-ink'], ['chosen', 'QueuePilot', 'text-qp']] as const
  const past = step * P.dt_s >= limit
  return (
    <div className="grid min-h-0 flex-1 grid-cols-2 gap-px bg-line">
      {sides.map(([k, name, color]) => {
        const f = D.frames[k], { people, out } = frameAt(f, step, start)
        const left = Math.max(0, Math.round(total - out))
        const late = past && left > 0
        return (
          <div key={k} className="flex min-h-0 flex-col bg-bg px-4 pt-3">
            <div className="flex items-baseline justify-between">
              <span className={`text-[18px] font-semibold ${color}`}>{name}</span>
              <span className="num text-[13px] text-dim">{f.exits.length} exits: {labelList(f.exits)}</span>
            </div>
            <div className="mt-1 flex items-baseline gap-3">
              <span className={`num text-[44px] font-semibold leading-none ${late ? 'text-alert' : left === 0 ? color : 'text-ink'}`}>{left}</span>
              <span className="text-[13px] text-dim">still inside{late && <span className="text-alert">, past the {limit} s limit</span>}{left === 0 && ', all out'}</span>
            </div>
            <div className="min-h-0 flex-1 py-2">
              <PlanView plan={P} exits={f.exits} blocked={f.lost_exit ?? null} people={people} compact ours={k === 'chosen'} />
            </div>
          </div>
        )
      })}
    </div>
  )
}

// One clock for both sides: playhead, the safe-limit moment, and when each building is empty.
function Timeline({ D, step, last, dt, limit, onScrub }: { D: Design; step: number; last: number; dt: number; limit: number; onScrub: (s: number) => void }) {
  const end = last * dt, pct = (t: number) => `${(Math.min(t, end) / end) * 100}%`
  const marks = [[D.frames.rule_of_thumb.clearance_s, 'bg-ink', 'rule of thumb empty'], [D.frames.chosen.clearance_s, 'bg-qp', 'QueuePilot empty']] as const
  return (
    <div className="flex items-center gap-5 border-t border-line px-5 py-2">
      <span className="num w-[72px] text-[18px] font-semibold">{mmss(step * dt)}</span>
      <div className="relative h-8 flex-1">
        <div className="absolute inset-x-0 top-3.5 h-1 bg-raised" />
        <div className="absolute top-3.5 h-1 bg-dim" style={{ width: pct(step * dt) }} />
        <div className="absolute top-1 h-6 w-0.5 bg-alert" style={{ left: pct(limit) }} />
        <span className="absolute -top-0.5 ml-1.5 text-[13px] text-alert" style={{ left: pct(limit) }}>limit {limit} s</span>
        {marks.map(([t, c, label]) => t != null && (
          <span key={label} className={`absolute top-2.5 h-3 w-3 -translate-x-1/2 rounded-full ${c}`} style={{ left: pct(t) }} title={`${label} at ${t} s`} />
        ))}
        <input type="range" min={0} max={last} value={step} onChange={e => onScrub(Number(e.target.value))} aria-label="Scrub the evacuation"
          className="absolute inset-0 w-full cursor-pointer opacity-0" />
      </div>
      <span className="flex items-center gap-1.5 text-[13px] text-dim"><i className="inline-block h-2.5 w-2.5 rounded-full bg-ink" />rule of thumb empty</span>
      <span className="flex items-center gap-1.5 text-[13px] text-dim"><i className="inline-block h-2.5 w-2.5 rounded-full bg-qp" />QueuePilot empty</span>
      <span className="flex items-center gap-1 text-[13px] text-dim">
        {DENSITY_STOPS.map(d => <i key={d} className="inline-block h-3 w-4" style={{ background: densityColor(d) }} />)}
        <span className="ml-1">0–4+ people/m²</span>
      </span>
    </div>
  )
}

function PlanLegend({ revealed }: { revealed: boolean }) {
  return (
    <div className="flex items-center gap-6 border-t border-line px-5 py-2 text-[13px] text-dim">
      <span className="flex items-center gap-2"><i className={`inline-block h-3 w-3 rounded-full ${revealed ? 'bg-qp' : 'bg-ink'}`} />exit built ({revealed ? 'QueuePilot' : 'rule of thumb'})</span>
      <span className="flex items-center gap-2"><i className="inline-block h-3 w-3 rounded-full border border-dashed border-faint" />possible position{revealed && recommend ? ', size = value' : ''}</span>
      {revealed && <span className="flex items-center gap-2"><i className="inline-block h-2 w-4 bg-qp" />bottleneck door</span>}
      <span className="ml-auto">rooms: name and floor area</span>
    </div>
  )
}

// What the PG-GNN screened, and how the simulator re-checked its top 5.
function AiCheck({ rec, limit }: { rec: Recommend; limit: number }) {
  return (
    <div className="mt-auto">
      <div className="text-[13px] text-dim">AI proposes, simulator verifies: <span className="num text-ink">{fmt(rec.screened)}</span> layouts screened by the PG-GNN</div>
      <table className="num mt-1 w-full text-[13px]">
        <thead><tr className="text-left text-faint"><th className="font-normal">top 5 exits</th><th className="text-right font-normal">PG-GNN</th><th className="text-right font-normal">simulator</th></tr></thead>
        <tbody>{rec.top5.map((t, i) => (
          <tr key={i} className="border-t border-line"><td className="py-0.5">{labelList(t.exits)}</td><td className="text-right">{t.predicted_s ?? '–'} s</td>
            <td className={`text-right ${t.verified_s == null || t.verified_s > limit ? 'text-alert' : 'text-ink'}`}>{t.verified_s ?? 'fails'}{t.verified_s != null && ' s'}</td></tr>
        ))}</tbody>
      </table>
    </div>
  )
}

// Before the architect presses Recommend: what the rule of thumb gives them.
function Before({ ruleN, ruleS, limit, screened, onGo }: { ruleN: number | null; ruleS: number | null; limit: number; screened?: number; onGo: () => void }) {
  return (
    <div className="flex flex-1 flex-col gap-4">
      <div>
        <div className="text-[13px] text-dim">Rule of thumb: fewest spread-out exits that pass</div>
        <div className="num mt-1 text-[44px] font-semibold leading-none">{ruleN ?? '–'}<span className="ml-2 text-[18px] font-normal text-dim">exits</span></div>
      </div>
      {ruleS != null && <Gauge value={ruleS} limit={limit} bound={null} rule={null} n={null} neutral />}
      <p className="text-[13px] leading-snug text-dim">Spread as far apart as possible, checked under panic in every fire scenario. Can fewer exits, placed better, do the same job?</p>
      <button onClick={onGo} className="mt-auto rounded-sm bg-qp py-3.5 text-[18px] font-semibold text-bg hover:brightness-110">Recommend exits<Key k="R" /></button>
      {screened !== undefined && <p className="text-center text-[13px] text-faint">the PG-GNN screens {fmt(screened)} layouts; the simulator re-checks the top 5</p>}
    </div>
  )
}

// Worst-case time to empty on a scale with the safe limit, the max-flow bound,
// and the rule of thumb with the SAME number of exits for comparison.
function Gauge({ value, limit, bound, rule, n, neutral }: { value: number; limit: number; bound: number | null; rule: number | null; n: number | null; neutral?: boolean }) {
  const max = Math.ceil(Math.max(value, limit, rule ?? 0) * 1.1 / 30) * 30
  const pct = (v: number) => `${(Math.min(v, max) / max) * 100}%`
  const bar = value > limit ? 'bg-alert' : neutral ? 'bg-ink' : 'bg-qp'
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span className="text-[13px] text-dim">Worst-case time to empty</span>
        <span className={`num text-[18px] font-semibold ${value > limit ? 'text-alert' : 'text-ink'}`}>{value} s</span>
      </div>
      <div className="relative mt-2 h-3 bg-raised">
        <div className={`absolute inset-y-0 left-0 ${bar}`} style={{ width: pct(value) }} />
        <div className="absolute -inset-y-1 w-0.5 bg-alert" style={{ left: pct(limit) }} />
        {bound != null && <div className="absolute -inset-y-1 w-px bg-dim" style={{ left: pct(bound) }} />}
      </div>
      {rule != null && (
        <div className="relative mt-1 h-3 bg-raised">
          <div className="absolute inset-y-0 left-0 bg-ink" style={{ width: pct(rule) }} />
          <div className="absolute -inset-y-1 w-0.5 bg-alert" style={{ left: pct(limit) }} />
        </div>
      )}
      <div className="mt-1 flex flex-wrap gap-x-4 text-[13px] text-dim">
        <span><i className="mr-1 inline-block h-3 w-0.5 bg-alert align-middle" />limit {limit} s</span>
        {rule != null && <span className="text-ink">rule of thumb with {n}: {rule} s</span>}
        {bound != null && <span><i className="mr-1 inline-block h-3 w-px bg-dim align-middle" />max-flow bound {bound} s</span>}
      </div>
    </div>
  )
}

function Empty({ text }: { text: string }) {
  return <div className="grid h-screen place-items-center"><p className="num text-[18px] text-dim">{text}</p></div>
}
