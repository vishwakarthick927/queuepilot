import { gain, type ForecastResponse } from '../api'
import { Frame, Label } from './Frame'

const DAY_START = 9 // display only: the engine's 8-hour day is minutes 0–480; we label it 09:00–17:00

const clock = (block: number) => {
  const mins = DAY_START * 60 + block * 30
  return `${String(Math.floor(mins / 60)).padStart(2, '0')}:${mins % 60 === 0 ? '00' : '30'}`
}

// One column per 30-minute block; each lit cell is one open counter.
export function StaffingPlan({ plan, compare }: { plan: number[]; compare: ForecastResponse['staffing_comparison'] }) {
  const max = Math.max(...plan)
  const { fixed, planned } = compare
  const rows = [
    { label: 'Peak queue', unit: 'people', a: fixed.peak_queue, b: planned.peak_queue },
    { label: 'Average wait', unit: 'min', a: fixed.avg_wait_min, b: planned.avg_wait_min },
    { label: 'Average queue', unit: 'people', a: fixed.avg_queue, b: planned.avg_queue },
  ]

  return (
    <Frame index="02" title="Plan" subtitle="Counters to open per 30 min, from the forecast (Little's law: wait = queue ÷ throughput)">
      <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
        <div className="overflow-x-auto">
          <div className="flex min-w-[520px] items-end gap-1.5">
            {plan.map((n, i) => (
              <div key={i} className="flex flex-1 flex-col items-center gap-1.5">
                <span className="num text-[11px] text-dim">{n}</span>
                <div className="flex w-full flex-col-reverse gap-1">
                  {Array.from({ length: max }, (_, k) => (
                    <div key={k} className={`h-3.5 border ${k < n ? 'border-qp/80 bg-qp/70' : 'border-line bg-transparent'}`} />
                  ))}
                </div>
                <span className={`num text-[10px] ${i % 2 === 0 ? 'text-faint' : 'text-transparent'}`}>{clock(i)}</span>
              </div>
            ))}
          </div>
        </div>

        <div>
          <Label>Same {planned.staff_minutes.toLocaleString()} staff-minutes · spread evenly vs planned</Label>
          <div className="mt-3 space-y-3">
            {rows.map((r) => (
              <div key={r.label} className="flex items-baseline justify-between border-b border-line pb-2">
                <span className="text-sm text-dim">{r.label}</span>
                <span className="num text-sm">
                  <span className="text-base">{r.a}</span>
                  <span className="mx-1.5 text-faint">→</span>
                  <span className="text-qp">{r.b}</span>
                  <span className="ml-1 text-faint">{r.unit}</span>
                  <span className="ml-2 text-qp">−{gain(r.a, r.b).toFixed(0)}%</span>
                </span>
              </div>
            ))}
          </div>
          <p className="mt-3 text-xs leading-relaxed text-dim">
            No extra staff. The forecast moves the same people to the rush hours, so the peak queue shrinks.
          </p>
        </div>
      </div>
    </Frame>
  )
}
