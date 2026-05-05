# FormulaForge

> Agentic AI for specialized food R&D — multi-agent system for clinical and medical food formulation.

[![Build Status](https://img.shields.io/badge/status-in%20development-yellow)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

## What this is

FormulaForge is a multi-agent AI system that compresses early-stage R&D scoping for **specialized food products** — renal-diet, dysphagia-safe, oncology-targeted, and post-surgical medical foods. It takes a product brief and produces a clinically informed, regulation-aware formulation concept with cost estimates in minutes rather than weeks.

## Why this exists

Traditional CPG R&D scoping is sequential and slow: concept → formulation → clinical/dietary review → regulatory review → cost analysis → revision. Each handoff loses context. Three weeks of work compresses into a few hours of orchestrated agent reasoning.

NotCo's Giuseppe AI has validated this category for mainstream CPG ($428M raised, partnerships with Kraft Heinz, Magnum, Barry Callebaut, Mondelēz). FormulaForge wedges into the **clinical and specialized food** vertical — a genuinely underserved market where renal-diet, dysphagia (IDDSI framework), and oncology-relevant constraints require different optimization than mainstream plant-based work.

## Architecture

Five LangGraph agents coordinated by a supervisor:

| Agent | Responsibility |
|-------|----------------|
| **Orchestrator** | Decomposes brief, routes tasks, manages state, produces final scoping doc |
| **Concept** | Generates 3–5 viable concept directions with target nutritional profiles |
| **Formulation** | Retrieves comparable products, suggests ingredient combinations |
| **Clinical Constraints** | Applies renal-diet, IDDSI dysphagia, and oncology-relevant rules |
| **Regulatory Compliance** | Checks against FDA labeling rules, allergen disclosure, medical food regulations |
| **Cost Estimation** | Approximates COGS and identifies cost-driver ingredients |

## Tech stack

**Frontend:** React 18 + TypeScript + Tailwind + shadcn/ui — deployed on Vercel
**Backend:** FastAPI + Python 3.12 — deployed on Railway
**Agents:** LangGraph for orchestration
**LLM:** Claude (Anthropic API) primary, Groq fallback
**Vector DB:** ChromaDB (local) → Pinecone (production)
**Database:** Supabase (Postgres)
**Observability:** LangSmith for trace inspection
**Auth:** Clerk (or API key for early demo)

## Data sources

- **USDA FoodData Central** — ingredient nutritional data
- **Open Food Facts** — comparable product corpus
- **FDA Food Labeling Guide** — regulatory RAG corpus
- **IDDSI framework** — dysphagia texture standards
- **PubMed** — clinical food/nutrition literature

## Status

Active build — Week 1, Day 1.

| Week | Milestone |
|------|-----------|
| 1 | Foundation: skeleton end-to-end |
| 2 | Concept Agent shipped |
| 3 | Formulation + Clinical Constraints |
| 4 | Regulatory Compliance |
| 5 | Cost Estimation + persistence + auth |
| 6 | Three flagship demos + eval harness |
| 7 | Polish + docs + Loom walkthrough |
| 8 | Public launch |

## Running locally

*(Setup instructions added as they become real — currently scaffolding only.)*

## License

MIT — see [LICENSE](./LICENSE)

## Author

Built by Rich — 26 years CPG R&D process engineering, MS AI/ML 2026. Background includes formulation work on Magnum, Talenti, Breyers, and other major frozen dessert brands.