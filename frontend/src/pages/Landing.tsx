// Marketing landing page — the editorial front door at "/". Warmer and more
// serif-forward than the workspace (bigger Fraunces moments, paper-white
// ground), but the same token system so the two read as one product. The
// centerpiece is the real FormulaReport component rendered with sample data:
// the brochure layer shows the actual document the engine produces.

import { useEffect } from "react"
import {
  ArrowRight,
  ArrowUpRight,
  FlaskConical,
  HeartPulse,
  Leaf,
  ShieldCheck,
  Snowflake,
} from "lucide-react"
import { FormulaReport } from "@/components/FormulaReport"
import { SAMPLE_FORMULA } from "./sampleFormula"

const PIPELINE = [
  { label: "Propose", detail: "LLM drafts structure", model: true },
  { label: "Resolve", detail: "governed library only", model: false },
  { label: "Compute", detail: "deterministic nutrition", model: false },
  { label: "Validate", detail: "physics + compliance", model: false },
  { label: "Score", detail: "texture & cost", model: false },
]

const USE_CASES = [
  {
    icon: HeartPulse,
    title: "Renal-safe",
    constraint: "K ≤ 200 · P ≤ 120 · Na ≤ 150 mg/serving",
    body: "Desserts dialysis and CKD foodservice can actually serve — potassium, phosphorus, and sodium verified per serving, not estimated.",
  },
  {
    icon: ShieldCheck,
    title: "Diabetic-friendly",
    constraint: "total sugars ≤ 8 g/serving",
    body: "Polyol-sweetened structures with freezing-point physics rebalanced, so low-sugar doesn't mean freezes-like-a-brick.",
  },
  {
    icon: FlaskConical,
    title: "High-protein recovery",
    constraint: "protein ≥ 8 g/serving",
    body: "Post-surgical and geriatric nutrition targets hit without protein sandiness — lactose and MSNF bands enforced.",
  },
  {
    icon: Leaf,
    title: "Vegan / dairy-free",
    constraint: "no dairy, egg, or animal-derived",
    body: "Plant-base rebuilds that keep PAC and POD in the scoopable band when dairy solids leave the mix.",
  },
]

const REPORT_FEATURES = [
  { title: "Provenance on every number", body: "✓ rule-verified vs ~ model-estimated — nothing ambiguous." },
  { title: "Measured vs limit", body: "Compliance failures show the number, the limit, and how far over." },
  { title: "Weigh-out batch sheet", body: "1 / 10 / 100 kg gram conversions, totals, cost — CSV for Excel." },
  { title: "Process method", body: "Pasteurize → homogenize → age → freeze, templated from verified data." },
]

function LaunchButton({ children, ghost }: { children: React.ReactNode; ghost?: boolean }) {
  return (
    <a
      href="/app"
      className={
        ghost
          ? "inline-flex items-center gap-2 rounded-xl border border-slate-300 px-5 py-3 text-sm font-medium text-slate-700 hover:border-slate-500 hover:text-slate-900 transition-colors"
          : "inline-flex items-center gap-2 rounded-xl bg-teal-700 px-5 py-3 text-sm font-semibold text-white hover:bg-teal-600 transition-colors shadow-[0_1px_0_rgba(255,255,255,0.2)_inset,0_8px_24px_rgba(13,148,136,0.25)]"
      }
    >
      {children}
      <ArrowRight className="w-4 h-4" aria-hidden />
    </a>
  )
}

