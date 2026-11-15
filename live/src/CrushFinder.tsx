import { useEffect, useMemo, useRef, useState } from 'react'
import { PLAZA, PGCNN } from './data'

// Crush-Point Finder (docs/STAMPEDE.md version 3). The same plaza in front of the gate, three ways, one clock:
// what the site plan says, what the PG-CNN says, what really happens. Smooth heat maps (bilinear between the 2 m
// cells, coloured per pixel), crisp rings where density reaches the danger line, the clutter reveal, the pressure view.
// Every number comes from data/crowd/plaza_demo.json or research/live/pgcnn_plaza.json (simulated).

const P = PLAZA
const PX = 10                         // canvas pixels per 2 m cell
const CW = P.width * PX, CH = P.height * PX
const FRAMES = P.truth.density.length

// Thermal-camera ramp: dark → blue → pale below danger, then the alarm colour from the danger line up. No purple.
const STOPS: [number, [number, number, number]][] = [
  [0.0, [9, 14, 20]], [0.4, [14, 34, 52]], [1.2, [22, 72, 112]], [2.4, [47, 124, 179]], [3.4, [120, 182, 226]], [3.98, [214, 236, 248]],
  [4.0, [255, 77, 61]], [4.7, [255, 128, 104]], [5.4, [255, 214, 204]],
]
function ramp(v: number): [number, number, number] {
  if (v <= 0) return STOPS[0][1]
  for (let i = 1; i < STOPS.length; i++) {
    const [b, cb] = STOPS[i]
    if (v <= b) {
      const [a, ca] = STOPS[i - 1]
      const k = (v - a) / (b - a)
      return [0, 1, 2].map((j) => ca[j] + (cb[j] - ca[j]) * k) as [number, number, number]
    }
  }
  return STOPS[STOPS.length - 1][1]
}

// Value at a fractional cell position, bilinear between cell centres.
function sample(g: number[][], fx: number, fy: number) {
  const x = Math.max(0, Math.min(P.width - 1, fx - 0.5)), y = Math.max(0, Math.min(P.height - 1, fy - 0.5))
  const x0 = Math.floor(x), y0 = Math.floor(y), x1 = Math.min(P.width - 1, x0 + 1), y1 = Math.min(P.height - 1, y0 + 1)
  const kx = x - x0, ky = y - y0
  return (g[y0][x0] * (1 - kx) + g[y0][x1] * kx) * (1 - ky) + (g[y1][x0] * (1 - kx) + g[y1][x1] * kx) * ky
}

// The clutter the site plan does not show, as smooth hatched shapes (computed once).
const HATCH = (() => {
  const a = new Uint8ClampedArray(CW * CH * 4)
  for (let py = 0; py < CH; py++) for (let px = 0; px < CW; px++) {
    const c = sample(P.clutter, (px + 0.5) / PX, (py + 0.5) / PX)
    if (c < 0.35) continue
    const edge = c < 0.37
    const line = (px + py) % 7 < 1.6
    if (edge || line) { const i = (py * CW + px) * 4; a[i] = 236; a[i + 1] = 242; a[i + 2] = 248; a[i + 3] = edge ? 200 : 105 }
  }
  return new ImageData(a, CW, CH)
})()

