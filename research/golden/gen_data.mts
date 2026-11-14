// Generates training data for the Overflow Radar from the Golden Hour simulator.
// Run from repo root:  node --experimental-strip-types research/golden/gen_data.mts
// Each row = one hospital at one moment (what a control room can see) + the true
// number of people waiting there 30 minutes later.
import { writeFileSync } from 'node:fs'
import { HOSPITALS, MINUTES, simulate, snapshot, type Crash, type Policy } from '../../frontend/src/golden/sim.ts'

const AHEAD = 30
let s = 12345
const r = () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296)
const rows: number[][] = []
for (let day = 0; day < 1200; day++) {
  const crash: Crash | null = r() < 0.65
    ? { t: 60 + r() * 200, x: 1 + r() * 18, y: 1 + r() * 12, n: Math.round(8 + r() * 30), label: '' } : null
  const policy: Policy = r() < 0.5 ? 'nearest' : 'queuepilot'
  const ps = simulate(policy, 1000 + day, crash, 2.0 + r() * 1.4)
  for (let t = 20; t + AHEAD < MINUTES; t += 10) {
    const now = snapshot(ps, t), later = snapshot(ps, t + AHEAD)
    const cityCalls15 = ps.filter((p) => p.t0 > t - 15 && p.t0 <= t).length
    HOSPITALS.forEach((h, i) => {
      const n = now.hospitals[i]
      const arrived30 = ps.filter((p) => p.hospital === h.id && p.arrive > t - 30 && p.arrive <= t).length
      // day, hospital, minute, waiting, busy, inbound, doctors, arrived in last 30, city calls in last 15 | target
      rows.push([day, i, t, n.waiting, n.busy, n.inbound, h.doctors, arrived30, cityCalls15, later.hospitals[i].waiting])
    })
  }
}
writeFileSync('research/golden/radar_data.json', JSON.stringify(rows))
console.log('rows', rows.length)
