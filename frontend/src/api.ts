// Talks to the FastAPI backend. If the backend is not running, we fall back to
// real responses saved from it (src/data/*.json) so the dashboard never goes blank.
import fallbackSim from './data/simulate.json'
import fallbackForecast from './data/forecast.json'

export const API = import.meta.env.VITE_API ?? 'http://localhost:8000'

// One snapshot every 5 minutes of a single simulated day (for the replay).
export type Frame = {
  t: number
  waiting: number                    // people waiting, not yet at a counter
  queues: Record<string, number>     // people lined up at each counter (0 for pooled)
  serving: Record<string, boolean>   // is the counter busy right now
}

export type StrategyResult = {
  avg_wait: number
  max_wait: number
  p95_wait: number
  jain_fairness: number
  utilisation: Record<string, number>
  avg_wait_priority?: number
  avg_wait_normal?: number
  timeline?: Frame[]
}

// The three strategies the engine compares, in display order.
export const STRATEGIES = ['fcfs', 'queuepilot', 'pooled'] as const
export type StrategyKey = (typeof STRATEGIES)[number]

export type SimResponse = Record<StrategyKey, StrategyResult> & { labels: Record<StrategyKey, string> }

export type StaffingStats = { avg_queue: number; peak_queue: number; avg_wait_min: number; staff_minutes: number }
export type ForecastResponse = {
  forecast_error: { physics: number; data: number; hybrid: number }
  example: { minutes: number[]; actual: number[]; physics: number[]; data: number[]; hybrid: number[] }
  staffing_plan: number[]
  staffing_comparison: { fixed: StaffingStats; planned: StaffingStats }
}

// closures: counter name -> list of [start_minute, end_minute] windows when it is shut
export type Closures = Record<string, [number, number][]>
export type Scenario = { closures: Closures; priority_share: number }

export type Source = 'live' | 'offline'

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(API + path, { ...init, signal: AbortSignal.timeout(20000) })
  if (!res.ok) throw new Error(`${path} ${res.status}`)
  return res.json()
}

export async function simulate(s: Scenario, runs = 60): Promise<{ data: SimResponse; source: Source }> {
  try {
    const data = await call<SimResponse>('/simulate', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ n_people: 150, runs, closures: s.closures, priority_share: s.priority_share, trace: true }),
    })
    return { data, source: 'live' }
  } catch {
    return { data: fallbackSim as unknown as SimResponse, source: 'offline' }
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

// Short display names + colours, shared by every panel.
export const STRAT_STYLE: Record<StrategyKey, { short: string; color: string }> = {
  fcfs: { short: 'Shortest line', color: 'var(--color-base)' },
  queuepilot: { short: 'QP route-on-arrival', color: 'var(--color-route)' },
  pooled: { short: 'QP pooled queue', color: 'var(--color-qp)' },
}
