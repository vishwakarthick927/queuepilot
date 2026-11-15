import { useCallback, useEffect, useMemo, useState } from 'react'
import { Guard } from '../components/Guard'
import { design, plan, results, recommend, type Design, type Frames, type Plan, type Score } from './data'
import HowItWorks from './HowItWorks'
import PlanView, { DENSITY_STOPS, densityColor } from './PlanView'
import { Key } from './ui'

// QueuePilot Design: one message. "More exits don't make a building safer. The right ones do."
// Try your own exits -> Find the best exits -> watch both evacuate side by side. Everything else is in "How it works".
// Every number comes from data/design/design.json (MAIN's simulator) or research/design/*.json. Nothing typed by hand.
// Keys: F find the best exits · Space play · H how it works · Z start again · Esc back.

const FRAME_MS = 80                                    // one 2-second simulation step per 80 ms on screen
const STAMP_PAUSE_MS = 1400                            // the clock freezes this long at the time limit
const ONE_FONT = { '--font-mono': 'var(--font-sans)' } as React.CSSProperties
type Mode = 'try' | 'found' | 'play'

export default function DesignStudio() {
  if (!plan) return <Empty text="No floor plan yet: waiting for data/design/demo_plan.json." />
  if (!design) return <Empty text="No results yet: waiting for data/design/design.json." />
  return <Studio P={plan.data} D={design.data} />
}

