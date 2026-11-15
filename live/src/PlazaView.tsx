import { useMemo } from 'react'
import type { Venue } from './data'
import { PLAZA, PGCNN_DEMO } from './data'
import { densityColor } from './VenueMap'

export type PlazaSource = 'plan' | 'real' | 'pgcnn'

// The second scale: inside the critical plaza, a 2 m grid (engine/plaza.py, plaza_demo.json).
// "What the site plan predicts" (no clutter) vs "What really happens" vs our PG-CNN.
// The cells the site plan misses (dangerous in truth, never dangerous in the plan) are outlined.
type Props = { venue: Venue; f: number; source: PlazaSource; onSource: (s: PlazaSource) => void; onBack: () => void }

export default function PlazaView({ venue, f, source, onSource, onBack }: Props) {
  const P = PLAZA
  const frames = source === 'plan' ? P.textbook.density : source === 'pgcnn' && PGCNN_DEMO ? PGCNN_DEMO.density : P.truth.density
  const k = Math.max(0, Math.min(frames.length - 1, Math.round(f)))
  const now = frames[k]
  const cell = 2 // schematic units per metre: viewBox in metres

  const missed = useMemo(() => {
    const hot = (fr: number[][][]) => fr[0].map((row, y) => row.map((_, x) => fr.some((s) => s[y][x] >= P.danger_density)))
    const t = hot(P.truth.density), b = hot(P.textbook.density)
    return t.map((row, y) => row.map((v, x) => v && !b[y][x]))
  }, [P])
  const nMissed = missed.flat().filter(Boolean).length
  const caught = PGCNN_DEMO?.textbook_missed_cells_we_catch

  const W = P.width * cell, H = P.height * cell
  const tabs: { id: PlazaSource; label: string; n: number | null }[] = [
    { id: 'plan', label: 'What the site plan predicts', n: P.textbook.danger_cells },
    { id: 'real', label: 'What really happens', n: P.truth.danger_cells },
    { id: 'pgcnn', label: 'PG-CNN', n: PGCNN_DEMO ? PGCNN_DEMO.danger_cells : null },
  ]

  return (
    <div className="plaza">
      <div className="plaza-head">
        <button className="linkbtn" onClick={onBack}>← Venue <kbd>P</kbd></button>
        <div className="plaza-title"><b>Inside {venue.today.worst_zone}</b> · {P.height * P.cell_m} × {P.width * P.cell_m} m on a {P.cell_m} m grid</div>
        <nav className="seg" aria-label="Plaza source">
          {tabs.map((t) => (
            <button key={t.id} aria-pressed={source === t.id} onClick={() => onSource(t.id)} disabled={t.id === 'pgcnn' && !PGCNN_DEMO}>
              {t.label}{t.n !== null ? <span className="key">{t.n} danger cells</span> : <span className="key">training</span>}
            </button>
          ))}
        </nav>
      </div>

      <svg className="grid" viewBox={`-6 -6 ${W + 30} ${H + 12}`} preserveAspectRatio="xMidYMid meet" role="img"
        aria-label="Crowd density on the plaza grid">
        <defs>
          <pattern id="hatch" width="1.2" height="1.2" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="1.2" stroke="#c9d3de" strokeWidth="0.35" />
          </pattern>
        </defs>
        <rect x={-0.5} y={-0.5} width={W + 1} height={H + 1} className="plaza-wall" />
        {now.map((row, y) => row.map((d, x) => (
          <rect key={`${y}-${x}`} x={x * cell + 0.1} y={y * cell + 0.1} width={cell - 0.2} height={cell - 0.2}
            fill={d < 0.05 ? '#0d141c' : densityColor(d, P.danger_density)} />
        )))}
        {/* clutter the site plan does not show: hatched, stronger where denser */}
        {P.clutter.map((row, y) => row.map((c, x) => c > 0.25 && (
          <rect key={`c${y}-${x}`} x={x * cell} y={y * cell} width={cell} height={cell} fill="url(#hatch)" opacity={Math.min(0.9, c)} />
        )))}
        {missed.map((row, y) => row.map((m, x) => m && (
          <rect key={`m${y}-${x}`} x={x * cell + 0.3} y={y * cell + 0.3} width={cell - 0.6} height={cell - 0.6} className="missed" />
        )))}
        {P.gate.map((row, y) => row.map((g, x) => g === 1 && (
          <rect key={`g${y}-${x}`} x={x * cell + cell + 0.6} y={y * cell + 0.2} width={1.2} height={cell - 0.4} className="pgate" />
        )))}
        <text x={W + 3.2} y={(P.gate.findIndex((r) => r.some((g) => g === 1)) + 1.6) * cell} className="plabel" transform="">gate</text>
        <text x={-1} y={H + 4.5} className="plabel">people enter here ←</text>
      </svg>

      <div className="plaza-foot">
        <span className="pf-key"><i className="pf-hatch" /> clutter not on the site plan</span>
        <span className="pf-key"><i className="pf-missed" /> {nMissed} danger cells the site plan misses
          {caught !== undefined && source === 'pgcnn' && <b className="num"> · PG-CNN catches {caught}</b>}</span>
        <span className="pf-note">One simulated arrival wave of {P.total_people.toLocaleString('en-IN')} people. Plaza is schematic.</span>
      </div>
    </div>
  )
}
