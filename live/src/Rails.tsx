import { useState } from 'react'
import type { Run, Venue } from './data'
import { densityAt, fmt1, minutesAt, frameAt } from './data'

// Worst crowd zone at this instant (gates hold nobody, so they are skipped).
function worstZone(v: Venue, run: Run, f: number) {
  const d = densityAt(run, f)
  let best = 0
  v.zones.forEach((z, i) => { if (z.kind !== 'gate' && d[i] > d[best]) best = i })
  return { zone: v.zones[best], d: d[best] }
}

const mmss = (min: number) => `${Math.floor(min)}:${String(Math.floor((min % 1) * 60)).padStart(2, '0')}`

// Crowd Pressure Index: worst density / max density × 100. A machined half-dial with the danger band marked.
function Gauge({ value, danger }: { value: number; danger: number }) {
  const R = 84, cx = 100, cy = 96
  const pt = (p: number, r: number) => {
    const a = Math.PI * (1 - p / 100)
    return [cx + r * Math.cos(a), cy - r * Math.sin(a)]
  }
  const arc = (p0: number, p1: number, r: number) => {
    const [x0, y0] = pt(p0, r), [x1, y1] = pt(p1, r)
    return `M${x0},${y0} A${r},${r} 0 0 1 ${x1},${y1}`
  }
  const v = Math.max(0, Math.min(100, value))
  const hot = v >= danger
  const [nx, ny] = pt(v, R - 14)
  return (
    <svg viewBox="0 0 200 112" className="gauge" aria-label={`Crowd pressure index ${Math.round(v)} of 100`}>
      <path d={arc(0, 100, R)} className="g-track" />
      <path d={arc(danger, 100, R)} className="g-danger" />
      {v > 0.5 && <path d={arc(0, v, R)} className={hot ? 'g-val hot' : 'g-val'} />}
      {Array.from({ length: 21 }, (_, i) => i * 5).map((p) => {
        const [x0, y0] = pt(p, R + 6), [x1, y1] = pt(p, R + (p % 25 === 0 ? 13 : 9))
        return <line key={p} x1={x0} y1={y0} x2={x1} y2={y1} className="g-tick" />
      })}
      {[0, 50, 100].map((p) => { const [x, y] = pt(p, R - 22); return <text key={p} x={x} y={y + 3} textAnchor="middle" className="g-lab">{p}</text> })}
      <line x1={cx} y1={cy} x2={nx} y2={ny} className={hot ? 'g-needle hot' : 'g-needle'} />
      <circle cx={cx} cy={cy} r={4} className="g-hub" />
    </svg>
  )
}

type NowProps = { venue: Venue; run: Run; f: number; planOn: boolean; twinOn: boolean; other?: Run }

export function NowRail({ venue, run, f, planOn, twinOn, other }: NowProps) {
  const { zone, d } = worstZone(venue, run, f)
  const cpi = (d / venue.max_density) * 100
  const dangerCpi = (venue.danger_density / venue.max_density) * 100
  const hot = d >= venue.danger_density
  const t = minutesAt(venue, f)
  const left = venue.today.danger_at_min - t
  const alarmed = t >= venue.forecast.alarm_at_min
  const through = run.through[Math.min(run.through.length - 1, Math.round(f))]

  // The countdown: hindsight in Today mode; in QueuePilot mode only once the twin has raised the alarm.
  let count: { label: string; value: string; tone: 'hot' | 'ok' | 'dim' }
  if (planOn && alarmed && (run as { stays_below_danger?: boolean }).stays_below_danger) count = { label: 'Crush danger', value: 'Avoided', tone: 'ok' }
  else if (left <= 0) count = { label: 'Crush danger', value: 'NOW', tone: 'hot' }
  else if (twinOn && !alarmed) count = { label: 'Twin forecast', value: 'No danger yet', tone: 'dim' }
  else count = { label: twinOn ? 'Twin forecast: danger in' : 'Danger in', value: mmss(left), tone: twinOn ? 'hot' : 'dim' }

  return (
    <aside className="rail">
      <h2>Now</h2>
      <div className="cpi">
        <Gauge value={cpi} danger={dangerCpi} />
        <div className={hot ? 'cpi-num num hot' : 'cpi-num num'}>{Math.round(cpi)}</div>
        <div className="cpi-cap">Crowd Pressure Index</div>
      </div>
      <div className="worst">
        <div className="worst-zone">{zone.name}</div>
        <div className="num worst-d"><b className={hot ? 'hot' : ''}>{fmt1(d)}</b> people per m²</div>
        {other && <div className="worst-other num">no intervention: {fmt1(worstZone(venue, other, f).d)} per m²</div>}
      </div>
      <div className={`count ${count.tone}`}>
        <span>{count.label}</span>
        <b className="num">{count.value}</b>
      </div>
      <div className="thru">
        <div className="thru-row"><span>Through the gates</span><span className="num">{through.toLocaleString('en-IN')} / {venue.total_people.toLocaleString('en-IN')}</span></div>
        <div className="thru-bar"><i style={{ width: `${(through / venue.total_people) * 100}%` }} /></div>
      </div>
    </aside>
  )
}

