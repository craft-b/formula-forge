// The formula "lab report" — the verification surface, structured like a
// document an R&D reviewer would read: identity → compliance → composition →
// physics → nutrition → ingredients → notes. Every number is provenance-labeled
// (✓ rule-verified / ~ model-estimated).

import { Markdown } from "@/lib/markdown"
import type { RejectedFormula, ValidatedFormula } from "@/types/api"
import {
  BulletBand,
  COMPOSITION_COLORS,
  CompositionBar,
  LimitRow,
  StatTile,
  StatusPill,
} from "./viz"

// Mirrors backend/domain/constants.py bands (single place to update in the UI).
const PAC_BAND = { lo: 22, hi: 34, domainLo: 0, domainHi: 50 }
const POD_BAND = { lo: 12, hi: 18, domainLo: 0, domainHi: 30 }

function ruleName(ruleId: string): string {
  const pretty: Record<string, string> = {
    "renal.phosphorus": "Renal · phosphorus",
    "renal.potassium": "Renal · potassium",
    "renal.sodium": "Renal · sodium",
    "diabetic.sugars": "Diabetic · total sugars",
    "high_protein.protein": "High-protein · protein floor",
    "low_fat.fat": "Low-fat · fat ceiling",
    "physical.total_solids": "Physics · total solids",
    "physical.fat": "Physics · fat",
    "physical.msnf": "Physics · MSNF",
    "physical.pac": "Physics · PAC (freezing)",
    "physical.pod": "Physics · POD (sweetness)",
    "physical.stabilizer": "Physics · stabilizer",
    "physical.lactose_sandiness": "Physics · lactose (sandiness)",
    "dysphagia_iddsi.stub": "Dysphagia / IDDSI",
  }
  if (pretty[ruleId]) return pretty[ruleId]
  if (ruleId.endsWith(".blacklist")) return "Ingredient not permitted"
  if (ruleId.includes(".allergen.")) return `Allergen · ${ruleId.split(".").pop()}`
  return ruleId
}

