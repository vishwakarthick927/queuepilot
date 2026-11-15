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
  across_plans?: { n_plans: number; solved_both: number; mean_exits_ours: number | null; mean_exits_rule: number | null; plans_where_ours_needs_fewer: number; plans_where_rule_never_passes: number }
}
export type ModelScore = { clearance_err_s: number; ci95: number; people_error: number; runs?: number }
export type Results = {
  models: { physics: ModelScore; gnn: ModelScore; pggnn: ModelScore }
  speed: { pggnn_per_s: number; simulator_per_s: number }
  setup?: { test_runs?: number; unseen?: string }
}
export type Recommend = {
  agreement?: { top1: number; top5: number }
  candidate_value: { id: number; score: number }[]
  screened: number
  top5: { exits: number[]; predicted_s: number | null; verified_s: number | null }[]
}

type Loaded<T> = { data: T; stub: boolean }

// Vite bundles whichever of these files exist at build time.
const real = import.meta.glob(['../../../data/design/demo_plan.json', '../../../data/design/design.json',
  '../../../research/design/results.json', '../../../research/design/recommend.json'], { eager: true, import: 'default' })
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

// Exits are labelled by their name in the plan ("Exit A" -> "A"), the same names MAIN's files use.
export const exitLabel = (id: number) => {
  const c = plan?.data.candidates.find(x => x.id === id)
  return (c && plan?.data.nodes[c.node]?.name?.replace(/^Exit\s*/, '')) || `E${id + 1}`
}
export const labelList = (ids: number[]) => ids.map(exitLabel).join(' ')
// "fire blocks exit 0" -> "fire blocks exit A"
export const nameScenario = (s?: string) => s?.replace(/exit (\d+)/, (_, d) => `exit ${exitLabel(Number(d))}`)
