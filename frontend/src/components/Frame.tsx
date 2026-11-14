import type { ReactNode } from 'react'

// A panel with machined corner brackets and an indexed header ("01 / ALLOCATION").
export function Frame(props: { index: string; title: string; subtitle?: string; right?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`relative border border-line bg-panel/95 ${props.className ?? ''}`}>
      {/* corner brackets */}
      {['top-0 left-0 border-t border-l', 'top-0 right-0 border-t border-r', 'bottom-0 left-0 border-b border-l', 'bottom-0 right-0 border-b border-r'].map((pos) => (
        <span key={pos} aria-hidden className={`absolute ${pos} -m-px h-3 w-3 border-qp/70`} />
      ))}
      <header className="flex flex-wrap items-end justify-between gap-3 border-b border-line px-5 py-3">
        <div className="flex items-baseline gap-3">
          <span className="num text-xs text-qp">{props.index}</span>
          <h2 className="text-sm font-semibold uppercase tracking-[0.16em]">{props.title}</h2>
          {props.subtitle && <span className="hidden text-xs text-dim md:inline">{props.subtitle}</span>}
        </div>
        {props.right}
      </header>
      <div className="p-5">{props.children}</div>
    </section>
  )
}

// Small all-caps label used above numbers and controls.
export function Label({ children }: { children: ReactNode }) {
  return <div className="num text-[11px] uppercase tracking-[0.14em] text-faint">{children}</div>
}

// Legend chip: colour swatch + name.
export function Key({ color, children, dashed }: { color: string; children: ReactNode; dashed?: boolean }) {
  return (
    <span className="num inline-flex items-center gap-2 text-xs text-dim">
      <span className="inline-block w-4 border-t-2" style={{ borderColor: color, borderStyle: dashed ? 'dashed' : 'solid' }} />
      {children}
    </span>
  )
}
