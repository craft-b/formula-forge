// Visualization primitives for the formulation workspace.
// Palette validated with the dataviz six-checks (lightness band, chroma floor,
// CVD separation, contrast vs surface) — do not swap hues without re-validating:
//   composition categorical: teal #0d9488 · indigo #4f46e5 · amber #d97706 · fuchsia #c026d3
// Water is the neutral remainder track, not a category. Status colors are
// reserved (pass/fail/warn) and always ship with an icon + label.

import type { ReactNode } from "react"

export const COMPOSITION_COLORS = {
  fat: "#0d9488",
  msnf: "#4f46e5",
  sugars: "#d97706",
  other: "#c026d3",
  water: "#e2e8f0",
} as const

// ── Stat tile ─────────────────────────────────────────────────────────────────

export function StatTile({
  label,
  value,
  unit,
  estimated,
  hint,
}: {
  label: string
  value: string | number
  unit?: string
  estimated?: boolean
  hint?: string
}) {
  return (
    <div className="bg-white border border-slate-200/80 rounded-xl px-3.5 py-3" title={hint}>
      <div className="text-[11px] text-slate-500 font-medium flex items-center gap-1.5">
        <span className="truncate">{label}</span>
        {estimated !== undefined &&
          (estimated ? (
            <span title="Model-estimated" className="text-amber-600 font-semibold shrink-0">~</span>
          ) : (
            <span title="Rule-verified (computed)" className="text-teal-600 shrink-0">✓</span>
          ))}
      </div>
      <div className="text-lg font-semibold text-slate-900 mt-1 leading-none">
        {value}
        {unit && <span className="text-[11px] font-normal text-slate-400 ml-1">{unit}</span>}
      </div>
    </div>
  )
}

// ── Bullet bar: value against a target band (PAC / POD) ───────────────────────

export function BulletBand({
  label,
  value,
  bandLo,
  bandHi,
  domainLo,
  domainHi,
  caption,
}: {
  label: string
  value: number
  bandLo: number
  bandHi: number
  domainLo: number
  domainHi: number
  caption: string
}) {
  const clamp = (v: number) => Math.min(Math.max(v, domainLo), domainHi)
  const pct = (v: number) => ((clamp(v) - domainLo) / (domainHi - domainLo)) * 100
  const inBand = value >= bandLo && value <= bandHi

  return (
    <div title={`${label} ${value} — target ${bandLo}–${bandHi}`}>
      <div className="flex justify-between items-baseline mb-1.5">
        <span className="text-[11px] font-medium text-slate-500">{label}</span>
        <span className="text-xs font-semibold text-slate-800 tabular-nums">
          {value.toFixed(1)}
          <span className={`ml-1.5 text-[10px] font-medium ${inBand ? "text-teal-700" : "text-amber-700"}`}>
            {inBand ? "in band" : value < bandLo ? "below band" : "above band"}
          </span>
        </span>
      </div>
      <div className="relative h-3 rounded-full bg-slate-100">
        {/* target band */}
        <div
          className="absolute inset-y-0 bg-teal-600/15 border-x border-teal-600/30"
          style={{ left: `${pct(bandLo)}%`, width: `${pct(bandHi) - pct(bandLo)}%` }}
        />
        {/* value marker: 2px line with surface ring */}
        <div
          className="absolute -inset-y-0.5 w-[2px] bg-slate-800 ring-2 ring-white rounded-full"
          style={{ left: `calc(${pct(value)}% - 1px)` }}
        />
      </div>
      <div className="flex justify-between mt-1 text-[10px] text-slate-400 tabular-nums">
        <span>{domainLo}</span>
        <span className="text-slate-500">target {bandLo}–{bandHi}</span>
        <span>{domainHi}</span>
      </div>
      <p className="text-[10px] text-slate-400 mt-0.5">{caption}</p>
    </div>
  )
}

// ── 100% stacked composition bar ──────────────────────────────────────────────

export interface Segment {
  key: string
  label: string
  value: number // percentage points of the mix
  color: string
}

export function CompositionBar({ segments }: { segments: Segment[] }) {
  const shown = segments.filter((s) => s.value > 0.05)
  return (
    <div>
      {/* 2px surface gaps between segments via flex gap on a white background */}
      <div className="flex h-4 rounded-md overflow-hidden bg-white gap-[2px]">
        {shown.map((s) => (
          <div
            key={s.key}
            title={`${s.label} ${s.value.toFixed(1)}%`}
            className="first:rounded-l-md last:rounded-r-md transition-opacity hover:opacity-80"
            style={{ width: `${s.value}%`, backgroundColor: s.color }}
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2">
        {shown.map((s) => (
          <span key={s.key} className="inline-flex items-center gap-1.5 text-[11px] text-slate-600">
            <span className="w-2.5 h-2.5 rounded-[3px]" style={{ backgroundColor: s.color }} />
            {s.label}
            <span className="text-slate-400 tabular-nums">{s.value.toFixed(1)}%</span>
          </span>
        ))}
      </div>
    </div>
  )
}

// ── Measured-vs-limit compliance row ──────────────────────────────────────────

export function LimitRow({
  name,
  explanation,
  measured,
  limit,
  severity,
}: {
  name: string
  explanation: string
  measured?: number | null
  limit?: number | null
  severity: "error" | "warn"
}) {
  const isError = severity === "error"
  const icon = isError ? "✕" : "!"
  const tone = isError
    ? { text: "text-red-700", fill: "#b91c1c", chip: "bg-red-50 border-red-100" }
    : { text: "text-amber-700", fill: "#b45309", chip: "bg-amber-50 border-amber-100" }
  const hasBar = measured != null && limit != null && limit > 0
  const ratio = hasBar ? Math.min(measured! / limit!, 1.6) : 0

  return (
    <div className={`rounded-lg border px-3.5 py-2.5 ${tone.chip}`}>
      <div className="flex items-start gap-2.5">
        <span className={`text-xs font-bold mt-px ${tone.text}`}>{icon}</span>
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline justify-between gap-3">
            <span className={`text-xs font-semibold ${tone.text}`}>{name}</span>
            {hasBar && (
              <span className="text-[11px] text-slate-600 tabular-nums shrink-0">
                {measured} <span className="text-slate-400">/ limit {limit}</span>
              </span>
            )}
          </div>
          <p className="text-[11px] text-slate-600 mt-0.5 leading-relaxed">{explanation}</p>
          {hasBar && (
            <div className="relative h-1.5 mt-2 rounded-full bg-white/80">
              <div
                className="absolute inset-y-0 left-0 rounded-full"
                style={{ width: `${Math.min((ratio / 1.6) * 100, 100)}%`, backgroundColor: tone.fill }}
              />
              {/* limit tick at 1.0 of the 1.6 domain */}
              <div className="absolute -inset-y-0.5 w-[2px] bg-slate-700 ring-2 ring-white rounded-full" style={{ left: `${(1 / 1.6) * 100}%` }} />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Status pill ───────────────────────────────────────────────────────────────

export function StatusPill({ ok, children }: { ok: boolean; children: ReactNode }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 text-[11px] font-semibold px-2.5 py-1 rounded-full ${
        ok ? "bg-teal-50 text-teal-700 border border-teal-200" : "bg-red-50 text-red-700 border border-red-200"
      }`}
    >
      <span>{ok ? "✓" : "✕"}</span>
      {children}
    </span>
  )
}
