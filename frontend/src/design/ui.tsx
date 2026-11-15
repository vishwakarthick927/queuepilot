import type { ReactNode } from 'react'

// Small shared pieces so every panel reads the same way.
// Type scale for the whole Design Studio: one family, three sizes (13 / 18 / 44 px), two weights (400 / 600).

// Section heading: index number, title, optional right-hand content.
export function Head({ n, title, tag }: { n: string; title: string; tag?: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-line pb-2">
      <h2 className="text-[13px] font-semibold uppercase tracking-[0.12em] text-dim">
        <span className="num mr-2 text-faint">{n}</span>{title}
      </h2>
      {tag}
    </div>
  )
}

// "simulated" (or any) tag: every simulated number sits under one of these.
export function Tag({ children, tone = 'dim' }: { children: ReactNode; tone?: 'dim' | 'alert' }) {
  const c = tone === 'alert' ? 'border-alert/60 text-alert' : 'border-line-strong text-faint'
  return <span className={`rounded-sm border px-1.5 text-[13px] lowercase ${c}`}>{children}</span>
}

// One row of a key/value list: label left, value right, hairline under it.
export function Row({ label, value, unit, tone, note }: { label: string; value: ReactNode; unit?: string; tone?: 'qp' | 'alert'; note?: ReactNode }) {
  const c = tone === 'qp' ? 'text-qp' : tone === 'alert' ? 'text-alert' : 'text-ink'
  return (
    <div className="border-b border-line py-2">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-[13px] text-dim">{label}</span>
        <span className={`num text-[18px] font-semibold ${c}`}>{value}{unit && <span className="ml-1 text-[13px] font-normal text-dim">{unit}</span>}</span>
      </div>
      {note && <div className="mt-0.5 text-right text-[13px] text-faint">{note}</div>}
    </div>
  )
}

// A keyboard hint next to a control.
export const Key = ({ k }: { k: string }) => <kbd className="num ml-2 rounded-sm border border-current/40 px-1 text-[13px] font-normal opacity-70">{k}</kbd>

// mm:ss for simulated seconds.
export const mmss = (s: number) => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(Math.round(s % 60)).padStart(2, '0')}`
export const fmt = (n: number) => n.toLocaleString('en-IN')
