import { Frame, Label } from './Frame'

const DAY_START = 9 // display only: the engine's 8-hour day is minutes 0–480; we label it 09:00–17:00
const FIXED = 6     // the steady staffing used in training: 6 counters open all day

const clock = (block: number) => {
  const mins = DAY_START * 60 + block * 30
  return `${String(Math.floor(mins / 60)).padStart(2, '0')}:${mins % 60 === 0 ? '00' : '30'}`
}

// One column per 30-minute block; each lit cell is one open counter.
export function StaffingPlan({ plan }: { plan: number[] }) {
  const max = Math.max(FIXED, ...plan)
  const planHours = plan.reduce((a, b) => a + b, 0) / 2
  const fixedHours = FIXED * plan.length / 2

  return (
    <Frame index="02" title="Plan" subtitle="Counters to open per 30 min · keeps wait ≤ 10 min (Little's law)">
      <div className="grid gap-6 lg:grid-cols-[1fr_240px]">
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
        <div className="space-y-4">
          <div>
            <Label>Counter-hours needed</Label>
            <div className="num mt-1 text-3xl text-qp">{planHours}<span className="ml-2 text-sm text-faint">h</span></div>
          </div>
          <div>
            <Label>vs {FIXED} counters all day</Label>
            <div className="num mt-1 text-xl">{fixedHours}<span className="ml-2 text-sm text-faint">h</span></div>
          </div>
          <p className="border-t border-line pt-3 text-xs leading-relaxed text-dim">
            Staff follows the forecast: more counters in the morning and afternoon rush, fewer in the lull.
            <span className="num ml-1 text-qp">{Math.round((1 - planHours / fixedHours) * 100)}% fewer counter-hours.</span>
          </p>
        </div>
      </div>
    </Frame>
  )
}
