# FormulaForge — Enterprise Design Specification (v1.0, Stage 1)

**Status:** Build-ready spec for a builder model. Companion document: `docs/AUDIT_FINDINGS.md` (finding IDs `F1–F20` referenced throughout).
**Product target per brief:** AI formulation system for **ice cream / frozen desserts** meeting **health-and-wellness and medical-dietary constraints while preserving eating quality**. The current codebase (generic clinical-nutrition chat) is the migration starting point, not the target.
**Prime directive:** the LLM proposes; deterministic physics and a governed composition database verify. No formula reaches a user without passing the validation gate (§4.3).

---

## 1. Product Vision & Users

**Vision.** FormulaForge compresses the early-stage frozen-dessert formulation cycle from weeks of spreadsheet iteration and bench trials to minutes of constrained, explainable exploration. A formulator states medical/wellness targets ("renal-safe, ≤120 mg K per 100 g, standard-of-identity ice cream body") and quality priorities; the system generates candidate formulas that are *computed-compliant* (hard constraints verified against real composition data), *quality-scored* (predicted texture, melt, scoopability), and *explainable* (which constraints bind, what was traded). The status quo — Excel mass-balance sheets, tribal PAC/POD tables, and serial bench iterations at ~$2–10k per pilot batch — becomes the last mile instead of the whole road.

**Why frozen desserts is the right wedge:** it is the hardest common food matrix — simultaneously an emulsion, a foam, and a partially frozen solution — so a system that handles it credibly generalizes down to simpler matrices, not the reverse. Every medical constraint fights a physical property (see §4.2), which makes the constrained-optimization framing genuinely necessary rather than decorative.

**Personas & jobs-to-be-done**

| Persona | JTBD | What they need from the system |
|---|---|---|
| **R&D formulator** (primary) | "Get me 3 feasible starting formulas for a low-phosphorus frozen dessert that won't be a hockey puck at −18 °C." | Fast candidate generation; PAC/POD/total-solids readouts; side-by-side compare; export to bench sheet. |
| **Regulatory / nutrition lead** | "Prove this complies before we spend pilot money; document the basis." | Deterministic nutrient computation with data lineage to FDC records; constraint-rule versioning; audit trail; standard-of-identity checks. |
| **Innovation manager** | "Scope whether a renal-friendly novelty line is feasible this quarter." | Feasibility summaries, trade-off frontiers ("you can have low-K or 12% fat, not both at this cost"), shareable reports. |

---

## 2. System Architecture

### 2.1 Three coupled subsystems

The enterprise system decomposes into three subsystems with hard boundaries. The current codebase implements a thin slice of (G) only.

**G — Generative** (RAG + LLM structured generation)
Proposes candidate formulations: ingredient set, percentages, process notes, rationale. Retrieval-augmented from (a) the governed ingredient library and (b) a domain-knowledge corpus (formulation science notes, prior internal formulas). Output is a typed `CandidateFormula` — *a proposal, never a result*.

**P — Predictive** (quality/sensory estimation)
Estimates soft quality attributes from computed composition features: hardness/scoopability at serving temp, iciness risk, melt rate, mouthfeel/body, chalkiness risk (protein systems), heat-shock stability. v1: physics-derived indices + calibrated heuristics (transparent, defensible). v2: gradient-boosted models trained on bench/sensory feedback (§3).

**C — Constraint & Optimization** (hard compliance + feasible-space search)
Deterministic. Computes the full nutrient vector and physical indices (total solids, fat, MSNF, sugars, PAC, POD) from the composition database via mass balance; evaluates against the active **constraint modules** (renal, diabetic, high-protein, low-fat, vegan/allergen — pluggable, §2.3 adaptability); on violation, runs a bounded repair step (constrained least-squares projection of percentages onto the feasible region, holding the ingredient set fixed) before rejecting.

**Control flow:** `G proposes → C computes & validates (repair loop, ≤2 attempts) → P scores → rank & explain → user`. C is the gate; P is advisory; G never talks to the user directly.

### 2.2 Component diagram (textual) & data flow

