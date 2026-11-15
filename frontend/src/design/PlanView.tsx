import { useId } from 'react'
import { exitsOf, type Plan } from './data'

// The floor plan, drawn in metres (SVG viewBox = metres), so every size on screen is to scale.
// Rooms are tinted by crowd density (people per m²) when an animation frame is passed in.

type Props = {
  plan: Plan
  exits: number                       // layout bitmask over plan.candidates
  people?: number[]                   // people per node at the current step (animation)
  fireNode?: number | null
  minCut?: number[]                   // edge indices to widen
  value?: Record<string, number>      // candidate id -> value score (marker size)
  label?: string
  compact?: boolean
  ours?: boolean                      // green = QueuePilot's exits; white = any other layout
}

// One sequential scale for density, same everywhere on the page (legend in the plan footer).
export const DENSITY_STOPS = [0, 1, 2, 3, 4]
export function densityColor(d: number) {
  const t = Math.max(0, Math.min(1, d / 4))
  const a = [24, 32, 43], b = [242, 165, 65], c = [255, 77, 77]        // empty -> amber -> red at 4 p/m²
  const [p, q, u] = t < 0.5 ? [a, b, t / 0.5] : [b, c, (t - 0.5) / 0.5]
  return `rgb(${p.map((v, i) => Math.round(v + (q[i] - v) * u)).join(',')})`
}

// Rectangle of a node (drawing hint w_m/h_m if MAIN sends it, else a square of the same area).
function box(n: Plan['nodes'][number]) {
  const w = n.w_m ?? Math.sqrt(Math.max(n.area_m2, 4)), h = n.h_m ?? Math.sqrt(Math.max(n.area_m2, 4))
  return { x: n.x - w / 2, y: n.y - h / 2, w, h }
}

