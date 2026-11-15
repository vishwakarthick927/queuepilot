import { useEffect, useMemo, useState } from 'react'
import { Guard } from '../components/Guard'
import Curve from './Curve'
import { countExits, design, plan, recommend, results, exitsOf } from './data'
import ModelDrawer from './ModelDrawer'
import PlanView, { DENSITY_STOPS, densityColor } from './PlanView'
import { Head, Stat, Tag, fmt, mmss } from './ui'

// QueuePilot Design Studio: where should the fire exits go? (docs/BUILD.md "The MVP screen")
// Every number is read from the JSON files in data.ts; nothing here is typed by hand.

const FRAME_MS = 70                                   // one 2-second simulation step per 70 ms on screen

export default function DesignStudio() {
  if (!plan) return <Empty text="No floor plan loaded. Waiting for data/design/demo_plan.json." />
  if (!design) return <Empty text="No design results yet. Waiting for data/design/design.json." />
  return <Studio />
}

function Studio() {
  const P = plan!.data, D = design!.data
  const stub = [plan, design, results, recommend].some(f => f?.stub)
  const chosenN = countExits(D.chosen), ruleN = countExits(D.rule_of_thumb)
  const [n, setN] = useState(chosenN)
  const [panic, setPanic] = useState(true)
  // ?compare=1&t=60 opens the side-by-side evacuation at step 60 (for rehearsals and screenshots)
  const q = new URLSearchParams(window.location.search)
  const [step, setStep] = useState(Number(q.get('t')) || 0)
  const [playing, setPlaying] = useState(false)
  const [compare, setCompare] = useState(q.get('compare') === '1')
  const [drawer, setDrawer] = useState(false)
  // Demo order: the page opens on the rule-of-thumb layout; "Recommend exits" reveals ours (?rec=1 skips ahead)
  const [revealed, setRevealed] = useState(q.get('rec') === '1' || q.get('compare') === '1')
  const frames = D.frames
  const last = Math.min(frames.chosen.length, frames.rule_of_thumb.length) - 1

  // the animation clock: advance one step per tick, stop at the end
  useEffect(() => {
    if (!playing) return
    const id = setInterval(() => setStep(s => (s >= last ? (setPlaying(false), s) : s + 1)), FRAME_MS)
    return () => clearInterval(id)
  }, [playing, last])

  const layout = D.layouts.find(l => countExits(l.exits) === n) ?? D.layouts.find(l => l.exits === D.chosen)!
  const point = D.curve.find(c => c.n_exits === n)
  const value = useMemo(() => Object.fromEntries((recommend?.data.candidate_value ?? []).map(v => [v.id, v.score])), [])
  const fire = P.fires.find(f => f.id === D.frames_fire)?.start_node ?? null
  const limit = P.safe_limit_s
  const worstChosen = panic ? D.cost_of_panic.panic_s : D.cost_of_panic.calm_s
  const cut = D.min_cut.map(i => P.edges[i]).filter(Boolean)
  const nodeName = (i: number) => P.nodes[i]?.name || `#${i}`
  const play = () => { setCompare(true); if (step >= last) setStep(0); setPlaying(p => !p) }
  const inside = (f: number[]) => f.reduce((s, v, i) => s + (P.nodes[i].kind === 'exit' ? 0 : v), 0)

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
            <Stat label="Occupancy" value={fmt(P.nodes.reduce((s, x) => s + x.people0, 0))} unit="people" />
            <Stat label="Floor area" value={fmt(Math.round(P.nodes.reduce((s, x) => s + (x.kind === 'exit' ? 0 : x.area_m2), 0)))} unit="m²" />
            <Stat label="Safe limit to empty" value={limit} unit="s" />
            <Stat label="Possible exit positions" value={P.candidates.length} sub={`${P.fires.length} fire scenarios tested on every layout`} />
          </div>
          <fieldset className="space-y-2">
            <legend className="text-[12px] uppercase tracking-[0.12em] text-dim">Behaviour</legend>
            <div className="grid grid-cols-2 gap-px bg-line-strong p-px">
              {[false, true].map(v => (
                <button key={String(v)} onClick={() => setPanic(v)} aria-pressed={panic === v}
                  className={`py-2 text-[15px] ${panic === v ? 'bg-qp text-bg font-semibold' : 'bg-panel text-dim hover:text-ink'}`}>{v ? 'Panic' : 'Calm'}</button>
              ))}
            </div>
          </fieldset>
          <label className="block space-y-2">
            <span className="flex justify-between text-[12px] uppercase tracking-[0.12em] text-dim">Number of exits <span className="num text-[15px] text-ink">{revealed ? n : '–'}</span></span>
            <input type="range" disabled={!revealed} min={D.curve[0].n_exits} max={D.curve[D.curve.length - 1].n_exits} value={n}
              onChange={e => setN(Number(e.target.value))} className="w-full" aria-label="Number of exits" />
            <span className="flex justify-between text-[13px] text-faint num"><span>{D.curve[0].n_exits}</span><span>code minimum 2</span><span>{D.curve[D.curve.length - 1].n_exits}</span></span>
          </label>
          <div className="mt-auto text-[13px] leading-snug text-faint">Never below the building-code minimum. The fire authority approves.</div>
        </section>

        {/* CENTRE: the plan, or the side-by-side evacuation */}
        <section className="flex min-h-0 flex-col bg-bg">
          <div className="flex items-center gap-4 border-b border-line px-5 py-3">
            <Head n="02" title={compare ? 'Evacuation, panic, fire in progress' : revealed ? `QueuePilot layout, ${n} exits` : `Rule of thumb, ${ruleN} exits evenly spaced`} />
            <div className="ml-auto flex items-center gap-3">
              {compare && <span className="num text-[15px] text-dim">t = <span className="text-ink">{mmss(step * P.dt_s)}</span></span>}
              <button onClick={play} className="rounded-sm bg-qp px-5 py-2 text-[15px] font-semibold text-bg hover:brightness-110">
                {playing ? 'Pause' : step > 0 && step < last ? 'Resume' : 'Play evacuation'}
              </button>
              {compare && <button onClick={() => { setCompare(false); setPlaying(false); setStep(0) }} className="rounded-sm border border-line-strong px-4 py-2 text-[14px] text-dim hover:text-ink">Back to plan</button>}
            </div>
          </div>
          <Guard name="Floor plan">
            {compare ? (
              <div className="grid min-h-0 flex-1 grid-rows-2 gap-px bg-line">
                {([['rule_of_thumb', `Rule of thumb, ${ruleN} exits evenly spaced`, D.rule_of_thumb], ['chosen', `QueuePilot, ${chosenN} exits`, D.chosen]] as const).map(([k, t, mask]) => {
                  const f = frames[k][Math.min(step, frames[k].length - 1)]
                  const left = Math.round(inside(f))
                  return (
                    <div key={k} className="relative min-h-0 bg-bg px-4 pb-2 pt-9">
                      <div className="absolute left-5 top-3 flex items-baseline gap-4">
                        <span className={`text-[16px] font-medium ${k === 'chosen' ? 'text-qp' : 'text-ink'}`}>{t}</span>
                        <span className="num text-[15px] text-dim">still inside <span className={left > 0 && step * P.dt_s > limit ? 'text-alert' : 'text-ink'}>{left}</span></span>
                      </div>
                      <PlanView plan={P} exits={mask} people={f} fireNode={fire} compact ours={k === 'chosen'} />
                    </div>
                  )
                })}
              </div>
            ) : (
              <div className="min-h-0 flex-1 px-6 py-4">{revealed ? <PlanView plan={P} exits={layout.exits} minCut={D.min_cut} value={value} /> : <PlanView plan={P} exits={D.rule_of_thumb} ours={false} />}</div>
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
                <span className="flex items-center gap-2"><i className={`inline-block h-3.5 w-3.5 rounded-full ${revealed ? 'bg-qp' : 'bg-ink'}`} />exit in this layout</span>
                <span className="flex items-center gap-2"><i className="inline-block h-3.5 w-3.5 rounded-full border border-dashed border-faint" />possible position (size = value)</span>
                <span className="flex items-center gap-2"><i className="inline-block h-2 w-4 bg-qp" />door to widen</span>
              </>
            )}
          </div>
        </section>

        {/* RIGHT: the verdict */}
        <section className="row-span-2 flex min-h-0 flex-col gap-4 overflow-hidden bg-panel p-6">
          <Head n="03" title="Verdict" tag={<Tag>simulated</Tag>} />
          {!revealed ? <Before ruleN={ruleN} ruleS={D.curve.find(c => c.n_exits === ruleN)?.rule_s} limit={limit}
            screened={recommend?.data.screened} onGo={() => { setRevealed(true); setN(chosenN) }} /> : <>
          <div>
            <div className="text-[13px] uppercase tracking-[0.12em] text-dim">Fewest exits that pass</div>
            <div className="mt-1 flex items-baseline gap-3">
              <span className="num text-[60px] font-semibold leading-none text-qp">{chosenN}</span>
              <span className="text-[17px] text-dim">vs <span className="num text-ink">{ruleN}</span> by rule of thumb</span>
            </div>
            <div className="mt-2 text-[14px] text-dim">under {panic ? 'panic' : 'calm'} behaviour, worst fire, safe limit {limit} s</div>
          </div>
          <Gauge value={worstChosen} limit={limit} bound={D.bound_maxflow_s} />
          <div className="grid grid-cols-2 gap-5">
            <Stat label="Exits saved" value={ruleN - chosenN} tone="qp" />
            <Stat label="Floor area freed" value={fmt(D.area_freed_m2)} unit="m²" sub={D.m2_per_exit ? `at ${D.m2_per_exit} m² per exit core` : undefined} />
            <Stat label="Cost of panic" value={`+${D.cost_of_panic.panic_s - D.cost_of_panic.calm_s}`} unit="s" sub={`${D.cost_of_panic.calm_s} s calm → ${D.cost_of_panic.panic_s} s panic`} />
            <Stat label={`${n} exits, worst case`} value={point ? point.ours_s : '–'} unit="s" tone={point && point.ours_s > limit ? 'alert' : undefined}
              sub={point ? `rule of thumb ${point.rule_s} s` : undefined} />
          </div>
          {cut.length > 0 && (
            <div className="border-l-2 border-qp bg-raised px-4 py-3">
              <div className="text-[12px] uppercase tracking-[0.12em] text-dim">Bottleneck to widen (min-cut)</div>
              {cut.map((e, i) => <div key={i} className="mt-1 text-[16px]">{nodeName(e.a)} → {nodeName(e.b)} <span className="num text-dim">{e.width_m} m door</span></div>)}
            </div>
          )}
          {recommend && (
            <div className="mt-auto">
              <div className="text-[12px] uppercase tracking-[0.12em] text-dim">AI proposes, simulator verifies</div>
              <div className="mt-1 text-[14px] text-dim"><span className="num text-ink">{fmt(recommend.data.screened)}</span> layouts screened by the PG-GNN; top 5 re-checked</div>
              <table className="num mt-1.5 w-full text-[13px]">
                <thead><tr className="text-left text-faint"><th className="font-normal">exits</th><th className="font-normal">predicted</th><th className="font-normal">verified</th></tr></thead>
                <tbody>{recommend.data.top5.map((t, i) => (
                  <tr key={i} className="border-t border-line"><td className="py-0.5">{exitsOf(t.exits, P).map(c => c.id).join(' ')}</td><td>{t.predicted_s} s</td><td className={t.verified_s > limit ? 'text-alert' : 'text-ink'}>{t.verified_s} s</td></tr>
                ))}</tbody>
              </table>
            </div>
          )}
          </>}
        </section>

        {/* BOTTOM: the curve */}
        <section className="flex min-h-0 flex-col bg-panel px-5 pb-3 pt-4">
          <Head n="04" title="Exits vs worst-case clearance" tag={
            <span className="flex items-center gap-4 text-[13px] text-dim">
              {revealed && <span className="flex items-center gap-2"><i className="inline-block h-0.5 w-5 bg-qp" />QueuePilot</span>}
              <span className="flex items-center gap-2"><i className="inline-block h-0.5 w-5 bg-dim" />Rule of thumb</span>
              <Tag>simulated</Tag>
            </span>} />
          <div className="min-h-0 flex-1"><Guard name="Curve"><Curve curve={D.curve} limit={limit} selected={revealed ? n : ruleN} onPick={setN} ours={revealed} /></Guard></div>
        </section>
      </main>
      <ModelDrawer open={drawer} onClose={() => setDrawer(false)} plan={P} results={results?.data ?? null} recommend={recommend?.data ?? null} stub={!!results?.stub} />
    </div>
  )
}

