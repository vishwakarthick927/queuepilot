import { useCallback, useEffect, useState } from 'react'
import { forecast, gain, type ForecastResponse, type SimResponse, type Source } from './api'
import { AllocationPanel } from './components/AllocationPanel'
import { ForecastPanel } from './components/ForecastPanel'
import { StaffingPlan } from './components/StaffingPanel'
import { Label } from './components/Frame'

export default function App() {
  const [fc, setFc] = useState<ForecastResponse | null>(null)
  const [sim, setSim] = useState<SimResponse | null>(null)
  const [source, setSource] = useState<Source>('live')

  useEffect(() => { forecast().then((r) => { setFc(r.data); if (r.source === 'offline') setSource('offline') }) }, [])
  const onSim = useCallback((r: SimResponse, s: Source) => { setSim(r); setSource(s) }, [])

  // Headline numbers for the KPI strip.
  const err = fc?.forecast_error
  const kpis = [
    { label: 'Forecast error vs physics', value: err ? gain(err.physics, err.hybrid) : null, note: 'hybrid model' },
    { label: 'Forecast error vs pure data', value: err ? gain(err.data, err.hybrid) : null, note: 'hybrid model' },
    { label: 'Average wait', value: sim ? gain(sim.fcfs.avg_wait, sim.queuepilot.avg_wait) : null, note: 'vs shortest line' },
    { label: 'Worst-case wait', value: sim ? gain(sim.fcfs.max_wait, sim.queuepilot.max_wait) : null, note: 'vs shortest line' },
  ]

  return (
    <div className="mx-auto max-w-[1360px] px-4 py-6 md:px-8">
      {/* ---------- header ---------- */}
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-line pb-5">
        <div className="flex items-center gap-4">
          <Logo />
          <div>
            <h1 className="text-xl font-bold tracking-tight">QueuePilot</h1>
            <p className="text-sm text-dim">Physics-guided control for any queue: counters, clinics, chargers, servers.</p>
          </div>
        </div>
        <div className="flex items-center gap-5">
          <Pipeline />
          <span className={`num inline-flex items-center gap-2 border px-2.5 py-1 text-[11px] tracking-widest ${source === 'live' ? 'border-qp/50 text-qp' : 'border-base/50 text-base'}`}>
            <span className={`h-1.5 w-1.5 rounded-full ${source === 'live' ? 'bg-qp' : 'bg-base'}`} />
            {source === 'live' ? 'ENGINE LIVE' : 'OFFLINE · SAVED RUN'}
          </span>
        </div>
      </header>

      {/* ---------- KPI strip ---------- */}
      <div className="grid grid-cols-2 border-x border-b border-line lg:grid-cols-4">
        {kpis.map((k, i) => (
          <div key={k.label} className={`px-5 py-4 ${i > 0 ? 'border-l border-line' : ''} ${i === 2 ? 'max-lg:border-l-0 max-lg:border-t' : ''} ${i === 3 ? 'max-lg:border-t' : ''}`}>
            <Label>{k.label}</Label>
            <div className="num mt-1 text-3xl font-medium text-qp">
              {k.value == null ? '—' : `−${k.value.toFixed(0)}%`}
            </div>
            <div className="text-xs text-faint">{k.note}</div>
          </div>
        ))}
      </div>

      {/* ---------- the three layers ---------- */}
      <main className="mt-6 space-y-6">
        {fc && <ForecastPanel data={fc} />}
        {fc && <StaffingPlan plan={fc.staffing_plan} />}
        <AllocationPanel onResult={onSim} />
      </main>

      <footer className="num mt-8 flex flex-wrap justify-between gap-2 border-t border-line pt-4 text-[11px] text-faint">
        <span>Team Counter Intelligence · ZeroHour 2026 · PES University</span>
        <span>Hybrid model after Yu &amp; Wang, PNAS 2024</span>
      </footer>
    </div>
  )
}

// FORECAST → PLAN → ROUTE, the three layers in order.
function Pipeline() {
  return (
    <ol className="num hidden items-center gap-2 text-[11px] tracking-widest text-dim md:flex">
      {['FORECAST', 'PLAN', 'ROUTE'].map((s, i) => (
        <li key={s} className="flex items-center gap-2">
          {i > 0 && <span className="text-faint">→</span>}
          <span><span className="text-qp">0{i + 1}</span> {s}</span>
        </li>
      ))}
    </ol>
  )
}

// Mark: a counter with three lanes merging into one routed path.
function Logo() {
  return (
    <svg width="40" height="40" viewBox="0 0 40 40" aria-hidden className="shrink-0">
      <rect x="0.5" y="0.5" width="39" height="39" fill="none" stroke="var(--color-line-strong)" />
      <path d="M6 10 H16 L24 20 H34 M6 20 H34 M6 30 H16 L24 20" fill="none" stroke="var(--color-dim)" strokeWidth="1.5" />
      <path d="M6 20 H34" stroke="var(--color-qp)" strokeWidth="2" />
      <circle cx="34" cy="20" r="2.5" fill="var(--color-qp)" />
    </svg>
  )
}
