import { useId } from 'react'
import { exitLabel, type Plan } from './data'

// The floor plan, drawn in metres (SVG viewBox = metres), so every size on screen is to scale.
// MAIN's plans sit on a 6 m grid: a room fills its grid cell, a corridor is a band as wide as its
// passage, an exit sits outside the wall it opens from. Rooms are tinted by crowd density when an
// animation frame is passed in.

const CELL = 6            // grid spacing of engine/plans.py, metres
const ROOM = 5.6          // drawn room size inside its cell (the rest is wall)

type Props = {
  plan: Plan
  exits: number[]                      // candidate ids built in this layout
  blocked?: number | null              // a built exit the fire has blocked (drawn crossed out)
  people?: number[]                    // people per node at the current step (animation)
  fireNode?: number | null
  closed?: number[]                    // edges cut by the fire at this moment
  minCut?: number[]                    // edges to widen
  value?: Record<number, number>       // candidate id -> value score (marker size)
  compact?: boolean
  ours?: boolean                       // green = QueuePilot's exits; white = any other layout
  onPick?: (id: number) => void        // click an exit position to place / remove an exit
  tags?: Record<number, string>        // short label next to a built exit, e.g. "1  Exit here"
  smoke?: { cells: number[][]; x0: number; y0: number; cell: number }   // smoke level per 2 m cell, drawn over the plan
}

// One sequential scale for density, single hue (amber), dark = empty to light = crowded, same everywhere.
export const DENSITY_STOPS = [0, 1, 2, 3, 4]
export function densityColor(d: number) {
  const t = Math.max(0, Math.min(1, d / 4))
  const lo = [38, 34, 28], hi = [255, 214, 150]                       // 0 -> 4+ people/m²
  return `rgb(${lo.map((v, i) => Math.round(v + (hi[i] - v) * Math.sqrt(t))).join(',')})`
}

