import type { Venue } from './data'
import { fmt1, minutesAt, lastFrame } from './data'

type Props = {
  venue: Venue
  f: number
  playing: boolean
  showQp: boolean            // draw the With-QueuePilot line too
  approved: boolean
  onSeek: (f: number) => void
  onPlay: () => void
}

const clock = (min: number) => `${String(Math.floor(min)).padStart(2, '0')}:${String(Math.round((min % 1) * 60) % 60).padStart(2, '0')}`

// Scrubber: worst density over the whole run as a thin trace, the danger line, and the two markers that matter,
// ALARM (when the twin warns) and DANGER (when the crush starts with no intervention). The gap is the hero number.
export default function Timeline({ venue, f, playing, showQp, approved, onSeek, onPlay }: Props) {
  const n = lastFrame(venue)
  const W = 1000, H = 54
  const top = venue.max_density
  const x = (i: number) => (i / n) * W
  const y = (d: number) => H - (Math.min(d, top) / top) * (H - 4)
  const path = (s: number[]) => s.map((d, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(d).toFixed(1)}`).join('')
  const pct = (min: number) => `${(min / venue.minutes) * 100}%`
  const alarm = venue.forecast.alarm_at_min
  const danger = venue.today.danger_at_min
  const t = minutesAt(venue, f)

  const seek = (e: React.PointerEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect()
    onSeek(Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)) * n)
  }

  return (
    <div className="timeline">
      <button className="play" onClick={onPlay} aria-label={playing ? 'Pause' : 'Play'}>
        {playing
          ? <svg viewBox="0 0 12 12" width="12" height="12"><rect x="2" y="1.5" width="3" height="9" /><rect x="7" y="1.5" width="3" height="9" /></svg>
          : <svg viewBox="0 0 12 12" width="12" height="12"><path d="M3 1.5 L10.5 6 L3 10.5 Z" /></svg>}
      </button>
      <div className="clock num">{clock(t)}<span> / {clock(venue.minutes)}</span></div>

      <div className="track-wrap">
        {/* the warning gap, labelled: the hero number */}
        <div className="gap" style={{ left: pct(alarm), width: `calc(${pct(danger)} - ${pct(alarm)})` }}>
          <span><b className="num">{fmt1(venue.forecast.warning_min)}</b> minutes of warning</span>
        </div>
        <div className="track" onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); seek(e) }}
          onPointerMove={(e) => e.buttons && seek(e)} role="slider" aria-label="Time" aria-valuemin={0}
          aria-valuemax={venue.minutes} aria-valuenow={Number(t.toFixed(1))} tabIndex={0}>
          <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
            <line x1={0} x2={W} y1={y(venue.danger_density)} y2={y(venue.danger_density)} className="tl-danger" />
            <path d={path(venue.today.worst)} className="tl-today" />
            {showQp && <path d={path(venue.with_queuepilot.worst)} className={approved ? 'tl-qp' : 'tl-qp ghost'} />}
            <rect x={0} y={0} width={x(f)} height={H} className="tl-played" />
          </svg>
          <div className="marker alarm" style={{ left: pct(alarm) }}><span>ALARM {fmt1(alarm)}</span></div>
          <div className="marker danger" style={{ left: pct(danger) }}><span>DANGER {fmt1(danger)}</span></div>
          <div className="head" style={{ left: `${(f / n) * 100}%` }} />
        </div>
        <div className="ticks num">
          {[0, 10, 20, 30, 40].filter((m) => m <= venue.minutes).map((m) => <span key={m} style={{ left: pct(m) }}>{m} min</span>)}
        </div>
      </div>
    </div>
  )
}
