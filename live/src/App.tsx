import { useCallback, useEffect, useRef, useState } from 'react'
import { VENUES, TAB, densityAt, frameAt, lastFrame, fmt1, type Venue } from './data'
import VenueMap from './VenueMap'
import Timeline from './Timeline'
import { NowRail, DoRail } from './Rails'

// Modes: what no one does (today), the twin + an approved plan (qp), or both at once (side).
export type Mode = 'today' | 'qp' | 'side'
const MODES: { id: Mode; label: string; key: string }[] = [
  { id: 'today', label: 'Today', key: 'T' },
  { id: 'qp', label: 'With QueuePilot', key: 'Q' },
  { id: 'side', label: 'Side by side', key: 'S' },
]
const SPEED = 4 // frames per second of playback = 2 simulated minutes per second

// URL flags for screenshots and the demo: ?v=temple&mode=qp&t=9&ok=1&play=1
const q = new URLSearchParams(window.location.search)

// Gates open at this instant: the ones open at the start, plus the closed one once an approved plan opens it.
function openGates(v: Venue, planOn: boolean, f: number) {
  const opens = planOn && v.with_queuepilot.actions.includes('open') && f >= frameAt(v, v.forecast.alarm_at_min)
  return new Set(v.gates.filter((g) => g.open_at_start || opens).map((g) => g.id))
}

