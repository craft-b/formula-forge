import { useState, useRef, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Markdown } from "@/lib/markdown"
import type {
  SSEEvent,
  ValidatedFormula,
  RejectedFormula,
  Violation,
} from "@/types/api"

const API_URL = import.meta.env.VITE_API_URL

// ── Types ────────────────────────────────────────────────────────────────────

interface Message {
  role: "user" | "assistant"
  content: string
  formula?: ValidatedFormula
  rejection?: RejectedFormula
}

// ── Small UI atoms ────────────────────────────────────────────────────────────

function MetricTile({
  label,
  value,
  unit,
  estimated,
}: {
  label: string
  value: number | string
  unit?: string
  estimated?: boolean
}) {
  return (
    <div className="bg-slate-50 rounded-xl px-3 py-2.5">
      <div className="text-[11px] text-slate-400 font-medium flex items-center gap-1">
        {label}
        {estimated ? (
          <span title="Model-estimated" className="text-amber-500">~</span>
        ) : (
          <span title="Rule-verified (computed)" className="text-teal-500">✓</span>
        )}
      </div>
      <div className="text-base font-bold text-slate-800 mt-0.5 tabular-nums">
        {value}
        {unit && <span className="text-xs font-normal text-slate-400 ml-0.5">{unit}</span>}
      </div>
    </div>
  )
}

function ViolationRow({ v }: { v: Violation }) {
  const isError = v.severity === "error"
  return (
    <div
      className={`flex gap-2 items-start text-xs rounded-lg px-3 py-2 ${
        isError ? "bg-red-50 text-red-700" : "bg-amber-50 text-amber-700"
      }`}
    >
      <span className="font-bold mt-px">{isError ? "✕" : "!"}</span>
      <div className="min-w-0">
        <span>{v.explanation}</span>
        {v.measured != null && v.limit != null && (
          <span className="ml-1 font-semibold tabular-nums">
            ({v.measured} vs limit {v.limit})
          </span>
        )}
      </div>
    </div>
  )
}

// ── Verification surface (formula card) ───────────────────────────────────────

