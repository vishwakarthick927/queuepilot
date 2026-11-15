import type { Venue, Zone } from './data'

// One light-to-dark blue ramp for density below danger; the alarm colour only at and above danger.
const RAMP = ['#101a24', '#132a3d', '#18405e', '#1f5a85', '#2f7cb3', '#5aa3d8', '#9ccdf0']
export function densityColor(d: number, danger: number) {
  if (d >= danger) return 'var(--alarm)'
  const t = Math.max(0, d / danger) * (RAMP.length - 1)
  const i = Math.min(RAMP.length - 2, Math.floor(t))
  return mix(RAMP[i], RAMP[i + 1], t - i)
}
function mix(a: string, b: string, k: number) {
  const p = (h: string) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16))
  const [x, y] = [p(a), p(b)]
  return `rgb(${x.map((v, i) => Math.round(v + (y[i] - v) * k)).join(',')})`
}

type Props = {
  venue: Venue
  density: number[]         // people per m² per zone, this instant
  openGates: Set<number>    // gate ids open now
  flowing: boolean          // draw moving dots along the passages
  learned?: { gate: string; learned_share: number }  // once the twin has found the failing gate, tag it on the map
}

// Elbow path between two zone centres: across first, then up or down. Reads like a floor plan, not a mind map.
function elbow(a: Zone, b: Zone) {
  if (a.x === b.x || a.y === b.y) return `M${a.x},${a.y} L${b.x},${b.y}`
  return `M${a.x},${a.y} L${b.x},${a.y} L${b.x},${b.y}`
}

export default function VenueMap({ venue, density, openGates, flowing, learned }: Props) {
  const z = venue.zones
  const pad = 34
  const x0 = Math.min(...z.map((q) => q.x - q.w / 2)) - pad
  const x1 = Math.max(...z.map((q) => q.x + q.w / 2)) + pad
  const y0 = Math.min(...z.map((q) => q.y - q.h / 2)) - pad - 10
  const y1 = Math.max(...z.map((q) => q.y + q.h / 2)) + pad
  const gateOf = new Map(venue.gates.map((g) => [g.zone, g]))
  const danger = venue.danger_density

  return (
    <svg className="map" viewBox={`${x0} ${y0} ${x1 - x0} ${y1 - y0}`} preserveAspectRatio="xMidYMid meet" role="img"
      aria-label={`${venue.name}: crowd density per zone`}>
      {/* passages: band thickness follows the real width in metres */}
      {venue.links.map((l, i) => {
        const a = z[l.a], b = z[l.b]
        const d = elbow(a, b)
        return (
          <g key={i}>
            <path d={d} className="link" strokeWidth={l.width_m * 1.6} />
            {flowing && l.gate === null && (density[l.a] > 0.05 || density[l.b] > 0.05) && (
              <path d={d} className="flow" style={{ animationDuration: `${Math.max(0.6, 2.4 - (density[l.a] + density[l.b]) * 0.12)}s` }} />
            )}
          </g>
        )
      })}

      {z.map((q) => {
        if (q.kind === 'gate') {
          const g = gateOf.get(q.id)
          const open = g ? openGates.has(g.id) : true
          return (
            <g key={q.id} className={open ? 'gate open' : 'gate shut'}>
              <rect x={q.x - 15} y={q.y - 3} width={6} height={10} rx={1} />
              <rect x={q.x + 9} y={q.y - 3} width={6} height={10} rx={1} />
              {open ? null : <line x1={q.x - 9} x2={q.x + 9} y1={q.y + 2} y2={q.y + 2} />}
              <text x={q.x} y={q.y - 9} textAnchor="middle" className="gate-name">{q.name}</text>
              {!open && <text x={q.x + 20} y={q.y + 6} className="gate-tag">closed</text>}
              {learned && learned.gate === q.name && (
                <text x={q.x + 20} y={q.y + 6} className="gate-tag learned">at {Math.round(learned.learned_share * 100)}%</text>
              )}
            </g>
          )
        }
        const d = density[q.id] ?? 0
        const hot = d >= danger
        return (
          <g key={q.id} className={hot ? 'zone hot' : 'zone'}>
            <rect x={q.x - q.w / 2} y={q.y - q.h / 2} width={q.w} height={q.h} rx={7} fill={densityColor(d, danger)} />
            <text x={q.x - q.w / 2 + 7} y={q.y - q.h / 2 + 13} className={d > danger * 0.62 && !hot ? 'zname on-light' : 'zname'}>
              {q.name}
            </text>
            {d >= 0.5 && (
              // narrow or flat zones (stairs, lanes) get a smaller number with no unit so it stays inside the box
              <text x={q.w < 70 ? q.x : q.x + q.w / 2 - 7} y={q.y + q.h / 2 - (q.h < 45 ? 6 : 8)} textAnchor={q.w < 70 ? 'middle' : 'end'}
                className={`${q.w < 70 || q.h < 45 ? 'zden small' : 'zden'} num${d > danger * 0.62 && !hot ? ' on-light' : ''}`}>
                {d.toFixed(1)}
                {q.w >= 70 && <tspan className="zunit"> /m²</tspan>}
              </text>
            )}
            {q.kind === 'source' && <text x={q.x - q.w / 2 + 7} y={q.y + q.h / 2 - 8} className="ztag">arrivals</text>}
          </g>
        )
      })}
    </svg>
  )
}