export default function PlanView({ plan, exits, blocked = null, people, fireNode, closed = [], minCut = [], value = {}, compact, ours = true, onPick, tags = {}, smoke }: Props) {
  const hatch = useId()
  const N = plan.nodes
  const xs = N.map(n => n.x), ys = N.map(n => n.y)
  const x0 = Math.min(...xs) - CELL / 2, x1 = Math.max(...xs) + CELL / 2
  const y0 = Math.min(...ys) - CELL / 2, y1 = Math.max(...ys) + CELL / 2
  const top = compact ? 0 : 4                                              // room for the dimension line
  const vb = `${x0 - 1} ${y0 - 1 - top} ${x1 - x0 + 2} ${y1 - y0 + 2 + top}`
  const built = new Set(exits)
  const ex = ours ? 'var(--color-qp)' : 'var(--color-ink)'
  const maxVal = Math.max(1, ...Object.values(value).map(Math.abs))
  const walls = N.filter(n => n.kind !== 'exit')
  const bx0 = Math.min(...walls.map(n => n.x)) - CELL / 2, bx1 = Math.max(...walls.map(n => n.x)) + CELL / 2
  const density = (i: number) => (people ? people[i] / Math.max(N[i].area_m2, 1) : 0)
  const corridorEdges = plan.edges.map((e, i) => ({ e, i })).filter(({ e }) => N[e.a].kind === 'corridor' && N[e.b].kind === 'corridor')

  return (
    <svg viewBox={vb} className="h-full w-full" role="img" aria-label={`Floor plan: ${plan.name}`}>
      <defs>
        <pattern id={hatch} width="1.2" height="1.2" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <line x1="0" y1="0" x2="0" y2="1.2" stroke="var(--color-alert)" strokeWidth="0.35" />
        </pattern>
      </defs>

      {/* overall dimension line, like an architect's sheet */}
      {!compact && (
        <g className="num" stroke="var(--color-faint)" strokeWidth="0.1" fill="var(--color-faint)">
          <line x1={bx0} y1={y0 - 2.5} x2={bx1} y2={y0 - 2.5} />
          <line x1={bx0} y1={y0 - 3.3} x2={bx0} y2={y0 - 1.7} /><line x1={bx1} y1={y0 - 3.3} x2={bx1} y2={y0 - 1.7} />
          <text x={(bx0 + bx1) / 2} y={y0 - 3} fontSize={1.3} textAnchor="middle" stroke="none">{(bx1 - bx0).toFixed(0)} m</text>
        </g>
      )}

      {/* corridors: bands between corridor nodes, as wide as the passage */}
      {corridorEdges.map(({ e, i }) => {
        const a = N[e.a], b = N[e.b], cut = closed.includes(i)
        const d = (density(e.a) + density(e.b)) / 2
        return <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} strokeWidth={e.width_m + 0.6} strokeLinecap="square"
          stroke={cut ? 'var(--color-alert)' : people ? densityColor(d) : 'var(--color-raised)'} />
      })}
      {N.filter(n => n.kind === 'corridor').map(n => (
        <rect key={n.id} x={n.x - 1.5} y={n.y - 1.5} width={3} height={3} fill={people ? densityColor(density(n.id)) : 'var(--color-raised)'} />
      ))}

      {/* rooms: one grid cell each; floor area, or people inside when animating */}
      {N.filter(n => n.kind === 'room').map(n => (
        <g key={n.id}>
          <rect x={n.x - ROOM / 2} y={n.y - ROOM / 2} width={ROOM} height={ROOM} rx={0.2}
            fill={people ? densityColor(density(n.id)) : 'var(--color-raised)'} stroke="var(--color-line-strong)" strokeWidth="0.12" />
          {fireNode === n.id && <rect x={n.x - ROOM / 2} y={n.y - ROOM / 2} width={ROOM} height={ROOM} fill={`url(#${hatch})`} stroke="var(--color-alert)" strokeWidth="0.3" />}
          {people ? (
            <text x={n.x} y={n.y} fontSize={1.7} textAnchor="middle" dominantBaseline="central" className="num" fontWeight={600}
              fill={density(n.id) > 1.6 ? 'var(--color-bg)' : 'var(--color-ink)'}>{Math.round(people[n.id])}</text>
          ) : (
            <text x={n.x} y={n.y} fontSize={1.1} textAnchor="middle" dominantBaseline="central" fill="var(--color-dim)">{n.name ?? `Room ${n.id}`}</text>
          )}
        </g>
      ))}

      {/* doors from rooms: a small bar on the room's wall, as wide as the door */}
      {plan.edges.map((e, i) => {
        const r = N[e.a].kind === 'room' ? N[e.a] : N[e.b].kind === 'room' ? N[e.b] : null
        if (!r || e.candidate !== null) return null
        const c = r === N[e.a] ? N[e.b] : N[e.a]
        const vertical = Math.abs(r.y - c.y) > Math.abs(r.x - c.x)
        const mx = vertical ? r.x : r.x + Math.sign(c.x - r.x) * ROOM / 2
        const my = vertical ? r.y + Math.sign(c.y - r.y) * ROOM / 2 : r.y
        const cut = minCut.includes(i)
        return <rect key={i} x={vertical ? mx - e.width_m / 2 : mx - 0.25} y={vertical ? my - 0.25 : my - e.width_m / 2}
          width={vertical ? e.width_m : 0.5} height={vertical ? 0.5 : e.width_m}
          fill={cut ? 'var(--color-qp)' : 'var(--color-bg)'} stroke={cut ? 'var(--color-qp)' : 'var(--color-dim)'} strokeWidth="0.1" />
      })}

      {/* smoke: one grey square per 2 m cell, more opaque where it is thicker (0.6 = too thick to walk through) */}
      {smoke && smoke.cells.map((row, r) => row.map((v, c) => v > 0.04 && (
        <rect key={`s${r}-${c}`} x={smoke.x0 + c * smoke.cell} y={smoke.y0 + r * smoke.cell} width={smoke.cell} height={smoke.cell}
          fill="#c7ccd4" fillOpacity={Math.min(0.85, v * 1.1)} />
      )))}

      {/* the bottleneck passage (min-cut) on corridors, outlined */}
      {minCut.map(i => {
        const e = plan.edges[i]
        if (!e || N[e.a].kind !== 'corridor' || N[e.b].kind !== 'corridor') return null
        const a = N[e.a], b = N[e.b]
        return <line key={'cut' + i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="var(--color-qp)" strokeWidth={0.25} strokeDasharray="0.6 0.4" />
      })}

      {/* corridors blocked by smoke at this moment */}
      {closed.map(i => {
        const e = plan.edges[i]
        if (!e) return null
        const mx = (N[e.a].x + N[e.b].x) / 2, my = (N[e.a].y + N[e.b].y) / 2, v = Math.abs(N[e.a].x - N[e.b].x) < 0.1
        return <g key={'blk' + i} stroke="var(--color-alert)" strokeWidth={0.6} strokeLinecap="round">
          <line x1={mx - (v ? 2 : 0)} y1={my - (v ? 0 : 2)} x2={mx + (v ? 2 : 0)} y2={my + (v ? 0 : 2)} />
        </g>
      })}

      {/* candidate exits: ring = possible position, filled = built in this layout; size = value score */}
      {plan.candidates.map(c => {
        const n = N[c.node], at = N[c.attach_to], on = built.has(c.id)
        const r = 1.0 + 1.1 * Math.abs(value[c.id] ?? 0) / maxVal
        const front = c.id === plan.main_entrance
        const pick = onPick && !front ? () => onPick(c.id) : undefined
        const out = { x: n.x - at.x, y: n.y - at.y }                     // which side of the building the exit is on
        const tx = n.x, ty = n.y + (out.y < 0 ? -2.6 : 3.3)              // tag above exits on the top wall, else below
        const anchor = 'middle'
        return (
          <g key={c.id} onClick={pick} className={pick ? 'cursor-pointer' : undefined} role={pick ? 'button' : undefined}
            aria-label={pick ? `${on ? 'Remove' : 'Place'} exit ${exitLabel(c.id)}` : undefined}>
            {pick && <circle cx={n.x} cy={n.y} r={2.6} fill="transparent" />}
            {on && <line x1={at.x} y1={at.y} x2={n.x} y2={n.y} stroke={ex} strokeWidth={c.width_m / 3} />}
            <circle cx={n.x} cy={n.y} r={r} fill={on ? ex : 'var(--color-bg)'}
              stroke={on ? ex : 'var(--color-faint)'} strokeWidth="0.15" strokeDasharray={on ? undefined : '0.45 0.35'} />
            <text x={n.x} y={n.y} fontSize={compact ? 1.25 : 1.05} textAnchor="middle" dominantBaseline="central" fontWeight={600}
              fill={on ? 'var(--color-bg)' : 'var(--color-faint)'} className="num">{tags[c.id]?.split(' ')[0] ?? exitLabel(c.id)}</text>
            {front && !compact && <text x={tx} y={ty} fontSize={1.2} textAnchor={anchor} fill="var(--color-dim)">Front door</text>}
            {tags[c.id] && !front && <text x={tx} y={ty} fontSize={1.3} textAnchor={anchor} fontWeight={600} fill={ex}>Exit here</text>}
            {blocked === c.id && (
              <g stroke="var(--color-alert)" strokeWidth="0.45" strokeLinecap="round">
                <line x1={n.x - r - 0.4} y1={n.y - r - 0.4} x2={n.x + r + 0.4} y2={n.y + r + 0.4} />
                <line x1={n.x - r - 0.4} y1={n.y + r + 0.4} x2={n.x + r + 0.4} y2={n.y - r - 0.4} />
              </g>
            )}
          </g>
        )
      })}
    </svg>
  )
}
