import { useEffect, useMemo } from 'react'
import katex from 'katex'
import 'katex/dist/katex.min.css'

// The physics behind the screen, typeset with KaTeX, each equation with one plain line.
// Crush-Point Finder: docs/STAMPEDE.md version 3 (five equations). Venue and twin: version 2 section B.
type Eq = { t: string; tex: string; plain: string; cite?: string }

const CRUSH: Eq[] = [
  { t: 'People are conserved', tex: String.raw`\frac{\partial \rho}{\partial t} + \nabla \cdot (\rho\,\mathbf{v}) = 0`,
    plain: 'Density only changes because people walk in or out. Nobody appears or disappears.', cite: 'continuity equation' },
  { t: 'Crowds walk slower', tex: String.raw`v(\rho) = v_0\left(1 - e^{-\gamma\left(\frac{1}{\rho} - \frac{1}{\rho_{\max}}\right)}\right)`,
    plain: 'Walking speed measured on real pedestrians: it falls towards zero as the space fills up.', cite: 'Weidmann 1993' },
  { t: 'People take the quickest path', tex: String.raw`\lvert \nabla T \rvert = \frac{1}{v(\rho)}, \qquad T = 0 \text{ at the gate}`,
    plain: 'Not the shortest path: routes bend around dense patches, which is why crowds pile up in odd places.', cite: 'Hughes 2002' },
  { t: 'Crowd pressure', tex: String.raw`P = \rho \cdot \operatorname{Var}(v)`,
    plain: 'Dense and jerky: when people are packed and speeds vary, pushing waves travel through the crowd.', cite: 'Helbing et al. 2007' },
  { t: 'What the PG-CNN learns', tex: String.raw`u(x) = \sigma\big(\mathrm{CNN}(\text{survey image})\big) \in [0, 1]`,
    plain: 'Only the share of each patch of floor that is really usable. Density is people per m² of usable floor.' },
]

const VENUE: Eq[] = [
  { t: 'Flow through a passage', tex: String.raw`f_{ij} = \min\!\Big( \tfrac{N_i\, s_{ij}\, v(\rho_i)\, \Delta t}{L_{ij}},\; w_{ij}\, q_{\max}\, \Delta t\, \eta_{ij},\; A_j \rho_{\max} - N_j \Big)`,
    plain: 'The smallest of: who can walk there, what the door passes, what fits on the other side.' },
  { t: 'What the PG-GNN learns', tex: String.raw`\eta_{ij} = \sigma(\cdot) \in [0,1], \qquad s_{ij} = \operatorname{softmax}(\cdot)`,
    plain: 'How well each door really works, and which way people really go. Shares sum to 1.' },
  { t: 'The twin calibrates each gate', tex: String.raw`\hat\eta = \arg\min_{\eta} \Big\lvert \textstyle\sum_t f^{\,\mathrm{model}}_{\mathrm{gate}}(\eta) - \sum_t f^{\,\mathrm{counted}}_{\mathrm{gate}} \Big\rvert`,
    plain: 'Every 30 s: which gate efficiency makes the model match the people counted through it?' },
  { t: 'Danger and the decision', tex: String.raw`\rho \ge 4\ \mathrm{m^{-2}}, \qquad a^\star = \arg\min_{\text{action sets}}\ \max_{\text{zones},\,t}\ \rho`,
    plain: 'Above 4 people per m² people can no longer move freely. Keep the actions with the lowest peak.' },
]

function Block({ eqs, start }: { eqs: Eq[]; start: number }) {
  const html = useMemo(() => eqs.map((e) => katex.renderToString(e.tex, { displayMode: true, throwOnError: false })), [eqs])
  return (
    <ol className="formulas">
      {eqs.map((e, i) => (
        <li key={i}>
          <span className="how-n num">{start + i}</span>
          <div>
            <div className="f-title">{e.t}{e.cite && <span className="f-cite">{e.cite}</span>}</div>
            <div className="f-math" dangerouslySetInnerHTML={{ __html: html[i] }} />
            <div className="f-plain">{e.plain}</div>
          </div>
        </li>
      ))}
    </ol>
  )
}

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
        <h3 className="f-section">Crush-Point Finder <span>where in the plaza</span></h3>
        <Block eqs={CRUSH} start={1} />
        <p className="f-const">v₀ = 1.34 m/s, γ = 1.913 m⁻², ρ<sub>max</sub> = 5.4 m⁻². Constants from Weidmann 1993; model from Hughes 2002; pressure from Helbing et al. 2007.</p>
        <h3 className="f-section">The venue and the twin <span>which zone, which gate</span></h3>
        <Block eqs={VENUE} start={6} />
        <p className="honest">
          Venue constants: Δt = 5 s, q<sub>max</sub> = 1.3 people/s per metre, v<sub>0</sub> = 1.3 m/s, ρ<sub>max</sub> = 6 m⁻²; they are
          parameters, not measurements. Physics hard-coded, learned terms bounded: the residual idea in Yu &amp; Wang, PNAS 2024, §3A.
        </p>
      </aside>
    </div>
  )
}