type Ring = { x: number; y: number; r: number; peak: number }
// Crush points: groups of touching cells at or above the danger line. One ring per group, labelled with its peak.
function rings(g: number[][]): Ring[] {
  const seen = g.map((r) => r.map(() => false))
  const out: Ring[] = []
  for (let y = 0; y < P.height; y++) for (let x = 0; x < P.width; x++) {
    if (seen[y][x] || g[y][x] < P.danger_density) continue
    const stack = [[y, x]], cells: number[][] = []
    seen[y][x] = true
    while (stack.length) {
      const [cy, cx] = stack.pop()!
      cells.push([cy, cx])
      for (const [dy, dx] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
        const ny = cy + dy, nx = cx + dx
        if (ny >= 0 && ny < P.height && nx >= 0 && nx < P.width && !seen[ny][nx] && g[ny][nx] >= P.danger_density) { seen[ny][nx] = true; stack.push([ny, nx]) }
      }
    }
    const mx = cells.reduce((s, c) => s + c[1] + 0.5, 0) / cells.length, my = cells.reduce((s, c) => s + c[0] + 0.5, 0) / cells.length
    const r = Math.max(...cells.map((c) => Math.hypot(c[1] + 0.5 - mx, c[0] + 0.5 - my))) + 0.9
    out.push({ x: mx * PX, y: my * PX, r: r * PX, peak: Math.max(...cells.map((c) => g[c[0]][c[1]])) })
  }
  // Rings that touch become one ring around both, so each crush point gets one clean label.
  for (let merged = true; merged;) {
    merged = false
    for (let i = 0; i < out.length && !merged; i++) for (let j = i + 1; j < out.length && !merged; j++) {
      const a = out[i], b = out[j], d = Math.hypot(b.x - a.x, b.y - a.y)
      if (d > a.r + b.r - 2) continue
      let c: Ring
      if (d + b.r <= a.r) c = { ...a, peak: Math.max(a.peak, b.peak) }
      else if (d + a.r <= b.r) c = { ...b, peak: Math.max(a.peak, b.peak) }
      else {
        const r = (d + a.r + b.r) / 2, k = (r - a.r) / d
        c = { x: a.x + (b.x - a.x) * k, y: a.y + (b.y - a.y) * k, r, peak: Math.max(a.peak, b.peak) }
      }
      out.splice(j, 1); out.splice(i, 1, c); merged = true
    }
  }
  return out
}

function Heat({ grid, scale, clutter, label }: { grid: number[][] | null; scale: (v: number) => number; clutter: boolean; label: string }) {
  const ref = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const ctx = ref.current?.getContext('2d')
    if (!ctx) return
    const img = ctx.createImageData(CW, CH)
    for (let py = 0; py < CH; py++) for (let px = 0; px < CW; px++) {
      const i = (py * CW + px) * 4
      const [r, gg, b] = grid ? ramp(scale(sample(grid, (px + 0.5) / PX, (py + 0.5) / PX))) : [11, 16, 22]
      img.data[i] = r; img.data[i + 1] = gg; img.data[i + 2] = b; img.data[i + 3] = 255
    }
    ctx.putImageData(img, 0, 0)
    if (clutter) {
      const tmp = document.createElement('canvas'); tmp.width = CW; tmp.height = CH
      tmp.getContext('2d')!.putImageData(HATCH, 0, 0)
      ctx.drawImage(tmp, 0, 0)
    }
  }, [grid, scale, clutter])
  return <canvas ref={ref} width={CW} height={CH} className="heat" aria-label={label} role="img" />
}

// Display scales. Below the danger line a square-root lift so thin crowd lanes show, like a thermal image;
// at and above it the true value, so the alarm colour starts exactly at 4 people per m².
const dens = (v: number) => (v < P.danger_density ? P.danger_density * Math.sqrt(Math.max(0, v) / P.danger_density) : v)
// pressure: blue part of the ramp only (no danger threshold is claimed for it); saturates at a quarter of the peak so
// the build-up is visible, not only the single worst spot
const pres = (v: number) => 3.9 * Math.min(1, Math.sqrt(Math.max(0, v) / (0.25 * P.truth.peak_pressure)))
const lin = (v: number) => v

type Stat = { found: number; of: number; false_alarms: number; err: number } | null
type ViewProps = { title: string; sub: string; grid: number[][] | null; ringsOn: number[][] | null; scale: (v: number) => number; clutter: boolean; note?: string; accent?: boolean; stat?: Stat }

