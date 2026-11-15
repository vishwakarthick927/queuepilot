import { useEffect } from 'react'
import type { Venue } from './data'
import { VENUES, TAB, fmt1 } from './data'

// The drawer behind "How it works": three short blocks and the incident log. Everything read from data/crowd.
export default function HowItWorks({ venue, onClose }: { venue: Venue; onClose: () => void }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [onClose])

  const fc = venue.forecast
  const chosen = venue.actions.filter((a) => a.chosen)
  const plans = 2 ** venue.actions.length - 1

  return (
    <div className="drawer-back" onClick={onClose}>
      <aside className="drawer" role="dialog" aria-label="How it works" onClick={(e) => e.stopPropagation()}>
        <header>
          <h2>How it works</h2>
          <button className="linkbtn" onClick={onClose}>Close <kbd>Esc</kbd></button>
        </header>

        <section className="how">
          <div className="how-n num">1</div>
          <div>
            <h3>The physics we know</h3>
            <ul>
              <li>Nobody appears or disappears: people are conserved.</li>
              <li>A gate passes only so many people a second; a space holds only so many.</li>
              <li>People walk slower when it is dense.</li>
            </ul>
          </div>
        </section>

        <section className="how">
          <div className="how-n num">2</div>
          <div>
            <h3>What the twin learns</h3>
            <p>Nobody tells it a gate is failing. Every 30 s it fits one number per main gate, the share of its design
              throughput that matches the people counted through it, and re-runs the forecast.</p>
            <div className="learn-grid">
              {VENUES.map((v) => {
                const h = v.forecast.hidden_problem
                return (
                  <div key={v.id} className={v.id === venue.id ? 'lg-row on' : 'lg-row'}>
                    <span>{TAB[v.id]}</span>
                    <span className="lg-gate">{h.gate}</span>
                    <div className="lg-bars">
                      <i className="lg-true" style={{ width: `${h.true_share_of_design_flow * 100}%` }} />
                      <i className="lg-learn" style={{ width: `${h.learned_share * 100}%` }} />
                    </div>
                    <span className="num">{Math.round(h.learned_share * 100)}% <em>vs {Math.round(h.true_share_of_design_flow * 100)}%</em></span>
                  </div>
                )
              })}
              <div className="lg-key"><i className="lg-learn" /> learned <i className="lg-true" /> hidden truth</div>
            </div>
          </div>
        </section>

        <section className="how">
          <div className="how-n num">3</div>
          <div>
            <h3>How it decides</h3>
            <p>At the alarm it simulates every combination of the venue's {venue.actions.length} actions ({plans} plans)
              and picks the one with the lowest peak crowd. A person approves it.</p>
          </div>
        </section>

        <section className="log">
          <h3>Incident log · {venue.name}</h3>
          <dl>
            <dt>Alarm</dt><dd className="num">{fmt1(fc.alarm_at_min)} min</dd>
            <dt>Crush forecast</dt><dd className="num">{fmt1(fc.predicted_danger_at_min)} min, {venue.today.worst_zone}</dd>
            <dt>Warning</dt><dd className="num qp">{fmt1(fc.warning_min)} min</dd>
            <dt>Textbook plan</dt><dd>{fc.textbook_warning}</dd>
            <dt>Approved</dt><dd>{chosen.map((a) => a.label).join(' · ')}</dd>
            <dt>Peak crowd</dt><dd className="num">{fmt1(venue.today.peak_density)} → <b className="qp">{fmt1(venue.with_queuepilot.peak_density)}</b> people per m²</dd>
            <dt>Person-minutes in danger</dt><dd className="num">{venue.today.danger_person_min.toLocaleString('en-IN')} → <b className="qp">{venue.with_queuepilot.danger_person_min.toLocaleString('en-IN')}</b></dd>
          </dl>
        </section>

        <p className="honest">
          This forecaster is physics with one learned number per gate (the residual idea in Yu &amp; Wang, PNAS 2024), not a
          neural network. The trained deep models, PG-GNN for people and PG-CNN for smoke, are in QueuePilot Design; training
          the PG-GNN on venue runs is the next step. Simulated crowd on a schematic layout.
        </p>
      </aside>
    </div>
  )
}
