import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import GoldenHour from './golden/GoldenHour.tsx'
import FloodTwin from './flood/FloodTwin.tsx'
import DesignStudio from './design/DesignStudio.tsx'

// "/" = Design Studio (hero, docs/BUILD.md) · "?view=flood" = Flood Twin · "?view=golden" = Golden Hour · "?view=engine" = the queue engine room
const view = new URLSearchParams(window.location.search).get('view')
const Page = view === 'engine' ? App : view === 'golden' ? GoldenHour : view === 'flood' ? FloodTwin : DesignStudio

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Page />
  </StrictMode>,
)