export default function App() {
  const [vid, setVid] = useState(q.get('v') ?? VENUES[0].id)
  const venue = VENUES.find((v) => v.id === vid) ?? VENUES[0]
  const [mode, setMode] = useState<Mode>((q.get('mode') as Mode) ?? 'today')
  const [f, setF] = useState(q.has('t') ? frameAt(venue, Number(q.get('t'))) : 0)
  const [playing, setPlaying] = useState(q.get('play') === '1')
  const [approved, setApproved] = useState(q.get('ok') === '1')

  const alarmF = frameAt(venue, venue.forecast.alarm_at_min)
  const dangerF = frameAt(venue, venue.today.danger_at_min)
  const n = lastFrame(venue)

  // Playback. In With-QueuePilot mode the clock stops at the alarm until a person approves the plan.
  const last = useRef<number | null>(null)
  useEffect(() => {
    if (!playing) { last.current = null; return }
    let id = 0
    const tick = (now: number) => {
      const dt = last.current === null ? 0 : (now - last.current) / 1000
      last.current = now
      setF((prev) => {
        let next = prev + dt * SPEED
        if (mode === 'qp' && !approved && prev < alarmF && next >= alarmF) { next = alarmF; setPlaying(false) }
        if (next >= n) { next = n; setPlaying(false) }
        return next
      })
      id = requestAnimationFrame(tick)
    }
    id = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(id)
  }, [playing, mode, approved, alarmF, n])

  const pickVenue = useCallback((id: string) => { setVid(id); setF(0); setPlaying(false); setApproved(false) }, [])
  const pickMode = useCallback((m: Mode) => { setMode(m); setPlaying(false) }, [])
  const play = useCallback(() => {
    if (f >= n) setF(0)
    setPlaying((p) => !p)
  }, [f, n])
  // A person approves the plan; only possible once the twin has raised the alarm.
  const approve = useCallback(() => {
    if (mode === 'qp' && f >= alarmF && !approved) { setApproved(true); setPlaying(true) }
  }, [mode, f, alarmF, approved])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement) return
      const k = e.key.toLowerCase()
      if (k === ' ') { e.preventDefault(); play() }
      else if (k >= '1' && k <= '4' && VENUES[+k - 1]) pickVenue(VENUES[+k - 1].id)
      else if (k === 't') pickMode('today')
      else if (k === 'q') pickMode('qp')
      else if (k === 's') pickMode('side')
      else if (k === 'a') approve()
      else if (k === 'b') document.querySelector<HTMLButtonElement>('.broadcast')?.click()
      else if (k === 'r') { setF(0); setPlaying(false); setApproved(false) }
      else if (k === 'arrowright') setF((x) => Math.min(n, Math.floor(x) + 1))
      else if (k === 'arrowleft') setF((x) => Math.max(0, Math.ceil(x) - 1))
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [play, pickVenue, pickMode, n, approve])

  const planOn = mode === 'side' || (mode === 'qp' && approved)
  const run = planOn ? venue.with_queuepilot : venue.today
  const pane = (withPlan: boolean) => {
    const r = withPlan ? venue.with_queuepilot : venue.today
    const crushed = !withPlan && f >= dangerF
    return (
      <div className="pane">
        {mode === 'side' && (
          <div className={withPlan ? 'pane-head qp' : 'pane-head'}><span className="dot" />
            {withPlan ? `With QueuePilot: plan approved at ${fmt1(venue.forecast.alarm_at_min)} min` : 'No intervention'}
          </div>
        )}
        <VenueMap venue={venue} density={densityAt(r, f)} openGates={openGates(venue, withPlan, f)} flowing={playing} />
        {crushed && (
          <div className="stamp danger">
            <b>DANGER</b>
            <span>{venue.today.worst_zone} above {venue.danger_density} people per m² from {fmt1(venue.today.danger_at_min)} min</span>
          </div>
        )}
        {withPlan && f >= alarmF && (
          <div className="stamp safe">
            <b>{venue.with_queuepilot.stays_below_danger ? 'DANGER AVOIDED' : 'PLAN RUNNING'}</b>
            <span>peak {fmt1(venue.with_queuepilot.peak_density)} people per m²</span>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="app">
      <header className="top">
        <div className="brand"><span className="mark" />QueuePilot Live</div>
        <nav className="seg" aria-label="Venue">
          {VENUES.map((v, i) => (
            <button key={v.id} aria-pressed={v.id === venue.id} onClick={() => pickVenue(v.id)}>
              {TAB[v.id] ?? v.name}<span className="key">{i + 1}</span>
            </button>
          ))}
        </nav>
        <span className="spacer" />
        <nav className="seg" aria-label="Mode">
          {MODES.map((m) => (
            <button key={m.id} aria-pressed={m.id === mode} onClick={() => pickMode(m.id)}>
              {m.label}<span className="key">{m.key}</span>
            </button>
          ))}
        </nav>
      </header>
      <main className="body">
        <NowRail venue={venue} run={run} f={f} planOn={planOn} twinOn={mode !== 'today'}
          other={mode === 'side' ? venue.today : undefined} />
        <section className="center">
          <div className="venue-head">
            <div className="vh-row">
              <h1>{venue.name}</h1>
              <span className="place">{venue.total_people.toLocaleString('en-IN')} people</span>
            </div>
            <p className="result">
              Alarm <b className="num qp">{fmt1(venue.forecast.warning_min)} minutes</b> before the crush.
              Peak crowd <b className="num">{fmt1(venue.today.peak_density)}</b> → <b className="num qp">{fmt1(venue.with_queuepilot.peak_density)}</b> people per m².
            </p>
          </div>
          <div className={mode === 'side' ? 'stage split' : 'stage'}>
            {mode === 'side' ? <>{pane(false)}{pane(true)}</> : pane(planOn)}
          </div>
          <Timeline venue={venue} f={f} playing={playing} showQp={mode !== 'today'} approved={planOn}
            onSeek={(x) => { setF(x); setPlaying(false) }} onPlay={play} />
        </section>
        <DoRail key={venue.id} venue={venue} f={f} twinOn={mode !== 'today'} approved={planOn} onApprove={approve} />
      </main>
      <footer className="foot">
        <span>Simulated crowd on a schematic layout. A person approves every action. Counts only, no faces.</span>
        <span className="spacer" />
        <span className="inspired">Inspired by <b>{venue.inspired_by.event}</b>, {venue.inspired_by.date}: {venue.inspired_by.toll}. Layout is schematic, not a reconstruction.</span>
      </footer>
    </div>
  )
}
