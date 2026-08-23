# What the live eval found on its first run

The eval harness (`backend/eval/live_eval.py`) was built to catch regressions in
generation quality. It found four existing defects before it made a single API
call — all of them in the deterministic routing layer, which is the half that
decides whether a clinical ruleset is enforced at all.

**All four are fixed.** Each has a named regression test in
`tests/test_formula_forge.py::TestEvalFindingRegressions`, so a future pattern
edit that reintroduces one fails by name rather than as a shifted aggregate.

| Metric | Before | After |
|---|---:|---:|
| `intent_routing` | 78% (64–88%) | **100%** (92–100%) |
| `module_detection` | 89% (77–95%) | **100%** (92–100%) |
| `module_detection_constrained` | 86% (72–94%) | **100%** (91–100%) |

Nothing here was a *new* break. These were pre-existing gaps that no test
covered, because until now nothing scored routing against natural phrasing.

---

## F-E1 — [FIXED] The intent pattern does not recognise the product's own name

**Severity: high for the chat surface.** Ten of 46 briefs route to the Q&A agent
instead of the formula agent.

`_FORMULATION_RE` accepts a verb followed by `formula | formulation | recipe |
product`. It does not accept **`dessert`** or **`ice cream`** — the two things
this application actually makes.

```
Build me a frozen dessert for patients   →  search      ✗
Build me a formula for patients          →  formulate   ✓
Create a chocolate ice cream             →  search      ✗
Create a chocolate recipe                →  formulate   ✓
```

A user who types *"Build me a frozen dessert for hemodialysis patients"* gets a
chat answer, not a formula.

**Mitigation already in place:** the brief-builder's "Generate verified formula"
button sets `intent="formulate"` explicitly and bypasses the regex, so the
primary UI path is unaffected. This bites the free-text chat entry only.

**Fix:** add the product nouns to the alternation, plus a bare-noun form so
`"renal formula"` and `"vegan formula please"` route correctly without a verb.

---

## F-E2 — [FIXED] An ingredient name activates a clinical ruleset

**Severity: medium. False-positive constraint.**

`_MODULE_PATTERNS["low_fat"]` matches `non[\s-]?fat`, which fires on the
*ingredient* **nonfat dry milk**:

```
Formulate a renal dessert with nonfat dry milk  →  ['renal', 'low_fat']   ✗
Formulate a renal dessert with skim milk        →  ['renal']              ✓
```

Naming a common dairy ingredient silently imposes a low-fat clinical ceiling the
user never asked for. The formula is then rejected, or quietly steered, for a
constraint that exists only because of a substring collision.

This is the mirror image of F-E3: same pattern family, opposite failure. One
over-fires on ingredient names, the other under-fires on clinical language.

**Fix:** require the dietary sense — `fat[\s-]?free`, `non[\s-]?fat` only when
not followed by `dry milk` / `milk solids` — or match against the brief with
governed ingredient names masked out first.

---

## F-E3 — [FIXED] Word-boundary anchors miss real clinical vocabulary

**Severity: high. Silent under-constraint — the dangerous direction.**

```
dialysis patients      →  ['renal']    ✓
hemodialysis patients  →  []           ✗
diabetic dessert       →  ['diabetic'] ✓
prediabetic dessert    →  []           ✗
```

`\bdialysis\b` cannot match inside *hemodialysis*; `\bdiabet\w*` cannot match
inside *prediabetic*. Both are the ordinary clinical terms.

This is the worst failure mode in the system. A missed module is not a visible
error — the formula generates, validates against *no* renal ruleset, and passes.
The user receives a clean, verified-looking formula that was never checked
against the constraint that mattered. Every other failure in this document is
loud; this one is silent.

**Fix:** allow a leading-stem prefix (`\w*dialysis`, `(?:pre)?diabet\w*`) and add
`nephrology`, `renal replacement`, `ESRD`.

---

## F-E4 — [FIXED] Clinical intent expressed without keywords is not detected

**Severity: medium.**

```
Create a formula appropriate for a nephrology ward     →  []   (want renal)
Design a dessert that will not spike blood glucose     →  []   (want diabetic)
```

Unambiguous to any dietitian; invisible to a keyword matcher. Unlike F-E3 this
is not a near-miss on an existing pattern — the vocabulary is simply absent.

**Fix:** extend the vocabulary for the cheap wins (`nephrology`, `blood
glucose`, `glycaemic`). The general case is not solvable by regex, and the
honest options are an explicit module picker in the UI (already present in the
brief builder) or a classifier — which is a real decision, not a patch.

---

## What this says about the architecture

The generation path is well defended: the model proposes structure, deterministic
code computes every number, and the validation gate cannot be bypassed. All four
findings sit *upstream* of that defence, in the step that decides which rules to
apply — and a gate that never runs cannot fail.

That is worth stating plainly because it is a general lesson about LLM systems.
The guardrails here are strong and were the obvious thing to test. The routing
that decides whether the guardrails engage was regex, looked trivial, and had
never been scored against a single realistic brief.

## What the fixes were

- **F-E3** — `[a-z]*dialysis` and `(?:pre)?diabet\w*` so a clinical prefix no
  longer defeats the word-boundary anchor.
- **F-E1** — `_PRODUCT_NOUN` now includes `dessert`, `ice cream`, `gelato`,
  `sorbet`, `soft serve`; verbs gained `need` and `want`; and a bare
  `formula|formulation` handles verbless briefs like "renal formula".
- **F-E2** — `non[\s-]?fat(?!\s+(?:dry\s+)?milk)` keeps the dietary sense and
  drops the ingredient one.
- **F-E4** — added `nephrolog\w*`, `esrd`, `end-stage renal`, `blood
  glucose|sugar`, `glyca?emic index|load`, and a numeric protein target.

One of these was caught by its own regression test rather than by review: the
first attempt at British spelling used `glyc[ae]mic`, which matches *glycemic*
and *glycaemic* only if you misread the class as an optional letter. It is one
character (`ae`), not one of two, so the correct form is `glyca?emic`.

## Still open

**Negation is not handled.** "non-diabetic residents" activates the diabetic
ruleset, because `\b` treats the hyphen as a boundary. This was true before
these fixes and remains true. It is the *safe* direction — an over-constrained
formula fails loudly at the gate rather than passing unchecked — which is why it
is not urgent, but it is real. Regex is the wrong tool for negation scope; the
honest options are an explicit module picker (already present in the brief
builder) or a classifier.

## Re-recording the baseline

```bash
cd backend && python -m eval.live_eval --offline --update-baseline
```

The baseline now records 100% across all three routing rates, so the gate
protects the fixed state. Raising it should stay a visible commit: its job is to
stop things getting worse, not to assert that they are good.
