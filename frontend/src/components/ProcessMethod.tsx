// Deterministic manufacture instructions — a standard frozen-dessert method
// (Goff & Hartel conventions) parameterized by the computed composition and
// product format. No LLM text here: every step is rule-templated from verified
// data, so it carries the same trust as the numbers. It is still a template —
// plant equipment, local regs, and validated pasteurization schedules govern.

import type { ComputedComposition } from "@/types/api"
import { SectionTitle } from "./viz"

interface Step {
  title: string
  detail: string
}

// Pure step derivation, used only by ProcessMethod below.
function buildProcessSteps(c: ComputedComposition): Step[] {
  const format = c.product_format
  const softServe = format === "soft_serve"
  const novelty = format === "novelty"
  const gelato = format === "gelato"

  const steps: Step[] = []

  steps.push({
    title: "Prepare the liquid phase",
    detail: "Combine liquid ingredients in the mix tank and heat to 40–45 °C to aid dispersion.",
  })

  steps.push(
    c.stabilizer_pct > 0.05
      ? {
          title: "Dry-blend and disperse",
          detail:
            "Dry-blend stabilizers/emulsifiers with several parts of the sugars or other powders, then disperse into the liquid phase under high shear to prevent clumping.",
        }
      : {
          title: "Disperse dry ingredients",
          detail: "Add powders gradually under high shear until fully dispersed with no visible lumps.",
        }
  )

  steps.push({
    title: "Pasteurize",
    detail: "HTST 80 °C for 25 s, or batch 69 °C for 30 min. Follow your validated schedule and local regulations.",
  })

  steps.push({
    title: "Homogenize",
    detail: "Two-stage at 65–70 °C: 13.8 MPa first stage / 3.4 MPa second stage (≈2000/500 psi).",
  })

  steps.push({
    title: "Cool and age",
    detail: "Cool rapidly to ≤ 4 °C and age 4–12 h so proteins and stabilizers hydrate and fat crystallizes for dryness at draw.",
  })

  steps.push({
    title: "Flavor",
    detail: "Add heat-sensitive flavors (extracts, purées, inclusions concentrate) after aging, immediately before freezing.",
  })

  if (softServe) {
    steps.push({
      title: "Freeze and serve",
      detail: `Freeze in the soft-serve unit; draw at −7 to −8 °C targeting ${c.overrun_pct}% overrun and serve directly — no hardening step.`,
    })
  } else {
    steps.push({
      title: "Freeze",
      detail: `Continuous or batch freezer; draw at −5 to −6 °C targeting ${c.overrun_pct}% overrun.`,
    })
    steps.push(
      novelty
        ? {
            title: "Mold and harden",
            detail: "Fill molds or extrude, insert sticks as applicable, and harden in a brine bath or blast tunnel (≤ −30 °C) until core reaches −18 °C.",
          }
        : {
            title: "Fill and harden",
            detail: "Fill containers and blast-harden at ≤ −25 °C until the core reaches −18 °C.",
          }
    )
    steps.push({
      title: "Store and temper",
      detail: gelato
        ? "Store at ≤ −25 °C; temper in a serving case to −11 to −13 °C for display and scooping."
        : "Store at ≤ −25 °C; temper to −13 to −15 °C before scooping.",
    })
  }

  return steps
}

export function ProcessMethod({ composition }: { composition: ComputedComposition }) {
  const steps = buildProcessSteps(composition)
  return (
    <section>
      <SectionTitle meta="· standard method, templated from verified data — adjust to plant equipment">
        Process
      </SectionTitle>
      <ol className="space-y-0">
        {steps.map((s, i) => (
          <li key={s.title} className="flex gap-3 relative pb-3 last:pb-0">
            {/* step rail */}
            {i < steps.length - 1 && (
              <span className="absolute left-[11px] top-6 bottom-0 w-px bg-slate-200" aria-hidden />
            )}
            <span className="w-[23px] h-[23px] shrink-0 rounded-full bg-slate-100 border border-slate-200 text-micro font-semibold text-slate-600 flex items-center justify-center num relative">
              {i + 1}
            </span>
            <div className="min-w-0 pt-0.5">
              <span className="text-data font-semibold text-slate-800">{s.title}</span>
              <span className="text-data text-slate-600"> — {s.detail}</span>
            </div>
          </li>
        ))}
      </ol>
    </section>
  )
}
