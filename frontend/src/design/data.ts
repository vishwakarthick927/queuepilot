// Data for the Design Studio. Shapes = what MAIN's engine/design.py and our research/design/*.py write.
// Real files (data/design/*.json, research/design/*.json) win; the stub/ copies are only there so the
// page works before they land. Every file says whether it is a stub, and the page shows a badge.

export type PlanNode = { id: number; kind: 'room' | 'corridor' | 'stair' | 'exit'; x: number; y: number; area_m2: number; people0: number; name?: string }
export type PlanEdge = { a: number; b: number; width_m: number; length_m: number; candidate: number | null }
export type Candidate = { id: number; node: number; attach_to: number; width_m: number; familiarity: number }
export type Fire = { id: number; start_node: number; close: { edge: number; step: number }[] }
export type Plan = {
  id: string; name: string; safe_limit_s: number; dt_s: number; max_density: number; flow_per_m_s: number
  walk_speed_m_s: number; max_travel_m: number
  nodes: PlanNode[]; edges: PlanEdge[]; candidates: Candidate[]; main_entrance: number; fires: Fire[]
  smoke_fires?: Fire[]                 // fires whose blocked corridors come from the smoke model (engine/smoke.py)
}

// One scored layout (engine.design.score). worst_case_s null = somebody never got out.
export type Score = { exits: number[]; clearance_s: number | null; worst_case_s: number | null; worst_fire: string | null; passes: boolean; code_ok: boolean; max_travel_m: number | null }
export type CurvePoint = { n_exits: number; ours_s: number | null; ours_passes: boolean; rule_s: number | null; rule_passes: boolean }
export type PanicResult = {
  panic: number; chosen: Score | null; chosen_n_exits: number | null; rule_of_thumb: Score | null; rule_n_exits: number | null
  rule_same_count: Score | null; exits_saved: number | null; area_freed_m2: number | null; curve: CurvePoint[]; layouts: Score[]
}
export type Frames = { exits: number[]; scenario?: string; lost_exit?: number | null; fire: number | null; panic: number; clearance_s: number | null; people: number[][]; evacuated: number[]; exit_use: Record<string, number> }
export type Design = {
  plan: string; safe_limit_s: number; design_panic: number; panic_levels: number[]; exit_core_m2: number
  chosen: Score | null; rule_of_thumb: Score | null; by_panic: Record<string, PanicResult>
  bound_maxflow_s: number | null; min_cut: number[]; maxflow_rate_per_s: number
  cost_of_panic: { calm_s: number | null; panic_s: number | null }
  frames: { chosen: Frames; rule_of_thumb: Frames }
  frames_scenario?: string; frames_fire?: number | null; m2_per_exit?: number
  frames_smoke?: Record<string, { chosen: Frames; rule_of_thumb: Frames }>
  smoke_check?: { fewest_ours: number | null; fewest_rule: number | null }
  across_plans?: { n_plans: number; solved_both: number; mean_exits_ours: number | null; mean_exits_rule: number | null; plans_where_ours_needs_fewer: number; plans_where_rule_never_passes: number }
}
export type ModelScore = { clearance_err_s: number; ci95: number; people_error: number; runs?: number }
export type Results = {
  models: { physics: ModelScore; gnn: ModelScore; pggnn: ModelScore }
  speed: { pggnn_per_s: number; simulator_per_s: number }
  setup?: { test_runs?: number; unseen?: string }
  // one row per fix of the PG-GNN (MAIN's review), same test: what each fix changed
  ablation?: { label: string; clearance_err_s: number; ci95: number }[]
}
export type Recommend = {
  agreement?: { top1: number; top5: number; exit_counts?: number[] }
  agreement_physics_only?: { top1: number; top5: number }
  screen_seconds?: number
  fewest_exits?: number | null
  candidate_value: { id: number; score: number }[]
  screened: number
  top5: { exits: number[]; predicted_s: number | null; verified_s: number | null }[]
}

type Loaded<T> = { data: T; stub: boolean }

// Vite bundles whichever of these files exist at build time.
const real = import.meta.glob(['../../../data/design/demo_plan.json', '../../../data/design/design.json', '../../../data/design/smoke_demo.json',
  '../../../research/design/results.json', '../../../research/design/recommend.json',
  '../../../research/design/pgcnn_results.json', '../../../research/design/pgcnn_demo.json'], { eager: true, import: 'default' })
const stub = import.meta.glob('./stub/*.json', { eager: true, import: 'default' })

function pick<T>(name: string): Loaded<T> | null {
  const r = Object.entries(real).find(([k]) => k.endsWith('/' + name))
  if (r) return { data: r[1] as T, stub: false }
  const s = stub['./stub/' + name]
  return s ? { data: s as T, stub: true } : null
}

export const plan = pick<Plan>('demo_plan.json')
export const design = pick<Design>('design.json')
export const results = pick<Results>('results.json')
export const recommend = pick<Recommend>('recommend.json')

// Smoke (the PG-CNN's side). smoke_demo.json = MAIN's simulator; pgcnn_demo.json = what our PG-CNN predicts.
export type SmokeFire = { fire: number; start_node: number; close: { edge: number; step: number }[]; close_textbook?: { edge: number; step: number }[]; smoke: number[][][] }
export type SmokeDemo = { cell_m: number; sub: number; frame_every_steps: number; block_level: number; origin_tile: [number, number]; fires: SmokeFire[] }
export type CnnScore = { smoke_error: number; smoke_created: number; block_time_err_s: number; block_time_ci95: number; passages?: number; fires?: number }
export type CnnResults = { models: { physics: CnnScore; cnn: CnnScore; pgcnn: CnnScore }; vent_error?: { textbook: number; pgcnn: number }; setup?: { test_fires?: number } }
export const smokeDemo = pick<SmokeDemo>('smoke_demo.json')

// Building switcher (round 6): data/design/buildings.json lists each building's plan, design and smoke files.
export type BuildingEntry = { id: string; name: string; building: string; people: number; plan: string; design: string; smoke: string }
export type Building = { id: string; name: string; plan: Plan; design: Design; smoke: SmokeDemo | null }
const files = import.meta.glob(['../../../data/design/buildings.json', '../../../data/design/demo_plan.json', '../../../data/design/design.json',
  '../../../data/design/smoke_demo.json', '../../../data/design/buildings/*/*.json'], { eager: true, import: 'default' })
const file = (rel: string) => files['../../../data/design/' + rel]
export const buildings: Building[] = ((file('buildings.json') as BuildingEntry[] | undefined) ?? [])
  .filter(b => file(b.plan) && file(b.design))
  .map(b => ({ id: b.id, name: b.name, plan: file(b.plan) as Plan, design: file(b.design) as Design, smoke: (file(b.smoke) as SmokeDemo) ?? null }))
export const cnnResults = pick<CnnResults>('pgcnn_results.json')
export const cnnDemo = pick<{ fires: SmokeFire[] }>('pgcnn_demo.json')

// Exits are labelled by their name in the plan ("Exit A" -> "A"), the same names MAIN's files use.
export const exitLabel = (id: number) => {
  const c = plan?.data.candidates.find(x => x.id === id)
  return (c && plan?.data.nodes[c.node]?.name?.replace(/^Exit\s*/, '')) || `E${id + 1}`
}
export const labelList = (ids: number[]) => ids.map(exitLabel).join(' ')
// "fire blocks exit 0" -> "fire blocks exit A"
export const nameScenario = (s?: string) => s?.replace(/exit (\d+)/, (_, d) => `exit ${exitLabel(Number(d))}`)
