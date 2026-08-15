// GENERATED FROM backend/domain/models.py — DO NOT EDIT BY HAND.
// Regenerate: cd backend && python -m scripts.gen_frontend_types

export interface NutrientVector {
  energy_kcal: number;
  protein_g: number;
  fat_g: number;
  carbs_g: number;
  sugars_g: number;
  fiber_g: number;
  sodium_mg: number;
  potassium_mg: number;
  phosphorus_mg: number;
  calcium_mg: number;
  water_g: number;
}

export interface ResolvedLine {
  ref: string;
  ingredient_id: string;
  ingredient_name: string;
  percentage: number;
  notes?: string;
}

export interface Violation {
  rule_id: string;
  severity: "error" | "warn";
  measured?: number | null;
  limit?: number | null;
  explanation: string;
}

export interface ValidationReport {
  passed: boolean;
  repaired?: boolean;
  violations?: Violation[];
  active_modules?: string[];
}

export interface ComputedComposition {
  nutrients_per_100g: NutrientVector;
  nutrients_per_serving: NutrientVector;
  serving_g: number;
  overrun_pct: number;
  product_format: string;
  total_solids_pct: number;
  fat_pct: number;
  msnf_pct: number;
  sugars_pct: number;
  lactose_pct: number;
  stabilizer_pct: number;
  pac_total: number;
  pod_total: number;
  scoopability_index: number;
  total_cost_per_kg_usd: number;
  allergens: string[];
}

export interface ValidatedFormula {
  type?: "formula";
  product_name: string;
  description?: string;
  product_format: string;
  ingredients: ResolvedLine[];
  composition: ComputedComposition;
  validation: ValidationReport;
  formulation_notes?: string;
  verified_fields?: string[];
  estimated_fields?: string[];
  process_dependent_fields?: string[];
  notes_contain_numeric_claims?: boolean;
}

export interface RejectedFormula {
  type?: "rejection";
  product_name: string;
  reason: string;
  violations?: Violation[];
  unresolved_ingredients?: string[];
}

// ── Server-sent event envelope (matches backend/main.py _stream_agent) ─────────
export interface TokenEvent { type: "token"; content: string; }
export interface FormulaEvent { type: "formula"; formula: ValidatedFormula; response: string; }
export interface RejectionEvent { type: "rejection"; rejection: RejectedFormula; response: string; }
export interface ErrorEvent { type: "error"; message: string; }
export interface DoneEvent { type: "done"; session_id: string; }
export type SSEEvent = TokenEvent | FormulaEvent | RejectionEvent | ErrorEvent | DoneEvent;
