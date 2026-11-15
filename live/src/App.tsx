import { useState } from 'react'
import { VENUES, TAB, densityAt, frameAt } from './data'
import VenueMap from './VenueMap'

const q = new URLSearchParams(window.location.search)

export default function App() {
  const [vid, setVid] = useState(q.get('v') ?? VENUES[0].id)
  const venue = VENUES.find((v) => v.id === vid) ?? VENUES[0]
  const f = frameAt(venue, Number(q.get('t') ?? venue.today.danger_at_min))
  const open = new Set(venue.gates.filter((g) => g.open_at_start).map((g) => g.id))

  return (
    <div className="app">
      <header className="top">
        <div className="brand"><span className="mark" />QueuePilot Live</div>
        <nav className="seg" aria-label="Venue">
          {VENUES.map((v, i) => (
            <button key={v.id} aria-pressed={v.id === venue.id} onClick={() => setVid(v.id)}>
              {TAB[v.id] ?? v.name}<span className="key">{i + 1}</span>
            </button>
          ))}
        </nav>
      </header>
      <main className="body">
        <aside className="rail"><h2>Now</h2></aside>
        <section className="center">
          <div />
          <div className="stage"><VenueMap venue={venue} density={densityAt(venue.today, f)} openGates={open} flowing /></div>
          <div />
        </section>
        <aside className="rail right"><h2>Do</h2></aside>
      </main>
      <footer className="foot">Simulated crowd on a schematic layout. A person approves every action. Counts only, no faces.</footer>
    </div>
  )
}
