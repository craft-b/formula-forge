# FormulaForge

FormulaForge was built by a food scientist and process engineer with 26 years of CPG R&D
experience — Post Cereals, Magnum Ice Cream (Unilever), Talenti, and Breyers — because that
career made one thing clear: early-stage scoping of **medical and institutional frozen
desserts** wastes weeks on questions a trained formulator can answer in minutes. FormulaForge
generates ice-cream / frozen-dessert formulations that meet dietary constraints (renal,
diabetic, high-protein, low-fat, vegan) while respecting the physics that make a frozen
dessert worth eating.

The core idea: **the LLM proposes; deterministic food science verifies.** The model only
proposes an ingredient structure — it never reports a nutrition number. Every calorie,
milligram of potassium, freezing-point value, and compliance check is computed by a pure
domain layer from a governed ingredient database before anything reaches the user.

> **Positioning:** FormulaForge is a formulation-design tool for qualified professionals.
> It makes no medical claims and is not a medical device. Dietary thresholds are configurable
> defaults sourced from published guidance and require professional review.

**[→ Try the live demo](https://formula-forge-chi.vercel.app)**

[![CI](https://img.shields.io/badge/CI-backend%20%2B%20frontend-brightgreen)]()
[![Frontend](https://img.shields.io/badge/App-Vercel-black)](https://formula-forge-chi.vercel.app)
[![Python](https://img.shields.io/badge/Python-3.11-blue)]()
[![LangGraph](https://img.shields.io/badge/LangGraph-agentic-orange)]()

---

## What it does

A formulator describes a target — *"renal-safe scoopable vanilla, potassium ≤ 200 mg/serving."*
FormulaForge detects the active dietary constraints, has the LLM propose an ingredient
structure drawn **only** from a governed ingredient library, then:

1. **Resolves** every ingredient to the library (an unrecognized ingredient is rejected, never
   guessed).
2. **Computes** the full nutrient vector, total solids / fat / MSNF / sugars, PAC
   (freezing-point depression), POD (sweetness), per-serving values (overrun-adjusted), and a
   scoopability index — all deterministically.
3. **Validates** against physical-plausibility bands and the active compliance rulesets.
4. **Returns** a verified formula (or an explained rejection). A follow-up like *"now make it
   dairy-free"* iterates on the previous formula.

The UI is a verification surface: every number is labelled **rule-verified** (computed) or
**model-estimated**, with compliance failures shown as measured-vs-limit rows.

**Example query:** *"Create a formula for a high-protein renal-diet shake"*

<img width="479" height="491" alt="image" src="https://github.com/user-attachments/assets/a767f0a6-9b42-41e6-9e2f-d183573b838b" />

---

## Architecture

The prime directive — *LLM proposes, domain verifies* — is enforced by the pipeline and by a
test asserting no path emits LLM numbers to the client.

```
POST /api/chat  (rate-limited, token-budgeted, request-id traced)
      │
      ▼
  detect_intent / detect_modules / detect_iteration
      │
      ├─ RAG question ─────► rag_agent ─ search_foods() over governed library
      │                                   (real nutrients) → Groq → streamed text
      │
      └─ formulate / iterate ─► formula_agent (Groq JSON mode, library-constrained)
                                   │  proposes ingredient STRUCTURE only (no nutrition)
                                   ▼
                          domain.validate_candidate()   ◄── THE VALIDATION GATE
                                   │  resolve → mass-balance repair → compute
                                   │  (nutrients, PAC/POD, per-serving) → validate
                                   │  (physical bands + constraint rulesets)
                                   │  one repair re-prompt on failure
                                   ▼
                          ValidatedFormula | RejectedFormula  → SSE → verification card
```

`domain/` is pure (no I/O except the ingredient repository, no web framework), so the food
science is unit- and property-tested in isolation.

### Key design decisions

| Decision | What we did | Why |
|---|---|---|
| Trust model | LLM proposes structure; `domain/` computes every number | Nutrition/compliance for medical use must be verifiable, not generated |
| Ingredient data | Governed library: USDA FDC Foundation Foods nutrients + curated PAC/POD functional table, built by a versioned ETL | Replaces the old names-only dataset; real nutrients with provenance |
| Constraint modules | Declarative versioned JSON rulesets + generic evaluator | Add a diet (renal, diabetic, …) without touching core logic; no rules in prompts |
| Retrieval | Keyword scoring over the governed library | No ONNX/embedding cold-start on the free tier; semantic search is the Phase B upgrade |
| LLM routing | `detect_intent()` / `detect_modules()` regex, not an LLM call | Deterministic, zero added latency/cost per message |
| Provider layer | `llm.py` ports-and-adapters registry + `with_fallbacks` | Groq default + fallback model; OpenAI/Anthropic adapters when their SDKs are installed |
| Structured output | Groq JSON mode + one repair re-prompt | Reliable parsing; the gate discards any LLM-supplied nutrition |
| Session memory | In-memory `TTLCache` (history + last formula) | Enough for single-instance Phase A; Redis is the Phase B swap |
| Frontend types | Generated from the Pydantic models | Single source of truth; no hand-copied shapes (CI checks they're in sync) |

---

## Stack

| Layer | Tech |
|---|---|
| Frontend | React 19 + TypeScript + Vite + Tailwind v4 + shadcn/ui |
| Backend | FastAPI + LangGraph + langchain-groq, pydantic-settings, slowapi |
| LLM | Groq — Llama 3.3 70B (primary) + 3.1 8B (fallback) |
| Data | USDA FoodData Central Foundation Foods (nutrients) + curated functional properties |
| Tests | pytest + hypothesis (property-based) + a golden-set compliance eval, run in CI |
| Hosting | Vercel (frontend) + Render (backend) |

---

## Local setup

**Backend**
```bash
cd backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env   # add your GROQ_API_KEY
# (Re)build the governed ingredient dataset from the FDC bulk CSVs in backend/data/:
python -m etl.build_ingredients
uvicorn main:app --reload
```

**Frontend**
```bash
cd frontend
npm install
# create frontend/.env.local with: VITE_API_URL=http://localhost:8000
npm run dev
```

**Tests**
```bash
cd backend && pytest tests/ -v          # domain, gate, golden-set eval, API
cd frontend && npm run build            # tsc + vite build
```

---

## Project structure

```
formula-forge/
├── backend/
│   ├── main.py            # FastAPI app: streaming, validation gate wiring, abuse controls
│   ├── graph.py           # LangGraph: intent/module/iteration routing, RAG + formula agents
│   ├── llm.py             # Provider registry (Groq/OpenAI/Anthropic) + fallback chain
│   ├── config.py          # pydantic-settings (single .env load point)
│   ├── observability.py   # structured logging + per-request ids
│   ├── budget.py          # daily token budget
│   ├── json_utils.py      # shared JSON extraction
│   ├── domain/            # PURE food-science core
│   │   ├── models.py          # CandidateFormula (structure only) → ValidatedFormula
│   │   ├── composition.py     # mass balance, nutrients, PAC/POD, per-serving math
│   │   ├── validator.py       # the validation gate
│   │   ├── pipeline.py        # validate_candidate(): the only proposal→user route
│   │   ├── constraints/       # declarative renal/diabetic/… rulesets + evaluator
│   │   └── data/ingredients.json   # governed library (built by the ETL)
│   ├── etl/               # versioned FDC → governed-library build
│   ├── eval/              # golden-set compliance regression cases
│   ├── scripts/           # gen_frontend_types.py (Pydantic → TS)
│   └── tests/
└── frontend/
    └── src/
        ├── App.tsx        # chat + verification-surface formula card
        ├── lib/markdown.tsx
        └── types/api.ts   # GENERATED from the Pydantic models
```

---

## About

Bobby Craft is a food scientist and process engineer with 26 years of CPG R&D experience
at Post Cereals, Magnum Ice Cream (Unilever), Talenti, and Breyers. FormulaForge grew out
of a direct problem: early-stage product development in clinical nutrition requires rapid
ingredient feasibility assessment that typically takes a team of formulators weeks to
scope. This project applies agentic AI to compress that process — built to reflect the
actual constraint hierarchies a clinical nutritionist or product developer works within,
not a generic LLM wrapper.

[LinkedIn](https://linkedin.com/in/craft-bobby-5739b6) · [GitHub](https://github.com/craft-b/formula-forge)
