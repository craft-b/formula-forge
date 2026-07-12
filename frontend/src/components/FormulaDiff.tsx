// "Changes from vN" — the delta between two verified formulas in an iteration
// chain. Everything here is computed from rule-verified data, so the diff
// carries the same trust as the reports it compares. Ingredients are keyed by
// governed ingredient_id; nutrients/physics show old → new with % change.

import type { ValidatedFormula } from "@/types/api"
import { SectionTitle } from "./viz"

interface IngredientChange {
  name: string
  kind: "added" | "removed" | "adjusted"
  oldPct?: number
  newPct?: number
}

function diffIngredients(prev: ValidatedFormula, cur: ValidatedFormula): IngredientChange[] {
  const prevBy = new Map(prev.ingredients.map((i) => [i.ingredient_id, i]))
  const curBy = new Map(cur.ingredients.map((i) => [i.ingredient_id, i]))
  const changes: IngredientChange[] = []

  for (const ing of cur.ingredients) {
    const before = prevBy.get(ing.ingredient_id)
    if (!before) {
      changes.push({ name: ing.ingredient_name, kind: "added", newPct: ing.percentage })
    } else if (Math.abs(before.percentage - ing.percentage) >= 0.05) {
      changes.push({
        name: ing.ingredient_name,
        kind: "adjusted",
        oldPct: before.percentage,
        newPct: ing.percentage,
      })
    }
  }
  for (const ing of prev.ingredients) {
    if (!curBy.has(ing.ingredient_id)) {
      changes.push({ name: ing.ingredient_name, kind: "removed", oldPct: ing.percentage })
    }
  }
  // Added first, then adjusted, then removed — the order a reviewer scans.
  const rank = { added: 0, adjusted: 1, removed: 2 }
  return changes.sort((a, b) => rank[a.kind] - rank[b.kind])
}

interface MetricDelta {
  label: string
  unit: string
  oldV: number
  newV: number
  fmt: (v: number) => string
}

const NUTRIENT_DELTAS: { key: string; label: string; unit: string; fmt: (v: number) => string; minAbs: number }[] = [
  { key: "energy_kcal", label: "Energy", unit: "kcal", fmt: (v) => String(Math.round(v)), minAbs: 2 },
  { key: "protein_g", label: "Protein", unit: "g", fmt: (v) => v.toFixed(1), minAbs: 0.2 },
  { key: "fat_g", label: "Fat", unit: "g", fmt: (v) => v.toFixed(1), minAbs: 0.2 },
  { key: "sugars_g", label: "Sugars", unit: "g", fmt: (v) => v.toFixed(1), minAbs: 0.2 },
  { key: "sodium_mg", label: "Sodium", unit: "mg", fmt: (v) => String(Math.round(v)), minAbs: 2 },
  { key: "potassium_mg", label: "Potassium", unit: "mg", fmt: (v) => String(Math.round(v)), minAbs: 2 },
  { key: "phosphorus_mg", label: "Phosphorus", unit: "mg", fmt: (v) => String(Math.round(v)), minAbs: 2 },
]

const PHYSICS_DELTAS: { key: keyof ValidatedFormula["composition"]; label: string; unit: string; fmt: (v: number) => string; minAbs: number }[] = [
  { key: "pac_total", label: "PAC", unit: "", fmt: (v) => v.toFixed(1), minAbs: 0.3 },
  { key: "pod_total", label: "POD", unit: "", fmt: (v) => v.toFixed(1), minAbs: 0.3 },
  { key: "total_solids_pct", label: "Total solids", unit: "%", fmt: (v) => v.toFixed(1), minAbs: 0.3 },
  { key: "total_cost_per_kg_usd", label: "Cost", unit: "$/kg", fmt: (v) => v.toFixed(2), minAbs: 0.05 },
]

