// Golden Hour: a city's emergency care as a network of queues.
// The same incidents (same seed) are routed two ways and simulated minute by minute:
//   "nearest"    = what happens today: the ambulance goes to the closest hospital
//   "queuepilot" = go where treatment STARTS soonest: travel time + forecast ER wait
// Everything is plain arithmetic so it can be explained line by line.

export type Hospital = { id: string; name: string; x: number; y: number; doctors: number }
export type Policy = 'nearest' | 'queuepilot'

export const HOSPITALS: Hospital[] = [
  { id: 'H1', name: 'Central', x: 10, y: 7, doctors: 6 },
  { id: 'H2', name: 'North', x: 8.5, y: 2.2, doctors: 3 },
  { id: 'H3', name: 'East', x: 16.2, y: 5.6, doctors: 3 },
  { id: 'H4', name: 'South', x: 9.2, y: 12.2, doctors: 3 },
  { id: 'H5', name: 'West', x: 3.2, y: 7.8, doctors: 3 },
  { id: 'H6', name: 'Ring Road', x: 14.2, y: 10.8, doctors: 4 },
]

export const CITY = { w: 20, h: 14 }          // km
export const START_HOUR = 14                  // clock starts 14:00
export const MINUTES = 360                    // simulate until 20:00
export const GOLDEN = 60                      // minutes from call to treatment
const SPEED = 0.45                            // km per minute in city traffic (27 km/h)
const ROAD = 1.3                              // roads are ~30% longer than a straight line
const PICKUP = 8                              // minutes for an ambulance to reach the patient
const TREAT_MEAN = 25                         // average minutes a doctor spends stabilising a patient
export const CRASH = { t: 150, x: 15.6, y: 4.6, n: 28, label: 'Bus crash, Outer Ring Road' }

export type Patient = {
  id: number; t0: number; x: number; y: number; surge: boolean
  hospital: string; arrive: number; start: number; end: number
  ttt: number        // time to treatment = call -> doctor starts
  late: boolean      // past the golden hour
}

// Small deterministic random generator so every run (and every judge) sees the same city.
function rng(seed: number) {
  let s = seed >>> 0
  return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296)
}

export const travel = (x: number, y: number, h: Hospital) => (Math.hypot(h.x - x, h.y - y) * ROAD) / SPEED

// The same calls for both policies: a normal afternoon + one mass-casualty event.
function makeIncidents(seed = 7) {
  const r = rng(seed)
  const exp = (mean: number) => -Math.log(1 - r()) * mean
  const calls: { t0: number; x: number; y: number; surge: boolean; dur: number }[] = []
  for (let t = exp(2.4); t < MINUTES - 60; t += exp(2.4)) {
    // more calls near the dense centre
    const cx = r() < 0.5 ? 10 + (r() - 0.5) * 8 : 1 + r() * 18
    const cy = r() < 0.5 ? 7 + (r() - 0.5) * 6 : 1 + r() * 12
    calls.push({ t0: t, x: cx, y: cy, surge: false, dur: 10 + r() * 30 })
  }
  for (let k = 0; k < CRASH.n; k++) {
    calls.push({ t0: CRASH.t + r() * 12, x: CRASH.x + (r() - 0.5) * 0.6, y: CRASH.y + (r() - 0.5) * 0.6, surge: true, dur: 15 + r() * 30 })
  }
  return calls.sort((a, b) => a.t0 - b.t0)
}

