import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import GoldenHour from './golden/GoldenHour.tsx'

// "/" = the Golden Hour demo; "/?view=engine" = the engine room (queue dashboard).
const engine = new URLSearchParams(window.location.search).get('view') === 'engine'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {engine ? <App /> : <GoldenHour />}
  </StrictMode>,
)
