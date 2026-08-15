// The formula "lab report" — the verification surface, structured like a
// document an R&D reviewer would read: identity → compliance → composition →
// physics → nutrition → ingredients → notes. Every number is provenance-labeled
// (✓ rule-verified / ~ model-estimated). Report actions (copy JSON / print)
// make it a shareable artifact, not just a chat reply.

import { useState } from "react"
import { Check, Copy, Download, Printer } from "lucide-react"
import { Markdown } from "@/lib/markdown"
import { FormulaDiff } from "./FormulaDiff"
import { ProcessMethod } from "./ProcessMethod"
import type { NutrientVector, RejectedFormula, ValidatedFormula } from "@/types/api"
import {
  BulletBand,
  COMPOSITION_COLORS,
  CompositionBar,
  InlineBar,
  LimitRow,
  SectionTitle,
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

// Full panel rows for the progressive-disclosure nutrient table.
const NUTRIENT_ROWS: { key: keyof NutrientVector; label: string; unit: string; digits: number }[] = [
  { key: "energy_kcal", label: "Energy", unit: "kcal", digits: 0 },
  { key: "protein_g", label: "Protein", unit: "g", digits: 1 },
  { key: "fat_g", label: "Fat", unit: "g", digits: 1 },
  { key: "carbs_g", label: "Carbohydrate", unit: "g", digits: 1 },
  { key: "sugars_g", label: "Total sugars", unit: "g", digits: 1 },
  { key: "fiber_g", label: "Fiber", unit: "g", digits: 1 },
  { key: "sodium_mg", label: "Sodium", unit: "mg", digits: 0 },
  { key: "potassium_mg", label: "Potassium", unit: "mg", digits: 0 },
  { key: "phosphorus_mg", label: "Phosphorus", unit: "mg", digits: 0 },
  { key: "calcium_mg", label: "Calcium", unit: "mg", digits: 0 },
  { key: "water_g", label: "Water", unit: "g", digits: 1 },
]

// Batch-sheet math — pure conversion from verified percentages, so it carries
// rule-verified trust. 10 kg default ≈ pilot-plant scale.
const BATCH_SIZES = [1, 10, 100]

function gramsFor(pct: number, batchKg: number): string {
  const g = (pct / 100) * batchKg * 1000
  if (g >= 100) return g.toLocaleString(undefined, { maximumFractionDigits: 0 })
  return g.toFixed(1)
}

function downloadBatchCsv(formula: ValidatedFormula, batchKg: number) {
  const sorted = [...formula.ingredients].sort((a, b) => b.percentage - a.percentage)
  const rows = [
    ["Ingredient", "% w/w", `g per ${batchKg} kg batch`, "Function"],
    ...sorted.map((i) => [
      i.ingredient_name,
      i.percentage.toFixed(2),
      ((i.percentage / 100) * batchKg * 1000).toFixed(1),
      i.notes ?? "",
    ]),
    ["Total", sorted.reduce((s, i) => s + i.percentage, 0).toFixed(2), (batchKg * 1000).toFixed(0), ""],
  ]
  const csv = rows.map((r) => r.map((f) => `"${String(f).replace(/"/g, '""')}"`).join(",")).join("\r\n")
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = `${formula.product_name.replace(/[^\w-]+/g, "_").toLowerCase()}_batch_${batchKg}kg.csv`
  a.click()
  URL.revokeObjectURL(url)
}

function ReportActions({ formula }: { formula: ValidatedFormula }) {
  const [copied, setCopied] = useState(false)

  async function copyJson() {
    try {
      await navigator.clipboard.writeText(JSON.stringify(formula, null, 2))
      setCopied(true)
      setTimeout(() => setCopied(false), 1600)
    } catch {
      /* clipboard unavailable (permissions/insecure context) — leave state as-is */
    }
  }

  const btn =
    "inline-flex items-center gap-1.5 text-meta font-medium text-slate-600 hover:text-slate-800 px-2 py-1 rounded-md hover:bg-slate-100 transition-colors"

  return (
    <div className="flex items-center gap-0.5 print-hide" aria-label="Report actions">
      <button onClick={() => void copyJson()} className={btn} title="Copy the full validated formula as JSON">
        {copied ? <Check className="w-3.5 h-3.5 text-teal-600" /> : <Copy className="w-3.5 h-3.5" />}
        {copied ? "Copied" : "Copy JSON"}
      </button>
      <button onClick={() => window.print()} className={btn} title="Print or save the report as PDF">
        <Printer className="w-3.5 h-3.5" />
        Export
      </button>
    </div>
  )
}

export function FormulaReport({
  formula,
  version,
  previous,
}: {
  formula: ValidatedFormula
  version?: number
  previous?: ValidatedFormula | null
}) {
  const { composition: c, validation: val } = formula
  const passed = val.passed
  const violations = val.violations ?? []
  const errors = violations.filter((v) => v.severity === "error")
  const warnings = violations.filter((v) => v.severity === "warn")

  const [basis, setBasis] = useState<"serving" | "per100">("serving")
  const [fullPanel, setFullPanel] = useState(false)
  const [batchKg, setBatchKg] = useState(10)
  const nv = basis === "serving" ? c.nutrients_per_serving : c.nutrients_per_100g
  const sortedIngredients = [...formula.ingredients].sort((a, b) => b.percentage - a.percentage)
  const totalPct = formula.ingredients.reduce((s, i) => s + i.percentage, 0)

  const otherSolids = Math.max(
    c.total_solids_pct - c.fat_pct - c.msnf_pct - c.sugars_pct,
    0
  )
  const water = Math.max(100 - c.total_solids_pct, 0)
  const maxIngredient = Math.max(...formula.ingredients.map((i) => i.percentage), 1)

  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-[0_1px_3px_rgba(15,23,42,0.06)] overflow-hidden ff-rise print-block">
      {/* ── Identity band ── */}
      <div className="px-6 pt-5 pb-4 border-b border-slate-100">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-micro font-semibold tracking-[0.14em] text-slate-500 uppercase">
                Formula report
              </span>
              {version != null && (
                <span className="num text-micro font-semibold px-1.5 py-0.5 rounded-full bg-slate-900 text-white">
                  v{version}
                </span>
              )}
              <span className="text-micro font-medium px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 capitalize">
                {c.product_format.replace("_", " ")}
              </span>
              {(val.active_modules ?? []).map((m) => (
                <span
                  key={m}
                  className="text-micro font-medium px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-100 capitalize"
                >
                  {m.replace("_", " ")}
                </span>
              ))}
            </div>
            <h3 className="font-heading text-[1.35rem] font-semibold text-slate-900 mt-1.5 leading-snug tracking-[-0.01em]">
              {formula.product_name}
            </h3>
            {formula.description && (
              <p className="text-sm text-slate-500 mt-1 leading-relaxed max-w-2xl">
                {formula.description}
              </p>
            )}
          </div>
          <div className="flex flex-col items-end gap-1.5 shrink-0">
            <div className="flex items-center gap-2">
              <ReportActions formula={formula} />
              <StatusPill ok={passed}>{passed ? "Compliant" : "Flagged"}</StatusPill>
            </div>
            <span className="text-micro text-slate-500">
              <span className="text-teal-700">✓</span> rule-verified ·{" "}
              <span className="text-amber-700">~</span> model-estimated
            </span>
          </div>
        </div>
      </div>

      <div className="px-6 py-5 space-y-6">
        {/* ── What changed vs the previous iteration ── */}
        {previous && version != null && (
          <div className="ff-rise ff-rise-1">
            <FormulaDiff previous={previous} current={formula} fromVersion={version - 1} />
          </div>
        )}

        {/* ── Compliance ── */}
        {(errors.length > 0 || warnings.length > 0) && (
          <section className="ff-rise ff-rise-1">
            <SectionTitle>
              Validation — {passed ? "passed with advisories" : `${errors.length} compliance failure${errors.length === 1 ? "" : "s"}`}
            </SectionTitle>
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
              <p className="text-meta text-slate-500 mt-2">
                Ingredient percentages were normalized to sum to 100%.
              </p>
            )}
          </section>
        )}
        {passed && violations.length === 0 && (
          <section className="rounded-lg bg-teal-50/60 border border-teal-100 px-3.5 py-2.5 ff-rise ff-rise-1">
            <span className="text-xs text-teal-700 font-medium">
              ✓ All physical-plausibility and compliance checks passed.
            </span>
          </section>
        )}

        {/* ── Mix composition ── */}
        <section className="ff-rise ff-rise-2">
          <SectionTitle meta={<>· total solids <span className="num">{c.total_solids_pct.toFixed(1)}%</span></>}>
            Mix composition
          </SectionTitle>
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
        <section className="grid sm:grid-cols-2 gap-x-8 gap-y-4 ff-rise ff-rise-2">
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

        {/* ── Nutrition ── */}
        <section className="ff-rise ff-rise-3">
          <div className="flex items-baseline justify-between gap-3 flex-wrap">
            <SectionTitle
              meta={
                basis === "serving"
                  ? <>· <span className="num">{c.serving_g} g</span> mix · <span className="num">{c.overrun_pct}%</span> overrun</>
                  : <>· unfrozen mix basis</>
              }
            >
              Nutrition {basis === "serving" ? "per serving" : "per 100 g"}
            </SectionTitle>
            {/* Basis toggle */}
            <div
              role="tablist"
              aria-label="Nutrition basis"
              className="inline-flex rounded-lg border border-slate-200 p-0.5 bg-slate-50 print-hide"
            >
              {([["serving", "Per serving"], ["per100", "Per 100 g"]] as const).map(([id, label]) => (
                <button
                  key={id}
                  role="tab"
                  aria-selected={basis === id}
                  onClick={() => setBasis(id)}
                  className={`px-2.5 py-1 text-meta font-medium rounded-md transition-colors ${
                    basis === id ? "bg-white text-slate-800 shadow-sm border border-slate-200" : "text-slate-500 hover:text-slate-700"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <StatTile label="Energy" value={Math.round(nv.energy_kcal)} unit="kcal" estimated={false} />
            <StatTile label="Protein" value={nv.protein_g.toFixed(1)} unit="g" estimated={false} />
            <StatTile label="Fat" value={nv.fat_g.toFixed(1)} unit="g" estimated={false} />
            <StatTile label="Sugars" value={nv.sugars_g.toFixed(1)} unit="g" estimated={false} />
            <StatTile label="Sodium" value={Math.round(nv.sodium_mg)} unit="mg" estimated={false} />
            <StatTile label="Potassium" value={Math.round(nv.potassium_mg)} unit="mg" estimated={false} />
            <StatTile label="Phosphorus" value={Math.round(nv.phosphorus_mg)} unit="mg" estimated={false} />
            <StatTile label="Scoopability" value={c.scoopability_index.toFixed(0)} unit="/100" estimated
                      hint="Model-estimated index from PAC distance to the scoopable band" />
          </div>
          {/* Progressive disclosure: full nutrient panel */}
          <button
            onClick={() => setFullPanel((v) => !v)}
            aria-expanded={fullPanel}
            className="mt-2 text-meta font-medium text-slate-600 hover:text-slate-700 transition-colors print-hide"
          >
            {fullPanel ? "− Hide full nutrient panel" : "+ Full nutrient panel"}
          </button>
          {fullPanel && (
            <table className="w-full text-sm mt-1 ff-rise">
              <thead>
                <tr className="text-micro uppercase tracking-[0.08em] text-slate-500">
                  <th className="text-left font-semibold py-1.5">Nutrient</th>
                  <th className="text-right font-semibold py-1.5">Per serving</th>
                  <th className="text-right font-semibold py-1.5">Per 100 g</th>
                </tr>
              </thead>
              <tbody>
                {NUTRIENT_ROWS.map((r) => (
                  <tr key={r.key} className="border-t border-slate-100">
                    <td className="py-1.5 pr-3 text-data text-slate-600">{r.label}</td>
                    <td className="py-1.5 text-right text-data text-slate-800 num">
                      {c.nutrients_per_serving[r.key].toFixed(r.digits)} <span className="text-slate-500">{r.unit}</span>
                    </td>
                    <td className="py-1.5 text-right text-data text-slate-800 num">
                      {c.nutrients_per_100g[r.key].toFixed(r.digits)} <span className="text-slate-500">{r.unit}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        {/* ── Batch sheet ── */}
        <section className="ff-rise ff-rise-4">
          <div className="flex items-baseline justify-between gap-3 flex-wrap">
            <SectionTitle
              meta={
                <>
                  · est. <span className="num">${c.total_cost_per_kg_usd.toFixed(2)}/kg</span>
                  {" "}(<span className="num">${(c.total_cost_per_kg_usd * batchKg).toFixed(2)}</span>/batch)
                  {c.allergens.length > 0 && <> · allergens: {c.allergens.join(", ")}</>}
                </>
              }
            >
              Batch sheet
            </SectionTitle>
            <div className="flex items-center gap-2 print-hide">
              {/* Batch size */}
              <div role="tablist" aria-label="Batch size" className="inline-flex rounded-lg border border-slate-200 p-0.5 bg-slate-50">
                {BATCH_SIZES.map((kg) => (
                  <button
                    key={kg}
                    role="tab"
                    aria-selected={batchKg === kg}
                    onClick={() => setBatchKg(kg)}
                    className={`px-2.5 py-1 text-meta font-medium rounded-md transition-colors num ${
                      batchKg === kg ? "bg-white text-slate-800 shadow-sm border border-slate-200" : "text-slate-500 hover:text-slate-700"
                    }`}
                  >
                    {kg} kg
                  </button>
                ))}
              </div>
              <button
                onClick={() => downloadBatchCsv(formula, batchKg)}
                title="Download the batch sheet as CSV"
                className="inline-flex items-center gap-1.5 text-meta font-medium text-slate-600 hover:text-slate-800 px-2 py-1 rounded-md hover:bg-slate-100 transition-colors"
              >
                <Download className="w-3.5 h-3.5" />
                CSV
              </button>
            </div>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-micro uppercase tracking-[0.08em] text-slate-500">
                <th className="text-left font-semibold pb-1.5">Ingredient</th>
                <th className="text-right font-semibold pb-1.5 w-16">% w/w</th>
                <th className="text-right font-semibold pb-1.5 w-24">
                  g / <span className="num">{batchKg}</span> kg
                </th>
                <th className="pb-1.5 w-24 hidden sm:table-cell" aria-hidden />
                <th className="text-left font-semibold pb-1.5 pl-3 hidden sm:table-cell">Function</th>
              </tr>
            </thead>
            <tbody>
              {sortedIngredients.map((ing, i) => (
                <tr key={i} className="border-t border-slate-100">
                  <td className="py-2 pr-3 text-slate-800">{ing.ingredient_name}</td>
                  <td className="py-2 text-right font-semibold text-slate-900 num">
                    {ing.percentage.toFixed(2)}%
                  </td>
                  <td className="py-2 text-right text-slate-700 num">
                    {gramsFor(ing.percentage, batchKg)}
                  </td>
                  <td className="py-2 pl-3 hidden sm:table-cell align-middle">
                    <InlineBar value={ing.percentage} max={maxIngredient} />
                  </td>
                  <td className="py-2 pl-3 text-meta text-slate-400 italic leading-snug hidden sm:table-cell">
                    {ing.notes}
                  </td>
                </tr>
              ))}
              <tr className="border-t-2 border-slate-200">
                <td className="py-2 pr-3 text-meta font-semibold uppercase tracking-[0.08em] text-slate-500">Total</td>
                <td className="py-2 text-right font-semibold text-slate-900 num">{totalPct.toFixed(2)}%</td>
                <td className="py-2 text-right font-semibold text-slate-900 num">{(batchKg * 1000).toLocaleString()}</td>
                <td className="hidden sm:table-cell" />
                <td className="hidden sm:table-cell" />
              </tr>
            </tbody>
          </table>
        </section>

        {/* ── Process method ── */}
        <div className="ff-rise ff-rise-4">
          <ProcessMethod composition={c} />
        </div>

        {/* ── Notes ── */}
        {formula.formulation_notes && (
          <section className="rounded-xl bg-slate-50 border border-dashed border-slate-300 px-4 py-3 ff-rise ff-rise-4">
            <SectionTitle>Formulation notes — written by the model</SectionTitle>
            <p className="text-meta text-slate-500 -mt-1 mb-2">
              Prose, not computed output. Unlike the figures above, nothing here
              was derived from the ingredient library.
              {formula.notes_contain_numeric_claims && (
                <span className="text-amber-700">
                  {" "}It mentions quantities the system did not calculate — treat
                  them as suggestions to check, not as results.
                </span>
              )}
            </p>
            <div className="text-data text-slate-600 leading-relaxed italic">
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
    <div className="rounded-2xl border border-red-200 bg-white overflow-hidden ff-rise print-block">
      <div className="px-6 py-4 bg-red-50/70 border-b border-red-100">
        <div className="flex items-center justify-between gap-3">
          <div>
            <span className="text-micro font-semibold tracking-[0.14em] text-red-600 uppercase">
              Verification failed
            </span>
            <h3 className="font-heading text-base font-semibold text-red-900 mt-0.5">{rejection.product_name}</h3>
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
