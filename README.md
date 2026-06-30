# FormulaForge

FormulaForge was built by a food scientist and process engineer with 26 years of CPG R&D
experience — Post Cereals, Magnum Ice Cream (Unilever), Talenti, and Breyers — because
that career made one thing clear: early-stage product scoping in clinical and medical
nutrition wastes weeks on questions a trained formulator can answer in minutes. This system
compresses that cycle using a LangGraph agent, Groq Llama 3.3 70B, and 1,000 USDA
Foundation Foods.

**[→ Try the live demo](https://formula-forge-chi.vercel.app)**

[![API Status](https://img.shields.io/badge/API-live-brightgreen)](https://formula-forge-qye9.onrender.com/health)
[![Frontend](https://img.shields.io/badge/App-Vercel-black)](https://formula-forge-chi.vercel.app)
[![Python](https://img.shields.io/badge/Python-3.11-blue)]()
[![LangGraph](https://img.shields.io/badge/LangGraph-agentic-orange)]()

---

## What it does

FormulaForge targets the early-stage scoping problem in clinical and medical nutrition:
renal-diet, dysphagia-safe, oncology-targeted, and post-surgical formulations. A food
scientist types a request. The agent detects formulation intent, queries 1,000 USDA
Foundation Foods, and returns either a structured formula with ingredient percentages and
estimated nutrition, or a targeted ingredient or regulatory answer — all inside a single
chat session with persistent conversation memory.

The formulation outputs are domain-accurate because the system was designed by someone who
has built these products at scale. The prompts reflect real constraint hierarchies:
phosphorus limits before protein targets in renal diet, osmolality bounds in tube feeds,
IDDSI compliance categories for dysphagia. That context is not in the USDA database — it
comes from the engineer who built the system.

**Example query:** *"Create a formula for a high-protein renal-diet shake"*

<img width="479" height="491" alt="image" src="https://github.com/user-attachments/assets/a767f0a6-9b42-41e6-9e2f-d183573b838b" />

---

## Architecture

```
POST /api/chat
      │
      ▼
  main.py  ── session_id → conversation_store (in-memory history)
      │
      ▼
  LangGraph
      │
  orchestrator
  detect_intent(message)
      │
      ├─── "formulate" ──► formula_agent
      │                        │
      │                    search_foods()   ← USDA JSON keyword match
      │                        │
      │                    Groq Llama 3.3 70B
      │                        │
      │                    structured JSON formula
      │
      └─── "search"  ──►  rag_agent
                               │
                           search_foods()   ← USDA JSON keyword match
                               │
                           Groq Llama 3.3 70B + message history
                               │
                           text response
      │
      ▼
  main.py  ── parse formula JSON → ChatResponse{response, formula, session_id}
      │
      ▼
  React frontend  ── formula? render FormulaCard : render text bubble
```

### Key design decisions

| Decision | What we did | Why |
|---|---|---|
| Embeddings | Keyword scoring over USDA JSON | No ONNX/model download on Render free tier — cold starts killed the service |
| LLM routing | `detect_intent()` trigger phrases, not an LLM call | Avoids extra latency and token cost on every message |
| LLM abstraction | `llm.py` provider swap layer | Swap Groq → OpenAI → Anthropic via env var with zero graph changes |
| Session memory | In-memory `dict` keyed by `session_id` | Free tier has no persistent storage; good enough for single-session use |
| Formula structure | LLM returns raw JSON, `main.py` parses and validates | Keeps graph.py stateless; frontend gets a typed object, not a string to parse |

---

## Stack

| Layer | Tech |
|---|---|
| Frontend | React 19 + TypeScript + Vite + Tailwind v4 + shadcn/ui (Nova) |
| Backend | FastAPI + LangGraph + langchain-groq |
| LLM | Groq — Llama 3.3 70B Versatile |
| Data | USDA FoodData Central Foundation Foods (1,000 foods as JSON) |
| Hosting | Vercel (frontend) + Render (backend) |

---

## Local setup

**Backend**
```bash
cd backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # add your GROQ_API_KEY
uvicorn main:app --reload
```

**Frontend**
```bash
cd frontend
npm install
# create frontend/.env.local with: VITE_API_URL=http://localhost:8000
npm run dev
```

---

## Project structure

```
formula-forge/
├── backend/
│   ├── main.py          # FastAPI app, session store, formula JSON parsing
│   ├── graph.py         # LangGraph — orchestrator, rag_agent, formula_agent
│   ├── llm.py           # Provider swap layer (Groq / OpenAI / Anthropic)
│   ├── usda_foods.json  # 1,000-row USDA Foundation Foods dataset
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    └── src/
        └── App.tsx      # Chat UI, FormulaCard, session management
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
