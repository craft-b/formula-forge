import json
import logging
import os
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
from config import groq_key_fingerprint, settings

from graph import (
    agent,
    detect_iteration,
    detect_modules,
    formula_llm,
    iterate_formula,
    regenerate_formula,
)
from generation import parse_and_validate as _parse_and_validate
from llm import verify_model_available
from budget import TokenBudget, estimate_tokens
from observability import new_request_id, request_id_var, setup_logging

setup_logging(settings.log_level)
logger = logging.getLogger(__name__)


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


def _repair_feedback(result) -> str:
    """Build repair instructions from a failed first attempt for the reprompt."""
    if result is None:
        return "The previous response was not valid JSON. Return a single JSON object."
    if result.type == "formula":
        # Computable but non-compliant: feed the measured-vs-limit failures back.
        parts = ["The formula computed successfully but FAILED these active "
                 "dietary constraints:"]
        for v in result.validation.violations or []:
            if v.severity != "error":
                continue
            detail = v.explanation
            if v.measured is not None and v.limit is not None:
                detail += f" (measured {v.measured}, limit {v.limit})"
            parts.append(detail)
        parts.append("Rework the ingredient structure and percentages to satisfy "
                     "every constraint.")
        return " ".join(parts)
    parts = [result.reason]
    if getattr(result, "unresolved_ingredients", None):
        parts.append("These ingredients are not in the allowed list and must be "
                     f"replaced: {', '.join(result.unresolved_ingredients)}.")
    for v in getattr(result, "violations", []):
        parts.append(v.explanation)
    return " ".join(parts)


def _compliance_errors(result) -> int:
    """Count error-severity violations on a validated formula (∞-ish otherwise)."""
    if result is None or result.type != "formula":
        return 10_000
    return sum(1 for v in (result.validation.violations or []) if v.severity == "error")


def _summarize_formula(vf) -> str:
    """Compact, human-readable parent summary carried into an iteration prompt."""
    lines = "; ".join(f"{l.ingredient_name} {l.percentage}%" for l in vf.ingredients)
    return f"{vf.product_name} [{vf.product_format}]: {lines}"


