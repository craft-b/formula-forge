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


---

# The first live run

Routing was scored before any API call. This section is what the model half
found once it ran for real, against `openai/gpt-oss-120b`.

| Metric | Rate | 95% CI | n |
|---|---:|---|---:|
| `schema_valid` | 97% | 84–99% | 32 |
| `grounded` | 100% | 89–100% | 31 |
| `gate_pass_first_try` | 75% | 58–87% | 32 |
| `repair_recovery` | 86% | 49–97% | 7 |
| `constraint_targeting` | 71% | 53–85% | 28 |
| `prose_free_of_numeric_claims` | 0% | 0–11% | 31 |
| `provider_answered` | 78% | 63–88% | 41 |

`grounded` at 100% is the headline worth keeping: across every formula the
model produced, not one ingredient fell outside the governed library. The
library-constrained prompt does its job, so nothing unverifiable ever reached
the composition step.

## F-P1 — Production was down, and /health said ok

**Severity: critical. Found by the eval's first live run.**

Groq retired `llama-3.3-70b-versatile`. Every generation request returned 404
`model_not_found`. Confirmed against production:

```
data: {"type": "error", "message": "The formulation agent encountered an
       error (NotFoundError). Please try again."}
```

Three things kept it invisible:

1. **`/health` reported `"status":"ok"`** with `"chat model initialized"`. The
   probes take no network call by design — a live call per probe would bill
   every uptime check and couple liveness to a third party. The cost of that
   correct decision is that "a client was constructed" and "the model still
   exists" are different questions, and only the first was asked.
2. **The fallback chain could not help.** `llama-3.1-8b-instant` was retired in
   the same sweep. A primary and a fallback from one family retire together.
3. **208 tests and a green CI never saw it**, because every test mocks the LLM.
   That is the exact gap this harness was built for, named in its own docstring
   before it turned out to be real.

**Fixed:** defaults moved to `openai/gpt-oss-120b` / `openai/gpt-oss-20b` —
deliberately from different families — and `verify_model_available` now checks
the configured id against the account's model list once at startup, caching the
verdict for the probe. A definitive absence fails readiness; a failure to check
reports `unverified` and leaves a working instance in rotation.

## F-E5 — The numeric-claim flag fires on every formula

**Severity: medium. A safety signal that always fires is off.**

`prose_free_of_numeric_claims` scored 0/31. That is the detector, not the model.

The pattern matches any number followed by a letter, so it catches processing
parameters:

```
"Age the mix for 4 hours at 4C"      -> flagged
"Pasteurize at 82C for 25 seconds"   -> flagged
"Draw at -6C; harden at -18C"        -> flagged
"Provides roughly 200 mg calcium"    -> flagged   (correct)
```

Only the last is an unverified nutrition claim. The first three are exactly
what the prompt asks notes to contain: *"processing, texture, or regulatory
considerations."* So the UI marks every single formula as carrying unverified
numbers, and a warning that never varies is a warning nobody reads.

Not fixed — this changes user-visible behaviour and deserves a deliberate call.
The shape of a fix is to distinguish a nutrient claim (a quantity in a unit the
domain computes: mg, g, kcal, per serving) from a process parameter (time,
temperature, rpm), rather than treating every digit as suspect.

## Corrections to the harness itself

Three defects in my own code, each found by using it:

- **Rate limits were scored as model failures.** Nine of ten apparent schema
  failures were 429s from the free tier's token ceiling. Uncorrected, the run
  reported 76% schema validity and 60% first-pass gate; excluding provider
  refusals gives 97% and 75%. `classify_error` now separates infrastructure
  from quality, and the throttled share is reported as its own rate.
- **The report printed before the artifacts were written.** The first
  successful live run completed, then died on a Windows cp1252
  `UnicodeEncodeError` from a narrow no-break space in model prose, losing
  every result. Files are now written first.
- **The key check ran before `.env` loaded**, so a valid key looked missing.

None of these would have surfaced without a real run. That is the argument for
running an eval against production infrastructure rather than only against
stubs.
