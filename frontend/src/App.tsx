import { useEffect, useRef, useState } from "react"
import { BriefPanel, FORMATS } from "@/components/BriefPanel"
import { FormulaReport, RejectionReport } from "@/components/FormulaReport"
import { StatTile } from "@/components/viz"
import { Markdown } from "@/lib/markdown"
import type { RejectedFormula, SSEEvent, ValidatedFormula } from "@/types/api"
import type { WorkspaceMeta } from "@/types/meta"

const API_URL = import.meta.env.VITE_API_URL

// ── Run feed types ────────────────────────────────────────────────────────────

interface Run {
  role: "user" | "assistant"
  content: string
  formula?: ValidatedFormula
  rejection?: RejectedFormula
  chips?: string[]
}

// ── Pipeline progress (shown while a run is in flight) ───────────────────────

const PIPELINE_STEPS = ["Propose", "Resolve", "Compute", "Validate", "Score"]

function PipelineProgress() {
  const [step, setStep] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setStep((s) => Math.min(s + 1, PIPELINE_STEPS.length - 1)), 1400)
    return () => clearInterval(t)
  }, [])
  return (
    <div className="rounded-2xl border border-slate-200 bg-white px-6 py-5">
      <div className="flex items-center gap-0">
        {PIPELINE_STEPS.map((label, i) => (
          <div key={label} className="flex items-center">
            <div className="flex flex-col items-center gap-1.5">
              <span
                className={`w-2.5 h-2.5 rounded-full transition-colors ${
                  i < step ? "bg-teal-500" : i === step ? "bg-teal-500 animate-pulse" : "bg-slate-200"
                }`}
              />
              <span className={`text-[10px] font-medium ${i <= step ? "text-slate-700" : "text-slate-400"}`}>
                {label}
              </span>
            </div>
            {i < PIPELINE_STEPS.length - 1 && (
              <span className={`w-10 sm:w-16 h-px mx-1 mb-4 ${i < step ? "bg-teal-400" : "bg-slate-200"}`} />
            )}
          </div>
        ))}
        <span className="ml-auto mb-4 text-[11px] text-slate-400">
          LLM proposes · domain verifies
        </span>
      </div>
    </div>
  )
}

// ── Run rows ──────────────────────────────────────────────────────────────────

function BriefRow({ run }: { run: Run }) {
  return (
    <div className="flex items-baseline gap-3 flex-wrap">
      <span className="text-[10px] font-semibold tracking-[0.14em] text-slate-400 uppercase shrink-0">
        Brief
      </span>
      <span className="text-sm font-medium text-slate-800">{run.content}</span>
      {(run.chips ?? []).map((c) => (
        <span key={c} className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-slate-200/70 text-slate-600 capitalize">
          {c.replace("_", " ")}
        </span>
      ))}
    </div>
  )
}

function AnswerBlock({ run }: { run: Run }) {
  if (run.formula) return <FormulaReport formula={run.formula} />
  if (run.rejection) return <RejectionReport rejection={run.rejection} />
  return (
    <div className="rounded-2xl border border-slate-200 bg-white px-6 py-4 text-sm text-slate-700 leading-relaxed">
      <Markdown text={run.content} />
    </div>
  )
}

// ── Empty-state hero ──────────────────────────────────────────────────────────

const TEMPLATES = [
  { title: "Renal-safe vanilla", brief: "Renal-safe scoopable vanilla ice cream, potassium ≤ 200 mg per serving", modules: ["renal"] },
  { title: "Diabetic low-sugar", brief: "Low-sugar diabetic-friendly frozen dessert with polyol sweetening", modules: ["diabetic"] },
  { title: "High-protein recovery", brief: "High-protein frozen dessert for post-surgical recovery nutrition", modules: ["high_protein"] },
  { title: "Vegan chocolate", brief: "Vegan chocolate frozen dessert on a coconut base", modules: ["vegan"] },
]

