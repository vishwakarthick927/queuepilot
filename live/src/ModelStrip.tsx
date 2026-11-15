import type { Venue } from './data'
import { PGCNN, PGGNN, fmt1 } from './data'

// The pipeline under the top bar: PG-GNN (venue) → PG-CNN (plaza) → Twin (gates) → Plan.
// The stage the demo is in lights up. Numbers only from result files; a model without a file says "training".
type Props = { venue: Venue; stage: number; onOpen: (what: 'venue' | 'plaza' | 'twin' | 'plan') => void }

export default function ModelStrip({ venue, stage, onOpen }: Props) {
  const gnn = PGGNN?.models
  const cnn = PGCNN?.models
  const hp = venue.forecast.hidden_problem
  const steps = [
    { id: 'venue' as const, tag: 'PG-GNN', name: 'the venue', what: 'people per zone',
      fact: gnn ? `${fmt1(gnn.pggnn.peak_density_err)} /m² peak error, unseen venue` : null },
    { id: 'plaza' as const, tag: 'PG-CNN', name: 'the plaza', what: 'where they pile up',
      fact: cnn ? `${cnn.pgcnn.danger_cells_found} of ${cnn.pgcnn.danger_cells_true} danger cells found` : null },
    { id: 'twin' as const, tag: 'Twin', name: 'the gates', what: 'learns each gate from counts',
      fact: `${hp.gate} at ${Math.round(hp.learned_share * 100)}%` },
    { id: 'plan' as const, tag: 'Plan', name: 'the decision', what: 'a person approves',
      fact: `peak ${fmt1(venue.today.peak_density)} → ${fmt1(venue.with_queuepilot.peak_density)} /m²` },
  ]
  return (
    <nav className="strip" aria-label="How QueuePilot Live thinks">
      {steps.map((s, i) => (
        <button key={s.id} className={i === stage ? 'step on' : i < stage ? 'step done' : 'step'} onClick={() => onOpen(s.id)}>
          <span className="step-n num">{i + 1}</span>
          <span className="step-txt">
            <span className="step-line"><b>{s.tag}</b> · {s.name}</span>
            <span className="step-fact num">{s.fact ?? <em>training</em>}</span>
          </span>
          {i < steps.length - 1 && <svg className="step-arrow" viewBox="0 0 10 10" aria-hidden="true"><path d="M2 1 L7 5 L2 9" /></svg>}
        </button>
      ))}
    </nav>
  )
}
