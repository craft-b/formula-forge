// Canned, physically-plausible renal-safe vanilla used by the landing page so
// visitors see the real FormulaReport component — not a mockup. Numbers are
// representative display data (not engine output); the live workspace computes
// everything from the governed library.

import type { ValidatedFormula } from "@/types/api"

export const SAMPLE_FORMULA: ValidatedFormula = {
  type: "formula",
  product_name: "Renal-Safe Vanilla — Premium Scoopable",
  description:
    "Scoopable vanilla for renal-diet foodservice: potassium 178 mg and phosphorus 96 mg per serving, inside renal limits with PAC in the scoopable band.",
  product_format: "premium",
  ingredients: [
    { ref: "ing-cream-heavy", ingredient_id: "cream_heavy_36", ingredient_name: "Cream, heavy (36% fat)", percentage: 30.0, notes: "Fat structure, richness, and dryness at draw" },
    { ref: "ing-water", ingredient_id: "water", ingredient_name: "Water", percentage: 28.4, notes: "Continuous phase" },
    { ref: "ing-skim", ingredient_id: "milk_skim", ingredient_name: "Milk, nonfat / skim", percentage: 15.0, notes: "MSNF within renal phosphorus budget" },
    { ref: "ing-sucrose", ingredient_id: "sucrose", ingredient_name: "Sucrose (table sugar)", percentage: 12.0, notes: "Primary sweetener; sets POD baseline" },
    { ref: "ing-dextrose", ingredient_id: "dextrose", ingredient_name: "Dextrose", percentage: 6.0, notes: "Freezing-point control (PAC 190)" },
    { ref: "ing-smp", ingredient_id: "skim_milk_powder", ingredient_name: "Skim milk powder", percentage: 4.5, notes: "Body and protein without excess potassium" },
    { ref: "ing-coconut-oil", ingredient_id: "coconut_oil_refined", ingredient_name: "Coconut oil, refined", percentage: 3.0, notes: "Fat top-up, clean flavor release" },
    { ref: "ing-vanilla", ingredient_id: "vanilla_extract", ingredient_name: "Vanilla extract", percentage: 0.8, notes: "Added post-pasteurization" },
    { ref: "ing-guar", ingredient_id: "guar_gum", ingredient_name: "Guar gum", percentage: 0.2, notes: "Water binding; ice-crystal control" },
    { ref: "ing-monodi", ingredient_id: "mono_diglycerides", ingredient_name: "Mono- and diglycerides", percentage: 0.1, notes: "Fat destabilization for dryness" },
  ],
  composition: {
    nutrients_per_100g: {
      energy_kcal: 221, protein_g: 3.6, fat_g: 13.8, carbs_g: 22.1, sugars_g: 18.4,
      fiber_g: 0, sodium_mg: 65, potassium_mg: 187, phosphorus_mg: 101, calcium_mg: 111, water_g: 60.2,
    },
    nutrients_per_serving: {
      energy_kcal: 210, protein_g: 3.4, fat_g: 13.1, carbs_g: 21.0, sugars_g: 17.5,
      fiber_g: 0, sodium_mg: 62, potassium_mg: 178, phosphorus_mg: 96, calcium_mg: 105, water_g: 57.2,
    },
    serving_g: 95,
    overrun_pct: 80,
    product_format: "premium",
    total_solids_pct: 39.2,
    fat_pct: 13.8,
    msnf_pct: 8.1,
    sugars_pct: 16.4,
    lactose_pct: 4.6,
    stabilizer_pct: 0.3,
    pac_total: 27.5,
    pod_total: 15.2,
    scoopability_index: 86,
    total_cost_per_kg_usd: 3.85,
    allergens: ["milk"],
  },
  validation: {
    passed: true,
    violations: [],
    active_modules: ["renal"],
  },
  formulation_notes:
    "Potassium and phosphorus are held inside renal limits by capping liquid skim and shifting MSNF to skim-milk powder. Dextrose carries freezing-point depression so PAC lands mid-band (27.5) for a scoopable texture at −14 °C. Vanilla extract is dosed post-pasteurization to preserve volatiles.",
}
