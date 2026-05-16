# FormulaForge

**AI-powered food formulation assistant for clinical and medical nutrition R&D.**

[![Backend health](https://img.shields.io/badge/API-live-brightgreen)](https://formula-forge-qye9.onrender.com/health)
[![Frontend](https://img.shields.io/badge/App-Vercel-black)](https://formula-forge-chi.vercel.app)
[![Built in public](https://img.shields.io/badge/built_in_public-8_weeks-teal)]()

---

## What it does

FormulaForge compresses early-stage R&D scoping for clinical and medical food products — renal-diet, dysphagia-safe, oncology-targeted, and post-surgical formulations.

A food scientist types a request. The agent detects formulation intent, queries 1,000 USDA Foundation Foods, and returns either a structured formula with ingredient percentages and estimated nutrition, or a targeted ingredient/regulatory answer — all inside a single chat session with memory.

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

## Built by

Bobby Craft — building in public, 8 weeks, $0 budget.

<!-- TODO: replace with your actual LinkedIn URL -->
[LinkedIn](https://linkedin.com/in/craft-bobby-5739b6) · [GitHub](https://github.com/craft-b/formula-forge)
