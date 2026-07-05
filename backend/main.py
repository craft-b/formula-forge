import json
import logging
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from cachetools import TTLCache
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

# config import is the single .env load point (F15); must precede graph import
# because graph.py calls get_llm() at module level.
from config import settings

from graph import (
    agent,
    detect_iteration,
    detect_modules,
    iterate_formula,
    regenerate_formula,
)
from domain import CandidateFormula, validate_candidate
from json_utils import extract_json_block
from budget import TokenBudget, estimate_tokens
from observability import new_request_id, request_id_var, setup_logging

setup_logging(settings.log_level)
logger = logging.getLogger(__name__)


def _parse_origins(raw: str) -> list[str]:
    return [o.strip() for o in raw.split(",") if o.strip()]


# ── Abuse controls (F4) ───────────────────────────────────────────────────────
# CORS locked to an explicit allowlist (no wildcard).
ALLOWED_ORIGINS = settings.origins
# Per-request rate limit, read at call time so tests can override the module global.
CHAT_RATE_LIMIT = settings.chat_rate_limit
# Daily token budgets (reserve-up-front) — global and per session.
budget = TokenBudget(
    global_daily=settings.global_daily_tokens,
    session_daily=settings.session_daily_tokens,
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


def _summarize_formula(vf) -> str:
    """Compact, human-readable parent summary carried into an iteration prompt."""
    lines = "; ".join(f"{l.ingredient_name} {l.percentage}%" for l in vf.ingredients)
    return f"{vf.product_name} [{vf.product_format}]: {lines}"


def _resolve_formula(raw_text: str, active_modules, user_message: str,
                     parent: Optional[str] = None):
    """Parse + validate a formula, with exactly one repair re-prompt on failure.

    Repair regenerates via the iteration prompt when a parent is present, else a
    fresh generation. Computable-but-non-compliant formulas are returned flagged
    (not repaired) so the user sees the verification surface.
    """
    result = _parse_and_validate(raw_text, active_modules)
    if result is not None and result.type == "formula":
        return result
    try:
        feedback = _repair_feedback(result)
        repaired = (iterate_formula(user_message, parent, feedback) if parent
                    else regenerate_formula(user_message, feedback))
        retry = _parse_and_validate(repaired, active_modules)
        if retry is not None and (result is None or retry.type == "formula"):
            result = retry
    except Exception:
        logger.exception("Formula repair re-prompt failed")
    return result


def _emit_and_store(result, session_id: str, history: list):
    """Yield SSE for a formula/rejection result and update the session stores.

    Successful formulas are remembered per session (rendered summary only) so a
    follow-up can iterate on them; conversation history stores a short summary,
    never the raw JSON, keeping later RAG turns clean (F9).
    """
    if result is None:
        yield f"data: {json.dumps({'type': 'error', 'message': 'The agent did not return a usable formula. Please try rephrasing your request.'})}\n\n"
        ai_content = "[formula] generation failed."
    elif result.type == "formula":
        passed = result.validation.passed
        verb = "a verified" if passed else "a flagged"
        response_text = f"Here's {verb} formula for {result.product_name}."
        yield f"data: {json.dumps({'type': 'formula', 'formula': result.model_dump(), 'response': response_text})}\n\n"
        ai_content = f"[formula] {result.product_name} — {'passed' if passed else 'flagged'} validation."
        last_formula_store[session_id] = _summarize_formula(result)
    else:  # RejectedFormula
        response_text = f"That formula could not be verified: {result.reason}"
        yield f"data: {json.dumps({'type': 'rejection', 'rejection': result.model_dump(), 'response': response_text})}\n\n"
        ai_content = f"[rejected] {result.product_name} — {result.reason}"
    conversation_store[session_id] = history + [AIMessage(content=ai_content)]

# Keyed by session_id. Evicts sessions older than 1 hour or when cap is reached.
conversation_store: TTLCache = TTLCache(maxsize=500, ttl=3600)
# Last validated formula per session, for parent-anchored iteration (F7).
last_formula_store: TTLCache = TTLCache(maxsize=500, ttl=3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # graph.py builds and compiles the LangGraph at import time above,
    # so by the time the first request arrives the graph is already warm.
    logger.info(
        "FormulaForge startup: LangGraph agent ready | LangSmith tracing %s",
        "ENABLED" if settings.langchain_tracing_v2 else "disabled",
    )
    yield


app = FastAPI(lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Attach a correlation id to every request for traceable structured logs."""
    rid = request.headers.get("X-Request-ID") or new_request_id()
    token = request_id_var.set(rid)
    try:
        response = await call_next(request)
    finally:
        request_id_var.reset(token)
    response.headers["X-Request-ID"] = rid
    return response

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
    history: list, session_id: str, active_modules: Optional[list] = None,
    iteration_parent: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """SSE generator that streams LLM tokens to the client.

    Three paths:
      * Iteration — a delta request against the session's existing formula.
        Generates a modified formula directly (no token streaming) and emits it.
      * Formula — a fresh formulation request routed through the graph; tokens
        are buffered (streaming raw JSON is meaningless) and the validated
        formula is emitted once complete.
      * RAG — an ingredient/nutrition question; tokens stream to the client.

    Every formula (fresh or iterated) passes through the domain validation gate.

    Event types emitted:
      {"type": "token",     "content": str}                 — one per RAG token
      {"type": "formula",   "formula": dict, "response": str}
      {"type": "rejection", "rejection": dict, "response": str}
      {"type": "error",     "message": str}
      {"type": "done",      "session_id": str}               — always last
    """
    user_msgs = [m for m in history if isinstance(m, HumanMessage)]
    user_message = user_msgs[-1].content if user_msgs else ""

    try:
        if iteration_parent is not None:
            # Modify the existing formula from the delta request (F7).
            raw = iterate_formula(user_message, iteration_parent)
            result = _resolve_formula(raw, active_modules, user_message,
                                      parent=iteration_parent)
            for chunk in _emit_and_store(result, session_id, history):
                yield chunk
        else:
            formula_buffer = ""
            streamed_text = ""
            is_formula_run = False
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

            if is_formula_run and formula_buffer:
                # The validation gate: no path emits LLM numbers to the client.
                result = _resolve_formula(formula_buffer, active_modules, user_message)
                for chunk in _emit_and_store(result, session_id, history):
                    yield chunk
            else:
                conversation_store[session_id] = history + [AIMessage(content=streamed_text)]

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

    # Iteration: a delta request against this session's existing formula (F7).
    parent = last_formula_store.get(session_id)
    iteration_parent = parent if (parent and detect_iteration(req.message)) else None

    return StreamingResponse(
        _stream_agent(history, session_id, active_modules, iteration_parent),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # prevents nginx from buffering chunks on Render
        },
    )
