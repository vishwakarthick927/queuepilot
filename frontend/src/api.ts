// Talks to the FastAPI backend. If the backend is not running, we fall back to
// real responses saved from it (src/data/*.json) so the dashboard never goes blank.
import fallbackSim from './data/simulate.json'
import fallbackForecast from './data/forecast.json'

export const API = import.meta.env.VITE_API ?? 'http://localhost:8000'

export type StrategyResult = {
  avg_wait: number
  max_wait: number
  utilisation: Record<string, number>
}
export type SimResponse = { fcfs: StrategyResult; queuepilot: StrategyResult }

export type ForecastResponse = {
  forecast_error: { physics: number; data: number; hybrid: number }
  example: { minutes: number[]; actual: number[]; physics: number[]; data: number[]; hybrid: number[] }
  staffing_plan: number[]
}

// closures: counter name -> list of [start_minute, end_minute] windows when it is shut
export type Closures = Record<string, [number, number][]>

export type Source = 'live' | 'offline'

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(API + path, { ...init, signal: AbortSignal.timeout(15000) })
  if (!res.ok) throw new Error(`${path} ${res.status}`)
  return res.json()
}

export async function simulate(closures: Closures, runs = 60): Promise<{ data: SimResponse; source: Source }> {
  try {
    const data = await call<SimResponse>('/simulate', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ n_people: 150, runs, closures }),
    })
    return { data, source: 'live' }
  } catch {
    return { data: fallbackSim as SimResponse, source: 'offline' }
  }
}

export async function forecast(): Promise<{ data: ForecastResponse; source: Source }> {
  try {
    return { data: await call<ForecastResponse>('/forecast'), source: 'live' }
  } catch {
    return { data: fallbackForecast as ForecastResponse, source: 'offline' }
  }
}

// Percentage improvement of `ours` over `theirs` (positive = we are better / lower).
export const gain = (theirs: number, ours: number) => (theirs > 0 ? ((theirs - ours) / theirs) * 100 : 0)
