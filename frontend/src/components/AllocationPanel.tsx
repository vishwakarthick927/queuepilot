import { gain, STRATEGIES, STRAT_STYLE, type SimResponse, type Source } from '../api'
import { Frame, Key, Label } from './Frame'
import { COUNTERS, type Controls } from '../scenario'


type Props = {
  controls: Controls
  setControls: (c: Controls) => void
  result: SimResponse | null
  source: Source
  busy: boolean
}

export function AllocationPanel({ controls, setControls, result, source, busy }: Props) {
  const { closed, from, length, priority } = controls
  const set = (patch: Partial<Controls>) => setControls({ ...controls, ...patch })
  const toggle = (c: string) => set({ closed: closed.includes(c) ? closed.filter((x) => x !== c) : [...closed, c] })

  return (
    <Frame
      index="03" title="Route" subtitle="Who goes to which counter · 150 arrivals × 60 random days"
      right={<div className="flex flex-wrap gap-4">{STRATEGIES.map((k) => <Key key={k} color={STRAT_STYLE[k].color}>{STRAT_STYLE[k].short}</Key>)}</div>}
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
          <Slider label="Closure starts" unit="min" value={from} min={0} max={200} step={10} onChange={(v) => set({ from: v })} disabled={!closed.length} />
          <Slider label="Closure lasts" unit="min" value={length} min={30} max={180} step={10} onChange={(v) => set({ length: v })} disabled={!closed.length} />
          <Slider label="Priority people" unit="%" value={priority} min={0} max={30} step={5} onChange={(v) => set({ priority: v })} />
          {source === 'offline' && (closed.length > 0 || priority > 0) && (
            <p className="num text-xs text-base">API offline: scenarios need the backend running.</p>
          )}
        </div>

        {/* --- results --- */}
        <div className={`space-y-6 transition-opacity duration-200 ${busy ? 'opacity-60' : ''}`} aria-busy={busy}>
          {result && (
            <>
              <div className="grid gap-4 md:grid-cols-3">
                <Compare label="Average wait" r={result} pick={(s) => s.avg_wait} />
                <Compare label="95th-percentile wait" r={result} pick={(s) => s.p95_wait} />
                <Compare label="Worst wait" r={result} pick={(s) => s.max_wait} />
              </div>

              {priority > 0 && result.queuepilot.avg_wait_priority != null && (
                <PriorityCallout r={result} />
              )}

              <div>
                <Label>Counter utilisation · % of the day busy</Label>
                <div className="mt-3 space-y-3">
                  {COUNTERS.map((c) => (
                    <div key={c.name} className="grid grid-cols-[36px_1fr] items-center gap-3">
                      <span className={`num text-sm ${closed.includes(c.name) ? 'text-alert' : 'text-dim'}`}>{c.name}</span>
                      <div className="space-y-1">
                        {STRATEGIES.map((k) => <Bar key={k} pct={result[k].utilisation[c.name]} color={STRAT_STYLE[k].color} />)}
                      </div>
                    </div>
                  ))}
                  <Scale />
                </div>
              </div>

              <p className="num border-t border-line pt-3 text-[11px] leading-relaxed text-faint">
                Fairness (Jain index of waits, 1 = everyone waits equally):{' '}
                {STRATEGIES.map((k, i) => (
                  <span key={k}>{i > 0 && ' · '}<span style={{ color: STRAT_STYLE[k].color }}>{result[k].jain_fairness.toFixed(2)}</span></span>
                ))}
              </p>
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

// Three bars on a shared scale; the headline % is pooled vs shortest line.
function Compare({ label, r, pick }: { label: string; r: SimResponse; pick: (s: SimResponse['fcfs']) => number }) {
  const vals = STRATEGIES.map((k) => pick(r[k]))
  const max = Math.max(...vals) * 1.1
  const g = gain(vals[0], vals[2])
  return (
    <div className="border border-line bg-raised/60 p-4">
      <div className="flex items-baseline justify-between gap-2">
        <Label>{label}</Label>
        <span className={`num text-sm font-semibold ${g >= 0 ? 'text-qp' : 'text-alert'}`}>{g >= 0 ? '−' : '+'}{Math.abs(g).toFixed(1)}%</span>
      </div>
      {STRATEGIES.map((k, i) => (
        <div key={k} className="mt-2.5 flex items-center gap-3">
          <div className="h-2 flex-1 bg-line/60">
            <div className="h-full transition-[width] duration-500" style={{ width: `${(vals[i] / max) * 100}%`, background: STRAT_STYLE[k].color }} />
          </div>
          <span className="num w-14 text-right text-sm">{vals[i].toFixed(1)}</span>
        </div>
      ))}
      <div className="num mt-2 text-right text-[10px] text-faint">minutes</div>
    </div>
  )
}

// Priority people (e.g. elderly, emergencies): how much faster are they served, and does anyone else pay for it?
function PriorityCallout({ r }: { r: SimResponse }) {
  const base = r.fcfs, qp = r.queuepilot
  return (
    <div className="grid gap-4 border border-qp/30 bg-qp/5 p-4 sm:grid-cols-2">
      <div>
        <Label>Priority people · avg wait</Label>
        <div className="num mt-1 text-2xl">
          <span className="text-base">{base.avg_wait_priority!.toFixed(1)}</span>
          <span className="mx-2 text-faint">→</span>
          <span className="text-qp">{qp.avg_wait_priority!.toFixed(1)}</span>
          <span className="ml-1 text-sm text-faint">min</span>
        </div>
      </div>
      <div>
        <Label>Everyone else · avg wait</Label>
        <div className="num mt-1 text-2xl">
          <span className="text-base">{base.avg_wait_normal!.toFixed(1)}</span>
          <span className="mx-2 text-faint">→</span>
          <span className="text-ink">{qp.avg_wait_normal!.toFixed(1)}</span>
          <span className="ml-1 text-sm text-faint">min</span>
        </div>
      </div>
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
