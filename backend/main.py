import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import uuid

load_dotenv()

conversation_store = {}

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
    session_id: str = None

class ChatResponse(BaseModel):
    response: str
    session_id: str

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

    return ChatResponse(
        response=updated_messages[-1].content,
        session_id=session_id
    )