import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from cachetools import TTLCache
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

# load_dotenv must run before graph import — graph.py calls get_llm() at module
# level, which reads GROQ_API_KEY and LangSmith vars from the environment.
load_dotenv()

from graph import agent, detect_modules, regenerate_formula
from domain import CandidateFormula, validate_candidate
from json_utils import extract_json_block
from budget import TokenBudget, estimate_tokens

logger = logging.getLogger(__name__)


def _parse_origins(raw: str) -> list[str]:
    return [o.strip() for o in raw.split(",") if o.strip()]


# ── Abuse controls (F4) ───────────────────────────────────────────────────────
# CORS locked to an explicit allowlist (no wildcard). Override via ALLOWED_ORIGINS.
ALLOWED_ORIGINS = _parse_origins(os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,http://localhost:3000,https://formula-forge-chi.vercel.app",
))
# Per-request rate limit, read at call time so tests can override the module global.
CHAT_RATE_LIMIT = os.getenv("CHAT_RATE_LIMIT", "30/minute")
# Daily token budgets (reserve-up-front) — global and per session.
budget = TokenBudget(
    global_daily=int(os.getenv("GLOBAL_DAILY_TOKENS", "2000000")),
    session_daily=int(os.getenv("SESSION_DAILY_TOKENS", "50000")),
)
limiter = Limiter(key_func=get_remote_address)


def _chat_rate_limit(*args, **kwargs) -> str:
    return CHAT_RATE_LIMIT


def _candidate_from_llm(raw: dict) -> CandidateFormula:
    """Adapt a raw LLM formula dict to a CandidateFormula (structure only).

    Any nutrition the LLM supplied is intentionally ignored — the domain layer
    computes all nutrition from the governed ingredient library.
    """
    ingredients = []
    for item in raw.get("ingredients", []):
        ingredients.append({
            "ref": item.get("ref") or item.get("name") or "",
            "percentage": item.get("percentage", 0),
            "notes": item.get("notes", ""),
        })
    return CandidateFormula(
        product_name=raw.get("product_name") or "Formula",
        description=raw.get("description", ""),
        product_format=raw.get("product_format") or "standard",
        overrun_pct=raw.get("overrun_pct"),
        ingredients=ingredients,
        formulation_notes=raw.get("formulation_notes", ""),
    )


def _parse_and_validate(raw_text: str, active_modules: Optional[list]):
    """Parse raw LLM text and run it through the domain gate. None on parse failure."""
    try:
        raw = json.loads(extract_json_block(raw_text))
        candidate = _candidate_from_llm(raw)
        return validate_candidate(candidate, active_modules=active_modules or [])
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Formula parse/validation setup failed: %s", exc)
        return None


def _repair_feedback(result) -> str:
    """Build repair instructions from a failed first attempt for the reprompt."""
    if result is None:
        return "The previous response was not valid JSON. Return a single JSON object."
    parts = [result.reason]
    if getattr(result, "unresolved_ingredients", None):
        parts.append("These ingredients are not in the allowed list and must be "
                     f"replaced: {', '.join(result.unresolved_ingredients)}.")
    for v in getattr(result, "violations", []):
        parts.append(v.explanation)
    return " ".join(parts)

