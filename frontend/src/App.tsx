import { useState, useRef, useEffect } from "react"
import { Button } from "@/components/ui/button"

const API_URL = import.meta.env.VITE_API_URL

// ── Types ────────────────────────────────────────────────────────────────────

interface Ingredient {
  name: string
  percentage: number
  notes: string
}

interface NutritionFacts {
  calories: number
  protein: number
  fat: number
  carbs: number
}

interface Formula {
  type: "formula"
  product_name: string
  description: string
  ingredients: Ingredient[]
  nutrition_per_100g: NutritionFacts
  formulation_notes: string
}

interface Message {
  role: "user" | "assistant"
  content: string
  formula?: Formula
}

// ── Formula Card ─────────────────────────────────────────────────────────────

function FormulaCard({ formula }: { formula: Formula }) {
  const total = formula.ingredients.reduce((s, i) => s + i.percentage, 0)

  return (
    <div className="mt-3 rounded-2xl border border-teal-100 bg-white shadow-sm overflow-hidden">
      <div className="bg-gradient-to-r from-teal-700 to-teal-500 px-5 py-4">
        <span className="inline-block text-[10px] font-semibold tracking-widest text-teal-200 uppercase mb-1.5">
          AI-Generated Formula
        </span>
        <h3 className="text-lg font-bold text-white leading-snug">{formula.product_name}</h3>
        <p className="text-sm text-teal-100 mt-1 leading-relaxed">{formula.description}</p>
      </div>

      <div className="divide-y divide-slate-100">
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
                  <span className="text-sm font-medium text-slate-800">{ing.name}</span>
                  <span className="text-sm font-semibold text-teal-600 tabular-nums ml-4">
                    {ing.percentage}%
                  </span>
                </div>
                <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-teal-400 to-teal-500 rounded-full transition-all"
                    style={{ width: `${Math.min(ing.percentage, 100)}%` }}
                  />
                </div>
                {ing.notes && (
                  <p className="text-xs text-slate-400 mt-0.5 leading-relaxed">{ing.notes}</p>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Nutrition + Notes */}
        <div className="px-5 py-4 grid sm:grid-cols-2 gap-5">
          <div>
            <h4 className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-3">
              Nutrition per 100g
            </h4>
            <div className="grid grid-cols-2 gap-2">
              {[
                { label: "Calories", value: formula.nutrition_per_100g.calories, unit: "kcal" },
                { label: "Protein",  value: formula.nutrition_per_100g.protein,  unit: "g" },
                { label: "Fat",      value: formula.nutrition_per_100g.fat,      unit: "g" },
                { label: "Carbs",    value: formula.nutrition_per_100g.carbs,    unit: "g" },
              ].map(({ label, value, unit }) => (
                <div key={label} className="bg-slate-50 rounded-xl px-3 py-2.5">
                  <div className="text-[11px] text-slate-400 font-medium">{label}</div>
                  <div className="text-base font-bold text-slate-800 mt-0.5">
                    {value}
                    <span className="text-xs font-normal text-slate-400 ml-0.5">{unit}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div>
            <h4 className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-3">
              Formulation Notes
            </h4>
            <p className="text-sm text-slate-600 leading-relaxed">{formula.formulation_notes}</p>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Message Bubble ────────────────────────────────────────────────────────────

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
        <div
          className={
            isUser
              ? "bg-teal-600 text-white rounded-2xl rounded-tr-sm px-4 py-2.5 text-sm leading-relaxed"
              : "bg-white border border-slate-200 text-slate-800 rounded-2xl rounded-tl-sm px-4 py-2.5 text-sm leading-relaxed shadow-sm"
          }
        >
          {message.content}
        </div>
        {message.formula && <FormulaCard formula={message.formula} />}
      </div>
    </div>
  )
}

// ── Typing Indicator ──────────────────────────────────────────────────────────

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

// ── Suggestions ───────────────────────────────────────────────────────────────

const SUGGESTIONS = [
  "Create a formula for a high-protein renal-diet shake",
  "What protein sources work for dysphagia-safe foods?",
  "Formulate a low-phosphorus meal replacement",
  "What thickeners are used in oncology nutrition products?",
]

// ── App ───────────────────────────────────────────────────────────────────────

export default function App() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, loading])

  async function sendMessage(text: string) {
    if (!text.trim() || loading) return
    setInput("")
    setMessages((prev) => [...prev, { role: "user", content: text }])
    setLoading(true)

    let hasAssistantMessage = false

    try {
      const res = await fetch(`${API_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, session_id: sessionId }),
      })

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

          let event: Record<string, unknown>
          try { event = JSON.parse(payload) } catch { continue }

          if (event.type === "token") {
            const content = event.content as string
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
              {
                role: "assistant",
                content: event.response as string,
                formula: event.formula as Formula,
              },
            ])
          } else if (event.type === "error") {
            hasAssistantMessage = true
            setMessages((prev) => [
              ...prev,
              { role: "assistant", content: event.message as string },
            ])
          } else if (event.type === "done") {
            setSessionId(event.session_id as string)
          }
        }
      }
    } catch {
      if (!hasAssistantMessage) {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: "Could not reach the server — check your connection." },
        ])
      }
    } finally {
      setLoading(false)
    }
  }

  function handleClear() {
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
              <div className="text-[11px] text-slate-400 mt-0.5">AI-Powered Food Formulation</div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {!isEmpty && (
              <Button
                variant="ghost"
                size="sm"
                onClick={handleClear}
                className="text-xs text-slate-500 h-7 px-2"
              >
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
                <span className="text-3xl">🧪</span>
              </div>
              <h2 className="text-xl font-semibold text-slate-800 mb-2">
                Start a formulation
              </h2>
              <p className="text-sm text-slate-500 max-w-xs leading-relaxed mb-8">
                Ask about ingredients, request a complete formula, or explore the USDA food database.
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
              placeholder="Ask about ingredients or request a formula…"
              value={input}
              disabled={loading}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && sendMessage(input)}
            />
            <Button
              onClick={() => sendMessage(input)}
              disabled={loading || !input.trim()}
              className="bg-teal-600 hover:bg-teal-700 text-white rounded-xl px-5 gap-2 transition-colors"
            >
              {loading ? (
                <>
                  <svg className="animate-spin h-3.5 w-3.5" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  Thinking
                </>
              ) : (
                "Send"
              )}
            </Button>
          </div>
          <p className="text-[11px] text-slate-400 mt-2 text-center">
            FormulaForge uses USDA FoodData Central · Formulas are AI-generated estimates
          </p>
        </div>
      </div>
    </div>
  )
}