// Before → after bar for one action, on the venue's density scale, with the danger line drawn in.
function Bar({ venue, from, to, strong }: { venue: Venue; from: number; to: number; strong?: boolean }) {
  const s = (x: number) => `${(Math.min(x, venue.max_density) / venue.max_density) * 100}%`
  return (
    <div className={strong ? 'abar strong' : 'abar'}>
      <div className="abar-track">
        <i className="abar-from" style={{ width: s(from) }} />
        <i className={to >= venue.danger_density ? 'abar-to hot' : 'abar-to'} style={{ width: s(to) }} />
        <i className="abar-danger" style={{ left: s(venue.danger_density) }} />
      </div>
      <span className="num">{fmt1(from)} → <b>{fmt1(to)}</b></span>
    </div>
  )
}

function speak(v: Venue) {
  const s = window.speechSynthesis
  if (!s) return
  s.cancel()
  const voices = s.getVoices()
  const say = (text: string, lang: string) => {
    const u = new SpeechSynthesisUtterance(text)
    u.lang = lang
    const voice = voices.find((x) => x.lang.toLowerCase().startsWith(lang.slice(0, 2)))
    if (voice) u.voice = voice
    u.rate = 0.95
    s.speak(u)
  }
  say(v.announcement.en, 'en-IN')
  say(v.announcement.hi, 'hi-IN')
}

type DoProps = { venue: Venue; f: number; twinOn: boolean; approved: boolean; onApprove: () => void }

export function DoRail({ venue, f, twinOn, approved, onApprove }: DoProps) {
  const [said, setSaid] = useState(false)
  const fc = venue.forecast
  const alarmed = f >= frameAt(venue, fc.alarm_at_min)
  const hp = fc.hidden_problem
  const gateCount = venue.gates.length

  if (!twinOn) {
    return (
      <aside className="rail right">
        <h2>Do</h2>
        <div className="quiet-card">
          <div className="qc-title">Textbook plan</div>
          <div className="qc-big">No warning</div>
          <p>It assumes every gate works as designed, so it never predicts the crush.</p>
        </div>
        <p className="hint">Press <kbd>Q</kbd> to watch the same crowd with QueuePilot.</p>
      </aside>
    )
  }

  if (!alarmed) {
    return (
      <aside className="rail right">
        <h2>Do</h2>
        <div className="quiet-card">
          <div className="qc-title">Watching</div>
          <div className="qc-big"><span className="num">{gateCount}</span> gates</div>
          <p>Every 30 s the twin checks each gate's real throughput against the people counted through it.</p>
        </div>
      </aside>
    )
  }

  return (
    <aside className="rail right">
      <div className="alarm-banner">
        <b>ALARM</b>
        <span className="num">{fmt1(fc.alarm_at_min)} min</span>
        <p>Crush forecast at <b className="num">{fmt1(fc.predicted_danger_at_min)}</b> min at {venue.today.worst_zone}.</p>
      </div>

      <div className="learned">
        <svg viewBox="0 0 28 28" className="gate-ico" aria-hidden="true"><rect x="3" y="6" width="6" height="18" rx="1" /><rect x="19" y="6" width="6" height="18" rx="1" /><path d="M9 9 H19" /></svg>
        <div className="lbars">
          <div className="ltitle">What the twin learned about <b>{hp.gate}</b></div>
          <div className="lrow"><span>planned</span><i style={{ width: '100%' }} /><b className="num">100%</b></div>
          <div className="lrow learnt"><span>learned</span><i style={{ width: `${hp.learned_share * 100}%` }} /><b className="num">{Math.round(hp.learned_share * 100)}%</b></div>
          <p>Found from gate counts. Nobody reported it. <span className="num">(hidden truth {Math.round(hp.true_share_of_design_flow * 100)}%)</span></p>
        </div>
      </div>

      <h2>Do</h2>
      <div className="actions">
        {venue.actions.map((a) => (
          <div key={a.id} className={a.chosen ? 'act chosen' : 'act'}>
            <span className="tick" aria-hidden="true">{a.chosen && <svg viewBox="0 0 12 12"><path d="M2.5 6.5 L5 9 L9.5 3.5" /></svg>}</span>
            <div className="act-body">
              <div className="act-label">{a.label}</div>
              <Bar venue={venue} from={venue.today.peak_density} to={a.alone_peak_density} />
            </div>
          </div>
        ))}
        <div className="act together">
          <span className="tick on" aria-hidden="true"><svg viewBox="0 0 12 12"><path d="M2.5 6.5 L5 9 L9.5 3.5" /></svg></span>
          <div className="act-body">
            <div className="act-label">All ticked, together</div>
            <Bar venue={venue} from={venue.today.peak_density} to={venue.with_queuepilot.peak_density} strong />
          </div>
        </div>
      </div>

      {!approved ? (
        <button className="approve" onClick={onApprove}>Approve plan <kbd>A</kbd></button>
      ) : (
        <div className="approved"><svg viewBox="0 0 12 12"><path d="M2.5 6.5 L5 9 L9.5 3.5" /></svg>Plan approved at {fmt1(fc.alarm_at_min)} min</div>
      )}
      <button className="broadcast" onClick={() => { speak(venue); setSaid(true) }}>
        <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M2 6 H5 L9 3 V13 L5 10 H2 Z" /><path d="M11.5 5.5 Q13.5 8 11.5 10.5" /></svg>
        Broadcast <kbd>B</kbd>
      </button>
      {said && (
        <div className="said">
          <p>{venue.announcement.en}</p>
          <p lang="hi">{venue.announcement.hi}</p>
        </div>
      )}
    </aside>
  )
}

export { speak }
