// Every number on screen comes from MAIN's simulated venue files in data/crowd (made by `python -m engine.crowd`).
// Field list: docs/STAMPEDE.md. Nothing here is typed in by hand.

export type Zone = { id: number; name: string; kind: 'source' | 'zone' | 'gate'; x: number; y: number; w: number; h: number; area_m2: number }
export type Link = { a: number; b: number; width_m: number; gate: number | null }
export type Gate = { id: number; name: string; zone: number; open_at_start: boolean; known_to_crowd: number }
export type Run = {
  density: number[][]   // [frame][zone], people per m²
  people: number[][]    // [frame][zone]
  through: number[]     // [frame] people through the gates so far
  worst: number[]       // [frame] highest density anywhere
  peak_density: number
  danger_person_min: number
}
export type Action = { id: string; label: string; kind: string; alone_peak_density: number; chosen: boolean }
export type Venue = {
  id: string
  name: string
  place: string
  note: string
  inspired_by: { event: string; date: string; toll: string; what: string }
  total_people: number
  danger_density: number
  max_density: number
  frame_s: number
  minutes: number
  zones: Zone[]
  links: Link[]
  gates: Gate[]
  today: Run & { danger_at_min: number; worst_zone: string }
  with_queuepilot: Run & { actions: string[]; stays_below_danger: boolean }
  forecast: {
    alarm_at_min: number
    predicted_danger_at_min: number
    warning_min: number
    textbook_warning: string
    hidden_problem: { gate: string; true_share_of_design_flow: number; learned_share: number }
  }
  actions: Action[]
  announcement: { en: string; hi: string }
}

const files = import.meta.glob('../../data/crowd/*.json', { eager: true, import: 'default' }) as Record<string, unknown>
const index = files['../../data/crowd/index.json'] as { id: string; file: string }[]

// Venues in the order MAIN listed them in index.json.
export const VENUES: Venue[] = index.map((v) => files[`../../data/crowd/${v.file}`] as Venue)

// Short tab names for the top bar.
export const TAB: Record<string, string> = { stadium: 'Stadium', temple: 'Temple', station: 'Station', ghat: 'Riverbank' }

export const minutesAt = (v: Venue, frame: number) => (frame * v.frame_s) / 60
export const frameAt = (v: Venue, min: number) => (min * 60) / v.frame_s
export const lastFrame = (v: Venue) => v.today.worst.length - 1

// Density of every zone at a fractional frame (linear between saved frames, so playback is smooth).
export function densityAt(run: Run, f: number): number[] {
  const i = Math.max(0, Math.min(run.density.length - 1, Math.floor(f)))
  const j = Math.min(run.density.length - 1, i + 1)
  const k = f - i
  return run.density[i].map((d, z) => d + (run.density[j][z] - d) * k)
}

export const fmt1 = (x: number) => x.toFixed(1)

// ---------------------------------------------------------------- version 2: the plaza grid and the two models
export type Plaza = {
  height: number; width: number; cell_m: number; frame_s: number; danger_density: number; max_density: number
  total_people: number; gate: number[][]; clutter: number[][]; passability_true: number[][]
  truth: { density: number[][][]; peak_density: number; danger_cells: number }
  textbook: { density: number[][][]; peak_density: number; danger_cells: number }
  danger_cells_textbook_misses: number
}
export const PLAZA = files['../../data/crowd/plaza_demo.json'] as Plaza

// Model results (WIN research/live). A file that is not there yet means that model is still training: show no numbers.
const results = import.meta.glob('../../research/live/*.json', { eager: true, import: 'default' }) as Record<string, unknown>
export type PgcnnResult = {
  models: Record<'physics' | 'cnn' | 'pgcnn', { density_error: number; people_created: number; danger_cells_true: number; danger_cells_found: number; danger_cells_missed: number; false_alarm_cells: number; plazas: number }>
  passability_error: { site_plan: number; pgcnn: number }
  setup: { train_plazas: number; test_plazas: number }
}
export type PgcnnDemo = { density: number[][][]; peak_density: number; danger_cells: number; passability: number[][]; textbook_missed_cells_we_catch: number; textbook_missed_cells: number }
export type PggnnResult = {
  models: Record<'physics' | 'gnn' | 'pggnn', { peak_density_err: number; peak_ci95: number; danger_start_err_min: number; danger_yes_no_agree_pct: number; people_created_or_lost: number; runs: number }>
  setup: { train_runs: number; test_runs: number; unseen: string }
}
export type PggnnDemo = { venues: Record<string, { worst: number[]; danger_at_min: number | null; peak_density: number }> }
export const PGCNN = results['../../research/live/pgcnn_plaza.json'] as PgcnnResult | undefined
export const PGCNN_DEMO = results['../../research/live/pgcnn_plaza_demo.json'] as PgcnnDemo | undefined
export const PGGNN = results['../../research/live/pggnn_venue.json'] as PggnnResult | undefined
export const PGGNN_DEMO = results['../../research/live/pggnn_venue_demo.json'] as PggnnDemo | undefined