// Worst-case clearance on a machined scale: ticks every 30 s, the safe limit, the max-flow bound.
function Gauge({ value, limit, bound }: { value: number; limit: number; bound: number }) {
  const max = Math.ceil(Math.max(value, limit) * 1.25 / 60) * 60
  const pct = (v: number) => `${(v / max) * 100}%`
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span className="text-[12px] uppercase tracking-[0.12em] text-dim">Worst-case clearance</span>
        <span className={`num text-[28px] ${value > limit ? 'text-alert' : 'text-ink'}`}>{value}<span className="ml-1 text-[15px] text-dim">s</span></span>
      </div>
      <div className="relative mt-3 h-4 bg-raised">
        <div className={`absolute inset-y-0 left-0 ${value > limit ? 'bg-alert' : 'bg-qp'}`} style={{ width: pct(Math.min(value, max)) }} />
        <div className="absolute -inset-y-1.5 w-0.5 bg-alert" style={{ left: pct(limit) }} />
        {bound > 0 && <div className="absolute -inset-y-1 w-px bg-ink/70" style={{ left: pct(bound) }} />}
      </div>
      <div className="relative mt-1 h-4">
        {Array.from({ length: max / 30 + 1 }, (_, i) => i * 30).map(t => (
          <span key={t} className="num absolute -translate-x-1/2 text-[11px] text-faint" style={{ left: pct(t) }}>{t % 60 === 0 ? t : '·'}</span>
        ))}
      </div>
      <div className="mt-1 flex gap-4 text-[13px] text-dim">
        <span><i className="mr-1.5 inline-block h-3 w-0.5 bg-alert align-middle" />limit {limit} s</span>
        {bound > 0 && <span><i className="mr-1.5 inline-block h-3 w-px bg-ink/70 align-middle" />best possible (max-flow) {bound} s</span>}
      </div>
    </div>
  )
}

