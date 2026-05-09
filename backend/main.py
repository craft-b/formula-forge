import asyncio
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


def _seed_chroma():
    import chromadb
    client = chromadb.PersistentClient(path="./chroma_db")
    collection = client.get_or_create_collection(name="usda_foods")
    if collection.count() == 0:
        print("ChromaDB empty — seeding sample foods...")
        sample_foods = [
            "Chicken, broilers or fryers, breast, meat only, cooked, roasted",
            "Beef, ground, 90% lean meat / 10% fat, patty, cooked, broiled",
            "Salmon, Atlantic, farmed, cooked, dry heat",
            "Egg, whole, cooked, hard-boiled",
            "Lentils, mature seeds, cooked, boiled, without salt",
            "Quinoa, cooked",
            "Almonds, dry roasted, without salt added",
            "Broccoli, cooked, boiled, drained, without salt",
            "Sweet potato, cooked, baked in skin, without salt",
            "Greek yogurt, plain, nonfat",
        ]
        collection.add(
            documents=sample_foods,
            ids=[str(i) for i in range(len(sample_foods))],
        )
        print(f"Seeded {len(sample_foods)} foods into ChromaDB")
    else:
        print(f"ChromaDB ready — {collection.count()} foods loaded")


@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_event_loop()
    executor = ThreadPoolExecutor(max_workers=1)
    loop.run_in_executor(executor, _seed_chroma)
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


class ChatResponse(BaseModel):
    response: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/chat")
def chat(req: ChatRequest):
    from graph import agent
    from langchain_core.messages import HumanMessage

    result = agent.invoke({"messages": [HumanMessage(content=req.message)]})
    return ChatResponse(response=result["messages"][-1].content)