function Hero({
  meta,
  onTemplate,
}: {
  meta: WorkspaceMeta | null
  onTemplate: (brief: string, modules: string[]) => void
}) {
  return (
    <div className="max-w-3xl mx-auto pt-10 sm:pt-16">
      <p className="text-[11px] font-semibold tracking-[0.18em] text-teal-600 uppercase">
        Constraint-verified formulation
      </p>
      <h1 className="text-3xl sm:text-4xl font-semibold text-slate-900 mt-2 leading-tight tracking-tight">
        Frozen desserts that meet medical constraints —{" "}
        <span className="text-slate-400">verified before you see them.</span>
      </h1>
      <p className="text-sm text-slate-500 mt-3 max-w-xl leading-relaxed">
        The LLM proposes an ingredient structure. A deterministic food-science engine computes
        every nutrient, checks freezing physics and compliance rules, and gates what reaches you.
      </p>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-8">
        <StatTile label="Governed ingredients" value={meta?.ingredient_count ?? "—"} hint="USDA FDC nutrients + curated functional data" />
        <StatTile label="Constraint modules" value={meta?.modules.length ?? "—"} hint="Declarative, versioned rulesets" />
        <StatTile label="Checks per formula" value="12+" hint="Mass balance, physics bands, compliance limits" />
        <StatTile label="LLM numbers trusted" value="0" hint="All nutrition computed by the domain engine" />
      </div>

      <h2 className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mt-10 mb-2.5">
        Start from a template
      </h2>
      <div className="grid sm:grid-cols-2 gap-2">
        {TEMPLATES.map((t) => (
          <button
            key={t.title}
            onClick={() => onTemplate(t.brief, t.modules)}
            className="text-left rounded-xl border border-slate-200 bg-white px-4 py-3.5 hover:border-teal-300 hover:shadow-sm transition-all group"
          >
            <span className="block text-sm font-medium text-slate-800 group-hover:text-teal-700">
              {t.title}
            </span>
            <span className="block text-xs text-slate-400 mt-0.5 leading-relaxed">{t.brief}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

// ── App shell ─────────────────────────────────────────────────────────────────

export default function App() {
  const [runs, setRuns] = useState<Run[]>([])
  const [input, setInput] = useState("")
  const [followUp, setFollowUp] = useState("")
  const [loading, setLoading] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [meta, setMeta] = useState<WorkspaceMeta | null>(null)
  const [selectedModules, setSelectedModules] = useState<Set<string>>(new Set())
  const [format, setFormat] = useState<string>("premium")
  const bottomRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [runs, loading])

  useEffect(() => () => abortRef.current?.abort(), [])

  useEffect(() => {
    fetch(`${API_URL}/api/meta`)
      .then((r) => (r.ok ? r.json() : null))
      .then((m) => m && setMeta(m))
      .catch(() => {})
  }, [])

  function toggleModule(id: string) {
    setSelectedModules((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function cancel() {
    abortRef.current?.abort()
    abortRef.current = null
    setLoading(false)
  }

  async function sendMessage(text: string, moduleOverride?: string[]) {
    if (!text.trim() || loading) return
    const modules = moduleOverride ?? Array.from(selectedModules)
    const hasFormatWord = FORMATS.some((f) => text.toLowerCase().includes(f.id.replace("_", " ")))
    const sentText = hasFormatWord ? text : `${text} — ${format.replace("_", " ")} format`

    setInput("")
    setFollowUp("")
    setRuns((prev) => [
      ...prev,
      { role: "user", content: text, chips: [format, ...modules] },
    ])
    setLoading(true)

    const controller = new AbortController()
    abortRef.current = controller
    let gotAnswer = false

    try {
      const res = await fetch(`${API_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: sentText, session_id: sessionId, modules }),
        signal: controller.signal,
      })

      if (res.status === 429) {
        setRuns((prev) => [...prev, { role: "assistant", content: "Rate or usage limit reached — please wait a moment and try again." }])
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
            if (!gotAnswer) {
              gotAnswer = true
              setRuns((prev) => [...prev, { role: "assistant", content }])
            } else {
              setRuns((prev) => {
                const next = [...prev]
                const last = next[next.length - 1]
                if (last.role === "assistant") {
                  next[next.length - 1] = { ...last, content: last.content + content }
                }
                return next
              })
            }
          } else if (event.type === "formula") {
            gotAnswer = true
            setRuns((prev) => [...prev, { role: "assistant", content: event.response, formula: event.formula }])
          } else if (event.type === "rejection") {
            gotAnswer = true
            setRuns((prev) => [...prev, { role: "assistant", content: event.response, rejection: event.rejection }])
          } else if (event.type === "error") {
            gotAnswer = true
            setRuns((prev) => [...prev, { role: "assistant", content: event.message }])
          } else if (event.type === "done") {
            setSessionId(event.session_id)
          }
        }
      }
    } catch (err) {
      if ((err as Error).name === "AbortError") return
      if (!gotAnswer) {
        setRuns((prev) => [...prev, { role: "assistant", content: "Could not reach the server — check your connection." }])
      }
    } finally {
      abortRef.current = null
      setLoading(false)
    }
  }

  function handleTemplate(brief: string, modules: string[]) {
    setSelectedModules(new Set(modules))
    void sendMessage(brief, modules)
  }

  function handleClear() {
    cancel()
    setRuns([])
    setSessionId(null)
  }

  const isEmpty = runs.length === 0
  const hasFormula = runs.some((r) => r.formula)

  return (
    <div className="h-screen flex bg-slate-100">
      {/* ── Left rail: brief console ── */}
      <aside className="hidden md:flex w-[300px] shrink-0 flex-col bg-slate-950 text-slate-200">
        <div className="px-5 pt-5 pb-4 border-b border-white/10">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-teal-500 flex items-center justify-center shadow-[0_0_20px_rgba(20,184,166,0.35)]">
              <span className="text-white font-bold text-sm">F</span>
            </div>
            <div className="leading-none">
              <div className="font-semibold text-white text-sm tracking-tight">FormulaForge</div>
              <div className="text-[10px] text-slate-500 mt-1">Formulation intelligence</div>
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-5">
          <BriefPanel
            modules={meta?.modules ?? []}
            selected={selectedModules}
            onToggle={toggleModule}
            format={format}
            onFormat={setFormat}
            disabled={loading}
          />
        </div>

        {/* Brief input */}
        <div className="px-5 pb-5 pt-3 border-t border-white/10">
          <label className="text-[10px] font-semibold tracking-[0.14em] text-slate-500 uppercase">
            Formulation brief
          </label>
          <textarea
            rows={3}
            value={input}
            disabled={loading}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault()
                void sendMessage(input)
              }
            }}
            placeholder="e.g. Renal-safe scoopable vanilla, K ≤ 200 mg/serving…"
            className="mt-1.5 w-full rounded-xl bg-white/[0.05] border border-white/10 px-3 py-2.5 text-xs text-slate-200 placeholder:text-slate-600 resize-none focus:outline-none focus:border-teal-500/60 focus:bg-white/[0.08] transition-colors"
          />
          {loading ? (
            <button
              onClick={cancel}
              className="mt-2 w-full rounded-xl border border-white/15 text-slate-300 text-xs font-medium py-2.5 hover:bg-white/5 transition-colors"
            >
              Stop generation
            </button>
          ) : (
            <button
              onClick={() => void sendMessage(input)}
              disabled={!input.trim()}
              className="mt-2 w-full rounded-xl bg-teal-500 text-white text-xs font-semibold py-2.5 hover:bg-teal-400 disabled:opacity-40 disabled:hover:bg-teal-500 transition-colors"
            >
              Generate verified formula
            </button>
          )}
          <p className="text-[9px] text-slate-600 mt-2.5 leading-relaxed">
            Formulation tool for qualified professionals. No medical claims — thresholds
            require professional review.
          </p>
        </div>
      </aside>

      {/* ── Main canvas ── */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <header className="shrink-0 bg-white/80 backdrop-blur border-b border-slate-200">
          <div className="px-4 sm:px-8 h-12 flex items-center justify-between">
            <div className="flex items-center gap-2 min-w-0">
              <span className="md:hidden w-6 h-6 rounded-md bg-teal-500 flex items-center justify-center text-white text-[10px] font-bold shrink-0">F</span>
              <span className="text-xs font-medium text-slate-700">Formulation workspace</span>
            </div>
            <div className="flex items-center gap-2 text-[10px]">
              <span className="hidden sm:inline-flex items-center gap-1.5 px-2 py-1 rounded-full bg-slate-100 text-slate-500">
                <span className="w-1.5 h-1.5 rounded-full bg-teal-500" />
                Validation gate active
              </span>
              {meta && (
                <span className="hidden lg:inline px-2 py-1 rounded-full bg-slate-100 text-slate-500">
                  Dataset {meta.dataset_version} · {meta.ingredient_count} ingredients
                </span>
              )}
              {!isEmpty && (
                <button onClick={handleClear} className="px-2 py-1 rounded-full text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors">
                  New session
                </button>
              )}
              <a
                href="https://github.com/craft-b/formula-forge"
                target="_blank"
                rel="noreferrer"
                className="px-2 py-1 rounded-full text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
              >
                GitHub
              </a>
            </div>
          </div>
        </header>

        {/* Feed */}
        <main className="flex-1 overflow-y-auto">
          <div className="px-4 sm:px-8 py-6 pb-10 max-w-4xl mx-auto w-full">
            {isEmpty ? (
              <Hero meta={meta} onTemplate={handleTemplate} />
            ) : (
              <div className="space-y-5">
                {runs.map((run, i) =>
                  run.role === "user" ? (
                    <BriefRow key={i} run={run} />
                  ) : (
                    <AnswerBlock key={i} run={run} />
                  )
                )}
                {loading && runs[runs.length - 1]?.role === "user" && <PipelineProgress />}
                <div ref={bottomRef} />
              </div>
            )}
          </div>
        </main>

        {/* Refine bar (appears once a formula exists) */}
        {hasFormula && (
          <div className="shrink-0 border-t border-slate-200 bg-white">
            <div className="px-4 sm:px-8 py-3 max-w-4xl mx-auto w-full flex gap-2">
              <input
                value={followUp}
                disabled={loading}
                onChange={(e) => setFollowUp(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                    void sendMessage(followUp)
                  }
                }}
                placeholder="Refine the formula — e.g. “now make it dairy-free” or “reduce potassium 15%”"
                className="flex-1 px-4 py-2.5 text-sm border border-slate-200 rounded-xl bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-teal-400 focus:border-transparent placeholder:text-slate-400 transition-colors"
              />
              <button
                onClick={() => (loading ? cancel() : void sendMessage(followUp))}
                disabled={!loading && !followUp.trim()}
                className={`rounded-xl px-5 text-sm font-medium transition-colors ${
                  loading
                    ? "border border-slate-300 text-slate-600 hover:bg-slate-50"
                    : "bg-teal-600 hover:bg-teal-700 text-white disabled:opacity-40"
                }`}
              >
                {loading ? "Stop" : "Refine"}
              </button>
            </div>
          </div>
        )}

        {/* Mobile brief input (rail hidden below md) */}
        <div className="md:hidden shrink-0 border-t border-slate-200 bg-white px-4 py-3 flex gap-2">
          <input
            value={input}
            disabled={loading}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                void sendMessage(input)
              }
            }}
            placeholder="Describe a formulation target…"
            className="flex-1 px-4 py-2.5 text-sm border border-slate-200 rounded-xl bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-teal-400 placeholder:text-slate-400"
          />
          <button
            onClick={() => (loading ? cancel() : void sendMessage(input))}
            disabled={!loading && !input.trim()}
            className="rounded-xl px-4 text-sm font-medium bg-teal-600 text-white disabled:opacity-40"
          >
            {loading ? "Stop" : "Go"}
          </button>
        </div>
      </div>
    </div>
  )
}