```
Client (React SPA)
  │  HTTPS + JWT
  ▼
API Gateway (FastAPI, stateless, N replicas)
  │  /v1/formulations (POST → job id)   /v1/formulations/{id}/events (SSE)
  │  /v1/chat (RAG Q&A, direct stream)  /v1/ingredients, /v1/constraints (CRUD, RBAC)
  ▼
Queue (Redis Streams / arq)  ←— long-running generation decoupled from HTTP
  ▼
Orchestration workers (LangGraph):
  intake_parser → retriever → generator(G) → calculator(C) → validator(C)
       │              │            │              │              │ fail→ repair(C) → validator
       │              │            │              │              │ pass ▼
       │              │            │              │         quality_predictor(P) → ranker → persist
  ▼
State & data plane:
  Postgres (+pgvector): ingredient library w/ nutrient vectors & lineage; formulas;
    constraint-rule versions; sessions; audit log
  Redis: session cache, semantic LLM cache, rate-limit counters
  Object store: dataset snapshots, exports
Cross-cutting: OTel traces (per-node), structured logs, metrics; LangSmith/Langfuse LLM traces
```

Session state moves from process-local `TTLCache` (F6, F10) to Redis; conversation history and formula lineage persist in Postgres for auditability. The current `orchestrator` pass-through node (F16) becomes `intake_parser`: extracts structured constraints/targets from natural language (small model or function-calling), replacing the regex router — regex remains only as a zero-cost pre-filter. The iterate dead-end (F7) is solved structurally: every generation is anchored to a `parent_formula_id`; "make it dairy-free" becomes a *delta request* carrying the parent's full composition into G's context.

### 2.3 Engineering-principles matrix (required)

Named practices are the floor. Each row: pattern → where it lives → rejected alternative → audit gap closed.

#### Reliability

| Practice | Concrete placement | Trade-off rejected | Gap closed |
|---|---|---|---|
| Hard validation gate before user | `validator` node (C); no bypass path exists in graph topology | "Trust but flag" (show formula with warnings) — rejected: medical constraints make soft-fail a liability | F1, F2 |
| Structured-output enforcement | Pydantic `CandidateFormula` schema; LLM called with JSON-schema/tool-call mode; parse failure → one re-prompt with validation errors → hard fail | Regex/fence-stripping repair (current) — brittle, duplicated (F13) | F2, F13 |
| Graceful degradation chains | Retrieval: pgvector → keyword fallback (current code becomes the fallback, honestly labeled). LLM: primary Groq → configured fallback provider | Single-path with error page — rejected; demo taught us free-tier retrieval dies (README design note) | F8 |
| Retries w/ exp. backoff + jitter, timeouts, circuit breaker | LLM adapter layer (all providers); circuit breaker trips to fallback model | Unbounded LangChain default retries — cost-blind | F4 (cost) |
| Idempotent endpoints | `POST /v1/formulations` accepts client `Idempotency-Key`; job dedupe in Redis | At-most-once fire-and-forget — silent loss on network retry | F10 |
| Liveness/readiness probes | `/health/live` (process), `/health/ready` (DB+Redis+LLM ping) | Current single `/health` (returns ok while dependencies are down) | F19 |
| SLOs w/ error budgets | p95 chat first-token <1.5 s; p95 formulation job <30 s; validation-gate availability 99.9%; burn-rate alerts | "Best effort" | — |
| Deterministic, seeded pipelines | temperature/model/prompt-version recorded per generation; calculator & validator are pure functions; dataset builds seeded & versioned | Creative sampling for "variety" — variety comes from explicit exploration parameters, not entropy | F1, F3 |
| Golden-dataset regression eval in CI | ~50 curated briefs (per constraint module) → assert schema-validity rate, compliance pass rate, mass-balance pass rate; fail CI on regression | Manual spot-checking (current: zero generation-quality tests) | F14 |

#### Adaptability

