import { useEffect, useState } from 'react'
import { Area, AreaChart, ReferenceLine, ResponsiveContainer, XAxis, YAxis } from 'recharts'
import { STRAT_STYLE, type Frame as Snap, type SimResponse } from '../api'
import { COUNTERS, replayStartFromUrl, type Controls } from '../scenario'
import { Frame, Label } from './Frame'

const STEP_MS = 220   // real milliseconds per 5 simulated minutes
const MAX_DOTS = 14   // draw at most this many people per line, then "+N"

// Replays ONE simulated day. The parent remounts it (key) on a new scenario, which rewinds it.
// (same crowd for both) so judges can watch the lines move.
export function ReplayPanel({ result, controls }: { result: SimResponse; controls: Controls }) {
  const left = result.fcfs.timeline ?? []
  const right = result.pooled.timeline ?? []
  const last = Math.max(left.length, right.length) - 1
  const [i, setI] = useState(() => Math.min(replayStartFromUrl(), last))
  const [playing, setPlaying] = useState(false)

  // Advance one frame per tick while playing; stop at the end.
  useEffect(() => {
    if (!playing) return
    const id = setInterval(() => setI((x) => {
      if (x >= last) { setPlaying(false); return x }
      return x + 1
    }), STEP_MS)
    return () => clearInterval(id)
  }, [playing, last])

  if (last < 1) return null
  const at = (tl: Snap[]) => tl[Math.min(i, tl.length - 1)]
  const a = at(left), b = at(right)
  const t = a?.t ?? b?.t ?? 0
  const closedNow = (c: string) => controls.closed.includes(c) && t >= controls.from && t < controls.from + controls.length

  // Total people waiting over the day, both strategies, for the strip chart.
  const series = Array.from({ length: last + 1 }, (_, k) => ({
    t: k * 5,
    base: left[Math.min(k, left.length - 1)]?.waiting ?? 0,
    pooled: right[Math.min(k, right.length - 1)]?.waiting ?? 0,
  }))

  const play = () => { if (i >= last) setI(0); setPlaying((p) => !p) }

  return (
    <Frame
      index="04" title="Replay" subtitle="One day, same crowd, two systems · watch the lines"
      right={
        <div className="flex items-center gap-3">
          <span className="num text-sm text-dim">{clock(t)}</span>
          <button onClick={play} className="num cursor-pointer border border-qp/60 px-3 py-1 text-xs tracking-widest text-qp transition-colors duration-150 hover:bg-qp/10">
            {playing ? 'PAUSE' : i >= last ? 'REPLAY' : 'PLAY'}
          </button>
        </div>
      }
    >
      <div className="grid gap-5 lg:grid-cols-2">
        <Side title="Shortest line" note="pick a line on arrival, stuck with it" color={STRAT_STYLE.fcfs.color} waiting={a?.waiting ?? 0}>
          {COUNTERS.map((c) => (
            <Lane key={c.name} name={c.name} serving={!!a?.serving[c.name]} closed={closedNow(c.name)} color={STRAT_STYLE.fcfs.color}>
              <Dots n={a?.queues[c.name] ?? 0} color={STRAT_STYLE.fcfs.color} />
            </Lane>
          ))}
        </Side>

        <Side title="QueuePilot pooled" note="one virtual queue, counter assigned when it frees" color={STRAT_STYLE.pooled.color} waiting={b?.waiting ?? 0}>
          <div className="flex min-h-9 items-center border border-dashed border-qp/30 px-3 py-2">
            <span className="num mr-3 text-[10px] tracking-widest text-faint">TOKENS</span>
            <Dots n={b?.waiting ?? 0} color={STRAT_STYLE.pooled.color} />
          </div>
          <div className="grid grid-cols-4 gap-2">
            {COUNTERS.map((c) => (
              <CounterBox key={c.name} name={c.name} serving={!!b?.serving[c.name]} closed={closedNow(c.name)} color={STRAT_STYLE.pooled.color} />
            ))}
          </div>
        </Side>
      </div>

      {/* strip chart + scrubber */}
      <div className="mt-6">
        <Label>People waiting over the day</Label>
        <div className="mt-2 h-24">
          <ResponsiveContainer>
            <AreaChart data={series} margin={{ top: 4, right: 4, bottom: 0, left: -24 }}>
              <XAxis dataKey="t" tick={{ fill: 'var(--color-faint)', fontSize: 10, fontFamily: 'JetBrains Mono' }} stroke="var(--color-line-strong)"
                tickFormatter={(m) => clock(m)} interval={11} />
              <YAxis tick={{ fill: 'var(--color-faint)', fontSize: 10, fontFamily: 'JetBrains Mono' }} stroke="var(--color-line-strong)" />
              <Area dataKey="base" stroke={STRAT_STYLE.fcfs.color} fill={STRAT_STYLE.fcfs.color} fillOpacity={0.12} isAnimationActive={false} />
              <Area dataKey="pooled" stroke={STRAT_STYLE.pooled.color} fill={STRAT_STYLE.pooled.color} fillOpacity={0.18} isAnimationActive={false} />
              <ReferenceLine x={t} stroke="var(--color-ink)" strokeDasharray="3 3" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
        <input type="range" aria-label="Replay time" className="mt-1 w-full cursor-pointer" min={0} max={last} value={i}
          onChange={(e) => { setPlaying(false); setI(Number(e.target.value)) }} />
      </div>
    </Frame>
  )
}