// Before the architect presses Recommend: what the rule of thumb gives them.
function Before({ ruleN, ruleS, limit, screened, onGo }: { ruleN: number; ruleS?: number; limit: number; screened?: number; onGo: () => void }) {
  return (
    <div className="flex flex-1 flex-col gap-5">
      <div>
        <div className="text-[13px] uppercase tracking-[0.12em] text-dim">Rule of thumb</div>
        <div className="mt-1 flex items-baseline gap-3">
          <span className="num text-[60px] font-semibold leading-none">{ruleN}</span><span className="text-[17px] text-dim">exits, evenly spaced</span>
        </div>
      </div>
      {ruleS !== undefined && <Gauge value={ruleS} limit={limit} bound={0} />}
      <p className="text-[15px] leading-relaxed text-dim">Worst case under panic, with a fire, against a safe limit of {limit} s.</p>
      <button onClick={onGo} className="mt-auto rounded-sm bg-qp py-4 text-[18px] font-semibold text-bg hover:brightness-110">Recommend exits</button>
      {screened !== undefined && <p className="text-center text-[13px] text-faint">screens {fmt(screened)} layouts with the PG-GNN, then verifies the top 5</p>}
    </div>
  )
}

function Empty({ text }: { text: string }) {
  return <div className="grid h-screen place-items-center"><p className="num text-[16px] text-dim">{text}</p></div>
}