function View({ title, sub, grid, ringsOn, scale, clutter, note, accent, stat }: ViewProps) {
  const rs = useMemo(() => (ringsOn ? rings(ringsOn) : []), [ringsOn])
  const gateRows = P.gate.map((r, y) => (r.some((g) => g === 1) ? y : -1)).filter((y) => y >= 0)
  const g0 = Math.min(...gateRows) * PX, g1 = (Math.max(...gateRows) + 1) * PX
  const m = 10 / P.cell_m * PX         // 10 m in canvas pixels
  return (
    <figure className={accent ? 'cview accent' : 'cview'}>
      <figcaption><b>{title}</b><span>{sub}{note && grid ? ` · ${note}` : ''}</span></figcaption>
      <div className="cframe">
        <Heat grid={grid} scale={scale} clutter={clutter} label={`${title}: crowd heat map`} />
        <svg viewBox={`-14 -6 ${CW + 34} ${CH + 26}`} className="cover">
          {/* walls, with the gate as a real opening on the right wall */}
          <path d={`M0,0 H${CW} V${g0} M${CW},${g1} V${CH} H0`} className="wall" />
          <path d={`M0,0 V${CH}`} className="wall open" />
          <rect x={CW - 1} y={g0} width={4} height={g1 - g0} className="gate-open" />
          <text x={CW + 7} y={(g0 + g1) / 2 + 3} className="clabel">GATE</text>
          <path d={`M-12,${CH / 2} H-3 M-7,${CH / 2 - 4} L-3,${CH / 2} L-7,${CH / 2 + 4}`} className="arrive" />
          {/* 10 m scale bar */}
          <path d={`M0,${CH + 11} H${m} M0,${CH + 8} V${CH + 14} M${m},${CH + 8} V${CH + 14}`} className="scale" />
          <text x={m + 6} y={CH + 14} className="clabel">10 m</text>
          {rs.map((r, i) => (
            <g key={i} className="ring">
              <circle cx={r.x} cy={r.y} r={r.r} />
              <text x={r.x + r.r * 0.72 + 3} y={r.y - r.r * 0.72 - 2}>{r.peak.toFixed(1)}</text>
            </g>
          ))}
        </svg>
        {!grid && <div className="training"><b>training</b><span>no numbers until the PG-CNN is trained</span></div>}
      </div>
      {stat !== undefined && (
        <div className="cstat num">
          {stat ? <><b>{stat.found}</b> of {stat.of} found <span>· {stat.false_alarms} false alarms · error {stat.err.toFixed(2)} /m²</span></>
            : <span>whole wave: training</span>}
        </div>
      )}
    </figure>
  )
}