const clock = (m: number) => {
  const mins = 9 * 60 + m
  return `${String(Math.floor(mins / 60)).padStart(2, '0')}:${String(mins % 60).padStart(2, '0')}`
}

function Side(p: { title: string; note: string; color: string; waiting: number; children: React.ReactNode }) {
  return (
    <div className="border border-line bg-raised/40 p-4">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold" style={{ color: p.color }}>{p.title}</div>
          <div className="text-xs text-faint">{p.note}</div>
        </div>
        <div className="text-right">
          <div className="num text-2xl leading-none" style={{ color: p.color }}>{p.waiting}</div>
          <div className="num text-[10px] tracking-widest text-faint">WAITING</div>
        </div>
      </div>
      <div className="space-y-2">{p.children}</div>
    </div>
  )
}

// One counter with its own line of people (shortest-line system).
function Lane(p: { name: string; serving: boolean; closed: boolean; color: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3">
      <CounterBox name={p.name} serving={p.serving} closed={p.closed} color={p.color} />
      <div className="min-h-6 flex-1 border-b border-line pb-1">{p.children}</div>
    </div>
  )
}

function CounterBox({ name, serving, closed, color }: { name: string; serving: boolean; closed: boolean; color: string }) {
  return (
    <div
      className="num flex h-9 w-14 shrink-0 flex-col items-center justify-center border text-xs transition-colors duration-150"
      style={closed ? { borderColor: 'var(--color-alert)', color: 'var(--color-alert)' }
        : serving ? { borderColor: color, color, background: `color-mix(in srgb, ${color} 14%, transparent)` }
        : { borderColor: 'var(--color-line-strong)', color: 'var(--color-faint)' }}
    >
      {name}
      <span className="text-[8px] tracking-widest">{closed ? 'SHUT' : serving ? 'BUSY' : 'IDLE'}</span>
    </div>
  )
}

// n people as dots; anything past MAX_DOTS becomes "+N".
function Dots({ n, color }: { n: number; color: string }) {
  return (
    <div className="flex flex-wrap items-center gap-1">
      {Array.from({ length: Math.min(n, MAX_DOTS) }, (_, k) => (
        <span key={k} className="h-2.5 w-2.5 rounded-full" style={{ background: color, opacity: 1 - k * 0.04 }} />
      ))}
      {n > MAX_DOTS && <span className="num ml-1 text-[11px] text-dim">+{n - MAX_DOTS}</span>}
    </div>
  )
}
