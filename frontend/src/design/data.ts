// Data for the Design Studio, in the shapes of docs/BUILD.md "Contract".
// Real files (MAIN: data/design/*.json, WIN: research/design/*.json) win; the stub/ copies are
// only there so the page works before they land. Every file says whether it is a stub.

export type PlanNode = { id: number; kind: 'room' | 'corridor' | 'stair' | 'exit'; x: number; y: number; area_m2: number; people0: number; name?: string; w_m?: number; h_m?: number }
export type PlanEdge = { a: number; b: number; width_m: number; length_m: number }
export type Candidate = { id: string; node: number; attach_to: number; width_m: number; familiarity: number }
export type Fire = { id: string; start_node: number; close: { edge: number; step: number }[] }
export type Plan = {
  id: string; name: string; safe_limit_s: number; dt_s: number; max_density: number; flow_per_m_s: number
  nodes: PlanNode[]; edges: PlanEdge[]; candidates: Candidate[]; main_entrance: string; fires: Fire[]
}
export type Layout = { exits: number; clearance_s: number; worst_case_s: number; worst_fire: string | null; passes: boolean }
export type Design = {
  layouts: Layout[]; chosen: number; rule_of_thumb: number
  curve: { n_exits: number; ours_s: number; rule_s: number }[]
  bound_maxflow_s: number; min_cut: number[]; area_freed_m2: number; m2_per_exit?: number
  cost_of_panic: { calm_s: number; panic_s: number }
  frames: { chosen: number[][]; rule_of_thumb: number[][] }
  frames_fire?: string | null
}
export type ModelScore = { clearance_err_s: number; ci95: number; people_error: number }
export type Results = {
  models: { physics: ModelScore; gnn: ModelScore; pggnn: ModelScore }
  speed: { pggnn_per_s: number; simulator_per_s: number }
}
export type Recommend = {
  agreement: { top1: number; top5: number }
  candidate_value: { id: string; score: number }[]
  screened: number
  top5: { exits: number; predicted_s: number; verified_s: number }[]
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

// Which candidate exits a layout bitmask switches on.
export const exitsOf = (mask: number, p: Plan) => p.candidates.filter((_, k) => (mask >> k) & 1)
export const countExits = (mask: number) => mask.toString(2).replace(/0/g, '').length