| Practice | Concrete placement | Trade-off rejected | Gap closed |
|---|---|---|---|
| Ports-and-adapters (hexagonal) | `LLMPort`, `EmbeddingPort`, `RetrieverPort`, `QualityModelPort` interfaces; adapters: Groq/OpenAI/Anthropic, pgvector/keyword | Concrete imports inside nodes (current `from llm import get_llm` at module level) — makes README's swap claim true instead of aspirational | F5, F15 |
| Strategy pattern for model/retrieval routing | Router selects adapter per task class (cheap model for intake parsing, capable model for generation) via config | One-model-for-everything — wasteful (see Scalability cost row) | — |
| **Declarative, pluggable dietary-constraint modules** | Each module = versioned YAML/JSON ruleset (`renal.v2.yaml`: nutrient limits per 100 g & per serving, ingredient blacklists, label rules) + registered evaluator; adding "low-FODMAP" touches zero core code (open/closed) | Hard-coded constraint logic in prompts (current: constraints live only in prose prompt text) | F1, F2 |
| Config-driven (12-factor), pydantic-settings | Single `Settings` object; no scattered `os.getenv`/double `load_dotenv` | Current env-read-at-import ordering trap | F15 |
| Feature flags; versioned prompts & rulesets; versioned API (`/v1/`) | Prompts in registry with semver + changelog; rule versions pinned per formula record (auditability) | Prompt strings inline in node code (current graph.py) | F20 |

#### Maintainability

| Practice | Concrete placement | Trade-off rejected | Gap closed |
|---|---|---|---|
| Separation of concerns / SRP | Packages: `domain/` (pure calc + rules, zero I/O), `orchestration/`, `adapters/`, `api/`; domain layer importable & testable without FastAPI or LangGraph | Current: parsing in main.py, science in prompts, duplication across files (F13) | F2, F13 |
| End-to-end type safety | Pydantic models shared → OpenAPI → generated TS client types; SSE event schema versioned | Hand-maintained TS interfaces (current App.tsx duplicates backend shape by eye) | F2, F11 |
| Full test pyramid + ML eval | Unit (domain calc — property-based tests on mass balance), integration (graph w/ fake adapters), e2e (API), eval (golden set); frontend build+lint in CI | Current: good unit/API tests, nothing above | F14 |
| CI/CD + IaC | GitHub Actions (extend current ci.yml): backend tests+eval, frontend `tsc && vite build`, deploy on tag; Terraform for managed infra | Click-ops on Render/Vercel dashboards (current) | F14, F18 |
| Observability: structured logs, OTel traces, metrics, LLM-node tracing | JSON logs w/ request_id; OTel spans per graph node (latency, token spend, retrieval hit-rate, validator outcome as span attributes); dashboards + alerts | LangSmith-or-nothing (current) | F19 |
| ADRs; pinned auditable deps | `docs/adr/` starting with ADR-001 "LLM proposes / system verifies"; deps stay pinned (already done) + `pip-audit` in CI | Tribal memory | F20 |

#### Scalability

| Practice | Concrete placement | Trade-off rejected | Gap closed |
|---|---|---|---|
| Stateless horizontal services | API replicas share nothing; all state in Postgres/Redis | Sticky sessions — hides the F6 problem instead of fixing it | F6 |
| Async I/O + queue/worker for long jobs | Formulation = job on Redis Streams; SSE relays worker progress; chat Q&A stays direct-stream | Holding HTTP open for 30 s multi-step generation — ties up gateway, breaks on LB timeouts | F6 |
| Multi-layer caching | Semantic LLM cache (embedding-keyed, Redis) for repeated briefs; embedding cache; ingredient-vector cache in-process (immutable per dataset version) | No caching (current) — every identical demo query pays full LLM cost | F4 (cost) |
| Rate limiting, backpressure, load shedding | Token-bucket per IP (anon) / per API key (authed) at gateway; queue depth threshold → 429 + Retry-After | Open endpoint (current) | F4 |
| Managed scalable vector store | pgvector on managed Postgres (one system of record + ANN in one engine at this corpus size) | Dedicated vector DB (Pinecone/Weaviate) — rejected at ~10⁴–10⁵ vectors as an extra moving part; revisit >10⁷ | F8 |
| Batch vs real-time separation | Dataset ETL, eval runs, model retraining = scheduled batch; user paths never block on them | Cron-in-webserver | F3 |
| Cost controls: model routing, token budgets, prompt compression | Intake/parsing → 8B-class model; generation → 70B; per-session and global daily token budgets enforced in adapter; retrieval context deduped & capped | Flat 70B for everything (current) | F4 |