function collectDeltas(prev: ValidatedFormula, cur: ValidatedFormula): MetricDelta[] {
  const out: MetricDelta[] = []
  const pn = prev.composition.nutrients_per_serving as unknown as Record<string, number>
  const cn = cur.composition.nutrients_per_serving as unknown as Record<string, number>
  for (const d of NUTRIENT_DELTAS) {
    const oldV = pn[d.key], newV = cn[d.key]
    if (Math.abs(newV - oldV) >= d.minAbs) out.push({ label: d.label, unit: d.unit, oldV, newV, fmt: d.fmt })
  }
  for (const d of PHYSICS_DELTAS) {
    const oldV = prev.composition[d.key] as number
    const newV = cur.composition[d.key] as number
    if (Math.abs(newV - oldV) >= d.minAbs) out.push({ label: d.label, unit: d.unit, oldV, newV, fmt: d.fmt })
  }
  return out
}

function PctPill({ oldV, newV }: { oldV: number; newV: number }) {
  if (oldV === 0) return null
  const pct = ((newV - oldV) / oldV) * 100
  if (!isFinite(pct) || Math.abs(pct) < 0.5) return null
  const up = pct > 0
  return (
    <span className="num text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-slate-100 text-slate-600">
      {up ? "↑" : "↓"} {Math.abs(pct).toFixed(0)}%
    </span>
  )
}

const KIND_STYLE = {
  added: { sym: "+", cls: "bg-teal-50 border-teal-200 text-teal-700" },
  removed: { sym: "−", cls: "bg-slate-100 border-slate-200 text-slate-500" },
  adjusted: { sym: "±", cls: "bg-indigo-50 border-indigo-100 text-indigo-700" },
} as const

export function FormulaDiff({
  previous,
  current,
  fromVersion,
}: {
  previous: ValidatedFormula
  current: ValidatedFormula
  fromVersion: number
}) {
  const ingredientChanges = diffIngredients(previous, current)
  const metricDeltas = collectDeltas(previous, current)

  return (
    <section className="rounded-xl border border-slate-200 bg-slate-50/60 px-4 py-3.5">
      <SectionTitle meta={`· deltas computed from rule-verified data`}>
        Changes from v{fromVersion}
      </SectionTitle>

      {ingredientChanges.length === 0 && metricDeltas.length === 0 ? (
        <p className="text-[13px] text-slate-500">
          No material changes — composition and nutrition are within display thresholds of v{fromVersion}.
        </p>
      ) : (
        <div className="space-y-3">
          {ingredientChanges.length > 0 && (
            <ul className="space-y-1">
              {ingredientChanges.map((c) => (
                <li key={`${c.kind}-${c.name}`} className="flex items-center gap-2.5 text-[13px]">
                  <span
                    className={`w-[18px] h-[18px] shrink-0 rounded-md border text-[11px] font-bold flex items-center justify-center ${KIND_STYLE[c.kind].cls}`}
                    aria-label={c.kind}
                  >
                    {KIND_STYLE[c.kind].sym}
                  </span>
                  <span className={`text-slate-800 ${c.kind === "removed" ? "line-through text-slate-400" : ""}`}>
                    {c.name}
                  </span>
                  <span className="num text-slate-500 ml-auto shrink-0">
                    {c.kind === "added" && <>{c.newPct!.toFixed(1)}%</>}
                    {c.kind === "removed" && <>was {c.oldPct!.toFixed(1)}%</>}
                    {c.kind === "adjusted" && (
                      <>
                        {c.oldPct!.toFixed(1)}% <span className="text-slate-400">→</span> {c.newPct!.toFixed(1)}%
                      </>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          )}

          {metricDeltas.length > 0 && (
            <div className="flex flex-wrap gap-x-5 gap-y-1.5 pt-2 border-t border-slate-200/70">
              {metricDeltas.map((d) => (
                <span key={d.label} className="inline-flex items-baseline gap-1.5 text-[12px]">
                  <span className="text-slate-500">{d.label}</span>
                  <span className="num text-slate-700">
                    {d.fmt(d.oldV)} <span className="text-slate-400">→</span>{" "}
                    <span className="font-semibold text-slate-900">{d.fmt(d.newV)}</span>
                    {d.unit && <span className="text-slate-400 ml-0.5">{d.unit}</span>}
                  </span>
                  <PctPill oldV={d.oldV} newV={d.newV} />
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  )
}