export default function PlanView({ plan, exits, people, fireNode, minCut = [], value = {}, label, compact, ours = true }: Props) {
  const ex = ours ? 'var(--color-qp)' : 'var(--color-ink)'
  const hatch = useId()
  const inside = plan.nodes.filter(n => n.kind !== 'exit')
  const boxes = inside.map(box)
  const x0 = Math.min(...boxes.map(b => b.x)), x1 = Math.max(...boxes.map(b => b.x + b.w))
  const y0 = Math.min(...boxes.map(b => b.y)), y1 = Math.max(...boxes.map(b => b.y + b.h))
  const pad = compact ? 4 : 9                                           // compact = the side-by-side view: use every pixel
  const top = compact ? 0 : 4                                           // room for the dimension line
  const vb = `${x0 - pad} ${y0 - pad - top} ${x1 - x0 + 2 * pad} ${y1 - y0 + 2 * pad + top}`
  const on = new Set(exitsOf(exits, plan).map(c => c.id))
  const maxVal = Math.max(1, ...Object.values(value).map(Math.abs))
  const fs = compact ? 2.6 : 2.1                                        // text size in metres

  return (
    <svg viewBox={vb} className="h-full w-full" role="img" aria-label={`Floor plan ${plan.name}${label ? ', ' + label : ''}`}>
      <defs>
        <pattern id={hatch} width="1.6" height="1.6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <line x1="0" y1="0" x2="0" y2="1.6" stroke="var(--color-alert)" strokeWidth="0.5" />
        </pattern>
      </defs>

      {/* overall dimension line along the top: the drawing's scale, like an architect's sheet */}
      {!compact && <g className="num" stroke="var(--color-faint)" strokeWidth="0.15" fill="var(--color-faint)">
        <line x1={x0} y1={y0 - 5} x2={x1} y2={y0 - 5} />
        <line x1={x0} y1={y0 - 6.2} x2={x0} y2={y0 - 3.8} /><line x1={x1} y1={y0 - 6.2} x2={x1} y2={y0 - 3.8} />
        <text x={(x0 + x1) / 2} y={y0 - 6} fontSize={fs * 0.85} textAnchor="middle" stroke="none">{(x1 - x0).toFixed(1)} m</text>
      </g>}

      {/* rooms and corridors */}
      {inside.map((n, i) => {
        const b = boxes[i], d = people ? people[n.id] / Math.max(n.area_m2, 1) : 0
        return (
          <g key={n.id}>
            <rect x={b.x} y={b.y} width={b.w} height={b.h} fill={people ? densityColor(d) : 'var(--color-raised)'}
              fillOpacity={people ? 0.85 : 1} stroke="var(--color-line-strong)" strokeWidth="0.25" />
            {fireNode === n.id && <rect x={b.x} y={b.y} width={b.w} height={b.h} fill={`url(#${hatch})`} stroke="var(--color-alert)" strokeWidth="0.5" />}
            {n.kind !== 'corridor' && b.h > 6 && (
              <text x={n.x} y={n.y} fontSize={fs} textAnchor="middle" dominantBaseline="middle" fill="var(--color-ink)" className="num">
                <tspan x={n.x} dy={people ? '-0.5em' : 0}>{n.name || `#${n.id}`}</tspan>
                {people && <tspan x={n.x} dy="1.2em" fill="var(--color-dim)">{Math.round(people[n.id])}</tspan>}
              </text>
            )}
          </g>
        )
      })}

      {/* doors: a short bar at the midpoint between the two spaces, as wide as the door */}
      {plan.edges.map((e, i) => {
        const a = plan.nodes[e.a], b = plan.nodes[e.b]
        if (a.kind === 'corridor' && b.kind === 'corridor') return null
        const vertical = Math.abs(a.y - b.y) > Math.abs(a.x - b.x)
        const r = a.kind === 'room' ? a : b, c = r === a ? b : a
        const my = vertical ? c.y + Math.sign(r.y - c.y) * ((c.h_m ?? 2.4) / 2) : (a.y + b.y) / 2
        const mx = vertical ? r.x : (a.x + b.x) / 2
        const cut = minCut.includes(i)
        return (
          <g key={i}>
            <rect x={vertical ? mx - e.width_m / 2 : mx - 0.4} y={vertical ? my - 0.4 : my - e.width_m / 2}
              width={vertical ? e.width_m : 0.8} height={vertical ? 0.8 : e.width_m}
              fill={cut ? 'var(--color-qp)' : 'var(--color-bg)'} stroke={cut ? 'var(--color-qp)' : 'var(--color-dim)'} strokeWidth="0.2" />
            {cut && !compact && <text x={mx + 1.6} y={my + (r.y > c.y ? 2.6 : -1.6)} fontSize={fs * 0.85} fill="var(--color-qp)" className="num">widen {e.width_m} m</text>}
          </g>
        )
      })}

      {/* candidate exits: ring = possible, filled = in this layout; size = value score */}
      {plan.candidates.map(c => {
        const n = plan.nodes[c.node], at = plan.nodes[c.attach_to], sel = on.has(c.id)
        const ab = box(at)                                                // the passage starts at the wall, not the room centre
        const wx = Math.max(ab.x, Math.min(ab.x + ab.w, n.x)), wy = Math.max(ab.y, Math.min(ab.y + ab.h, n.y))
        const r = 1.3 + 1.6 * Math.abs(value[c.id] ?? 0) / maxVal
        return (
          <g key={c.id}>
            {sel && <line x1={wx} y1={wy} x2={n.x} y2={n.y} stroke={ex} strokeWidth="0.35" strokeDasharray={c.id === plan.main_entrance ? undefined : '1 0.6'} />}
            <circle cx={n.x} cy={n.y} r={r} fill={sel ? ex : 'var(--color-bg)'}
              stroke={sel ? ex : 'var(--color-faint)'} strokeWidth="0.25" strokeDasharray={sel ? undefined : '0.6 0.5'} />
            <text x={n.x} y={n.y} fontSize={fs * 0.8} textAnchor="middle" dominantBaseline="central" fontWeight={600}
              fill={sel ? 'var(--color-bg)' : 'var(--color-faint)'} className="num">{c.id}</text>
          </g>
        )
      })}
    </svg>
  )
}
