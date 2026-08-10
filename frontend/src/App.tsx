import { useEffect, useRef, useState } from "react"
import { ArrowUpRight, Database, FlaskConical, Leaf, ShieldCheck, SlidersHorizontal, X, Zap } from "lucide-react"
import { BriefPanel } from "@/components/BriefPanel"
import { FormulaReport, RejectionReport } from "@/components/FormulaReport"
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
  /** Footnote shown when a run behaved differently than the user likely expected. */
  hint?: string
}

// ── Pipeline progress (shown while a run is in flight) ───────────────────────

const PIPELINE_STEPS = [
  { label: "Propose", detail: "LLM drafts an ingredient structure" },
  { label: "Resolve", detail: "each line matched to the governed library" },
  { label: "Compute", detail: "nutrients, PAC/POD, solids — deterministically" },
  { label: "Validate", detail: "physics bands + active compliance rules" },
  { label: "Score", detail: "scoopability and cost estimates" },
]

function PipelineProgress() {
  const [step, setStep] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setStep((s) => Math.min(s + 1, PIPELINE_STEPS.length - 1)), 1400)
    return () => clearInterval(t)
  }, [])
  return (
    <div className="rounded-2xl border border-slate-200 bg-white px-6 py-5 ff-rise" role="status" aria-label="Formulation pipeline running">
      <div className="flex items-center gap-0">
        {PIPELINE_STEPS.map((s, i) => (
          <div key={s.label} className="flex items-center">
            <div className="flex flex-col items-center gap-1.5">
              <span
                className={`w-2.5 h-2.5 rounded-full transition-colors ${
                  i < step ? "bg-teal-500" : i === step ? "bg-teal-500 animate-pulse" : "bg-slate-200"
                }`}
              />
              <span className={`text-micro font-medium ${i <= step ? "text-slate-700" : "text-slate-500"}`}>
                {s.label}
              </span>
            </div>
            {i < PIPELINE_STEPS.length - 1 && (
              <span className={`w-8 sm:w-14 h-px mx-1 mb-4 transition-colors ${i < step ? "bg-teal-400" : "bg-slate-200"}`} />
            )}
          </div>
        ))}
        <span className="ml-auto mb-4 hidden sm:inline text-meta text-slate-500">
          LLM proposes · domain verifies
        </span>
      </div>
      <p className="text-meta mt-1.5 ff-shimmer-text w-fit">
        {PIPELINE_STEPS[step].label} — {PIPELINE_STEPS[step].detail}…
      </p>
    </div>
  )
}

// ── Run rows ──────────────────────────────────────────────────────────────────

// Deliberately no format/module chips here: at send time the run's intent
// (formula vs question) isn't known, so chips would mislabel plain questions.
// The authoritative chips render on the FormulaReport from validated data.
function BriefRow({ run, index }: { run: Run; index: number }) {
  return (
    <div className="flex items-baseline gap-3 flex-wrap ff-rise pt-1">
      <span className="text-micro font-semibold tracking-[0.14em] text-slate-600 uppercase shrink-0 num">
        Brief {String(index).padStart(2, "0")}
      </span>
      <span className="text-sm font-medium text-slate-800">{run.content}</span>
      <span className="flex-1 border-t border-dashed border-slate-200 translate-y-[-3px] hidden sm:block" aria-hidden />
    </div>
  )
}

function AnswerBlock({
  run,
  version,
  previous,
}: {
  run: Run
  version?: number
  previous?: ValidatedFormula | null
}) {
  if (run.formula) {
    return (
      <div id={version != null ? `formula-v${version}` : undefined} className="scroll-mt-4">
        <FormulaReport formula={run.formula} version={version} previous={previous} />
      </div>
    )
  }
  if (run.rejection) return <RejectionReport rejection={run.rejection} />
  return (
    <div className="rounded-2xl border border-slate-200 bg-white px-6 py-4 text-sm text-slate-700 leading-relaxed ff-rise">
      <Markdown text={run.content} />
      {run.hint && (
        <p className="mt-3 pt-3 border-t border-slate-100 text-meta text-amber-700 bg-amber-50/60 -mx-6 -mb-4 px-6 py-2.5 rounded-b-2xl">
          {run.hint}
        </p>
      )}
    </div>
  )
}

// ── Empty-state hero ──────────────────────────────────────────────────────────