function FormulaCard({ formula }: { formula: ValidatedFormula }) {
  const { composition: c, validation: val } = formula
  const total = formula.ingredients.reduce((s, i) => s + i.percentage, 0)
  const passed = val.passed
  const errors = (val.violations ?? []).filter((v) => v.severity === "error")
  const warnings = (val.violations ?? []).filter((v) => v.severity === "warn")
  const ns = c.nutrients_per_serving

  return (
    <div className="mt-3 rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden">
      {/* Header */}
      <div className={`px-5 py-4 ${passed ? "bg-gradient-to-r from-teal-700 to-teal-500" : "bg-gradient-to-r from-amber-600 to-amber-500"}`}>
        <div className="flex items-center justify-between gap-3">
          <span className="inline-block text-[10px] font-semibold tracking-widest text-white/80 uppercase">
            {c.product_format} · verified formula
          </span>
          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-white/20 text-white">
            {passed ? "✓ COMPLIANT" : "⚠ FLAGGED"}
          </span>
        </div>
        <h3 className="text-lg font-bold text-white leading-snug mt-1.5">{formula.product_name}</h3>
        {formula.description && (
          <p className="text-sm text-white/85 mt-1 leading-relaxed">{formula.description}</p>
        )}
        {(val.active_modules ?? []).length > 0 && (
          <div className="flex flex-wrap gap-1 mt-2">
            {val.active_modules!.map((m) => (
              <span key={m} className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-white/15 text-white">
                {m}
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="divide-y divide-slate-100">
        {/* Compliance / validation surface */}
        {(errors.length > 0 || warnings.length > 0 || val.repaired) && (
          <div className="px-5 py-4 space-y-1.5">
            <h4 className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-2">
              Validation {passed ? "— passed with advisories" : "— compliance failures"}
            </h4>
            {errors.map((v, i) => <ViolationRow key={`e${i}`} v={v} />)}
            {warnings.map((v, i) => <ViolationRow key={`w${i}`} v={v} />)}
            {val.repaired && (
              <p className="text-[11px] text-slate-400 pt-1">
                Percentages were normalized to sum to 100%.
              </p>
            )}
          </div>
        )}
        {passed && errors.length === 0 && warnings.length === 0 && (
          <div className="px-5 py-3">
            <span className="text-xs text-teal-600 font-medium">✓ All checks passed.</span>
          </div>
        )}

        {/* Ingredients */}
        <div className="px-5 py-4">
          <h4 className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-3">
            Ingredient Breakdown
            {Math.round(total) !== 100 && (
              <span className="ml-2 text-amber-500">(Σ {total.toFixed(1)}%)</span>
            )}
          </h4>
          <div className="space-y-3">
            {formula.ingredients.map((ing, i) => (
              <div key={i}>
                <div className="flex justify-between items-baseline mb-1">
                  <span className="text-sm font-medium text-slate-800">{ing.ingredient_name}</span>
                  <span className="text-sm font-semibold text-teal-600 tabular-nums ml-4">
                    {ing.percentage}%
                  </span>
                </div>
                <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-teal-400 to-teal-500 rounded-full"
                    style={{ width: `${Math.min(ing.percentage, 100)}%` }}
                  />
                </div>
                {ing.notes && <p className="text-xs text-slate-400 mt-0.5 leading-relaxed">{ing.notes}</p>}
              </div>
            ))}
          </div>
        </div>

        {/* Nutrition per serving (rule-verified) */}
        <div className="px-5 py-4">
          <h4 className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-3">
            Per serving · {c.serving_g} g · {c.overrun_pct}% overrun
          </h4>
          <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
            <MetricTile label="Energy" value={Math.round(ns.energy_kcal)} unit="kcal" />
            <MetricTile label="Protein" value={ns.protein_g.toFixed(1)} unit="g" />
            <MetricTile label="Fat" value={ns.fat_g.toFixed(1)} unit="g" />
            <MetricTile label="Carbs" value={ns.carbs_g.toFixed(1)} unit="g" />
            <MetricTile label="Sugars" value={ns.sugars_g.toFixed(1)} unit="g" />
            <MetricTile label="Sodium" value={Math.round(ns.sodium_mg)} unit="mg" />
            <MetricTile label="Potassium" value={Math.round(ns.potassium_mg)} unit="mg" />
            <MetricTile label="Phosphorus" value={Math.round(ns.phosphorus_mg)} unit="mg" />
          </div>
        </div>

        {/* Structure & quality indices */}
        <div className="px-5 py-4">
          <h4 className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-3">
            Structure &amp; Quality
          </h4>
          <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
            <MetricTile label="Total solids" value={c.total_solids_pct.toFixed(1)} unit="%" />
            <MetricTile label="Fat" value={c.fat_pct.toFixed(1)} unit="%" />
            <MetricTile label="MSNF" value={c.msnf_pct.toFixed(1)} unit="%" />
            <MetricTile label="Sugars" value={c.sugars_pct.toFixed(1)} unit="%" />
            <MetricTile label="PAC" value={c.pac_total.toFixed(1)} />
            <MetricTile label="POD" value={c.pod_total.toFixed(1)} />
            <MetricTile label="Scoop" value={c.scoopability_index.toFixed(0)} estimated />
            <MetricTile label="Cost" value={`$${c.total_cost_per_kg_usd.toFixed(2)}`} unit="/kg" />
          </div>
          <p className="text-[10px] text-slate-400 mt-2">
            <span className="text-teal-500">✓</span> rule-verified (computed from USDA + governed data) ·{" "}
            <span className="text-amber-500">~</span> model-estimated. PAC target ≈ 22–34, POD ≈ 12–18.
          </p>
        </div>

        {/* Formulation notes */}
        {formula.formulation_notes && (
          <div className="px-5 py-4">
            <h4 className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-2">
              Formulation Notes
            </h4>
            <div className="text-sm text-slate-600 leading-relaxed">
              <Markdown text={formula.formulation_notes} />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function RejectionCard({ rejection }: { rejection: RejectedFormula }) {
  return (
    <div className="mt-3 rounded-2xl border border-red-200 bg-red-50 overflow-hidden">
      <div className="px-5 py-3 bg-red-100/60">
        <span className="text-[10px] font-semibold tracking-widest text-red-500 uppercase">
          Could not verify
        </span>
        <h3 className="text-sm font-bold text-red-800 mt-0.5">{rejection.product_name}</h3>
      </div>
      <div className="px-5 py-3 space-y-2">
        <p className="text-sm text-red-700">{rejection.reason}</p>
        {(rejection.unresolved_ingredients ?? []).length > 0 && (
          <p className="text-xs text-red-600">
            Unrecognized ingredients: {rejection.unresolved_ingredients!.join(", ")}
          </p>
        )}
        {(rejection.violations ?? []).map((v, i) => <ViolationRow key={i} v={v} />)}
      </div>
    </div>
  )
}

// ── Message + typing ──────────────────────────────────────────────────────────

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user"
  return (
    <div className={`flex gap-2 ${isUser ? "justify-end" : "justify-start"}`}>
      {!isUser && (
        <div className="w-7 h-7 rounded-full bg-teal-500 flex-shrink-0 flex items-center justify-center mt-0.5">
          <span className="text-white text-xs font-bold">F</span>
        </div>
      )}
      <div className={isUser ? "max-w-[75%]" : "flex-1 min-w-0"}>
        {message.content && (
          <div
            className={
              isUser
                ? "bg-teal-600 text-white rounded-2xl rounded-tr-sm px-4 py-2.5 text-sm leading-relaxed"
                : "bg-white border border-slate-200 text-slate-800 rounded-2xl rounded-tl-sm px-4 py-2.5 text-sm leading-relaxed shadow-sm"
            }
          >
            {isUser ? message.content : <Markdown text={message.content} />}
          </div>
        )}
        {message.formula && <FormulaCard formula={message.formula} />}
        {message.rejection && <RejectionCard rejection={message.rejection} />}
      </div>
    </div>
  )
}

function TypingIndicator() {
  return (
    <div className="flex gap-2 items-start">
      <div className="w-7 h-7 rounded-full bg-teal-500 flex-shrink-0 flex items-center justify-center">
        <span className="text-white text-xs font-bold">F</span>
      </div>
      <div className="bg-white border border-slate-200 rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm">
        <div className="flex gap-1 items-center">
          {[0, 150, 300].map((delay) => (
            <span
              key={delay}
              className="w-1.5 h-1.5 bg-slate-300 rounded-full animate-bounce"
              style={{ animationDelay: `${delay}ms` }}
            />
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Suggestions (frozen-dessert / medical brief) ──────────────────────────────

const SUGGESTIONS = [
  "Create a renal-safe scoopable vanilla ice cream, potassium ≤ 200 mg/serving",
  "Formulate a low-sugar diabetic-friendly frozen dessert",
  "Design a high-protein frozen dessert for recovery nutrition",
  "What ingredients lower phosphorus in a dairy frozen dessert?",
]

// ── App ───────────────────────────────────────────────────────────────────────

export default function App() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, loading])

  // Abort any in-flight request on unmount (fixes F12: no setState after unmount).
  useEffect(() => () => abortRef.current?.abort(), [])

  function cancel() {
    abortRef.current?.abort()
    abortRef.current = null
    setLoading(false)
  }

  async function sendMessage(text: string) {
    if (!text.trim() || loading) return
    setInput("")
    setMessages((prev) => [...prev, { role: "user", content: text }])
    setLoading(true)

    const controller = new AbortController()
    abortRef.current = controller
    let hasAssistantMessage = false

    try {
      const res = await fetch(`${API_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, session_id: sessionId }),
        signal: controller.signal,
      })

      if (res.status === 429) {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: "Rate or usage limit reached — please wait a moment and try again." },
        ])
        return
      }
      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`)

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ""

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const parts = buffer.split("\n\n")
        buffer = parts.pop() ?? ""

        for (const part of parts) {
          if (!part.startsWith("data: ")) continue
          const payload = part.slice(6)
          if (payload === "[DONE]") break

          let event: SSEEvent
          try {
            event = JSON.parse(payload) as SSEEvent
          } catch {
            continue
          }

          if (event.type === "token") {
            const content = event.content
            if (!hasAssistantMessage) {
              hasAssistantMessage = true
              setMessages((prev) => [...prev, { role: "assistant", content }])
            } else {
              setMessages((prev) => {
                const msgs = [...prev]
                const last = msgs[msgs.length - 1]
                if (last.role === "assistant") {
                  msgs[msgs.length - 1] = { ...last, content: last.content + content }
                }
                return msgs
              })
            }
          } else if (event.type === "formula") {
            hasAssistantMessage = true
            setMessages((prev) => [
              ...prev,
              { role: "assistant", content: event.response, formula: event.formula },
            ])
          } else if (event.type === "rejection") {
            hasAssistantMessage = true
            setMessages((prev) => [
              ...prev,
              { role: "assistant", content: event.response, rejection: event.rejection },
            ])
          } else if (event.type === "error") {
            hasAssistantMessage = true
            setMessages((prev) => [...prev, { role: "assistant", content: event.message }])
          } else if (event.type === "done") {
            setSessionId(event.session_id)
          }
        }
      }
    } catch (err) {
      if ((err as Error).name === "AbortError") return
      if (!hasAssistantMessage) {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: "Could not reach the server — check your connection." },
        ])
      }
    } finally {
      abortRef.current = null
      setLoading(false)
    }
  }

  function handleClear() {
    cancel()
    setMessages([])
    setSessionId(null)
  }

  const isEmpty = messages.length === 0

  return (
    <div className="h-screen flex flex-col bg-slate-50">
      {/* Header */}
      <header className="flex-shrink-0 bg-white border-b border-slate-200 shadow-sm">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-teal-500 flex items-center justify-center">
              <span className="text-white font-bold text-sm">F</span>
            </div>
            <div className="leading-none">
              <div className="font-semibold text-slate-900 text-sm">FormulaForge</div>
              <div className="text-[11px] text-slate-400 mt-0.5">
                Medical &amp; Institutional Frozen-Dessert Formulation
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {!isEmpty && (
              <Button variant="ghost" size="sm" onClick={handleClear} className="text-xs text-slate-500 h-7 px-2">
                Clear chat
              </Button>
            )}
            <a
              href="https://github.com/craft-b/formula-forge"
              target="_blank"
              rel="noreferrer"
              className="hidden sm:block text-xs text-slate-400 hover:text-teal-600 transition-colors"
            >
              GitHub
            </a>
          </div>
        </div>
      </header>

      {/* Messages */}
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 py-6">
          {isEmpty ? (
            <div className="flex flex-col items-center justify-center min-h-[60vh] text-center">
              <div className="w-16 h-16 rounded-2xl bg-teal-50 border border-teal-100 flex items-center justify-center mb-5">
                <span className="text-3xl">🍨</span>
              </div>
              <h2 className="text-xl font-semibold text-slate-800 mb-2">Formulate a frozen dessert</h2>
              <p className="text-sm text-slate-500 max-w-sm leading-relaxed mb-8">
                Describe your medical or dietary target. Every formula is verified against a governed
                ingredient database and physical-plausibility rules before you see it.
              </p>
              <div className="grid sm:grid-cols-2 gap-2 w-full max-w-lg">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => sendMessage(s)}
                    className="text-left px-4 py-3 rounded-xl border border-slate-200 bg-white text-sm text-slate-600 hover:border-teal-300 hover:bg-teal-50 hover:text-teal-700 transition-all shadow-sm"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="space-y-5">
              {messages.map((msg, i) => (
                <MessageBubble key={i} message={msg} />
              ))}
              {loading && messages[messages.length - 1]?.role === "user" && <TypingIndicator />}
              <div ref={bottomRef} />
            </div>
          )}
        </div>
      </main>

      {/* Input */}
      <div className="flex-shrink-0 bg-white border-t border-slate-200">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 py-3">
          <div className="flex gap-2">
            <input
              className="flex-1 px-4 py-2.5 text-sm border border-slate-200 rounded-xl bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-teal-400 focus:border-transparent placeholder:text-slate-400 transition-colors"
              placeholder="Describe a target, e.g. renal-safe scoopable vanilla…"
              value={input}
              disabled={loading}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                  sendMessage(input)
                }
              }}
            />
            {loading ? (
              <Button onClick={cancel} variant="outline" className="rounded-xl px-5">
                Stop
              </Button>
            ) : (
              <Button
                onClick={() => sendMessage(input)}
                disabled={!input.trim()}
                className="bg-teal-600 hover:bg-teal-700 text-white rounded-xl px-5 transition-colors"
              >
                Send
              </Button>
            )}
          </div>
          <p className="text-[11px] text-slate-400 mt-2 text-center">
            Formulation tool for qualified professionals · nutrition computed from USDA FoodData Central ·
            not medical advice
          </p>
        </div>
      </div>
    </div>
  )
}
