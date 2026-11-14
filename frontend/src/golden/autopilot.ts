// Autopilot = QueuePilot routing + acting on the radar.
// Pass 1: run the day with smart routing and watch the radar.
// Pass 2: whenever the radar first expects 8+ people waiting at an ER, 2 off-duty doctors are
//         called in and start 20 minutes later (time to get there). Re-run the same day with them.
import { radar } from './radar.ts'
import { HOSPITALS, MINUTES, simulate, snapshot, type Crash, type Extra, type Patient } from './sim.ts'

export const RADAR_ALERT = 8
export const CALL_IN = { doctors: 2, delay: 20 }

export function radarAlerts(ps: Patient[], extra: Extra[] = []) {
  const out: { t: number; hospital: string; n: number }[] = []
  const hot = new Set<string>()
  for (let t = 0; t < MINUTES; t++) {
    const snap = snapshot(ps, t, extra)
    snap.hospitals.forEach((h) => {
      const n = Math.round(radar(h, snap.calls15, t).forecast)
      if (n >= RADAR_ALERT && !hot.has(h.id)) { hot.add(h.id); out.push({ t, hospital: h.id, n }) }
      else if (n < RADAR_ALERT / 2) hot.delete(h.id)
    })
  }
  return out
}

export function simulateAutopilot(seed: number, crash: Crash | null, rate: number) {
  const first = simulate('queuepilot', seed, crash, rate)
  const alerts = radarAlerts(first)
  const extra: Extra[] = alerts.flatMap((a) =>
    Array.from({ length: CALL_IN.doctors }, () => ({ hospital: a.hospital, t: a.t + CALL_IN.delay })))
  return { ps: simulate('queuepilot', seed, crash, rate, extra), extra, alerts }   // alerts = the call-ins that happened
}

export const hospitalName = (id: string) => HOSPITALS.find((h) => h.id === id)!.name
