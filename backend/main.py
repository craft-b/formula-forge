import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from cachetools import TTLCache
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field

# load_dotenv must run before graph import — graph.py calls get_llm() at module
# level, which reads GROQ_API_KEY and LangSmith vars from the environment.
load_dotenv()

from graph import agent, detect_modules
from domain import CandidateFormula, validate_candidate

logger = logging.getLogger(__name__)


def _extract_json_block(text: str) -> str:
    """Pull the first JSON object out of an LLM response, tolerating code fences."""
    raw = text.strip()
    if "```" in raw:
        for block in raw.split("```"):
            cleaned = block.strip()
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].strip()
            if cleaned.startswith("{"):
                return cleaned
    return raw


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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
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
            try:
                raw = json.loads(_extract_json_block(formula_buffer))
                candidate = _candidate_from_llm(raw)
                result = validate_candidate(candidate, active_modules=active_modules or [])
            except (json.JSONDecodeError, ValueError) as exc:
                logger.warning("Formula parse/validation setup failed: %s", exc)
                yield f"data: {json.dumps({'type': 'error', 'message': 'The agent did not return a usable formula. Please try rephrasing your request.'})}\n\n"
                result = None

            if result is not None and result.type == "formula":
                passed = result.validation.passed
                verb = "a verified" if passed else "a flagged"
                response_text = f"Here's {verb} formula for {result.product_name}."
                yield f"data: {json.dumps({'type': 'formula', 'formula': result.model_dump(), 'response': response_text})}\n\n"
                ai_content = f"[formula] {result.product_name} — {'passed' if passed else 'flagged'} validation."
            elif result is not None:  # RejectedFormula
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
async def chat(req: ChatRequest):
    session_id = req.session_id or str(uuid.uuid4())
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