const TEMPLATES = [
  {
    title: "Renal-safe vanilla",
    brief: "Renal-safe scoopable vanilla ice cream, potassium ≤ 200 mg per serving",
    modules: ["renal"],
    Icon: ShieldCheck,
  },
  {
    title: "Diabetic low-sugar",
    brief: "Low-sugar diabetic-friendly frozen dessert with polyol sweetening",
    modules: ["diabetic"],
    Icon: FlaskConical,
  },
  {
    title: "High-protein recovery",
    brief: "High-protein frozen dessert for post-surgical recovery nutrition",
    modules: ["high_protein"],
    Icon: Zap,
  },
  {
    title: "Vegan chocolate",
    brief: "Vegan chocolate frozen dessert on a coconut base",
    modules: ["vegan"],
    Icon: Leaf,
  },
]

const HERO_PIPELINE = [
  { label: "Propose", detail: "LLM drafts structure" },
  { label: "Resolve", detail: "governed library only" },
  { label: "Compute", detail: "deterministic nutrition" },
  { label: "Validate", detail: "physics + compliance" },
  { label: "Score", detail: "texture & cost" },
]

function Hero({
  meta,
  onTemplate,
}: {
  meta: WorkspaceMeta | null
  onTemplate: (brief: string, modules: string[]) => void
}) {
  // overflow-x-clip: the backdrop below bleeds past the hero on purpose, but the
  // feed's scroll container would otherwise turn that bleed into a real sideways
  // swipe on narrow screens. `clip` contains it without becoming a scroll
  // container itself.
  return (
    <div className="max-w-3xl mx-auto pt-10 sm:pt-14 relative overflow-x-clip">
      <div className="absolute -inset-x-10 -top-6 h-[420px] bg-blueprint pointer-events-none" aria-hidden />
      <div className="relative">
        <p className="text-meta font-semibold tracking-[0.18em] text-teal-700 uppercase ff-rise">
          Constraint-verified formulation
        </p>
        <h1 className="font-heading text-3xl sm:text-[2.7rem] font-semibold text-slate-900 mt-2 leading-[1.12] tracking-[-0.015em] ff-rise ff-rise-1">
          Frozen desserts that meet medical constraints —{" "}
          <span className="text-slate-500">verified before you see them.</span>
        </h1>
        <p className="text-sm text-slate-600 mt-3.5 max-w-xl leading-relaxed ff-rise ff-rise-2">
          The LLM proposes an ingredient structure. A deterministic food-science engine computes
          every nutrient, checks freezing physics and compliance rules, and gates what reaches you.
        </p>

        {/* Evidence strip — hairline-divided, reads like a spec sheet */}
        <div className="mt-9 grid grid-cols-2 sm:grid-cols-4 rounded-2xl border border-slate-200 bg-white/70 backdrop-blur-sm divide-x divide-slate-100 max-sm:divide-y overflow-hidden ff-rise ff-rise-2">
          {[
            { value: meta?.ingredient_count ?? "—", label: "Governed ingredients", hint: "USDA FDC nutrients + curated functional data" },
            { value: meta?.modules.length ?? "—", label: "Constraint modules", hint: "Declarative, versioned rulesets" },
            { value: "12+", label: "Checks per formula", hint: "Mass balance, physics bands, compliance limits" },
            { value: "0", label: "LLM numbers trusted", hint: "All nutrition computed by the domain engine" },
          ].map((s) => (
            <div key={s.label} className="px-4 py-3.5" title={s.hint}>
              <div className="text-xl font-semibold text-slate-900 num font-mono leading-none">{s.value}</div>
              <div className="text-meta font-medium text-slate-600 mt-1.5">{s.label}</div>
            </div>
          ))}
        </div>

        {/* The verification pipeline — the product's moat, stated up front */}
        <div className="mt-3 rounded-2xl border border-slate-200 bg-slate-950 text-slate-300 px-5 py-4 overflow-x-auto no-scrollbar ff-rise ff-rise-3">
          <div className="flex items-center gap-3 min-w-max">
            <span className="text-micro font-semibold tracking-[0.14em] text-slate-400 uppercase shrink-0">
              Pipeline
            </span>
            {HERO_PIPELINE.map((s, i) => (
              <div key={s.label} className="flex items-center gap-3">
                <div>
                  <div className="text-meta font-semibold text-slate-100 flex items-center gap-1.5">
                    <span className={`w-1.5 h-1.5 rounded-full ${i === 0 ? "bg-amber-400" : "bg-teal-400"}`} aria-hidden />
                    {s.label}
                  </div>
                  <div className="text-micro text-slate-400 mt-0.5">{s.detail}</div>
                </div>
                {i < HERO_PIPELINE.length - 1 && <span className="text-slate-400" aria-hidden>→</span>}
              </div>
            ))}
          </div>
          <div className="flex justify-end mt-2 min-w-max">
            <span className="text-micro text-slate-400">
              <span className="text-amber-400">●</span> model &nbsp;<span className="text-teal-400">●</span> deterministic — the gate between them is the product
            </span>
          </div>
        </div>

        <h2 className="text-meta font-semibold text-slate-600 uppercase tracking-[0.08em] mt-10 mb-2.5 ff-rise ff-rise-3">
          Start from a template
        </h2>
        <div className="grid sm:grid-cols-2 gap-2 ff-rise ff-rise-4">
          {TEMPLATES.map((t) => (
            <button
              key={t.title}
              onClick={() => onTemplate(t.brief, t.modules)}
              className="text-left rounded-xl border border-slate-200 bg-white px-4 py-3.5 hover:border-teal-400/60 hover:shadow-[0_2px_12px_rgba(13,148,136,0.08)] transition-all group relative"
            >
              <span className="flex items-center gap-2">
                <t.Icon className="w-3.5 h-3.5 text-teal-700" aria-hidden />
                <span className="text-sm font-medium text-slate-800 group-hover:text-teal-800">
                  {t.title}
                </span>
                <ArrowUpRight className="w-3.5 h-3.5 text-slate-400 group-hover:text-teal-600 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform ml-auto" aria-hidden />
              </span>
              <span className="block text-xs text-slate-500 mt-1 leading-relaxed">{t.brief}</span>
            </button>
          ))}
        </div>
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
  // Below lg the rail is hidden, so the same panel opens as a sheet. Without
  // this the product format and every dietary constraint are unreachable on a
  // phone or tablet — the toggles are the product, not chrome.
  const [panelOpen, setPanelOpen] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [runs, loading])

  useEffect(() => () => abortRef.current?.abort(), [])

  // Escape closes the constraint sheet, and the body stays locked while it is
  // open so the feed behind it doesn't scroll under the user's finger.
  useEffect(() => {
    if (!panelOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setPanelOpen(false)
    }
    window.addEventListener("keydown", onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = "hidden"
    return () => {
      window.removeEventListener("keydown", onKey)
      document.body.style.overflow = prev
    }
  }, [panelOpen])

  // Idea Stream deep-link: /app?brief=...&modules=a,b prefills the console so
  // a trend concept lands ready to generate (never auto-runs — the user sends).
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const brief = params.get("brief")
    const mods = params.get("modules")
    if (brief) setInput(brief)
    if (mods) setSelectedModules(new Set(mods.split(",").filter(Boolean)))
    if (brief || mods) window.history.replaceState(null, "", "/app")
  }, [])

  // Meta powers the module toggles and evidence strip. Retry with backoff:
  // the demo backend cold-starts (~50 s on Render), and a single failed fetch
  // would leave the rail permanently empty.
  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout>
    const attempt = (n: number) => {
      fetch(`${API_URL}/api/meta`)
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
        .then((m) => {
          if (!cancelled && m) setMeta(m)
        })
        .catch(() => {
          if (!cancelled && n < 20) timer = setTimeout(() => attempt(n + 1), 5000)
        })
    }
    attempt(0)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
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

  // intent "formulate" forces the backend's formula path — used by the
  // "Generate verified formula" CTA and templates so they can never fall
  // through to a plain Q&A answer that ignores the constraint modules.
  async function sendMessage(text: string, moduleOverride?: string[], intent?: "formulate") {
    if (!text.trim() || loading) return
    const modules = moduleOverride ?? Array.from(selectedModules)

    setInput("")
    setFollowUp("")
    setRuns((prev) => [...prev, { role: "user", content: text }])
    setLoading(true)

    const controller = new AbortController()
    abortRef.current = controller
    let gotAnswer = false
    let answerKind: "tokens" | "structured" | null = null

    try {
      const res = await fetch(`${API_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          session_id: sessionId,
          modules,
          product_format: format,
          intent: intent ?? null,
        }),
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
            answerKind ??= "tokens"
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
            answerKind = "structured"
            setRuns((prev) => [...prev, { role: "assistant", content: event.response, formula: event.formula }])
            // The backend unions rail toggles with modules detected in the brief
            // text; reflect what was actually enforced so the rail never lies.
            const enforced = event.formula.validation.active_modules
            if (enforced) setSelectedModules(new Set(enforced))
          } else if (event.type === "rejection") {
            gotAnswer = true
            answerKind = "structured"
            setRuns((prev) => [...prev, { role: "assistant", content: event.response, rejection: event.rejection }])
          } else if (event.type === "error") {
            gotAnswer = true
            answerKind = "structured"
            setRuns((prev) => [...prev, { role: "assistant", content: event.message }])
          } else if (event.type === "done") {
            setSessionId(event.session_id)
          }
        }
      }
      // The stream can complete without emitting an answer (agent produced no
      // output). Never leave the formulator staring at a silent feed.
      if (!gotAnswer) {
        setRuns((prev) => [...prev, {
          role: "assistant",
          content: "The run completed without a result. Try rephrasing the brief — e.g. start with *\"Create a formula for…\"* — or start a new session.",
        }])
      }
      // Transparency: the brief was answered as a question, but constraint
      // modules were selected — tell the formulator why no report appeared.
      if (answerKind === "tokens" && modules.length > 0 && intent !== "formulate") {
        setRuns((prev) => {
          const next = [...prev]
          const last = next[next.length - 1]
          if (last?.role === "assistant" && !last.formula && !last.rejection) {
            next[next.length - 1] = {
              ...last,
              hint: "This was answered as a question, so the selected constraint modules were not applied. Use “Generate verified formula” or start the brief with “Create a formula for…” to run the verified pipeline.",
            }
          }
          return next
        })
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
    void sendMessage(brief, modules, "formulate")
  }

  function handleClear() {
    cancel()
    setRuns([])
    setSessionId(null)
  }

  const isEmpty = runs.length === 0
  const hasFormula = runs.some((r) => r.formula)
  let briefNo = 0

  // Version bookkeeping: the nth formula in the feed is vn; each formula run
  // also knows its predecessor so the report can render a verified diff.
  const versionByRunIndex = new Map<number, { version: number; previous: ValidatedFormula | null }>()
  {
    let prev: ValidatedFormula | null = null
    let v = 0
    runs.forEach((run, i) => {
      if (run.formula) {
        v += 1
        versionByRunIndex.set(i, { version: v, previous: prev })
        prev = run.formula
      }
    })
  }
  const versionCount = versionByRunIndex.size

  // h-dvh, not h-screen: on mobile 100vh is the URL-bar-hidden height, which
  // pushes the brief input below the visible viewport on load.
  return (
    <div className="h-dvh flex bg-slate-100">
      {/* Left rail: brief console. Shown at lg, not md — a 300px rail against a
          768px tablet leaves a canvas narrower than a phone gets full-bleed,
          while the report's sm: breakpoints still render their wide layout. */}
      <aside className="hidden lg:flex w-[300px] xl:w-[336px] shrink-0 flex-col bg-slate-950 text-slate-200 bg-rail-glow print-hide">
        <div className="px-5 pt-5 pb-4 border-b border-white/10">
          <a href="/" className="flex items-center gap-2.5" title="About FormulaForge">
            <div className="w-8 h-8 rounded-lg bg-teal-500 flex items-center justify-center shadow-[0_0_20px_rgba(20,184,166,0.35)]">
              <FlaskConical className="w-4 h-4 text-white" aria-hidden />
            </div>
            <div className="leading-none">
              <div className="font-semibold text-white text-sm tracking-tight">FormulaForge</div>
              <div className="text-micro text-slate-400 mt-1">Formulation intelligence</div>
            </div>
          </a>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-5 rail-scroll">
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
          <div className="flex items-baseline justify-between">
            <label htmlFor="brief-input" className="text-micro font-semibold tracking-[0.14em] text-slate-400 uppercase">
              Formulation brief
            </label>
            <span className="text-micro text-slate-400 border border-white/10 rounded px-1 py-px" aria-hidden>↵ to run</span>
          </div>
          <textarea
            id="brief-input"
            rows={3}
            value={input}
            disabled={loading}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault()
                void sendMessage(input, undefined, "formulate")
              }
            }}
            placeholder="e.g. Renal-safe scoopable vanilla, K ≤ 200 mg/serving…"
            className="mt-1.5 w-full rounded-xl bg-white/[0.05] border border-white/10 px-3 py-2.5 text-xs text-slate-200 placeholder:text-slate-400 resize-none focus:outline-none focus:border-teal-500/60 focus:bg-white/[0.08] transition-colors"
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
              onClick={() => void sendMessage(input, undefined, "formulate")}
              disabled={!input.trim()}
              className="mt-2 w-full rounded-xl bg-teal-500 text-slate-950 text-xs font-semibold py-2.5 hover:bg-teal-400 disabled:opacity-40 disabled:hover:bg-teal-500 transition-colors"
            >
              Generate verified formula
            </button>
          )}
          <p className="text-micro text-slate-400 mt-2.5 leading-relaxed">
            Formulation tool for qualified professionals. No medical claims — thresholds
            require professional review.
          </p>
        </div>
      </aside>

      {/* ── Main canvas ── */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <header className="shrink-0 bg-white/80 backdrop-blur border-b border-slate-200 print-hide">
          <div className="px-4 sm:px-8 h-12 flex items-center justify-between">
            <div className="flex items-center gap-2 min-w-0">
              <span className="lg:hidden w-6 h-6 rounded-md bg-teal-500 flex items-center justify-center shrink-0">
                <FlaskConical className="w-3 h-3 text-white" aria-hidden />
              </span>
              <span className="text-xs font-medium text-slate-700">Formulation workspace</span>
              <button
                onClick={() => setPanelOpen(true)}
                aria-expanded={panelOpen}
                aria-controls="constraint-sheet"
                className="lg:hidden inline-flex items-center gap-1.5 rounded-full border border-slate-300 px-2.5 py-1 text-micro font-medium text-slate-600 hover:border-slate-400 hover:text-slate-900 transition-colors"
              >
                <SlidersHorizontal className="w-3 h-3" aria-hidden />
                Constraints
                {selectedModules.size > 0 && (
                  <span className="num rounded-full bg-teal-600 text-white px-1.5 leading-[1.4]">
                    {selectedModules.size}
                  </span>
                )}
              </button>
            </div>
            <div className="flex items-center gap-2 text-micro">
              <span className="hidden sm:inline-flex items-center gap-1.5 px-2 py-1 rounded-full bg-slate-100 text-slate-600">
                <span className="w-1.5 h-1.5 rounded-full bg-teal-500" aria-hidden />
                Validation gate active
              </span>
              {meta && (
                <span className="hidden lg:inline-flex items-center gap-1.5 px-2 py-1 rounded-full bg-slate-100 text-slate-600 num">
                  <Database className="w-3 h-3" aria-hidden />
                  Dataset {meta.dataset_version} · {meta.ingredient_count} ingredients
                </span>
              )}
              <a
                href="/ideas"
                className="hidden sm:inline px-2 py-1 rounded-full text-slate-500 hover:text-slate-700 hover:bg-slate-100 transition-colors"
              >
                Idea stream
              </a>
              {!isEmpty && (
                <button onClick={handleClear} className="px-2 py-1 rounded-full text-slate-500 hover:text-slate-700 hover:bg-slate-100 transition-colors">
                  New session
                </button>
              )}
              <a
                href="https://github.com/craft-b/formula-forge"
                target="_blank"
                rel="noreferrer"
                className="px-2 py-1 rounded-full text-slate-500 hover:text-slate-700 hover:bg-slate-100 transition-colors"
              >
                GitHub
              </a>
            </div>
          </div>
        </header>

        {/* Feed */}
        <main className="flex-1 overflow-y-auto">
          <div className="px-4 sm:px-8 py-6 pb-10 max-w-4xl xl:max-w-5xl 2xl:max-w-6xl mx-auto w-full">
            {isEmpty ? (
              <Hero meta={meta} onTemplate={handleTemplate} />
            ) : (
              <div className="space-y-5" role="log" aria-live="polite">
                {versionCount > 1 && (
                  <nav
                    aria-label="Formula versions"
                    className="sticky top-2 z-10 flex justify-end print-hide"
                  >
                    <div className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white/85 backdrop-blur px-1.5 py-1 shadow-sm">
                      <span className="text-micro font-semibold tracking-[0.1em] text-slate-500 uppercase pl-1.5 pr-0.5">
                        Versions
                      </span>
                      {Array.from({ length: versionCount }, (_, vi) => (
                        <button
                          key={vi}
                          onClick={() =>
                            document
                              .getElementById(`formula-v${vi + 1}`)
                              ?.scrollIntoView({ behavior: "smooth", block: "start" })
                          }
                          className="num text-meta font-semibold px-2 py-0.5 rounded-full text-slate-600 hover:bg-slate-900 hover:text-white transition-colors"
                        >
                          v{vi + 1}
                        </button>
                      ))}
                    </div>
                  </nav>
                )}
                {runs.map((run, i) =>
                  run.role === "user" ? (
                    <BriefRow key={i} run={run} index={++briefNo} />
                  ) : (
                    <AnswerBlock
                      key={i}
                      run={run}
                      version={versionByRunIndex.get(i)?.version}
                      previous={versionByRunIndex.get(i)?.previous}
                    />
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
          <div className="shrink-0 border-t border-slate-200 bg-white print-hide">
            <div className="px-4 sm:px-8 py-3 max-w-4xl xl:max-w-5xl 2xl:max-w-6xl mx-auto w-full flex gap-2">
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
                aria-label="Refine the formula"
                className="flex-1 px-4 py-2.5 text-sm border border-slate-200 rounded-xl bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-teal-400 focus:border-transparent placeholder:text-slate-500 transition-colors"
              />
              <button
                onClick={() => (loading ? cancel() : void sendMessage(followUp))}
                disabled={!loading && !followUp.trim()}
                className={`rounded-xl px-5 text-sm font-medium transition-colors ${
                  loading
                    ? "border border-slate-300 text-slate-600 hover:bg-slate-50"
                    : "bg-teal-700 hover:bg-teal-600 text-white disabled:opacity-40"
                }`}
              >
                {loading ? "Stop" : "Refine"}
              </button>
            </div>
          </div>
        )}

        {/* Mobile brief input — stands in for the rail below lg. Only until the
            first formula: after that the refine bar above is the input, and
            rendering both would stack two near-identical fields on a phone.
            Sends intent "formulate" so a phone brief runs the same verified
            pipeline as the rail's CTA rather than falling through to Q&A. */}
        {!hasFormula && (
          <div className="lg:hidden shrink-0 border-t border-slate-200 bg-white px-4 py-3 flex gap-2 print-hide">
            <input
              value={input}
              disabled={loading}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                  void sendMessage(input, undefined, "formulate")
                }
              }}
              placeholder="Describe a formulation target…"
              aria-label="Formulation brief"
              className="flex-1 px-4 py-2.5 text-sm border border-slate-200 rounded-xl bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-teal-400 placeholder:text-slate-500"
            />
            <button
              onClick={() => (loading ? cancel() : void sendMessage(input, undefined, "formulate"))}
              disabled={!loading && !input.trim()}
              className="rounded-xl px-4 text-sm font-medium bg-teal-700 text-white disabled:opacity-40"
            >
              {loading ? "Stop" : "Go"}
            </button>
          </div>
        )}
      </div>

      {/* ── Constraint sheet (below lg, where the rail is hidden) ── */}
      {panelOpen && (
        <div className="lg:hidden fixed inset-0 z-50 print-hide">
          <div
            className="absolute inset-0 bg-slate-950/60 backdrop-blur-[2px]"
            onClick={() => setPanelOpen(false)}
            aria-hidden
          />
          <div
            id="constraint-sheet"
            role="dialog"
            aria-modal="true"
            aria-label="Product format and dietary constraints"
            className="absolute inset-y-0 left-0 w-[min(22rem,88vw)] flex flex-col bg-slate-950 text-slate-200 bg-rail-glow shadow-2xl ff-rise"
          >
            <div className="flex items-center justify-between px-5 h-12 border-b border-white/10 shrink-0">
              <span className="text-micro font-semibold tracking-[0.14em] text-slate-400 uppercase">
                Formulation setup
              </span>
              <button
                onClick={() => setPanelOpen(false)}
                aria-label="Close constraints"
                className="w-8 h-8 -mr-2 rounded-lg flex items-center justify-center text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
              >
                <X className="w-4 h-4" aria-hidden />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto px-5 py-5 rail-scroll">
              <BriefPanel
                modules={meta?.modules ?? []}
                selected={selectedModules}
                onToggle={toggleModule}
                format={format}
                onFormat={setFormat}
                disabled={loading}
              />
            </div>
            <div className="px-5 py-4 border-t border-white/10 shrink-0">
              <button
                onClick={() => setPanelOpen(false)}
                className="w-full rounded-xl bg-teal-500 text-slate-950 text-xs font-semibold py-2.5 hover:bg-teal-400 transition-colors"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