# Keyed by session_id. Evicts sessions older than 1 hour or when cap is reached.
conversation_store: TTLCache = TTLCache(maxsize=500, ttl=3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # graph.py builds and compiles the LangGraph at import time above,
    # so by the time the first request arrives the graph is already warm.
    tracing = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
    logger.info(
        "FormulaForge startup: LangGraph agent ready | LangSmith tracing %s",
        "ENABLED" if tracing else "disabled",
    )
    yield


app = FastAPI(lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: Optional[str] = None



@app.get("/health")
def health():
    return {"status": "ok"}


async def _stream_agent(
    history: list, session_id: str, active_modules: Optional[list] = None
) -> AsyncGenerator[str, None]:
    """SSE generator that streams LLM tokens to the client.

    RAG responses stream token-by-token. Formula responses accumulate silently
    (streaming raw JSON mid-parse is meaningless to the client) and are sent as
    a single structured event once the LLM finishes. The frontend renders a
    FormulaCard without any client-side JSON assembly.

    Event types emitted:
      {"type": "token",   "content": str}         — one per RAG token
      {"type": "formula", "formula": dict,
                          "response": str}         — end of formula run
      {"type": "error",   "message": str}         — on agent failure
      {"type": "done",    "session_id": str}      — always last
    """
    formula_buffer = ""
    streamed_text = ""
    is_formula_run = False

    try:
        async for event in agent.astream_events({"messages": history}, version="v2"):
            kind = event["event"]
            node = event.get("metadata", {}).get("langgraph_node", "")

            if kind == "on_chain_start" and node == "formula_agent":
                is_formula_run = True

            elif kind == "on_chat_model_stream":
                token = getattr(event["data"]["chunk"], "content", "") or ""
                if not token:
                    continue
                if is_formula_run:
                    formula_buffer += token
                else:
                    streamed_text += token
                    yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

        ai_content = streamed_text
        if is_formula_run and formula_buffer:
            # The validation gate: every formula passes through validate_candidate.
            # There is no path that emits LLM numbers directly to the client.
            result = _parse_and_validate(formula_buffer, active_modules)

            # Exactly one repair re-prompt when the first attempt cannot be turned
            # into a usable formula (unparseable or rejected). Computable-but-
            # non-compliant formulas are surfaced flagged, not repaired (v1).
            if result is None or result.type == "rejection":
                user_msgs = [m for m in history if isinstance(m, HumanMessage)]
                user_message = user_msgs[-1].content if user_msgs else ""
                try:
                    repaired_raw = regenerate_formula(user_message, _repair_feedback(result))
                    retry = _parse_and_validate(repaired_raw, active_modules)
                    if retry is not None and (result is None or retry.type == "formula"):
                        result = retry
                except Exception:
                    logger.exception("Formula repair re-prompt failed for %s", session_id)

            if result is None:
                yield f"data: {json.dumps({'type': 'error', 'message': 'The agent did not return a usable formula. Please try rephrasing your request.'})}\n\n"
            elif result.type == "formula":
                passed = result.validation.passed
                verb = "a verified" if passed else "a flagged"
                response_text = f"Here's {verb} formula for {result.product_name}."
                yield f"data: {json.dumps({'type': 'formula', 'formula': result.model_dump(), 'response': response_text})}\n\n"
                ai_content = f"[formula] {result.product_name} — {'passed' if passed else 'flagged'} validation."
            else:  # RejectedFormula
                response_text = f"That formula could not be verified: {result.reason}"
                yield f"data: {json.dumps({'type': 'rejection', 'rejection': result.model_dump(), 'response': response_text})}\n\n"
                ai_content = f"[rejected] {result.product_name} — {result.reason}"

        conversation_store[session_id] = history + [AIMessage(content=ai_content)]

    except Exception:
        logger.exception("Streaming failed for session %s", session_id)
        yield f"data: {json.dumps({'type': 'error', 'message': 'The formulation agent encountered an error. Please try again.'})}\n\n"

    yield f"data: {json.dumps({'type': 'done', 'session_id': session_id})}\n\n"
    yield "data: [DONE]\n\n"


@app.post("/api/chat")
@limiter.limit(_chat_rate_limit)
async def chat(request: Request, req: ChatRequest):
    session_id = req.session_id or str(uuid.uuid4())

    # Token budget: reserve an estimate up front so a burst cannot overrun.
    est = estimate_tokens(req.message)
    if not budget.allow(session_id, est):
        return JSONResponse(
            status_code=429,
            content={"error": "Daily token budget exceeded. Please try again tomorrow."},
        )
    budget.record(session_id, est)

    history = list(conversation_store.get(session_id, []))
    history.append(HumanMessage(content=req.message))
    active_modules = detect_modules(req.message)

    return StreamingResponse(
        _stream_agent(history, session_id, active_modules),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # prevents nginx from buffering chunks on Render
        },
    )
