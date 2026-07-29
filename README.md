# FormulaForge

FormulaForge generates frozen-dessert formulations for clinical and institutional
nutrition — renal, diabetic, high-protein, low-fat, and vegan diets — and verifies every
one of them before a user sees it. A language model proposes an ingredient structure;
deterministic Python resolves each ingredient against a governed library, computes the
full nutrient vector and the physical chemistry that makes a frozen dessert work, and
checks the result against the active dietary rulesets. It is built for formulators and
product developers doing early-stage feasibility work, where the question is not "what
could this look like" but "does this actually meet the constraint, and can you show me."

[Live demo](https://formula-forge-chi.vercel.app)

> FormulaForge is a formulation-design tool for qualified professionals. It makes no
> medical claims and is not a medical device. Dietary thresholds are configurable defaults
> drawn from published guidance and require professional review.

## The design problem

Language models produce numbers that are plausible and wrong. Ask one for the potassium
content of a dairy-based formulation and it will return a figure with the shape and
confidence of a real measurement. Nothing in the model distinguishes a value it recalled
from one it constructed, and nothing in the output signals which happened.

In clinical nutrition that failure mode is not a quality problem. A renal patient's
formulation carries hard per-serving ceilings on phosphorus, potassium, and sodium.
A number that is confidently wrong by 40% is a safety issue, and it is undetectable by
the person most likely to trust it — a reader who cannot recompute it themselves.

So the architecture starts from a constraint rather than a capability: **no number the
model produces is allowed to reach a user.** The model is used for the thing it is
genuinely good at, proposing plausible ingredient structures, and is given no authority
over anything that has to be true.

## Architecture

```
POST /api/chat
  │
  ├─ CORSMiddleware            explicit origin allowlist, no wildcard
  ├─ request_id_middleware     X-Request-ID in or minted, bound to a contextvar
  ├─ limiter.limit()           slowapi, per client address (default 30/minute)
  ├─ ChatRequest               pydantic: message 1–2000 chars, else 422
  └─ TokenBudget.allow()       daily global + per-session caps, else 429
  │
  ▼
_stream_agent()  ──────────────────────────────────────────────── SSE generator
  │
  ├─ iteration ──► iterate_formula(msg, parent)         delta on the session's
  │                                                     last formula (F7)
  ├─ formula ────► agent.astream_events()               LangGraph, Groq JSON mode
  │                  orchestrator → route → formula_agent
  │
  └─ question ───► agent.astream_events()               tokens streamed to client
                     orchestrator → route → rag_agent
  │
  ▼ (both formula paths)
_resolve_formula()  ═══════════════════ THE TRUST BOUNDARY ══════════════════════
  │
  ├─ extract_json_block → json.loads → _candidate_from_llm
  │      discards every nutrition field the model emitted
  │
  ├─ domain.validate_candidate()
  │      resolve against governed library → bounded mass-balance repair →
  │      compute_composition() → validate() against physical bands + rulesets
  │
  ├─ if it failed: ONE repair re-prompt, with measured-vs-limit feedback
  │      keep the retry only if it has fewer compliance errors
  │
  ▼
ValidatedFormula (flagged if still non-compliant) | RejectedFormula
  │
  ▼
SSE events: token | formula | rejection | error | done
```

A request arrives at `chat()` in [`backend/main.py`](backend/main.py). Middleware attaches
a request id and applies CORS; the slowapi decorator applies the per-address rate limit;
pydantic validates the body; `TokenBudget.allow()` reserves an estimated token spend or
returns 429.

Routing is then decided without an LLM call. `detect_modules()` regex-matches the message
against the constraint-module activation phrases and unions the result with the explicit
module ids the brief-builder UI sent. `detect_iteration()` decides whether this message
reads as a modification of the formula already in the session. `detect_intent()` inside
`route()` decides formulate-versus-question, unless the UI sent `intent: "formulate"`,
which forces the formula path so a CTA can never fall through to Q&A on a regex miss.
These are regex because routing is a deterministic pattern-match problem; an LLM hop here
would add a network round trip and an API call to every message.

`_stream_agent()` then takes one of three paths. Iteration calls `iterate_formula()`
directly with a summary of the parent formula and never touches the graph. A fresh
formulation runs the LangGraph agent, buffering tokens rather than streaming them —
streaming raw JSON to a UI is meaningless. A question runs the RAG path, where
`search_foods()` retrieves governed ingredients with their real per-100 g nutrients and
tokens stream to the client as they arrive.

One detail worth naming because it is not obvious: Groq's JSON mode does not emit
`on_chat_model_stream` events, so a formula run produces no token events at all. The
formula text is recovered from the `formula_agent` node's `on_chain_end` event
([`main.py`](backend/main.py), the `elif kind == "on_chain_end"` branch). Without that
branch every formula run ends silently.

The domain layer under [`backend/domain/`](backend/domain/) is pure — no FastAPI, no
LangGraph, no network. Its single I/O seam is `repository.py`, which loads the governed
ingredient library. That purity is what makes the food science unit- and property-testable
in isolation.

## The trust boundary

Everything above exists to funnel into one function: `_resolve_formula()` in
[`backend/main.py`](backend/main.py). It is the only route from generation to a user, and
an integration test asserts there is no bypass.

**Generation is constrained before it starts.** The formula prompt in
`build_formula_messages()` lists the governed ingredient names verbatim and instructs the
model to choose only from them. `constraint_brief()` renders the active rulesets' numeric
limits into the prompt as design targets — read from the same versioned JSON the validator
will enforce, so the model designs toward the limits instead of discovering them by
rejection. The prompt explicitly tells the model not to report nutrition, because the
system computes it.

**The model's numbers are structurally incapable of reaching the user.** `CandidateFormula`
in [`domain/models.py`](backend/domain/models.py) has no nutrition fields. `_candidate_from_llm()`
copies across exactly three things per line — `ref`, `percentage`, `notes` — and drops
everything else. A model that emits `"nutrition_per_100g": {"calories": 1}` alongside a
dairy-heavy formulation has that object discarded at the boundary; the test
`test_llm_supplied_nutrition_cannot_enter` pins the behaviour.

**Validation is deterministic.** `validate_candidate()` resolves every ingredient against
the library and hard-rejects anything unresolvable rather than guessing — an invented
ingredient cannot be verified, so it is never silently approximated to a real one. It
applies a bounded proportional repair when percentages miss 100% (rejecting outright past
40 points off, where repair would change the intended formula). It computes the nutrient
vector, total solids, fat, MSNF, PAC, POD, per-serving values, and cost from the library.
Then `validate()` checks physical-plausibility bands and every active ruleset. `passed` is
true only when there are zero error-severity violations.

**Exactly one repair is allowed.** When the first attempt fails — unparseable, unresolvable,
or computed-but-non-compliant — `_repair_feedback()` builds failure-specific instructions.
For a formula that computed but breached a limit, that means the measured value and the
limit for each error violation, so the retry is designing against numbers rather than
guessing. Then one call to `regenerate_formula()` or `iterate_formula()`, and no more.

The cap is structural, not a counter: `_resolve_formula()` is straight-line code with no
loop, so there is no execution path that reaches a third generation. Two reasons it is
one and not three. The first is cost — each retry is a full formula prompt carrying the
entire ingredient library, and a retry budget is a multiplier on every failure, paid on
exactly the requests that were already going badly. The second matters more: unbounded
retry loops hide systematic failure instead of fixing it. If a ruleset is mis-specified,
or the library genuinely cannot express a compliant formula for a brief, retrying converts
a diagnosable, visible failure into latency and spend, and eventually into a success that
was really luck. One attempt is enough to fix a transient formatting or arithmetic slip.
Anything that survives a measured-vs-limit re-prompt is a signal, and the right response
to a signal is to surface it.

**Failure is reported honestly.** If the repair does not improve things, the attempt with
fewer compliance errors is returned — `_compliance_errors()` counts error-severity
violations and treats an unresolvable result as effectively infinite, so a rejection that
becomes a formula always wins and a tie keeps the original. The returned formula is still
flagged: `validation.passed` is false, the violations carry `measured` and `limit`, and the
response text says "a flagged formula" rather than "a verified formula". A proposal that
cannot be resolved at all is emitted as a `RejectedFormula` with the reason and the
offending ingredient names — never as a formula. The user gets the work product and an
accurate account of what is wrong with it, which is more useful than either a fabricated
pass or a bare error.

Every field is provenance-labelled on the way out. `verified_fields` lists what was computed
by rule; `estimated_fields` lists what was modelled — currently only `scoopability_index`,
a transparent triangular function of PAC. The UI renders that distinction.

## Cost and abuse controls

`/api/chat` is unauthenticated and backed by a paid LLM, so it carries three independent
controls ([`backend/budget.py`](backend/budget.py), [`backend/main.py`](backend/main.py)).

**Daily token budget, reserved up front.** `TokenBudget` holds a global daily cap
(default 2,000,000 tokens) and a per-session cap (default 50,000), both reset at UTC day
rollover and guarded by a lock. The estimate is reserved *before* the LLM call, not
recorded after it, because accounting after the fact leaves a window in which a burst of
concurrent requests all pass a check that each of them then invalidates. The global cap
bounds the bill; the session cap stops one client consuming it alone. The budget reserves
and never releases — there is no refund path and no reconciliation against provider usage,
which is deliberate for a control whose job is to fail safe.

**Per-request rate limiting.** slowapi's `Limiter`, keyed on the client address, applied
to `/api/chat` only (default 30/minute). This bounds request velocity, which the token
budget does not: a client could stay well inside its daily allowance while still driving
enough concurrent streams to exhaust connections. The limit string is read at call time so
it can be overridden in tests.

**Explicit CORS allowlist.** Origins come from `ALLOWED_ORIGINS`, methods are restricted to
GET and POST, headers to `Content-Type`, and there is no wildcard — a test asserts `"*"`
never appears in the configured list. Worth being precise about what this buys: CORS is
enforced by browsers, so it stops an arbitrary web page driving this API from a visitor's
browser with their address. It does nothing against a direct client. That is why the rate
limit and the token budget exist independently of it.

## Observability

`setup_logging()` in [`backend/observability.py`](backend/observability.py) installs a
single stdout handler whose formatter includes a request id pulled from a contextvar by a
logging filter, so every line emitted while handling a request carries its correlation id
without any call site passing it around. `request_id_middleware` reads an inbound
`X-Request-ID` or mints one, and echoes it on the response, so a client-reported failure
can be traced to its log lines. Log level is configurable via `LOG_LEVEL`.

Errors inside the stream surface the exception class name to the client and nothing else —
enough to make "something broke" reportable, without leaking exception message content.
The full traceback goes to the log. LangSmith tracing is opt-in via `LANGCHAIN_TRACING_V2`
and reported at startup.

`GET /health` is a readiness probe. It checks that an API key is configured and the chat
model object initialized, that the LangGraph agent compiled at import, and that the
governed ingredient library loads and is non-empty. It returns 200 when all three are
ready and 503 when any is not, with a per-dependency breakdown, the app version, and the
model id in use:

```json
{
  "status": "ok",
  "version": "1.0.0",
  "model": "llama-3.3-70b-versatile",
  "dependencies": {
    "llm_client":         {"status": "ok", "detail": "API key configured; chat model initialized."},
    "agent_graph":        {"status": "ok", "detail": "Compiled LangGraph agent loaded."},
    "ingredient_library": {"status": "ok", "detail": "dataset 2026.07.0, 34 ingredients."}
  }
}
```

The probe makes no network call to the LLM provider. Checking readiness by calling Groq
would bill every uptime check and would take this instance out of rotation during a
provider outage even though `/api/meta`, `/api/ideas`, and the whole domain layer still
work. It reports whether *this process* is ready, which is the question a readiness probe
should answer. The key is never exposed: `config.groq_key_fingerprint()` carries the key's
length and an 11-character window of it — fine for a private startup log, not for an
unauthenticated response body — so it is used only as a presence oracle and its output
never enters the response.

## Stack

| Layer | Technology |
|---|---|
| API | FastAPI 0.136, uvicorn, slowapi, pydantic 2 / pydantic-settings |
| Orchestration | LangGraph 1.1, langchain-core 1.3 |
| LLM | Groq — `llama-3.3-70b-versatile` primary, `llama-3.1-8b-instant` fallback via `with_fallbacks` |
| Domain | Pure Python: composition math, constraint evaluator, declarative JSON rulesets |
| Data | Governed ingredient library built by a versioned ETL from USDA FDC Foundation Foods, plus curated functional properties (PAC/POD, allergens, cost) |
| Frontend | React 19, TypeScript, Vite, Tailwind v4, shadcn/ui |
| Tests | pytest, pytest-asyncio, hypothesis, plus a golden-set compliance eval |
| Hosting | Render (backend), Vercel (frontend) |

## Quickstart

### Backend, locally

```bash
cd backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env      # then set GROQ_API_KEY
uvicorn main:app --reload
```

The service listens on `http://127.0.0.1:8000`. Confirm it is ready:

```bash
curl -s http://127.0.0.1:8000/health
```

The committed ingredient library at `backend/domain/data/ingredients.json` is all the
backend needs to run. Rebuilding it from the USDA FDC bulk CSVs is only necessary when
changing the dataset, requires those CSVs in `backend/data/`, and runs with
`python -m etl.build_ingredients`.

### Environment variables

Full annotated list in [`backend/.env.example`](backend/.env.example). The ones that matter:

| Variable | Default | Purpose |
|---|---|---|
| `GROQ_API_KEY` | none | Required. The process exits at startup without it. |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Primary model id. |
| `LLM_PROVIDER` | `groq` | `openai` / `anthropic` also require their SDK and `LLM_MODEL`. |
| `ENABLE_LLM_FALLBACK` | `true` | Composes the fallback model via `with_fallbacks`. |
| `ALLOWED_ORIGINS` | localhost:5173 + the deployed frontend | Comma-separated CORS allowlist. No wildcard. |
| `CHAT_RATE_LIMIT` | `30/minute` | slowapi limit string for `/api/chat`. |
| `GLOBAL_DAILY_TOKENS` | `2000000` | Daily token cap across all sessions. |
| `SESSION_DAILY_TOKENS` | `50000` | Daily token cap per session. |
| `APP_VERSION` | `1.0.0` | Reported by `/health`. Stamp a git SHA here at build time. |
| `LOG_LEVEL` | `INFO` | Root log level. |

### Frontend, locally

```bash
cd frontend
npm install
echo "VITE_API_URL=http://127.0.0.1:8000" > .env.local
npm run dev
```

### Docker

The build context is `backend/`, which is where `.dockerignore` must live for Docker to
read it:

```bash
docker build -t formulaforge-api ./backend
```

```bash
docker run --rm -p 8000:8000 -e GROQ_API_KEY=your_key_here formulaforge-api
```

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/health
```

A ready container answers `200`. The image is multi-stage — dependencies are installed
into a virtualenv in the build stage and copied into a clean runtime stage, so pip and its
metadata never ship — and runs as a non-root user. No secrets are baked in; configuration
arrives at runtime. The `HEALTHCHECK` instruction polls `/health` using the interpreter
already in the image, so it needs no curl.

Two behaviours to expect. The container reads `$PORT` and defaults to 8000, which is what
lets the same image run locally and on Render. And it exits at startup if `GROQ_API_KEY`
is unset, because the LangGraph module builds its chat client at import — fail-fast rather
than a process that accepts traffic it cannot serve.

## Testing

```bash
cd backend && pytest tests/ -v
```

```bash
cd frontend && npm run build
```

No test calls a live LLM; the agent is mocked throughout, so the suite is deterministic and
runs in CI without an API key. Coverage by area:

- **Domain math** (`test_domain.py`) — property-based tests via hypothesis for mass balance
  and for the linearity, non-negativity, and scaling behaviour of the nutrient computation,
  plus per-serving/overrun math and PAC/POD ordering sanity.
- **The trust boundary** (`test_validation_gate_integration.py`) — spies on
  `validate_candidate` to assert the formula path calls it exactly once with no bypass, and
  that a formulation smuggling fabricated nutrition emits computed numbers instead.
- **Repair behaviour** (`test_structured_output.py`) — that a rejected first attempt
  triggers exactly one repair, that a valid first attempt triggers none, and that a repair
  which also fails still emits a rejection rather than a formula.
- **Iteration and session state** (`test_iteration.py`) — parent-anchored iteration, and
  that history stores a summary rather than raw formula JSON.
- **Abuse controls** (`test_abuse_controls.py`) — budget caps, day rollover, the 429 paths,
  and that no wildcard origin is configured.
- **Readiness** (`test_health.py`) — the healthy path, each degraded dependency returning
  503, that no key material appears in the response, and that the probe invokes neither the
  model nor the graph.
- **Dataset integrity** (`test_dataset.py`) — uniqueness, complete nutrient vectors,
  physical bounds, and provenance on every library row.
- **Compliance regression** (`test_golden_eval.py`) — 18 committed brief-to-formula cases
  run through the validator with no LLM involved. CI fails if schema validity or compliance
  accuracy drops below 100%, or if the case set shrinks below 15.

## What is deliberately not built yet

**Authentication.** `/api/chat` is open. The rate limit and token budget bound the damage,
but there is no notion of a principal, so there are no per-user quotas and no way to revoke
one abuser without affecting others. This is the first thing to add before the demo becomes
a service.

**Anything that survives a restart or a second replica.** Session history, the last-formula
store, the token budget, and slowapi's counters are all in-process. A second uvicorn worker
or a second Render instance forks all four silently: conversations fragment, and both the
budget and the rate limit become per-process rather than per-service. `TokenBudget`'s
`allow`/`record` interface is the shape a Redis adapter would implement. Until that exists
this is a single-process deployment by construction, not by accident.

**Rate limiting that is correct behind a proxy.** `get_remote_address()` reads
`request.client.host`. Behind Render's proxy, without trusted forwarded headers configured,
that is the proxy's address rather than the caller's — which collapses a per-client limit
toward a global one. Correct for local and direct traffic, understated in production.

**Token accounting that matches the bill.** `estimate_tokens()` counts the user's message
at roughly four characters per token plus a fixed output reserve. It does not count the
system prompt, which carries the entire governed ingredient list on every formula request,
and it does not count the second LLM call a repair makes. Real spend therefore exceeds
what is reserved. The budget is a conservative bound on request volume, not an accurate
meter; exact provider usage metadata would fix it.

**Semantic retrieval.** `search_foods()` is keyword scoring with word-boundary tokenization
over the governed library. It handles the ingredient-lookup case it is used for and avoids
an embedding-model cold start on a free tier, but it does not do synonymy or paraphrase.

**Evaluation of generation quality.** The golden-set eval is a regression gate on the
*validator* — deterministic, no LLM. Nothing measures how often the model's first proposal
is compliant, or whether the repair re-prompt actually improves compliance in aggregate.
That needs a live eval harness with a cost budget, and it is the highest-value missing
piece: the repair cap's design rationale is currently reasoned rather than measured.

**IDDSI texture compliance.** The `dysphagia_iddsi` module is a declared stub. It advises
and never fails, and says so in its own violation message and in `/api/meta`. Texture-modified
diets need rheological measurement the composition model does not currently produce, and
shipping a check that looks authoritative while being unimplemented would be worse than
shipping none.

## About

Built by Bobby Craft, a food scientist and process engineer with 26 years of CPG R&D
experience at Post Cereals, Magnum Ice Cream (Unilever), Talenti, and Breyers. The
constraint hierarchies encoded in `domain/constraints/` reflect how a formulator actually
works — physical plausibility first, then dietary limits, with the distinction between a
measured value and an estimated one kept visible throughout.

[LinkedIn](https://linkedin.com/in/craft-bobby-5739b6) · [GitHub](https://github.com/craft-b/formula-forge)
