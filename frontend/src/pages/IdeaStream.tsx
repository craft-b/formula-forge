// The Idea Stream — a ranked board of flavour/product concepts.
//
// The corpus behind it is a hand-curated snapshot: signal values are analyst
// judgement, not measurements, and there is no collection pipeline. The
// ranking over it is deterministic. The UI says both of those things out loud
// rather than letting "stream" imply a live feed.
// Original header comment follows.
// A ranked think-tank of flavor/product concepts sourced
// from consumer-trend intelligence (social listening, artisan menus, brand
// launches, trend reports). Ranking is computed by the backend's deterministic
// scoring engine over the governed corpus; every idea deep-links into the
// workspace with its brief and constraint modules prefilled.

import { useEffect, useState } from "react"
import { ArrowRight, FlaskConical, TrendingUp } from "lucide-react"

const API_URL = import.meta.env.VITE_API_URL

interface IdeaSource {
  type: "tiktok" | "reddit" | "artisan" | "brand" | "report"
  name: string
  note: string
}

interface Idea {
  id: string
  rank: number
  score: number
  title: string
  concept: string
  tags: string[]
  lifecycle: string
  sources: IdeaSource[]
  suggested_brief: string
  module_fits: string[]
  breakdown: Record<string, number>
}

interface Freshness {
  days_since_update: number | null
  status: "current" | "aging" | "stale" | "unknown"
  note: string
}

interface IdeasPayload {
  dataset_version: string
  updated: string
  freshness?: Freshness
  signal_basis?: string
  methodology: string
  ideas: Idea[]
}

const FRESHNESS_STYLE: Record<Freshness["status"], string> = {
  current: "bg-teal-50 text-teal-700 border-teal-200",
  aging: "bg-amber-50 text-amber-800 border-amber-200",
  stale: "bg-rose-50 text-rose-700 border-rose-200",
  unknown: "bg-slate-100 text-slate-600 border-slate-200",
}

