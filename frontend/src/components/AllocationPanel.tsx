import { useEffect, useState } from 'react'
import { simulate, gain, type Closures, type SimResponse, type Source } from '../api'
import { Frame, Key, Label } from './Frame'

// Mirrors COUNTERS in engine/simulation.py (what each counter can do).
const COUNTERS = [
  { name: 'C1', skills: 'ID · FEE · CERT' },
  { name: 'C2', skills: 'ID · FEE · CERT' },
  { name: 'C3', skills: 'ID · FEE' },
  { name: 'C4', skills: 'ID' },
]
const BASE = 'var(--color-base)'
const QP = 'var(--color-qp)'

export function AllocationPanel({ onResult }: { onResult: (r: SimResponse, s: Source) => void }) {
  const [closed, setClosed] = useState<string[]>([])  // counters switched off
  const [from, setFrom] = useState(60)                 // closure starts (minute)
  const [length, setLength] = useState(90)             // closure lasts (minutes)
  const [result, setResult] = useState<SimResponse | null>(null)
  const [source, setSource] = useState<Source>('live')
  const [busy, setBusy] = useState(false)

  // Re-run the simulation whenever the scenario changes (debounced so sliders feel smooth).
  useEffect(() => {
    const closures: Closures = Object.fromEntries(closed.map((c) => [c, [[from, from + length]]]))
    setBusy(true)
    const timer = setTimeout(async () => {
      const r = await simulate(closures)
      setResult(r.data); setSource(r.source); setBusy(false); onResult(r.data, r.source)
    }, 350)
    return () => clearTimeout(timer)
  }, [closed, from, length, onResult])

  const toggle = (c: string) => setClosed((cs) => (cs.includes(c) ? cs.filter((x) => x !== c) : [...cs, c]))

  return (
    <Frame
      index="03" title="Route" subtitle="Shortest line vs QueuePilot · 150 arrivals × 60 random days"
      right={<div className="flex gap-4"><Key color={BASE}>Shortest line</Key><Key color={QP}>QueuePilot</Key></div>}
    >
      <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
        {/* --- scenario controls --- */}
        <div className="space-y-5">
          <div>
            <Label>Break the system · close counters</Label>
            <div className="mt-2 grid grid-cols-2 gap-2">
              {COUNTERS.map((c) => {
                const off = closed.includes(c.name)
                return (
                  <button
                    key={c.name} onClick={() => toggle(c.name)} aria-pressed={off}
                    className={`cursor-pointer border px-3 py-2 text-left transition-colors duration-150 ${off ? 'border-alert/70 bg-alert/10' : 'border-line-strong bg-raised hover:border-qp/60'}`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="num text-sm font-semibold">{c.name}</span>
                      <span className={`num text-[10px] tracking-widest ${off ? 'text-alert' : 'text-qp'}`}>{off ? 'CLOSED' : 'OPEN'}</span>
                    </div>
                    <div className="num mt-1 text-[10px] text-faint">{c.skills}</div>
                  </button>
                )
              })}
            </div>
          </div>
          <Slider label="Closure starts" unit="min" value={from} min={0} max={200} step={10} onChange={setFrom} disabled={!closed.length} />
          <Slider label="Closure lasts" unit="min" value={length} min={30} max={180} step={10} onChange={setLength} disabled={!closed.length} />
          {source === 'offline' && closed.length > 0 && (
            <p className="num text-xs text-base">API offline: scenarios need the backend running.</p>
          )}
        </div>

        {/* --- results --- */}
        <div className={`space-y-6 transition-opacity duration-200 ${busy ? 'opacity-60' : ''}`} aria-busy={busy}>
          {result && (
            <>
              <div className="grid gap-4 sm:grid-cols-2">
                <Compare label="Average wait" unit="min" a={result.fcfs.avg_wait} b={result.queuepilot.avg_wait} />
                <Compare label="Worst wait" unit="min" a={result.fcfs.max_wait} b={result.queuepilot.max_wait} />
              </div>
              <div>
                <Label>Counter utilisation · % of the day busy</Label>
                <div className="mt-3 space-y-3">
                  {COUNTERS.map((c) => (
                    <div key={c.name} className="grid grid-cols-[36px_1fr] items-center gap-3">
                      <span className={`num text-sm ${closed.includes(c.name) ? 'text-alert' : 'text-dim'}`}>{c.name}</span>
                      <div className="space-y-1">
                        <Bar pct={result.fcfs.utilisation[c.name]} color={BASE} />
                        <Bar pct={result.queuepilot.utilisation[c.name]} color={QP} />
                      </div>
                    </div>
                  ))}
                  <Scale />
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </Frame>
  )
}

function Slider(p: { label: string; unit: string; value: number; min: number; max: number; step: number; onChange: (v: number) => void; disabled?: boolean }) {
  return (
    <label className={`block ${p.disabled ? 'opacity-40' : ''}`}>
      <div className="flex justify-between"><Label>{p.label}</Label><span className="num text-xs">{p.value} {p.unit}</span></div>
      <input type="range" className="mt-2 w-full cursor-pointer" min={p.min} max={p.max} step={p.step} value={p.value}
        disabled={p.disabled} onChange={(e) => p.onChange(Number(e.target.value))} />
    </label>
  )
}

// Two horizontal bars on a shared scale + the % improvement.
function Compare({ label, unit, a, b }: { label: string; unit: string; a: number; b: number }) {
  const max = Math.max(a, b) * 1.1
  const g = gain(a, b)
  return (
    <div className="border border-line bg-raised/60 p-4">
      <div className="flex items-baseline justify-between">
        <Label>{label}</Label>
        <span className={`num text-sm font-semibold ${g >= 0 ? 'text-qp' : 'text-alert'}`}>{g >= 0 ? '−' : '+'}{Math.abs(g).toFixed(1)}%</span>
      </div>
      {[{ v: a, c: BASE }, { v: b, c: QP }].map(({ v, c }) => (
        <div key={c} className="mt-3 flex items-center gap-3">
          <div className="h-2 flex-1 bg-line/60">
            <div className="h-full transition-[width] duration-500" style={{ width: `${(v / max) * 100}%`, background: c }} />
          </div>
          <span className="num w-20 text-right text-sm">{v.toFixed(1)} <span className="text-faint">{unit}</span></span>
        </div>
      ))}
    </div>
  )
}

function Bar({ pct, color }: { pct: number; color: string }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 flex-1 bg-line/60">
        <div className="h-full transition-[width] duration-500" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="num w-9 text-right text-[11px] text-dim">{pct}%</span>
    </div>
  )
}

// Graduated 0–100 tick scale under the utilisation bars.
function Scale() {
  return (
    <div className="grid grid-cols-[36px_1fr] gap-3">
      <span />
      <div className="mr-11 flex justify-between border-t border-line-strong pt-1">
        {[0, 25, 50, 75, 100].map((t) => <span key={t} className="num text-[10px] text-faint">{t}</span>)}
      </div>
    </div>
  )
}