export default function CrushFinder({ onClose }: { onClose: () => void }) {
  const [f, setF] = useState(Math.min(FRAMES - 1, 16))
  const [playing, setPlaying] = useState(false)
  const q = new URLSearchParams(window.location.search)
  const [clutter, setClutter] = useState(q.get('clutter') === '1')
  const [pressure, setPressure] = useState(q.get('pressure') === '1')

  useEffect(() => {
    if (!playing) return
    const id = window.setInterval(() => setF((x) => { if (x >= FRAMES - 1) { setPlaying(false); return x } return x + 1 }), 220)
    return () => window.clearInterval(id)
  }, [playing])
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      else if (e.key === ' ') { e.preventDefault(); e.stopPropagation(); setPlaying((p) => !p) }
      else if (e.key.toLowerCase() === 'c') setClutter((c) => !c)
      else if (e.key.toLowerCase() === 'v') setPressure((c) => !c)
    }
    window.addEventListener('keydown', k, true)
    return () => window.removeEventListener('keydown', k, true)
  }, [onClose])

  const plan = P.models.hughes, sp = P.models.shortest_path
  const cnn = PGCNN
  const truthGrid = pressure ? P.truth.pressure[f] : P.truth.density[f]
  const mm = Math.floor((f * P.frame_s) / 60), ss = (f * P.frame_s) % 60

  return (
    <section className="crush" aria-label="Crush-Point Finder">
      <header className="crush-head">
        <div>
          <h2>Crush-Point Finder</h2>
          <p>The venue map tells us <b>which</b> plaza is in trouble. The Crush-Point Finder tells us <b>where</b> in that plaza people will be crushed.</p>
        </div>
        <div className="crush-tools">
          <button className={pressure ? 'chip on' : 'chip'} onClick={() => setPressure((p) => !p)} aria-pressed={pressure}>Crowd pressure <kbd>V</kbd></button>
          <button className={clutter ? 'chip on' : 'chip'} onClick={() => setClutter((c) => !c)} aria-pressed={clutter}>Show what the plan leaves out <kbd>C</kbd></button>
          <button className="linkbtn" onClick={onClose}>Back to the venue <kbd>Esc</kbd></button>
        </div>
      </header>

      <div className="cviews">
        <View title="Site plan says" sub="crowd physics on the plan as drawn" grid={plan.density[f]} ringsOn={plan.density[f]}
          scale={dens} clutter={false} note={pressure ? 'density only' : undefined}
          stat={{ found: plan.found, of: plan.crush_cells_true, false_alarms: plan.false_alarms, err: plan.density_error }} />
        <View title="PG-CNN says" sub={clutter ? 'learned usable floor (brighter = less usable)' : 'same physics + learned usable floor'}
          grid={cnn ? (clutter ? cnn.usable_share_learned.map((r) => r.map((u) => (1 - u) * 3.9)) : cnn.density[f]) : null}
          ringsOn={cnn && !clutter ? cnn.density[f] : null} scale={clutter ? lin : dens} clutter={false} accent
          note={pressure && cnn ? 'density only' : undefined}
          stat={cnn ? { found: cnn.found, of: cnn.crush_cells_true, false_alarms: cnn.false_alarms, err: cnn.density_error } : null} />
        <View title="What really happens" sub={pressure ? 'crowd pressure  P = ρ · Var(v)' : clutter ? 'clutter not on the site plan, hatched' : 'the simulated truth'}
          grid={truthGrid} ringsOn={P.truth.density[f]} scale={pressure ? pres : dens} clutter={clutter} />
      </div>

      <div className="cbottom">
        <div className="cclock">
          <button className="play" onClick={() => { if (f >= FRAMES - 1) setF(0); setPlaying((p) => !p) }} aria-label={playing ? 'Pause' : 'Play'}>
            {playing
              ? <svg viewBox="0 0 12 12" width="12" height="12"><rect x="2" y="1.5" width="3" height="9" /><rect x="7" y="1.5" width="3" height="9" /></svg>
              : <svg viewBox="0 0 12 12" width="12" height="12"><path d="M3 1.5 L10.5 6 L3 10.5 Z" /></svg>}
          </button>
          <span className="num">{mm}:{String(ss).padStart(2, '0')}</span>
          <input type="range" min={0} max={FRAMES - 1} value={f} onChange={(e) => { setF(+e.target.value); setPlaying(false) }} aria-label="Time in the plaza" />
          <span className="cscale"><i />below 4 /m² <i className="hot" />crush risk, 4 /m² and up</span>
        </div>
        <div className="cnums">
          <span className="cn-lab">Crush points found, of <b className="num">{plan.crush_cells_true}</b></span>
          <span className="cn"><b className="num">{sp.found}</b> shortest path</span>
          <span className="cn-arrow">→</span>
          <span className="cn"><b className="num">{plan.found}</b> crowd physics</span>
          <span className="cn-arrow">→</span>
          <span className="cn qp">{cnn ? <><b className="num">{cnn.found}</b> PG-CNN</> : <><em>training</em> PG-CNN</>}</span>
        </div>
      </div>
      <p className="cfoot">One simulated arrival wave of {P.total_people.toLocaleString('en-IN')} people into a 40 × 64 m plaza (schematic). Constants from Weidmann 1993; model from Hughes 2002; pressure from Helbing et al. 2007.</p>
    </section>
  )
}
