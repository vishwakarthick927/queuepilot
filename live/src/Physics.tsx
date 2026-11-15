import { useEffect } from 'react'

// The formulas behind the screen (docs/STAMPEDE.md version 2, section B), each with one plain line.
const F = [
  { t: 'Nobody is created or lost', plain: 'People in a zone change only by who walks in and who walks out.',
    m: <>dN<sub>i</sub>/dt = Σ<sub>j</sub> f<sub>ji</sub> − Σ<sub>j</sub> f<sub>ij</sub></> },
  { t: 'Flow through a passage', plain: 'The smallest of: who can walk there, what the door passes, what fits on the other side.',
    m: <>f<sub>ij</sub> = min( N<sub>i</sub>·s<sub>ij</sub>·v(ρ<sub>i</sub>)·Δt / L<sub>ij</sub> , w<sub>ij</sub>·q<sub>max</sub>·Δt·η<sub>ij</sub> , A<sub>j</sub>·ρ<sub>max</sub> − N<sub>j</sub> )</> },
  { t: 'Crowds walk slower', plain: 'Walking speed falls as the space fills up.',
    m: <>v(ρ) = v<sub>0</sub> · max(0.15, 1 − ρ/ρ<sub>max</sub>),   ρ = N / A</> },
  { t: 'What the PG-GNN learns (bounded)', plain: 'How well each door really works, and which way people really go. Shares sum to 1.',
    m: <>η<sub>ij</sub> = σ(·) ∈ [0, 1],   s<sub>ij</sub> = softmax(·)</> },
  { t: 'The twin calibrates each gate', plain: 'Every 30 s: which gate efficiency makes the model match the people counted through it?',
    m: <>η̂ = argmin<sub>η</sub> | Σ<sub>t</sub> f<sub>gate</sub><sup>model</sup>(η) − Σ<sub>t</sub> f<sub>gate</sub><sup>counted</sup> |</> },
  { t: 'The plaza grid (PG-CNN)', plain: 'Each 2 m cell keeps its people; it takes in only what its usable floor can hold.',
    m: <>p<sub>c</sub>(t+1) = p<sub>c</sub> + Σ in − Σ out,   in ≤ π<sub>c</sub>·C − p<sub>c</sub>,   π<sub>c</sub> = σ(CNN(clutter)) ∈ [0, 1]</> },
  { t: 'Danger', plain: 'Above 4 people per m² people can no longer move freely. The index is the share of the maximum.',
    m: <>ρ ≥ 4 people/m²,   CPI = 100 · ρ / ρ<sub>max</sub></> },
  { t: 'The decision', plain: 'Try every set of actions; keep the one with the lowest peak crowd anywhere, any time.',
    m: <>a* = argmin<sub>action sets</sub> max<sub>zones, t</sub> ρ</> },
]

export default function Physics({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [onClose])
  return (
    <div className="drawer-back" onClick={onClose}>
      <aside className="drawer wide" role="dialog" aria-label="The physics" onClick={(e) => e.stopPropagation()}>
        <header>
          <h2>The physics</h2>
          <button className="linkbtn" onClick={onClose}>Close <kbd>Esc</kbd></button>
        </header>
        <ol className="formulas">
          {F.map((f, i) => (
            <li key={i}>
              <span className="how-n num">{i + 1}</span>
              <div>
                <div className="f-title">{f.t}</div>
                <div className="f-math">{f.m}</div>
                <div className="f-plain">{f.plain}</div>
              </div>
            </li>
          ))}
        </ol>
        <p className="honest">
          Constants: Δt = 5 s, q<sub>max</sub> = 1.3 people/s per metre, v<sub>0</sub> = 1.3 m/s, ρ<sub>max</sub> = 6 /m².
          They are parameters, not measurements. Physics hard-coded, learned terms bounded: the residual idea in
          Yu &amp; Wang, PNAS 2024, §3A.
        </p>
      </aside>
    </div>
  )
}
