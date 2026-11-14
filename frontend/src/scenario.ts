// Mirrors COUNTERS in engine/simulation.py (what each counter can do).
export const COUNTERS = [
  { name: 'C1', skills: 'ID · FEE · CERT' },
  { name: 'C2', skills: 'ID · FEE · CERT' },
  { name: 'C3', skills: 'ID · FEE' },
  { name: 'C4', skills: 'ID' },
]

// The scenario a judge can set: which counters close, when, for how long, and how many priority people.
export type Controls = { closed: string[]; from: number; length: number; priority: number }


// Read a starting scenario from the URL, e.g. ?close=C2&from=60&len=90&priority=10&t=24
// so a demo can open straight into a "broken" system with one link.
export function controlsFromUrl(): Controls {
  const q = new URLSearchParams(window.location.search)
  const num = (k: string, d: number) => (q.has(k) && !Number.isNaN(Number(q.get(k))) ? Number(q.get(k)) : d)
  const names = COUNTERS.map((c) => c.name)
  return {
    closed: (q.get('close') ?? '').split(',').filter((c) => names.includes(c)),
    from: num('from', 60),
    length: num('len', 90),
    priority: num('priority', 0),
  }
}
export const replayStartFromUrl = () => Number(new URLSearchParams(window.location.search).get('t')) || 0
