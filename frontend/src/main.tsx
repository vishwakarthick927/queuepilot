import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import GoldenHour from './golden/GoldenHour.tsx'
import FloodTwin from './flood/FloodTwin.tsx'

// "/" = the Flood Twin (hero) · "?view=golden" = Golden Hour · "?view=engine" = the queue engine room
const view = new URLSearchParams(window.location.search).get('view')

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {view === 'engine' ? <App /> : view === 'golden' ? <GoldenHour /> : <FloodTwin />}
  </StrictMode>,
)