export default function Landing() {
  useEffect(() => {
    document.title = "FormulaForge — AI formulation, physics-verified"
  }, [])

  return (
    <div className="min-h-screen bg-[#faf9f6] text-slate-900">
      {/* ── Nav ── */}
      <header className="sticky top-0 z-20 bg-[#faf9f6]/85 backdrop-blur border-b border-slate-900/5">
        <div className="max-w-6xl mx-auto px-5 sm:px-8 h-14 flex items-center justify-between">
          <a href="/" className="flex items-center gap-2.5">
            <span className="w-7 h-7 rounded-lg bg-teal-600 flex items-center justify-center">
              <FlaskConical className="w-3.5 h-3.5 text-white" aria-hidden />
            </span>
            <span className="font-semibold tracking-tight text-base">FormulaForge</span>
          </a>
          <nav className="flex items-center gap-5 text-data text-slate-600">
            <a href="#moat" className="hidden sm:inline hover:text-slate-900 transition-colors">How it verifies</a>
            <a href="#report" className="hidden sm:inline hover:text-slate-900 transition-colors">The report</a>
            <a href="/ideas" className="hidden sm:inline hover:text-slate-900 transition-colors">Idea stream</a>
            <a
              href="https://github.com/craft-b/formula-forge"
              target="_blank"
              rel="noreferrer"
              className="hidden sm:inline-flex items-center gap-1 hover:text-slate-900 transition-colors"
            >
              GitHub <ArrowUpRight className="w-3 h-3" aria-hidden />
            </a>
            <a
              href="/app"
              className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 text-white text-xs font-semibold px-3.5 py-2 hover:bg-slate-700 transition-colors"
            >
              Launch workspace
            </a>
          </nav>
        </div>
      </header>

      {/* ── Hero ── */}
      <section className="max-w-6xl mx-auto px-5 sm:px-8 pt-16 sm:pt-24 pb-14">
        <p className="text-meta font-semibold tracking-[0.18em] text-teal-700 uppercase ff-rise">
          Formulation intelligence for regulated frozen desserts
        </p>
        <h1 className="font-heading text-[2.6rem] sm:text-[4rem] leading-[1.05] tracking-[-0.02em] font-semibold mt-4 max-w-4xl ff-rise ff-rise-1">
          The model proposes.
          <br />
          <span className="text-teal-700 italic">The physics decide.</span>
        </h1>
        <p className="text-base sm:text-lg text-slate-600 leading-relaxed max-w-2xl mt-6 ff-rise ff-rise-2">
          FormulaForge drafts medical- and institutional-grade ice cream formulations — renal,
          diabetic, high-protein, vegan — then verifies every calorie, milligram, and
          freezing-point value against a governed ingredient library before you ever see it.
          The AI never reports a number it computed itself.
        </p>
        <div className="flex flex-wrap items-center gap-3 mt-8 ff-rise ff-rise-3">
          <LaunchButton>Launch the workspace</LaunchButton>
          <a
            href="#report"
            className="inline-flex items-center gap-2 rounded-xl border border-slate-300 px-5 py-3 text-sm font-medium text-slate-700 hover:border-slate-500 hover:text-slate-900 transition-colors"
          >
            See a verified report
          </a>
        </div>
        <div className="flex flex-wrap gap-x-7 gap-y-2 mt-10 text-data text-slate-600 ff-rise ff-rise-4">
          <span><span className="num font-semibold text-slate-900">34</span> governed ingredients</span>
          <span><span className="num font-semibold text-slate-900">12+</span> checks per formula</span>
          <span><span className="num font-semibold text-slate-900">6</span> constraint modules</span>
          <span><span className="num font-semibold text-slate-900">0</span> LLM numbers trusted</span>
        </div>
      </section>

      {/* ── Credibility strip ── */}
      <section className="border-y border-slate-900/5 bg-white/60">
        <div className="max-w-6xl mx-auto px-5 sm:px-8 py-5 flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="text-meta font-semibold tracking-[0.14em] text-slate-500 uppercase">
            Built from 26 years of CPG R&D
          </span>
          <span className="text-data text-slate-600">
            Post Cereals · Magnum Ice Cream (Unilever) · Talenti · Breyers
          </span>
        </div>
      </section>

      {/* ── The moat (dark statement band) ── */}
      <section id="moat" className="bg-slate-950 bg-rail-glow text-slate-300 scroll-mt-14">
        <div className="max-w-6xl mx-auto px-5 sm:px-8 py-16 sm:py-20">
          <p className="text-meta font-semibold tracking-[0.18em] text-teal-400 uppercase">
            Why it can be trusted
          </p>
          <h2 className="font-heading text-3xl sm:text-[2.5rem] leading-tight tracking-[-0.015em] font-semibold text-white mt-3 max-w-2xl">
            A generative system with a deterministic gate.
          </h2>
          <p className="text-base text-slate-400 leading-relaxed max-w-2xl mt-4">
            The model only proposes an ingredient structure, drawn from a governed library.
            Nutrition, freezing-point depression, sweetness, and compliance are computed by a
            pure food-science engine — and a formula that fails physics or a dietary ruleset
            is rejected with an explanation, never shown as if it worked.
          </p>

          <div className="mt-10 overflow-x-auto no-scrollbar">
            <div className="flex items-center gap-3 min-w-max">
              {PIPELINE.map((step, i) => (
                <div key={step.label} className="flex items-center gap-3">
                  <div className="rounded-xl border border-white/10 bg-white/[0.04] px-4 py-3">
                    <div className="flex items-center gap-2">
                      <span className={`w-1.5 h-1.5 rounded-full ${step.model ? "bg-amber-400" : "bg-teal-400"}`} />
                      <span className="text-data font-semibold text-white">{step.label}</span>
                    </div>
                    <div className="text-meta text-slate-400 mt-1">{step.detail}</div>
                  </div>
                  {i < PIPELINE.length - 1 && <span className="text-slate-400" aria-hidden>→</span>}
                </div>
              ))}
            </div>
            <div className="flex min-w-max mt-3">
              <span className="text-meta text-slate-400">
                <span className="text-amber-400">●</span> model &nbsp;
                <span className="text-teal-400">●</span> deterministic — the gate between them is the product
              </span>
            </div>
          </div>
        </div>
      </section>

      {/* ── Use cases ── */}
      <section className="max-w-6xl mx-auto px-5 sm:px-8 py-16 sm:py-20">
        <h2 className="font-heading text-3xl sm:text-[2.2rem] tracking-[-0.015em] font-semibold max-w-2xl">
          Weeks of dietary scoping, answered in minutes.
        </h2>
        <p className="text-base text-slate-600 leading-relaxed max-w-2xl mt-3">
          Early-stage scoping of constrained frozen desserts wastes weeks on questions a trained
          formulator can answer fast — if the arithmetic is done for them, correctly, every time.
        </p>
        <div className="grid sm:grid-cols-2 gap-4 mt-10">
          {USE_CASES.map((u) => (
            <div key={u.title} className="rounded-2xl border border-slate-900/8 bg-white px-6 py-5 hover:shadow-[0_8px_30px_rgba(15,23,42,0.06)] transition-shadow">
              <div className="flex items-center gap-2.5">
                <span className="w-8 h-8 rounded-lg bg-teal-50 border border-teal-100 flex items-center justify-center">
                  <u.icon className="w-4 h-4 text-teal-700" aria-hidden />
                </span>
                <h3 className="text-base font-semibold text-slate-900">{u.title}</h3>
              </div>
              <p className="num text-meta text-teal-700 font-medium mt-3">{u.constraint}</p>
              <p className="text-data text-slate-600 leading-relaxed mt-1.5">{u.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── The report (live component) ── */}
      <section id="report" className="border-t border-slate-900/5 bg-white/60 scroll-mt-14 overflow-x-clip">
        <div className="max-w-6xl mx-auto px-5 sm:px-8 py-16 sm:py-20">
          <p className="text-meta font-semibold tracking-[0.18em] text-teal-700 uppercase">
            The deliverable
          </p>
          <h2 className="font-heading text-3xl sm:text-[2.2rem] tracking-[-0.015em] font-semibold mt-3 max-w-2xl">
            Not a chat answer — a formula report you can take to the pilot plant.
          </h2>
          <div className="grid sm:grid-cols-4 gap-x-6 gap-y-4 mt-8">
            {REPORT_FEATURES.map((f) => (
              <div key={f.title}>
                <h3 className="text-data font-semibold text-slate-900">{f.title}</h3>
                <p className="text-meta text-slate-600 leading-relaxed mt-1">{f.body}</p>
              </div>
            ))}
          </div>

          <div className="mt-10 relative">
            <div className="absolute -inset-x-6 -top-6 bottom-1/2 bg-blueprint rounded-3xl" aria-hidden />
            <div className="relative max-w-4xl mx-auto">
              <FormulaReport formula={SAMPLE_FORMULA} />
              <p className="text-center text-meta text-slate-500 mt-3">
                Live component with representative data — the batch-size toggle and nutrition
                basis switch work right here. In the workspace, every number comes from the engine.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ── Final CTA ── */}
      <section className="max-w-6xl mx-auto px-5 sm:px-8 py-16 sm:py-24 text-center">
        <Snowflake className="w-6 h-6 text-teal-600 mx-auto" aria-hidden />
        <h2 className="font-heading text-3xl sm:text-[2.6rem] tracking-[-0.015em] font-semibold mt-4">
          Describe the constraint. <span className="italic text-teal-700">Get the formula.</span>
        </h2>
        <p className="text-base text-slate-600 mt-3 max-w-xl mx-auto">
          “Renal-safe scoopable vanilla, potassium ≤ 200 mg per serving” is a complete brief.
        </p>
        <div className="mt-7 flex justify-center">
          <LaunchButton>Launch the workspace</LaunchButton>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="border-t border-slate-900/5">
        <div className="max-w-6xl mx-auto px-5 sm:px-8 py-8 flex flex-wrap items-start justify-between gap-4">
          <div className="text-meta text-slate-600">
            <div className="flex items-center gap-2 text-slate-700 font-semibold">
              <span className="w-5 h-5 rounded-md bg-teal-600 flex items-center justify-center">
                <FlaskConical className="w-3 h-3 text-white" aria-hidden />
              </span>
              FormulaForge
            </div>
            <p className="mt-2 max-w-md leading-relaxed">
              Formulation-design tool for qualified professionals. No medical claims; not a
              medical device. Dietary thresholds are configurable defaults from published
              guidance and require professional review.
            </p>
          </div>
          <div className="flex gap-5 text-meta text-slate-600">
            <a href="/app" className="hover:text-slate-900 transition-colors">Workspace</a>
            <a href="https://github.com/craft-b/formula-forge" target="_blank" rel="noreferrer" className="hover:text-slate-900 transition-colors">GitHub</a>
          </div>
        </div>
      </footer>
    </div>
  )
}