// "2 min 26 s"
const minsec = (s: number) => `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`
const clock = (s: number) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`

// People still inside at clock step s (the files hold the totals AFTER each step; step 0 = everyone inside).
function insideAt(f: Frames, s: number, total: number) {
  if (s <= 0) return { left: total, people: null as number[] | null }
  const i = Math.min(s, f.people.length) - 1
  const inside = total - (f.evacuated[i] ?? 0)
  return { left: inside < 1 ? 0 : Math.round(inside), people: f.people[i] }      // under 1 person = empty (the simulator's rule)
}

function Studio({ P, D }: { P: Plan; D: Design }) {
  const q = new URLSearchParams(window.location.search)
  const R = D.by_panic[String(D.design_panic)]
  const chosen = R.chosen!, front = P.main_entrance
  const [mode, setMode] = useState<Mode>(q.get('play') === '1' ? 'play' : q.get('found') === '1' ? 'found' : 'try')
  const [mine, setMine] = useState<number[]>([front])                   // the viewer's own exits
  const [how, setHow] = useState(q.get('how') === '1')
  const [step, setStep] = useState(Number(q.get('t')) || 0)
  const [playing, setPlaying] = useState(false)
  const total = useMemo(() => P.nodes.reduce((a, n) => a + n.people0, 0), [P])
  const limitStep = Math.round(P.safe_limit_s / P.dt_s)
  const last = Math.max(D.frames.chosen.people.length, D.frames.rule_of_thumb.people.length)
  const lookup = useMemo(() => new Map(R.layouts.map(l => [l.exits.join(','), l])), [R])
  const verdict = lookup.get([...mine].sort((a, b) => a - b).join(','))

  // the animation clock; it freezes for a beat when it reaches the time limit (the stamp moment)
  useEffect(() => {
    if (!playing) return
    const wait = step === limitStep ? STAMP_PAUSE_MS : FRAME_MS
    const id = setTimeout(() => (step >= last ? setPlaying(false) : setStep(step + 1)), wait)
    return () => clearTimeout(id)
  }, [playing, step, last, limitStep])

  const toggle = (id: number) => { if (mode !== 'try') setMode('try'); setMine(m => (m.includes(id) ? m.filter(x => x !== id) : [...m, id])) }
  const find = useCallback(() => setMode('found'), [])
  const play = useCallback(() => { setMode('play'); setStep(s => (s >= last ? 0 : s)); setPlaying(p => !p) }, [last])
  const reset = useCallback(() => { setMode('try'); setMine([front]); setPlaying(false); setStep(0) }, [front])
  const back = useCallback(() => { setPlaying(false); setStep(0); setMode('found') }, [])

  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if (e.key === 'f' || e.key === 'F') find()
      else if (e.key === ' ') { e.preventDefault(); play() }
      else if (e.key === 'h' || e.key === 'H') setHow(v => !v)
      else if (e.key === 'z' || e.key === 'Z') reset()
      else if (e.key === 'Escape') { if (how) setHow(false); else if (mode === 'play') back() }
    }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [find, play, reset, back, how, mode])

  const tags = Object.fromEntries(chosen.exits.filter(x => x !== front).map((x, i) => [x, `${i + 1} Exit here`]))

  return (
    <div className="grid h-screen grid-rows-[auto_1fr_auto] overflow-hidden bg-bg" style={ONE_FONT}>
      <header className="flex items-end gap-8 border-b border-line px-8 pb-5 pt-6">
        <div>
          <div className="text-[15px] font-semibold uppercase tracking-[0.14em] text-dim">QueuePilot <span className="text-qp">Design</span></div>
          <h1 className="mt-2 text-[44px] font-semibold leading-[1.1] tracking-tight">More exits don't make a building safer. <span className="text-qp">The right ones do.</span></h1>
          <p className="mt-2 text-[22px] text-dim">QueuePilot tells architects where to place fire exits, so a building needs fewer of them and still empties in time.</p>
        </div>
        <button onClick={() => setHow(true)} className="mb-1 ml-auto shrink-0 rounded-sm border border-line-strong px-4 py-2 text-[15px] text-dim hover:border-ink hover:text-ink">How it works<Key k="H" /></button>
      </header>

      <main className="grid min-h-0 grid-cols-[1fr_400px]">
        <Guard name="Floor plan">
          {mode === 'play'
            ? <SideBySide P={P} D={D} step={step} total={total} limitStep={limitStep} />
            : (
              <div className="relative min-h-0 px-8 py-4">
                <PlanView plan={P} exits={mode === 'found' ? chosen.exits : mine} ours={mode === 'found'}
                  onPick={toggle} tags={mode === 'found' ? tags : {}} />
                <p className="pointer-events-none absolute bottom-3 left-8 text-[15px] text-dim">
                  {mode === 'try' ? 'Click the dashed circles to place exits. The front door is always there.' : 'Click any exit position to try your own layout again.'}
                </p>
              </div>
            )}
        </Guard>

        <aside className="flex min-h-0 flex-col gap-6 border-l border-line bg-panel px-7 py-6">
          {mode === 'try' && <TryPanel P={P} verdict={verdict} count={mine.length} onFind={find} />}
          {mode !== 'try' && <Result P={P} R={R} chosen={chosen} />}
          {mode === 'found' && (
            <button onClick={play} className="rounded-sm bg-qp py-3.5 text-[22px] font-semibold text-bg hover:brightness-110">Play the evacuation<Key k="Space" /></button>
          )}
          {mode === 'play' && (
            <div className="flex gap-2">
              <button onClick={play} className="flex-1 rounded-sm bg-qp py-3 text-[22px] font-semibold text-bg hover:brightness-110">{playing ? 'Pause' : step >= last ? 'Play again' : step > 0 ? 'Resume' : 'Play'}<Key k="Space" /></button>
              <button onClick={back} className="rounded-sm border border-line-strong px-4 text-[15px] text-dim hover:text-ink">Back<Key k="Esc" /></button>
            </div>
          )}
          {mode !== 'try' && <button onClick={reset} className="text-left text-[15px] text-dim underline-offset-4 hover:text-ink hover:underline">Start again with your own exits<Key k="Z" /></button>}
        </aside>
      </main>

      <footer className="flex items-center gap-6 border-t border-line px-8 py-2.5 text-[15px] text-faint">
        <span>Crowd behaviour is simulated. QueuePilot never recommends fewer exits than the building code allows.</span>
        {(results?.stub || recommend?.stub) && <span className="text-alert">stub data</span>}
        <span className="ml-auto">{total} people · panicked crowd · a fire can block any exit</span>
      </footer>
      <HowItWorks open={how} onClose={() => setHow(false)} plan={P} design={D} results={results?.data ?? null} recommend={recommend?.data ?? null} />
    </div>
  )
}

// Step 1: the viewer places exits; one verdict per click, looked up in the simulator's results.
function TryPanel({ P, verdict, count, onFind }: { P: Plan; verdict?: Score; count: number; onFind: () => void }) {
  const ok = verdict?.passes
  return (
    <>
      <div>
        <div className="text-[15px] font-semibold uppercase tracking-[0.14em] text-dim">Try it yourself</div>
        <p className="mt-2 text-[22px] leading-snug">Where would you put the fire exits? Every layout is tested with a panicked crowd and a fire that can block any exit.</p>
      </div>
      <div className={`border-l-4 py-1 pl-4 ${count < 2 ? 'border-line-strong' : ok ? 'border-qp' : 'border-alert'}`}>
        <div className="text-[15px] text-dim">{count} {count === 1 ? 'exit' : 'exits'} placed</div>
        {count < 2 ? <div className="mt-1 text-[22px] font-semibold text-dim">The building code needs at least 2.</div>
          : ok ? <div className="mt-1 text-[22px] font-semibold text-qp">Everyone out in time{verdict?.worst_case_s != null && <span className="font-normal text-dim">, {minsec(verdict.worst_case_s)}</span>}</div>
            : <div className="mt-1 text-[22px] font-semibold text-alert">Not safe: people still inside when time runs out</div>}
        <div className="mt-1 text-[15px] text-faint">time limit {minsec(P.safe_limit_s)}</div>
      </div>
      <button onClick={onFind} className="mt-auto rounded-sm bg-qp py-3.5 text-[22px] font-semibold text-bg hover:brightness-110">Find the best exits<Key k="F" /></button>
    </>
  )
}

// Step 2: one sentence, and at most three numbers.
function Result({ P, R, chosen }: { P: Plan; R: Design['by_panic'][string]; chosen: Score }) {
  const n = R.chosen_n_exits, rule = R.rule_n_exits, t = chosen.worst_case_s ?? 0
  return (
    <>
      <p className="text-[22px] font-semibold leading-snug">
        <span className="text-qp">{n} exits placed by QueuePilot</span> get everyone out in {minsec(t)}.
        {rule != null && <span className="text-dim"> Spread evenly, you would need {rule}.</span>}
      </p>
      <div className="grid grid-cols-1 gap-4">
        <Big label="Exits needed" value={String(n)} note={rule != null ? `instead of ${rule}` : undefined} />
        <Big label="Time to get everyone out" value={clock(t)} note={`limit ${clock(P.safe_limit_s)}`} />
        {R.area_freed_m2 != null && <Big label="Floor space saved" value={`${R.area_freed_m2} m²`} note="for rooms instead of exit stairs and lobbies" />}
      </div>
    </>
  )
}

function Big({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="border-t border-line pt-3">
      <div className="text-[15px] text-dim">{label}</div>
      <div className="num mt-1 text-[44px] font-semibold leading-none">{value}</div>
      {note && <div className="mt-1 text-[15px] text-dim">{note}</div>}
    </div>
  )
}

// Step 3: both buildings, same fire, same panicked crowd, same clock. The stamp at the time limit is the pitch.
function SideBySide({ P, D, step, total, limitStep }: { P: Plan; D: Design; step: number; total: number; limitStep: number }) {
  const t = step * P.dt_s, stamped = step >= limitStep
  const sides = [['rule_of_thumb', 'spread evenly', 'text-ink', false], ['chosen', 'placed by QueuePilot', 'text-qp', true]] as const
  return (
    <div className="flex min-h-0 flex-col">
      <div className="flex items-baseline gap-4 border-b border-line px-8 py-3">
        <span className="num text-[44px] font-semibold leading-none">{clock(t)}</span>
        <span className="text-[15px] text-dim">time limit {clock(P.safe_limit_s)} · the fire blocks the front door</span>
        <Bar step={step} limitStep={limitStep} last={Math.max(D.frames.chosen.people.length, D.frames.rule_of_thumb.people.length)} />
      </div>
      <div className="grid min-h-0 flex-1 grid-cols-2 gap-px bg-line">
        {sides.map(([k, label, color, ours]) => {
          const f = D.frames[k], { left, people } = insideAt(f, step, total)
          const atLimit = insideAt(f, limitStep, total).left
          return (
            <div key={k} className="relative flex min-h-0 flex-col bg-bg px-6 pt-4">
              <div className={`text-[22px] font-semibold ${color}`}>{f.exits.length} exits, {label}</div>
              <div className="mt-1 flex items-baseline gap-3">
                <span className="num text-[44px] font-semibold leading-none">{left}</span><span className="text-[15px] text-dim">people still inside</span>
              </div>
              <div className="min-h-0 flex-1 py-3">
                <PlanView plan={P} exits={f.exits} blocked={f.lost_exit ?? null} people={people ?? P.nodes.map(n => n.people0)} compact ours={ours} />
              </div>
              {stamped && (
                <div className={`pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -rotate-6 border-4 bg-bg/85 px-4 py-2 text-[22px] font-semibold uppercase tracking-wide ${atLimit > 0 ? 'border-alert text-alert' : 'border-qp text-qp'}`}>
                  {atLimit > 0 ? `${atLimit} still inside` : 'Everyone out'}
                </div>
              )}
            </div>
          )
        })}
      </div>
      <div className="flex items-center gap-2 border-t border-line px-8 py-2 text-[15px] text-dim">
        <span>crowding</span>
        {DENSITY_STOPS.map(d => <i key={d} className="inline-block h-3 w-5" style={{ background: densityColor(d) }} />)}
        <span>empty to packed</span>
      </div>
    </div>
  )
}

// The clock as a bar, with the time limit marked.
function Bar({ step, limitStep, last }: { step: number; limitStep: number; last: number }) {
  const pct = (s: number) => `${(Math.min(s, last) / last) * 100}%`
  return (
    <div className="relative ml-6 h-2 flex-1 self-center bg-raised">
      <div className="absolute inset-y-0 left-0 bg-dim" style={{ width: pct(step) }} />
      <div className="absolute -inset-y-2 w-1 bg-alert" style={{ left: pct(limitStep) }} />
    </div>
  )
}

function Empty({ text }: { text: string }) {
  return <div className="grid h-screen place-items-center"><p className="text-[22px] text-dim">{text}</p></div>
}