export function simulate(policy: Policy, seed = 7): Patient[] {
  const calls = makeIncidents(seed)
  // What the dispatcher believes: when each doctor will be free, using AVERAGE treatment time only.
  const est: Record<string, number[]> = Object.fromEntries(HOSPITALS.map((h) => [h.id, Array(h.doctors).fill(0)]))

  const chosen = calls.map((c) => {
    const arriveAt = (h: Hospital) => c.t0 + PICKUP + travel(c.x, c.y, h)
    const forecastStart = (h: Hospital) => Math.max(arriveAt(h), Math.min(...est[h.id]))
    const h = policy === 'nearest'
      ? HOSPITALS.reduce((a, b) => (travel(c.x, c.y, a) <= travel(c.x, c.y, b) ? a : b))
      : HOSPITALS.reduce((a, b) => (forecastStart(a) <= forecastStart(b) ? a : b))
    // book the earliest-free doctor (estimate)
    const docs = est[h.id]
    const i = docs.indexOf(Math.min(...docs))
    docs[i] = forecastStart(h) + TREAT_MEAN
    return { ...c, h, arrive: arriveAt(h) }
  })

  // What really happens: each ER treats patients in order of arrival with REAL treatment times.
  const out: Patient[] = []
  for (const h of HOSPITALS) {
    const free = Array(h.doctors).fill(0)
    chosen.filter((c) => c.h.id === h.id).sort((a, b) => a.arrive - b.arrive).forEach((c) => {
      const i = free.indexOf(Math.min(...free))
      const start = Math.max(c.arrive, free[i])
      free[i] = start + c.dur
      out.push({
        id: calls.indexOf(calls.find((k) => k.t0 === c.t0)!), t0: c.t0, x: c.x, y: c.y, surge: c.surge,
        hospital: h.id, arrive: c.arrive, start, end: start + c.dur, ttt: start - c.t0, late: start - c.t0 > GOLDEN,
      })
    })
  }
  return out.sort((a, b) => a.t0 - b.t0)
}

// State of the city at minute t (only uses what has happened by t).
export function snapshot(ps: Patient[], t: number) {
  const hospitals = HOSPITALS.map((h) => {
    const mine = ps.filter((p) => p.hospital === h.id)
    const waiting = mine.filter((p) => p.arrive <= t && p.start > t).length
    const busy = mine.filter((p) => p.start <= t && p.end > t).length
    const inbound = mine.filter((p) => p.t0 <= t && p.arrive > t).length
    // Physics forecast (conservation + Little's law): everyone waiting or on the way
    // must pass through `doctors` doctors, each taking ~TREAT_MEAN minutes.
    const backlog = Math.max(0, waiting + inbound + busy - h.doctors)
    const forecastWait = (backlog * TREAT_MEAN) / h.doctors
    return { ...h, waiting, busy, inbound, forecastWait }
  })
  const ambulances = ps.filter((p) => p.t0 <= t && p.arrive > t).map((p) => {
    const h = HOSPITALS.find((x) => x.id === p.hospital)!
    const leave = p.t0 + PICKUP
    const f = t < leave ? 0 : (t - leave) / (p.arrive - leave)   // 0 at the scene, 1 at the hospital
    return { id: p.id, x: p.x + (h.x - p.x) * f, y: p.y + (h.y - p.y) * f, to: h, surge: p.surge, loading: t < leave }
  })
  const done = ps.filter((p) => p.start <= t)
  const lateSoFar = done.filter((p) => p.late).length + ps.filter((p) => p.start > t && t - p.t0 > GOLDEN).length
  // In danger right now: called 30+ minutes ago and still no doctor.
  const atRisk = ps.filter((p) => p.t0 <= t && p.start > t && t - p.t0 >= GOLDEN / 2).length
  return { hospitals, ambulances, treated: done.length, lateSoFar, atRisk, calls: ps.filter((p) => p.t0 <= t).length }
}

export function summary(ps: Patient[]) {
  const late = ps.filter((p) => p.late).length
  const avg = ps.reduce((a, p) => a + p.ttt, 0) / ps.length
  const surge = ps.filter((p) => p.surge)
  return {
    patients: ps.length, late, onTime: 1 - late / ps.length, avgTtt: avg,
    worst: Math.max(...ps.map((p) => p.ttt)),
    surgeLate: surge.filter((p) => p.late).length, surgeN: surge.length,
  }
}

export const clock = (m: number) => {
  const mins = START_HOUR * 60 + Math.floor(m)
  return `${String(Math.floor(mins / 60)).padStart(2, '0')}:${String(mins % 60).padStart(2, '0')}`
}
