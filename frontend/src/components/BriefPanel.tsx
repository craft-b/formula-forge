// The brief console — the dark left rail where a formulator sets the product
// format and dietary-constraint modules, then describes the target. Module
// toggles are sent explicitly in the API request (not just keyword-detected).
// Switches are real ARIA switches so screen readers announce on/off state.

import type { ModuleInfo } from "@/types/meta"

export const FORMATS = [
  { id: "premium", label: "Premium" },
  { id: "standard", label: "Standard" },
  { id: "gelato", label: "Gelato" },
  { id: "soft_serve", label: "Soft serve" },
  { id: "novelty", label: "Novelty" },
] as const

const MODULE_HINTS: Record<string, string> = {
  renal: "K ≤ 200 · P ≤ 120 · Na ≤ 150 mg/serving",
  diabetic: "total sugars ≤ 8 g/serving",
  high_protein: "protein ≥ 8 g/serving",
  low_fat: "fat ≤ 3 g/serving",
  vegan: "no dairy, egg, or animal-derived",
  dysphagia_iddsi: "texture module — preview",
}

export function BriefPanel({
  modules,
  selected,
  onToggle,
  format,
  onFormat,
  disabled,
}: {
  modules: ModuleInfo[]
  selected: Set<string>
  onToggle: (id: string) => void
  format: string
  onFormat: (id: string) => void
  disabled: boolean
}) {
  return (
    <div className="space-y-6">
      {/* Product format */}
      <section>
        <h3 className="text-[10px] font-semibold tracking-[0.14em] text-slate-500 uppercase mb-2">
          Product format
        </h3>
        <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label="Product format">
          {FORMATS.map((f) => (
            <button
              key={f.id}
              role="radio"
              aria-checked={format === f.id}
              disabled={disabled}
              onClick={() => onFormat(f.id)}
              className={`text-[11px] px-2.5 py-1.5 rounded-lg border transition-all disabled:opacity-50 ${
                format === f.id
                  ? "bg-teal-500/15 border-teal-500/50 text-teal-300 font-medium"
                  : "bg-white/[0.03] border-white/10 text-slate-400 hover:border-white/25 hover:text-slate-200"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </section>

      {/* Constraint modules */}
      <section>
        <h3 className="text-[10px] font-semibold tracking-[0.14em] text-slate-500 uppercase mb-2">
          Dietary constraints
        </h3>
        <div className="space-y-1">
          {modules.map((m) => {
            const on = selected.has(m.id)
            return (
              <button
                key={m.id}
                role="switch"
                aria-checked={on}
                disabled={disabled || m.stub}
                onClick={() => onToggle(m.id)}
                className={`w-full flex items-center gap-2.5 rounded-lg border px-3 py-2 text-left transition-colors disabled:opacity-40 ${
                  on
                    ? "bg-teal-500/10 border-teal-500/40"
                    : "bg-white/[0.03] border-white/10 hover:border-white/25"
                }`}
              >
                <span
                  aria-hidden
                  className={`w-8 h-[18px] rounded-full relative shrink-0 transition-colors ${
                    on ? "bg-teal-500" : "bg-white/15"
                  }`}
                >
                  <span
                    className={`absolute top-[2px] w-[14px] h-[14px] rounded-full bg-white shadow transition-all duration-200 ${
                      on ? "left-[18px]" : "left-[2px]"
                    }`}
                  />
                </span>
                <span className="min-w-0">
                  <span className={`block text-xs font-medium capitalize ${on ? "text-teal-200" : "text-slate-300"}`}>
                    {m.id.replace("_", " ")}
                    {m.stub && <span className="ml-1.5 text-[9px] text-slate-500 uppercase">preview</span>}
                  </span>
                  <span className="block text-[10px] text-slate-500 truncate">
                    {MODULE_HINTS[m.id] ?? m.label}
                  </span>
                </span>
              </button>
            )
          })}
          {modules.length === 0 && (
            <div className="space-y-1" aria-hidden>
              {[0, 1, 2, 3].map((i) => (
                <div key={i} className="h-[52px] rounded-lg border border-white/5 bg-white/[0.02] animate-pulse" />
              ))}
            </div>
          )}
        </div>
        <p className="text-[10px] text-slate-600 mt-2 leading-relaxed">
          Thresholds are configurable defaults from published guidance — professional review required.
        </p>
      </section>
    </div>
  )
}
