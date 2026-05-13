import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

conversation_store: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    session_id: str
    formula: Optional[dict] = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/chat")
def chat(req: ChatRequest):
    from graph import agent
    from langchain_core.messages import HumanMessage

    session_id = req.session_id or str(uuid.uuid4())
    history = conversation_store.get(session_id, [])
    history.append(HumanMessage(content=req.message))

    result = agent.invoke({"messages": history})
    updated_messages = result["messages"]
    conversation_store[session_id] = updated_messages

    last_content = updated_messages[-1].content

    formula = None
    response_text = last_content
    try:
        parsed = json.loads(last_content)
        if isinstance(parsed, dict) and parsed.get("type") == "formula":
            formula = parsed
            response_text = f"Here's a formula for **{formula.get('product_name', 'your product')}**:"
    except (json.JSONDecodeError, ValueError, AttributeError):
        pass

    return ChatResponse(
        response=response_text,
        session_id=session_id,
        formula=formula,
    )
