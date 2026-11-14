// Overflow Radar: the physics-guided neural network trained in research/golden/train_radar.py,
// running here in the browser. It predicts people waiting in an ER 30 minutes from now.
//   physics      = waiting + on the way - free doctors - what all doctors can start in 30 min
//   network adds = new_arrivals (>= 0, people not called in yet) and relief (0..1 of the physics backlog)
//   forecast     = physics - relief * physics + new_arrivals      (can never go negative)
import model from './radar_weights.json' with { type: 'json' }

const AHEAD = 30, TREAT = 25, MINUTES = 360
type Layer = { W: number[][]; b: number[] }
const layers = model.layers as Layer[]

const dense = (x: number[], l: Layer) => l.W.map((row, i) => row.reduce((a, w, j) => a + w * x[j], l.b[i]))
const softplus = (v: number) => Math.log1p(Math.exp(v))
const sigmoid = (v: number) => 1 / (1 + Math.exp(-v))

export type RadarInput = { waiting: number; busy: number; inbound: number; doctors: number; arrived30: number }

export function radar(h: RadarInput, calls15: number, t: number) {
  const physics = Math.max(0, h.waiting + h.inbound - (h.doctors - h.busy) - (h.doctors * AHEAD) / TREAT)
  const x = [h.waiting / 10, h.busy / 6, h.inbound / 10, h.doctors / 6, h.arrived30 / 10, calls15 / 10,
    Math.sin((Math.PI * t) / MINUTES), Math.cos((Math.PI * t) / MINUTES)]
  const h1 = dense(x, layers[0]).map(Math.tanh)
  const h2 = dense(h1, layers[1]).map(Math.tanh)
  const [o1, o2] = dense(h2, layers[2])
  const newArrivals = softplus(o1) * 5
  const relief = sigmoid(o2)
  return { physics, newArrivals, forecast: physics - relief * physics + newArrivals }
}

// Test scores from training (shown to judges as-is).
export const RADAR_RESULTS = model.results as unknown as Record<string, Record<string, { all: number; ER_filling_up: number }>>
