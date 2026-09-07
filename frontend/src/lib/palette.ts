// Composition palette for the mix-composition bar.
//
// Validated with the dataviz six-checks (lightness band, chroma floor, CVD
// separation, contrast vs surface) — do not swap hues without re-validating:
//   composition categorical: teal #0d9488 · indigo #4f46e5 · amber #d97706 · fuchsia #c026d3
// Water is the neutral remainder track, not a category. Status colors are
// reserved (pass/fail/warn) and always ship with an icon + label.
//
// This lives outside viz.tsx because it is data shared across modules, not a
// component: viz.tsx declared it but never used it, and FormulaReport was the
// only consumer.

export const COMPOSITION_COLORS = {
  fat: "#0d9488",
  msnf: "#4f46e5",
  sugars: "#d97706",
  other: "#c026d3",
  water: "#e2e8f0",
} as const