function FreshnessChip({ freshness }: { freshness: Freshness }) {
  const days = freshness.days_since_update
  return (
    <span
      title={freshness.note}
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-meta font-medium ${FRESHNESS_STYLE[freshness.status]}`}
    >
      <span className="uppercase tracking-[0.08em]">{freshness.status}</span>
      {days !== null && <span className="num">· {days}d old</span>}
    </span>
  )
}

const SOURCE_STYLE: Record<IdeaSource["type"], string> = {
  tiktok: "bg-fuchsia-50 text-fuchsia-700 border-fuchsia-100",
  reddit: "bg-orange-50 text-orange-700 border-orange-100",
  artisan: "bg-teal-50 text-teal-700 border-teal-100",
  brand: "bg-indigo-50 text-indigo-700 border-indigo-100",
  report: "bg-slate-100 text-slate-600 border-slate-200",
}

const LIFECYCLE_LABEL: Record<string, string> = {
  emerging: "Emerging",
  artisan: "Artisan-proven",
  expanding: "Expanding to mainstream",
  mass: "Mass market",
}

const BREAKDOWN_ORDER = ["social", "momentum", "breadth", "adoption", "feasibility"] as const

function formulateHref(idea: Idea): string {
  const params = new URLSearchParams({ brief: idea.suggested_brief })
  if (idea.module_fits.length) params.set("modules", idea.module_fits.join(","))
  return `/app?${params.toString()}`
}

function ScoreBreakdown({ breakdown }: { breakdown: Record<string, number> }) {
  return (
    <div className="space-y-1">
      {BREAKDOWN_ORDER.map((k) => (
        <div key={k} className="flex items-center gap-2">
          <span className="w-[4.5rem] text-micro uppercase tracking-[0.08em] text-slate-500 text-right shrink-0">
            {k}
          </span>
          <div className="w-24 h-1.5 rounded-full bg-slate-100">
            <div
              className="h-full rounded-full bg-slate-400"
              style={{ width: `${breakdown[k]}%` }}
            />
          </div>
          <span className="num text-micro text-slate-600 w-6">{Math.round(breakdown[k])}</span>
        </div>
      ))}
    </div>
  )
}

function IdeaCard({ idea }: { idea: Idea }) {
  return (
    <article className="rounded-2xl border border-slate-900/8 bg-white px-5 sm:px-6 py-5 hover:shadow-[0_8px_30px_rgba(15,23,42,0.06)] transition-shadow">
      <div className="flex gap-4 sm:gap-5">
        {/* Rank */}
        <div className="shrink-0 w-10 sm:w-12 text-center">
          <div className="num text-2xl sm:text-[1.7rem] font-semibold text-slate-300 leading-none pt-0.5">
            {idea.rank}
          </div>
        </div>

        {/* Body */}
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div className="min-w-0">
              <h3 className="text-base font-semibold text-slate-900">{idea.title}</h3>
              <p className="text-data text-slate-600 leading-relaxed mt-1 max-w-xl">{idea.concept}</p>
            </div>
            {/* Score */}
            <div className="shrink-0 text-right">
              <div className="flex items-baseline gap-1 justify-end">
                <span className="num text-2xl font-semibold text-slate-900">{idea.score.toFixed(1)}</span>
                <span className="text-micro text-slate-500">/100</span>
              </div>
              <span className="text-micro uppercase tracking-[0.1em] text-slate-500">trend score</span>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-1.5 mt-3">
            <span className="inline-flex items-center gap-1 text-micro font-medium px-2 py-0.5 rounded-full bg-slate-900 text-white">
              <TrendingUp className="w-2.5 h-2.5" aria-hidden />
              {LIFECYCLE_LABEL[idea.lifecycle] ?? idea.lifecycle}
            </span>
            {idea.sources.map((s) => (
              <span
                key={s.name}
                title={s.note}
                className={`text-micro font-medium px-2 py-0.5 rounded-full border cursor-help ${SOURCE_STYLE[s.type]}`}
              >
                {s.name}
              </span>
            ))}
          </div>

          <div className="flex items-end justify-between gap-4 flex-wrap mt-4 pt-3 border-t border-slate-100">
            <ScoreBreakdown breakdown={idea.breakdown} />
            <a
              href={formulateHref(idea)}
              className="inline-flex items-center gap-1.5 rounded-lg bg-teal-700 text-white text-xs font-semibold px-3.5 py-2 hover:bg-teal-600 transition-colors shrink-0"
            >
              Formulate this
              <ArrowRight className="w-3.5 h-3.5" aria-hidden />
            </a>
          </div>
        </div>
      </div>
    </article>
  )
}

export default function IdeaStream() {
  const [data, setData] = useState<IdeasPayload | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    document.title = "FormulaForge — Idea Stream"
    fetch(`${API_URL}/api/ideas`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then(setData)
      .catch(() => setError(true))
  }, [])

  return (
    <div className="min-h-screen bg-[#faf9f6] text-slate-900">
      <header className="sticky top-0 z-20 bg-[#faf9f6]/85 backdrop-blur border-b border-slate-900/5">
        <div className="max-w-4xl mx-auto px-5 sm:px-8 h-14 flex items-center justify-between">
          <a href="/" className="flex items-center gap-2.5">
            <span className="w-7 h-7 rounded-lg bg-teal-600 flex items-center justify-center">
              <FlaskConical className="w-3.5 h-3.5 text-white" aria-hidden />
            </span>
            <span className="font-semibold tracking-tight text-base">FormulaForge</span>
          </a>
          <nav className="flex items-center gap-5 text-data text-slate-600">
            <a href="/" className="hidden sm:inline hover:text-slate-900 transition-colors">About</a>
            <a
              href="/app"
              className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 text-white text-xs font-semibold px-3.5 py-2 hover:bg-slate-700 transition-colors"
            >
              Launch workspace
            </a>
          </nav>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-5 sm:px-8 py-12 sm:py-16">
        <p className="text-meta font-semibold tracking-[0.18em] text-teal-700 uppercase ff-rise">
          Consumer-trend intelligence
        </p>
        <h1 className="font-heading text-4xl sm:text-[3rem] leading-[1.08] tracking-[-0.015em] font-semibold mt-3 ff-rise ff-rise-1">
          The Idea Stream
        </h1>
        <p className="text-base text-slate-600 leading-relaxed max-w-2xl mt-4 ff-rise ff-rise-2">
          Flavour and product concepts, ranked by a deterministic scoring engine and ready to
          drop into the workspace as a formulation brief.
        </p>
        <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 px-4 py-3 mt-4 max-w-2xl ff-rise ff-rise-2">
          <p className="text-meta text-slate-600 leading-relaxed">
            <span className="font-semibold text-slate-800">Curated snapshot, not a live feed.</span>{" "}
            The signal values are analyst judgement informed by the references on each card —
            they are not measured from social platforms, and no collection pipeline produces
            them. The ranking over them is fully deterministic and would accept instrumented
            signals unchanged. What a live version would require is written up in{" "}
            <span className="font-medium text-slate-700">docs/IDEA_STREAM.md</span>.
          </p>
        </div>
        {data && (
          <div className="flex flex-wrap items-center gap-x-2 gap-y-2 text-meta text-slate-500 mt-3 ff-rise ff-rise-3">
            {data.freshness && <FreshnessChip freshness={data.freshness} />}
            <span>
              Corpus <span className="num">{data.dataset_version}</span> · curated{" "}
              <span className="num">{data.updated}</span> · {data.ideas.length} concepts · score =
              25% social + 25% momentum + 15% corroborating references + 20% adoption stage +
              15% formulation feasibility
            </span>
          </div>
        )}

        <div className="space-y-3 mt-8">
          {error && (
            <div className="rounded-2xl border border-slate-200 bg-white px-6 py-5 text-sm text-slate-500">
              The idea corpus is waking up (free-tier backend) — refresh in a few seconds.
            </div>
          )}
          {!data && !error && (
            <div className="rounded-2xl border border-slate-200 bg-white px-6 py-5 text-sm text-slate-500">
              Loading ranked ideas…
            </div>
          )}
          {data?.ideas.map((idea) => <IdeaCard key={idea.id} idea={idea} />)}
        </div>

        {data && (
          <p className="text-meta text-slate-500 leading-relaxed max-w-2xl mt-8">
            {data.methodology}
          </p>
        )}
      </main>
    </div>
  )
}
