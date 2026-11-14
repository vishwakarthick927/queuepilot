import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { ForecastResponse } from '../api'
import { Frame, Key, Label } from './Frame'

const LINES = [
  { key: 'actual', name: 'Actual', color: 'var(--color-ink)', width: 1.5, dash: undefined },
  { key: 'physics', name: 'Physics only', color: 'var(--color-base)', width: 1.5, dash: '5 4' },
  { key: 'data', name: 'Data only', color: 'var(--color-data)', width: 1.5, dash: '2 3' },
  { key: 'hybrid', name: 'Hybrid (ours)', color: 'var(--color-qp)', width: 2.5, dash: undefined },
] as const

export function ForecastPanel({ data }: { data: ForecastResponse }) {
  const ex = data.example
  // Recharts wants one object per x value.
  const rows = ex.minutes.map((m, i) => ({ m, actual: ex.actual[i], physics: ex.physics[i], data: ex.data[i], hybrid: ex.hybrid[i] }))
  const err = data.forecast_error
  const worst = Math.max(err.physics, err.data, err.hybrid)

  return (
    <Frame index="01" title="Forecast" subtitle="People waiting, 60 min ahead · staffing never seen in training">
      <div className="grid gap-6 lg:grid-cols-[1fr_240px]">
        <div>
          <div className="mb-3 flex flex-wrap gap-4">
            {LINES.map((l) => <Key key={l.key} color={l.color} dashed={!!l.dash}>{l.name}</Key>)}
          </div>
          <div className="h-64">
            <ResponsiveContainer>
              <LineChart data={rows} margin={{ top: 4, right: 8, bottom: 0, left: -18 }}>
                <CartesianGrid stroke="var(--color-line)" vertical={false} />
                <XAxis dataKey="m" tick={{ fill: 'var(--color-faint)', fontSize: 11, fontFamily: 'JetBrains Mono' }}
                  stroke="var(--color-line-strong)" tickFormatter={(m) => `t+${m - ex.minutes[0] + 1}`} interval={9} />
                <YAxis tick={{ fill: 'var(--color-faint)', fontSize: 11, fontFamily: 'JetBrains Mono' }} stroke="var(--color-line-strong)" />
                <Tooltip
                  contentStyle={{ background: 'var(--color-raised)', border: '1px solid var(--color-line-strong)', borderRadius: 0, fontFamily: 'JetBrains Mono', fontSize: 12 }}
                  labelFormatter={(m) => `minute ${m}`} />
                {LINES.map((l) => (
                  <Line key={l.key} dataKey={l.key} name={l.name} stroke={l.color} strokeWidth={l.width}
                    strokeDasharray={l.dash} dot={false} isAnimationActive={false} />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="space-y-4">
          <Label>Avg error · people · lower is better</Label>
          {LINES.slice(1).map((l) => {
            const v = err[l.key as keyof typeof err]
            return (
              <div key={l.key}>
                <div className="flex items-baseline justify-between">
                  <span className="text-sm text-dim">{l.name}</span>
                  <span className="num text-lg" style={{ color: l.color }}>{v.toFixed(2)}</span>
                </div>
                <div className="mt-1 h-1.5 bg-line/60"><div className="h-full" style={{ width: `${(v / worst) * 100}%`, background: l.color }} /></div>
              </div>
            )
          })}
          <p className="border-t border-line pt-3 text-xs leading-relaxed text-dim">
            Physics = conservation of people, <span className="num text-ink">dq/dt = λ − μ·s</span>. Data learns what physics
            misses (people giving up). Together they beat both.
          </p>
        </div>
      </div>
    </Frame>
  )
}
