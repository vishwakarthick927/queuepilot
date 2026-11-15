import type { ReactNode } from 'react'

// Small shared pieces so every panel reads the same way.

// Section heading: a mono index number, a title, optional right-hand tag.
export function Head({ n, title, tag }: { n: string; title: string; tag?: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between border-b border-line pb-2">
      <h2 className="text-[13px] font-semibold uppercase tracking-[0.14em] text-dim">
        <span className="num mr-2 text-faint">{n}</span>{title}
      </h2>
      {tag}
    </div>
  )
}

// "SIMULATED" (or any) tag: every simulated number on the page sits under one of these.
export function Tag({ children, tone = 'dim' }: { children: ReactNode; tone?: 'dim' | 'qp' | 'alert' }) {
  const c = tone === 'qp' ? 'border-qp/50 text-qp' : tone === 'alert' ? 'border-alert/60 text-alert' : 'border-line-strong text-faint'
  return <span className={`num rounded-sm border px-1.5 py-px text-[11px] uppercase tracking-wider ${c}`}>{children}</span>
}

// A labelled readout: label on top, big tabular number with its unit.
export function Stat({ label, value, unit, tone, sub }: { label: string; value: ReactNode; unit?: string; tone?: 'qp' | 'alert'; sub?: ReactNode }) {
  const c = tone === 'qp' ? 'text-qp' : tone === 'alert' ? 'text-alert' : 'text-ink'
  return (
    <div>
      <div className="text-[12px] uppercase tracking-[0.12em] text-dim">{label}</div>
      <div className={`num mt-1 text-[27px] font-medium leading-none ${c}`}>
        {value}{unit && <span className="ml-1 text-[15px] text-dim">{unit}</span>}
      </div>
      {sub && <div className="mt-1 text-[13px] leading-snug text-dim">{sub}</div>}
    </div>
  )
}

// mm:ss for simulated seconds.
export const mmss = (s: number) => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(Math.round(s % 60)).padStart(2, '0')}`
export const fmt = (n: number) => n.toLocaleString('en-IN')
