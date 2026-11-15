import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { CurvePoint } from './data'

// "Number of exits -> worst-case clearance": ours vs rule of thumb, with the safe limit line.
export default function Curve({ curve, limit, selected, onPick, ours }: { curve: CurvePoint[]; limit: number; selected: number; onPick: (n: number) => void; ours: boolean }) {
  const tick = { fill: 'var(--color-dim)', fontSize: 13, fontFamily: 'var(--font-mono)' }
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={curve} margin={{ top: 10, right: 92, bottom: 4, left: 0 }}
        onClick={(s) => { const n = Number(s?.activeLabel); if (n) onPick(n) }}>
        <CartesianGrid stroke="var(--color-line)" vertical={false} />
        <XAxis dataKey="n_exits" tick={tick} stroke="var(--color-line-strong)" tickLine={false}
          label={{ value: 'exits', position: 'insideBottomRight', offset: -2, fill: 'var(--color-faint)', fontSize: 12 }} />
        <YAxis tick={tick} stroke="var(--color-line-strong)" tickLine={false} width={46} unit=" s" />
        <ReferenceLine y={limit} stroke="var(--color-alert)" strokeDasharray="5 4"
          label={{ value: `safe limit ${limit} s`, position: 'right', fill: 'var(--color-alert)', fontSize: 12 }} />
        <ReferenceLine x={selected} stroke="var(--color-line-strong)" />
        <Tooltip contentStyle={{ background: 'var(--color-panel)', border: '1px solid var(--color-line-strong)', fontFamily: 'var(--font-mono)', fontSize: 13 }}
          labelFormatter={(n) => `${n} exits`} formatter={(v, k) => [`${v} s`, k === 'ours_s' ? 'QueuePilot' : 'Rule of thumb']} />
        <Line dataKey="rule_s" stroke="var(--color-dim)" strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} />
        {ours && <Line dataKey="ours_s" stroke="var(--color-qp)" strokeWidth={2.5} dot={{ r: 3.5 }} isAnimationActive={false} />}
      </LineChart>
    </ResponsiveContainer>
  )
}
