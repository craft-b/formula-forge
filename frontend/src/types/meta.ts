// Shape of GET /api/meta (backend/main.py::meta). Hand-maintained — this is an
// API envelope, not a domain model, so it's not covered by gen_frontend_types.
export interface ModuleInfo {
  id: string
  label: string
  stub: boolean
  requires_professional_review: boolean
}

export interface WorkspaceMeta {
  dataset_version: string
  ingredient_count: number
  modules: ModuleInfo[]
  model: string
}