export function FormulaReport({ formula }: { formula: ValidatedFormula }) {
  const { composition: c, validation: val } = formula
  const passed = val.passed
  const violations = val.violations ?? []
  const errors = violations.filter((v) => v.severity === "error")
  const warnings = violations.filter((v) => v.severity === "warn")
  const ns = c.nutrients_per_serving

  const otherSolids = Math.max(
    c.total_solids_pct - c.fat_pct - c.msnf_pct - c.sugars_pct,
    0
  )
  const water = Math.max(100 - c.total_solids_pct, 0)

  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-[0_1px_3px_rgba(15,23,42,0.06)] overflow-hidden">
      {/* ── Identity band ── */}
      <div className="px-6 pt-5 pb-4 border-b border-slate-100">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-[10px] font-semibold tracking-[0.14em] text-slate-400 uppercase">
                Formula report
              </span>
              <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 capitalize">
                {c.product_format.replace("_", " ")}
              </span>
              {(val.active_modules ?? []).map((m) => (
                <span
                  key={m}
                  className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-100"
                >
                  {m.replace("_", " ")}
                </span>
              ))}
            </div>
            <h3 className="text-xl font-semibold text-slate-900 mt-1.5 leading-snug">
              {formula.product_name}
            </h3>
            {formula.description && (
              <p className="text-sm text-slate-500 mt-1 leading-relaxed max-w-2xl">
                {formula.description}
              </p>
            )}
          </div>
          <div className="flex flex-col items-end gap-1.5 shrink-0">
            <StatusPill ok={passed}>{passed ? "Compliant" : "Flagged"}</StatusPill>
            <span className="text-[10px] text-slate-400">
              <span className="text-teal-600">✓</span> rule-verified ·{" "}
              <span className="text-amber-600">~</span> model-estimated
            </span>
          </div>
        </div>
      </div>

      <div className="px-6 py-5 space-y-6">
        {/* ── Compliance ── */}
        {(errors.length > 0 || warnings.length > 0) && (
          <section>
            <h4 className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-2.5">
              Validation — {passed ? "passed with advisories" : `${errors.length} compliance failure${errors.length === 1 ? "" : "s"}`}
            </h4>
            <div className="space-y-1.5">
              {errors.map((v, i) => (
                <LimitRow key={`e${i}`} name={ruleName(v.rule_id)} explanation={v.explanation}
                          measured={v.measured} limit={v.limit} severity="error" />
              ))}
              {warnings.map((v, i) => (
                <LimitRow key={`w${i}`} name={ruleName(v.rule_id)} explanation={v.explanation}
                          measured={v.measured} limit={v.limit} severity="warn" />
              ))}
            </div>
            {val.repaired && (
              <p className="text-[11px] text-slate-400 mt-2">
                Ingredient percentages were normalized to sum to 100%.
              </p>
            )}
          </section>
        )}
        {passed && violations.length === 0 && (
          <section className="rounded-lg bg-teal-50/60 border border-teal-100 px-3.5 py-2.5">
            <span className="text-xs text-teal-700 font-medium">
              ✓ All physical-plausibility and compliance checks passed.
            </span>
          </section>
        )}

        {/* ── Mix composition ── */}
        <section>
          <h4 className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-2.5">
            Mix composition <span className="normal-case tracking-normal">· total solids {c.total_solids_pct.toFixed(1)}%</span>
          </h4>
          <CompositionBar
            segments={[
              { key: "fat", label: "Fat", value: c.fat_pct, color: COMPOSITION_COLORS.fat },
              { key: "msnf", label: "MSNF", value: c.msnf_pct, color: COMPOSITION_COLORS.msnf },
              { key: "sugars", label: "Sugars", value: c.sugars_pct, color: COMPOSITION_COLORS.sugars },
              { key: "other", label: "Other solids", value: otherSolids, color: COMPOSITION_COLORS.other },
              { key: "water", label: "Water", value: water, color: COMPOSITION_COLORS.water },
            ]}
          />
        </section>

        {/* ── Freezing & sweetness physics ── */}
        <section className="grid sm:grid-cols-2 gap-x-8 gap-y-4">
          <BulletBand
            label="PAC — freezing-point depression"
            value={c.pac_total}
            bandLo={PAC_BAND.lo} bandHi={PAC_BAND.hi}
            domainLo={PAC_BAND.domainLo} domainHi={PAC_BAND.domainHi}
            caption="Below band freezes hard (brick); above band stays soft and weepy."
          />
          <BulletBand
            label="POD — relative sweetness"
            value={c.pod_total}
            bandLo={POD_BAND.lo} bandHi={POD_BAND.hi}
            domainLo={POD_BAND.domainLo} domainHi={POD_BAND.domainHi}
            caption="Sucrose-equivalent sweetness of the finished mix."
          />
        </section>

        {/* ── Nutrition per serving ── */}
        <section>
          <h4 className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-2.5">
            Nutrition per serving <span className="normal-case tracking-normal">· {c.serving_g} g mix · {c.overrun_pct}% overrun</span>
          </h4>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <StatTile label="Energy" value={Math.round(ns.energy_kcal)} unit="kcal" estimated={false} />
            <StatTile label="Protein" value={ns.protein_g.toFixed(1)} unit="g" estimated={false} />
            <StatTile label="Fat" value={ns.fat_g.toFixed(1)} unit="g" estimated={false} />
            <StatTile label="Sugars" value={ns.sugars_g.toFixed(1)} unit="g" estimated={false} />
            <StatTile label="Sodium" value={Math.round(ns.sodium_mg)} unit="mg" estimated={false} />
            <StatTile label="Potassium" value={Math.round(ns.potassium_mg)} unit="mg" estimated={false} />
            <StatTile label="Phosphorus" value={Math.round(ns.phosphorus_mg)} unit="mg" estimated={false} />
            <StatTile label="Scoopability" value={c.scoopability_index.toFixed(0)} unit="/100" estimated
                      hint="Model-estimated index from PAC distance to the scoopable band" />
          </div>
        </section>

        {/* ── Ingredients table ── */}
        <section>
          <h4 className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-2">
            Ingredients <span className="normal-case tracking-normal">· est. ${c.total_cost_per_kg_usd.toFixed(2)}/kg</span>
            {c.allergens.length > 0 && (
              <span className="normal-case tracking-normal"> · allergens: {c.allergens.join(", ")}</span>
            )}
          </h4>
          <table className="w-full text-sm">
            <tbody>
              {formula.ingredients.map((ing, i) => (
                <tr key={i} className="border-t border-slate-100 first:border-0">
                  <td className="py-2 pr-3 text-slate-800">{ing.ingredient_name}</td>
                  <td className="py-2 pr-3 text-right font-semibold text-slate-900 tabular-nums w-16">
                    {ing.percentage.toFixed(1)}%
                  </td>
                  <td className="py-2 text-[11px] text-slate-400 leading-snug hidden sm:table-cell">
                    {ing.notes}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        {/* ── Notes ── */}
        {formula.formulation_notes && (
          <section className="rounded-xl bg-slate-50 border border-slate-100 px-4 py-3">
            <h4 className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1.5">
              Formulation notes
            </h4>
            <div className="text-[13px] text-slate-600 leading-relaxed">
              <Markdown text={formula.formulation_notes} />
            </div>
          </section>
        )}
      </div>
    </div>
  )
}

export function RejectionReport({ rejection }: { rejection: RejectedFormula }) {
  return (
    <div className="rounded-2xl border border-red-200 bg-white overflow-hidden">
      <div className="px-6 py-4 bg-red-50/70 border-b border-red-100">
        <div className="flex items-center justify-between gap-3">
          <div>
            <span className="text-[10px] font-semibold tracking-[0.14em] text-red-400 uppercase">
              Verification failed
            </span>
            <h3 className="text-base font-semibold text-red-900 mt-0.5">{rejection.product_name}</h3>
          </div>
          <StatusPill ok={false}>Rejected</StatusPill>
        </div>
      </div>
      <div className="px-6 py-4 space-y-2">
        <p className="text-sm text-red-800">{rejection.reason}</p>
        {(rejection.unresolved_ingredients ?? []).length > 0 && (
          <p className="text-xs text-red-600">
            Not in the governed library: {rejection.unresolved_ingredients!.join(", ")}
          </p>
        )}
        {(rejection.violations ?? []).map((v, i) => (
          <LimitRow key={i} name={ruleName(v.rule_id)} explanation={v.explanation}
                    measured={v.measured} limit={v.limit} severity={v.severity} />
        ))}
      </div>
    </div>
  )
}