---

## 3. Data Science & Data Engineering

### 3.1 ELT design

**Sources:** USDA FDC **Foundation Foods + SR Legacy** (full nutrient vectors — replaces F1/F3 artifact); supplier ingredient specs (functional properties: PAC/POD contributions, DE for glucose syrups, protein type, stabilizer class, allergen flags, cost); internal formulation + bench/sensory records (accumulates over time; feeds P-subsystem training).

**Extract → Load (raw) → Transform (governed):**
1. **Extract:** versioned pull of FDC full-download CSVs; supplier specs via templated intake sheet. Every raw file checksummed and snapshotted to object storage (`dataset/raw/fdc_2026-04/…`).
2. **Load raw:** land unmodified into `raw.*` Postgres schema. No cleaning at this layer — lineage requires the untouched original.
3. **Transform:** dbt-style versioned SQL/Python transforms → `core.ingredient` table: one row per approved ingredient with (a) complete nutrient vector per 100 g (energy, protein, fat, carbs, sugars, fiber, Na, K, P, Ca, plus module-required micros), (b) **functional feature block** (§3.2), (c) provenance columns (`source`, `source_id`, `dataset_version`, `transform_version`). Dedup rule: prefer Foundation > SR Legacy > Branded for the same food concept; assert uniqueness in CI (fixes F3's 75%-duplicate failure class permanently).

Embeddings for retrieval are generated per `core.ingredient` row and per knowledge-corpus chunk (300–500 token chunks, heading-anchored), stored in pgvector, re-embedded only on dataset-version or embedding-model change (versioned; stale vectors never mixed).

### 3.2 Feature design

**Per-ingredient (stored, governed):** nutrient vector /100 g; **PAC** (freezing-point-depression factor, sucrose = 100 basis); **POD** (relative sweetness, sucrose = 100); total-solids contribution; fat type & SFC class (dairy/coconut/HO-sunflower…); protein type & functionality class (micellar casein / whey / pea / soy — emulsification & gelation propensity); MSNF contribution; stabilizer/emulsifier class & typical use band; allergen vector; cost /kg; lactose content (sandiness ceiling driver).

**Formulation-level (derived, computed — never LLM-asserted):** total solids %; fat %; MSNF %; sugars %; **PAC_total & POD_total** (Σ wᵢ·factorᵢ); serving-basis nutrients (overrun- and serving-size-adjusted: nutrient per serving = nutrient per 100 g mix × serving g ÷ (1 + overrun)); water fraction; estimated frozen-water fraction at −18 °C (from PAC via FPD curve); protein % by type; stabilizer total.

**Targets:** (a) **hard compliance vector** — pass/fail per active constraint rule (deterministic labels, no ML); (b) **soft quality scores** — v1 physics indices (§4), v2 regression targets from bench data: instrumental hardness (penetrometer), melt rate (g/10 min), overrun achieved, sensory panel scores (iciness, chalkiness, body) on 9-pt scale.

### 3.3 Train/validation/test strategy (for P-subsystem v2)

- **Leakage control (non-negotiable):** split by **base-formula family**, never by row — all variants/iterations of one base formula stay in the same fold (grouped split on `parent_formula_id` lineage). Random row splits would leak near-duplicates and inflate metrics dishonestly.
- **Stratification:** by product type (ice cream / gelato / novelty / non-dairy) and constraint module, so minority classes (renal) aren't absent from validation.
- **Temporal discipline:** when models retrain on accumulating bench data, evaluate on a strictly-later time slice as the final check (guards against process-drift leakage).
- **Reproducibility:** seeds fixed; dataset versions pinned per training run; run config + metrics logged to experiment tracker (§6.2); model artifacts in registry with dataset-version lineage.

### 3.4 Evaluation

| Layer | Metric | Gate |
|---|---|---|
| Generation (G) | Schema-validity rate; ingredient-set plausibility (all ingredients resolve to `core.ingredient`) | ≥98% validity on golden set in CI |
| Compliance (C) | Compliance accuracy on golden briefs (formula passes the module it was asked to satisfy) | 100% post-gate by construction; measure *pre-repair* pass rate as G quality signal |
| Quality (P) | MAE vs bench hardness/melt; rank correlation vs sensory panel | Tracked per release; regression fails CI |
| End-to-end usefulness | Formulator accept/iterate/discard rates in product telemetry; bench-confirmation rate | Feedback loop: every bench result entered becomes a training row (with consent/IP flags, §6.1) |

---

## 4. The Formulation Domain Model

This section is the system's spine. Everything here is deterministic code in `domain/` — pure functions over the composition table.

### 4.1 The physics the system must respect

- **Mass balance.** Σ ingredient percentages = 100.000 ± 0.01 (w/w mix basis). All derived quantities (solids, fat, MSNF, sugars, nutrients) are linear mass-weighted sums. Standard mix envelope (product-type-dependent, configurable): fat 10–16% (ice cream SOI ≥10%), MSNF 9–12%, sweeteners 13–17% sucrose-equivalent, stabilizer+emulsifier 0.2–0.5%, **total solids 36–42%**. MSNF ceiling is lactose-bound: >~11% MSNF risks lactose crystallization (sandiness) unless lactose-reduced ingredients are used — encode as a rule keyed to computed lactose content, not to MSNF alone.
- **Freezing-point depression (PAC).** Small solutes depress freezing point ∝ molality. PAC (sucrose=100): dextrose ≈ 190, fructose ≈ 190, lactose ≈ 100, glycerol ≈ 370, erythritol ≈ 280, allulose ≈ 190, maltodextrin DE-dependent ≈ 5–20, polydextrose ≈ 10. Target PAC_total band per format (scoopable tub ≈ 240–300; soft-serve higher; novelty lower). Consequence the validator must catch: **sugar-free via erythritol overshoots PAC → soft, weepy product; via maltodextrin alone undershoots → brick.** Frozen-water fraction at serving temp (target ≈ 70–75% at −18 °C) computed from PAC curve; drives scoopability index.
- **Sweetness (POD).** POD (sucrose=100): dextrose ≈ 74, fructose ≈ 173, allulose ≈ 70, erythritol ≈ 65, high-intensity sweeteners ≈ 10³–10⁴ (dosed in ppm, contribute ~0 PAC/solids — bulking must come from elsewhere). Validator checks POD_total in target band (12–16 SE) *independently* of PAC — the diabetic module's core tension is satisfying both with non-sucrose parts.
- **Fat / MSNF / stabilizer roles.** Fat: flavor carrier, air-cell stabilization via partial coalescence, mouthfeel; below ~8% requires fat mimetics (microparticulated whey, inulin, polydextrose) — low-fat module auto-suggests. Protein (MSNF): emulsification, body, water-binding; >~4.5% added whey protein flags chalkiness + HTST gelation risk (heat-stability rule keyed to protein type). Stabilizers (LBG, guar, carrageenan blends): bind water, retard ice recrystallization (heat-shock defense); dosage band enforced.
- **Overrun.** 20–100% by format (premium 20–60, standard ~100). Affects per-serving nutrition via density (§3.2 formula) — a compliance-relevant computation the current system doesn't even represent. Declared overrun is an input with a per-format default.

### 4.2 Constraint-vs-quality tension matrix (what the optimizer actually negotiates)

| Constraint module | Hard rules (evaluator inputs) | Primary quality casualties | System's mitigation moves (encoded as repair/suggestion strategies) |
|---|---|---|---|
| **Renal** | P ≤ *x* mg, K ≤ *y* mg, Na ≤ *z* mg /serving; protein band | Body/texture (MSNF cut), flavor (dairy cut) | Swap caseinates→whey isolate (lower P per protein unit); non-dairy fat; MCT for calories; flag "not SOI ice cream" label consequence |
| **Diabetic / low-glycemic** | Added sugars ≤ *x* g; sugar alcohols declared; PAC & POD both in band | Scoopability (PAC mismatch), GI tolerance, cooling off-note (erythritol) | Allulose+erythritol+HIS triad balancing PAC/POD; polydextrose bulking; polyol dose cap (GI: erythritol ≲0.7 g/kg BW guidance encoded as per-serving cap) |
| **High-protein** | Protein ≥ *x* g/serving | Chalkiness, gelation at pasteurization, ice crystal size (water competition) | Micellar casein/whey blend ratios; hydrolysate fraction cap (bitterness); process note: batch pasteurization advisory |
| **Low-fat** | Fat ≤ *x* g/serving | Nearly all: flavor release, body, air stability, melt shape | Fat mimetic selection; raise MSNF within lactose ceiling; stabilizer uplift within band |
| **Vegan / allergen-free** | Allergen vector ∩ blacklist = ∅; no animal-derived flags | Melt behavior (SFC profile), foam stability (protein functionality), flavor baseline | Base selection (coconut/oat/soy) with SFC-class matching; pea+oat protein pairing; flavor-masking note |

### 4.3 The validation gate (spec for `domain/validator.py`)

Input: `CandidateFormula` (LLM proposal) + active constraint modules + product format. Every check is a typed `Violation{rule_id, severity, measured, limit, explanation}`.

1. **Schema & resolution:** Pydantic-valid; every ingredient resolves to `core.ingredient` (fuzzy-match assist, but unresolved = hard fail — no phantom ingredients).
2. **Mass balance:** Σ = 100 ± 0.01; each ingredient within its allowed use band.
3. **Deterministic recomputation:** full nutrient vector + PAC/POD/solids/MSNF from the composition table. **LLM-supplied nutrition fields are discarded**, kept only as a telemetry signal of model drift.
4. **Physical plausibility:** total solids, PAC band, POD band, lactose/sandiness ceiling, protein heat-stability flag, stabilizer band, overrun-consistent serving math.
5. **Compliance:** every active module's rules against computed per-100 g and per-serving values.
6. **Outcome:** pass → attach `ValidationReport` (shown in UI, §5); fail → repair loop (constrained least-squares re-weighting, ingredient set fixed, ≤2 attempts) → still failing → structured rejection with binding violations (fed back to G once) → final failure is an explicit, explained error. **There is no code path from G to the user that bypasses this function** — enforced by graph topology and by an integration test that asserts it.

---

## 5. UX / UI Design

**Aesthetic target:** clean, high-end, enterprise scientific — the NotCo Giuseppe bar. Data-rich but calm; the user is a scientist who distrusts magic. Trust is built by *showing the verification*, not by hiding the model.

**Core flows**

1. **Constraint & target intake.** Structured brief builder, not a bare chat box: product format (tub/novelty/soft-serve), constraint modules (toggle + per-rule value editing with sane defaults), quality priorities (rank: scoopability / flavor / cost), free-text intent field. Progressive disclosure: defaults visible, expert overrides one click deeper. (Chat remains for Q&A/RAG, clearly separated from formulation jobs.)
2. **Generation.** Job-based with live node progress ("retrieving ingredients → drafting → validating → scoring"); streamed status from the SSE relay (§2.2). Cancellable (fixes F12 class).
3. **Compliance & quality readout.** The formula card grows into a **verification surface**: ✅ computed-compliant rows per rule (measured vs limit, e.g. "K 96 mg / limit 120 mg per serving"), quality gauges (scoopability index at −18 °C, melt risk, PAC/POD dials against target bands), and a **provenance strip** — every nutrient traces to FDC record ids; every quality score labeled *rule-verified* (deterministic) vs *model-estimated* (P-subsystem) with confidence. This distinction is the product's honesty contract.
4. **Compare & iterate.** Side-by-side (2–4 formulas): ingredient deltas highlighted, radar/parallel-coordinates quality overlay, binding-constraints panel ("phosphorus binds in A; PAC binds in B"). Iteration is a first-class delta request anchored to the parent formula (fixes F7): "reduce K 15%, hold scoopability" — lineage tree visible.
5. **Export / handoff.** Bench sheet (batch-scaled masses for target batch size + overrun), PDF compliance report (regulatory persona), JSON/API for PLM integration.

**Interaction principles:** explainability panel on every formula ("why these ingredients; which constraints bind; what was traded"); clear async state (queued/running/validating/failed-with-reason); no dead-end errors (validation failure shows the violations and offers the repair-relaxation dialog: "allow +0.5% stabilizer?"); markdown rendered properly in chat (fixes F11).

**Design tokens (direction for builder):** type — Geist (keep) for UI, tabular-nums mandatory for all quantities; spacing — 4 px base grid, generous whitespace; color — neutral slate surfaces, single trust accent (current teal acceptable), semantic tokens only for verification states (pass/warn/fail = green/amber/red, WCAG AA on all pairs), never decorative color on data; data-viz — Tufte-lean: horizontal bars for composition, dials only for banded targets (PAC/POD), no 3-D, no gradients on data marks; density — comfortable default with a compact mode for the compare view; dark mode via existing shadcn token architecture (already in `index.css`).

---

## 6. Enterprise Non-Negotiables

### 6.1 Security, governance, deployment

- **AuthN/AuthZ:** OIDC SSO (enterprise IdP) + API keys for programmatic access; **RBAC** roles: `viewer` (read formulas), `formulator` (create/iterate), `reviewer` (approve/export), `admin` (constraint-rule + ingredient-library governance). Constraint rules and ingredient data are admin-governed — a formulator cannot silently edit a renal limit.
- **Audit logging:** append-only event log (who, what, when, prior value) on formulas, rule changes, exports. Formula records are immutable versions — iteration creates children, never edits.
- **Data lineage/provenance:** every formula pins `dataset_version`, `ruleset_versions`, `prompt_version`, `model_id`, seed — full recomputability years later (regulatory posture).
- **IP protection:** proprietary formulas are tenant-scoped rows with row-level security; **no customer formulation data in LLM prompts across tenants**; retrieval indexes are tenant-partitioned; contractual no-training flags enforced at the adapter (provider zero-retention endpoints).
- **Secrets:** managed secret store (not .env in prod); key rotation; `pip-audit`/`npm audit` in CI.
- **Deployment topology (no SPOF, no free tier):** managed Postgres (HA, PITR backups); Redis (managed, replicated); ≥2 API replicas + ≥2 workers behind LB across AZs; IaC (Terraform); blue-green deploys; CDN for SPA. Free-tier Render/Vercel is demo-only.

### 6.2 MLOps lifecycle

- **Registries & versioning:** model registry (MLflow-class) for P-subsystem models; DVC-class dataset versioning snapshotted to object storage; prompt registry (semver, changelog, owner).
- **Experiment tracking:** every training run logs config, data version, metrics, artifacts.
- **Production monitoring:** data drift (ingredient-usage and brief-distribution shift), concept drift (P-model error vs incoming bench results), generation-quality drift (golden-set eval re-run on schedule + on any model/prompt/dataset version bump). Alert on error-budget burn.
- **Retraining triggers:** threshold-based (drift metric or N new bench records) → automated pipeline → challenger model → **shadow deployment** (scores logged, not shown) → canary (5% traffic) → promote; **one-click rollback** to any registry version.
- **LLM change management:** provider model deprecations handled as registry events — golden-set eval must pass before a new model id serves traffic.

---

## 7. Migration / Refactor Plan

Two phases; each maps audit findings (F#) to work. Order within a phase is dependency order.

### Phase A — Demo-ready (credible to a technical reviewer; weeks, one engineer)

| Step | Work | Findings closed |
|---|---|---|
| A1 | **Rebuild dataset**: FDC Foundation Foods ETL with full nutrient vectors + PAC/POD functional table for common formulation ingredients; committed, versioned script; CI assertions on uniqueness/completeness | F1, F3 |
| A2 | **Domain layer + validation gate**: `domain/` package — Pydantic `Formula`, mass-balance & nutrient computation, PAC/POD calc, validator v1; wire as mandatory graph node; discard LLM nutrition | F2, F13 |
| A3 | Structured-output enforcement (JSON-schema mode + one repair re-prompt); delete fence-stripping duplicates | F2, F13 |
| A4 | Rate limiting (slowapi) + CORS allowlist + daily token budget counter | F4 |
| A5 | Honest provider layer: implement OpenAI/Anthropic adapters behind `LLMPort` *or* correct README claim (decide once; recommend: implement — it's small) | F5, F15 |
| A6 | Iteration support: `parent_formula` context into formula prompt + "iterate" intent | F7 |
| A7 | Frontend: markdown rendering, AbortController, typed SSE events from OpenAPI schema | F11, F12 |
| A8 | Golden-set eval (20 briefs) in CI + frontend build job; retrieval quick fixes (word-boundary tokenize, dedupe) | F14, F8 |
| A9 | Hygiene: pydantic-settings, structured logging + request ids, untrack `.claude/settings.local.json`, fix `runtime.txt`, README truth pass | F15, F17, F18, F19, F20 |

**Exit criteria:** every displayed number is computed, not generated; validation gate demonstrably rejects a bad formula in tests; endpoint abuse-limited; README accurate.

### Phase B — Enterprise-ready (adoptable by an R&D org; months, small team)

| Step | Work | Spec section |
|---|---|---|
| B1 | Postgres(+pgvector) + Redis; sessions/formulas/audit persisted; semantic retrieval restored w/ keyword fallback | §2.2, §3.1 (F6, F8, F10) |
| B2 | Queue/worker split; job API + SSE relay; idempotency keys | §2.2, §2.3 |
| B3 | Constraint-module framework (declarative rulesets, versioned) + renal/diabetic/high-protein/low-fat/vegan v1 rules | §2.3, §4.2 |
| B4 | P-subsystem v1 (physics indices) → UI quality readout; compare/iterate UX; brief-builder intake | §4, §5 |
| B5 | AuthN/AuthZ/RBAC, audit log, tenant isolation, secret store; HA topology via IaC | §6.1 |
| B6 | Observability build-out (OTel, dashboards, SLOs) + MLOps rails (registries, drift monitoring, shadow/canary) | §2.3, §6.2 |
| B7 | Bench-feedback loop → P-subsystem v2 training per §3.3 | §3 |

---

## Open questions & assumptions (for the builder / product owner)

1. **Assumption:** spec targets frozen desserts per brief, superseding the current generic clinical-nutrition chat; the chat/RAG surface survives as the Q&A sidecar. Confirm the clinical-nutrition positioning (current README) is being retired or kept as a second vertical.
2. **Assumption:** multi-tenant SaaS posture (drives §6.1 tenancy/IP design). If single-tenant/on-prem for one enterprise, RBAC stays but tenancy partitioning simplifies.
3. Constraint thresholds (renal P/K/Na, diabetic sugar limits) ship as *configurable defaults sourced from published clinical guidance*, reviewed by the customer's regulatory lead — the system is a formulation tool, not a medical device. Confirm no claim is made that triggers medical-device or health-claim regulatory scope.
4. PAC/POD table values vary by source (±10%); assume an internal curated table (admin-governed) is acceptable as system-of-record, refined against bench data over time.
5. Serving size & overrun defaults per product format need a product decision (drives per-serving compliance math).
6. Groq remains primary LLM for cost/latency; assumption that a second provider is contractually acceptable as fallback (affects §6.1 no-training flags).
7. Bench/sensory historical data availability is unknown — P-subsystem v2 timeline depends entirely on it; v1 physics indices carry the product until then.
8. Budget/hosting decision for Phase B (managed Postgres/Redis/compute ≈ low hundreds $/mo minimum) needs owner sign-off; Phase A runs on current free tier.