def _resolve_formula(raw_text: str, active_modules, user_message: str,
                     parent: Optional[str] = None,
                     product_format: Optional[str] = None):
    """Parse + validate a formula, with exactly one repair re-prompt on failure.

    Repair fires when the attempt can't be parsed/resolved OR when it computed
    but failed compliance (error-severity violations) — the measured-vs-limit
    numbers are fed back so the retry designs toward the limits. If the retry
    is no better, the attempt with fewer compliance errors is returned, still
    honestly flagged. Never more than one repair call (cost control).
    """
    result = _parse_and_validate(raw_text, active_modules, product_format)
    if result is not None and result.type == "formula" and result.validation.passed:
        return result
    try:
        feedback = _repair_feedback(result)
        repaired = (iterate_formula(user_message, parent, feedback,
                                    modules=active_modules) if parent
                    else regenerate_formula(user_message, feedback,
                                            modules=active_modules))
        retry = _parse_and_validate(repaired, active_modules, product_format)
        if retry is not None and _compliance_errors(retry) < _compliance_errors(result):
            result = retry
        elif retry is not None and result is None:
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
        "FormulaForge startup: LangGraph agent ready | LangSmith tracing %s | GROQ key %s",
        "ENABLED" if settings.langchain_tracing_v2 else "disabled",
        groq_key_fingerprint(),
    )

    # Verify the configured model exists, once, and cache the verdict for the
    # readiness probe. A retired model previously sat behind a green /health
    # while every generation request 404'd; the probes take no network call by
    # design, so the check has to happen here instead.
    status, detail = verify_model_available(_active_model())
    app.state.model_check = (status, detail)
    log = logger.error if status == "missing" else logger.info
    log("Model readiness: %s — %s", status, detail)
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
    except Exception:
        # Deliberately no reset on this path. The handler that turns this into a
        # 500 runs *outside* this middleware, so resetting here would unbind the
        # id before the one log line that describes the failure is written --
        # leaving the only request anyone would report as the only request with
        # no correlation id. The contextvar is task-local, so leaving it set
        # cannot leak into another request.
        raise
    request_id_var.reset(token)
    response.headers["X-Request-ID"] = rid
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Give unhandled failures the same correlation id every other response gets.

    Without this the 500 is generated above the middleware and carries neither
    the X-Request-ID header nor an id in its body, so a user reporting "it broke"
    has nothing to quote and the logs have nothing to search. The exception class
    is surfaced and the message is not -- same rule the SSE error path follows,
    since a message can carry internals a caller should not see.
    """
    rid = request_id_var.get()
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"type": "error", "error": type(exc).__name__, "request_id": rid},
        headers={"X-Request-ID": rid},
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: Optional[str] = None
    # Explicit constraint-module selection from the brief builder UI. Unioned
    # with keyword detection; unknown ids are ignored (validated server-side).
    modules: Optional[list[str]] = None
    # Explicit product-format selection from the brief builder. Applied ONLY on
    # formula runs (overrides the LLM's guess); ignored for RAG questions, so a
    # question is never polluted with formulation settings.
    product_format: Optional[str] = None
    # Explicit routing intent. "formulate" forces the formula path — the UI's
    # "Generate verified formula" CTA must never fall through to Q&A because the
    # keyword regex missed the phrasing. Anything else means auto-detect.
    intent: Optional[str] = None


@app.get("/api/meta")
def meta():
    """Workspace metadata for the frontend: dataset lineage + available modules."""
    from domain import available_modules, get_repository
    from domain.constraints import get_ruleset

    repo = get_repository()
    modules = []
    for mid in available_modules():
        rs = get_ruleset(mid) or {}
        modules.append({
            "id": mid,
            "label": rs.get("label", mid),
            "stub": bool(rs.get("stub", False)),
            "requires_professional_review": bool(rs.get("requires_professional_review", False)),
        })
    return {
        "dataset_version": repo.version,
        "ingredient_count": len(repo.ingredients),
        "modules": modules,
        "model": settings.groq_model,
    }



@app.get("/api/ideas")
def api_ideas():
    """The Idea Stream: trend corpus ranked by the deterministic scoring engine."""
    from ideas import ranked_ideas
    return ranked_ideas()


# ── Readiness (F19 operability) ───────────────────────────────────────────────
# Every probe below is local: no network call, no token spend, no writes. A live
# Groq call here would turn each uptime check into a billing line item and couple
# our liveness to a third party's availability — an outage at the provider would
# take this instance out of rotation even though it can still serve /api/meta,
# /api/ideas, and every cached path. All three dependencies are critical: without
# any one of them a formulation request cannot be served, so any failure is a 503.


def _active_model() -> str:
    """The model id this process will actually call.

    Mirrors `llm._model_for()` — the source of truth — so a non-Groq deployment
    does not get told it is running a Groq model.
    """
    if settings.llm_provider.lower() == "groq":
        return settings.groq_model
    return os.getenv("LLM_MODEL") or "unset"


def _probe_llm_client() -> dict:
    """Is a chat model configured, constructed, and does it still exist?

    Still no network call: the third question is answered from the verdict
    `lifespan` cached at startup. That indirection is the point — a configured
    model that has since been retired used to report "ok" here while every
    generation request failed with 404, because "constructed" and "exists" are
    different questions and only the first was being asked.

    `groq_key_fingerprint()` is used ONLY as a presence oracle. Its return value
    carries the key's exact length plus an 11-character window of the key — safe
    for a private startup log, never for an unauthenticated response body.
    """
    if groq_key_fingerprint() == "MISSING":
        return {"status": "unavailable", "detail": "API key is not configured."}
    # graph.py binds formula_llm from the same base client the RAG path uses, so
    # one check covers both routes.
    if formula_llm is None or not hasattr(formula_llm, "invoke"):
        return {"status": "unavailable", "detail": "Chat model failed to initialize."}

    status, detail = getattr(app.state, "model_check", ("unverified", "Not yet checked."))
    if status == "missing":
        return {"status": "unavailable", "detail": detail}
    if status == "unverified":
        # Could not confirm either way. Do not fail a possibly-working instance
        # over a metadata call, but do not claim it is verified either.
        return {"status": "ok",
                "detail": f"API key configured; chat model initialized. {detail}"}
    return {"status": "ok", "detail": f"API key configured; chat model initialized. {detail}"}


def _probe_agent_graph() -> dict:
    """Did the LangGraph agent compile at import time (see lifespan)?"""
    if agent is None or not hasattr(agent, "astream_events"):
        return {"status": "unavailable", "detail": "LangGraph agent did not load."}
    return {"status": "ok", "detail": "Compiled LangGraph agent loaded."}


def _probe_ingredient_library() -> dict:
    """Is the governed library readable? Without it nothing can be verified.

    `get_repository()` is lru_cached, so this loads once and is free thereafter.
    It is also the check that catches a container built without domain/data/.
    """
    try:
        from domain import get_repository
        repo = get_repository()
        count = len(repo.ingredients)
    except Exception as exc:
        logger.exception("Ingredient library readiness probe failed")
        return {"status": "unavailable",
                "detail": f"Library could not be loaded ({type(exc).__name__})."}
    if count == 0:
        return {"status": "unavailable", "detail": "Ingredient library is empty."}
    return {"status": "ok",
            "detail": f"dataset {repo.version or 'unversioned'}, {count} ingredients."}


def readiness_report() -> tuple[dict, bool]:
    """(response body, healthy) for the readiness probe."""
    dependencies = {
        "llm_client": _probe_llm_client(),
        "agent_graph": _probe_agent_graph(),
        "ingredient_library": _probe_ingredient_library(),
    }
    healthy = all(d["status"] == "ok" for d in dependencies.values())
    return {
        "status": "ok" if healthy else "unavailable",
        "version": settings.app_version,
        "model": _active_model(),
        "dependencies": dependencies,
    }, healthy


@app.get("/health")
def health():
    """Readiness: can this instance actually serve a formulation request?

    200 when every critical dependency is ready, 503 otherwise — a probe that
    always returns 200 tells an uptime monitor nothing. Deliberately not
    rate-limited: an uptime monitor must not be able to lock itself out, and the
    endpoint spends nothing.
    """
    body, healthy = readiness_report()
    return JSONResponse(status_code=200 if healthy else 503, content=body)


async def _stream_agent(
    history: list, session_id: str, active_modules: Optional[list] = None,
    iteration_parent: Optional[str] = None, product_format: Optional[str] = None,
    force_formulate: bool = False,
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
            raw = iterate_formula(user_message, iteration_parent,
                                  modules=active_modules)
            result = _resolve_formula(raw, active_modules, user_message,
                                      parent=iteration_parent,
                                      product_format=product_format)
            for chunk in _emit_and_store(result, session_id, history):
                yield chunk
        else:
            formula_buffer = ""
            streamed_text = ""
            is_formula_run = False
            graph_input = {"messages": history, "modules": active_modules}
            if force_formulate:
                graph_input["intent"] = "formulate"
            async for event in agent.astream_events(graph_input, version="v2"):
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
                elif kind == "on_chain_end" and (node == "formula_agent" or event.get("name") == "formula_agent"):
                    # Groq JSON mode does not stream, so on_chat_model_stream
                    # never fires for formula runs — recover the node's final
                    # AIMessage here or the run would end silently. The raw
                    # text still passes through the domain validation gate.
                    output = (event.get("data") or {}).get("output") or {}
                    messages = output.get("messages") if isinstance(output, dict) else None
                    if messages:
                        content = getattr(messages[-1], "content", "") or ""
                        if content:
                            formula_buffer = content

            if is_formula_run and formula_buffer:
                # The validation gate: no path emits LLM numbers to the client.
                result = _resolve_formula(formula_buffer, active_modules, user_message,
                                          product_format=product_format)
                for chunk in _emit_and_store(result, session_id, history):
                    yield chunk
            else:
                conversation_store[session_id] = history + [AIMessage(content=streamed_text)]

    except Exception as exc:
        logger.exception("Streaming failed for session %s", session_id)
        # Exception class only — safe to surface (no message content, so no
        # secrets), and it turns "something broke" into a reportable signal.
        detail = type(exc).__name__
        yield f"data: {json.dumps({'type': 'error', 'message': f'The formulation agent encountered an error ({detail}). Please try again.'})}\n\n"

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

    # Active modules = keyword detection ∪ explicit brief-builder selection
    # (unknown ids ignored). Order kept stable for display.
    from domain import available_modules as _avail
    known = set(_avail())
    active_modules = detect_modules(req.message)
    for m in req.modules or []:
        if m in known and m not in active_modules:
            active_modules.append(m)

    # Explicit product format (brief builder) — validated, applied only if the
    # run turns out to be a formula run.
    from domain.constants import DEFAULT_OVERRUN
    product_format = req.product_format if req.product_format in DEFAULT_OVERRUN else None

    # Iteration: a delta request against this session's existing formula (F7).
    parent = last_formula_store.get(session_id)
    iteration_parent = parent if (parent and detect_iteration(req.message)) else None

    return StreamingResponse(
        _stream_agent(history, session_id, active_modules, iteration_parent,
                      product_format, force_formulate=req.intent == "formulate"),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # prevents nginx from buffering chunks on Render
        },
    )
