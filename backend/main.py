import asyncio
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


def _seed_chroma():
    import chromadb
    import json
    import os

    client = chromadb.PersistentClient(path="./chroma_db")
    collection = client.get_or_create_collection(name="usda_foods")

    if collection.count() == 0:
        print("ChromaDB empty — loading USDA data from JSON...")
        json_path = os.path.join(os.path.dirname(__file__), "usda_foods.json")
        with open(json_path, "r") as f:
            foods = json.load(f)

        documents = [food["description"] for food in foods]
        ids = [str(food["fdc_id"]) for food in foods]

        batch_size = 100
        total_batches = (len(documents) + batch_size - 1) // batch_size
        for i in range(0, len(documents), batch_size):
            collection.add(
                documents=documents[i:i + batch_size],
                ids=ids[i:i + batch_size],
            )
            print(f"Ingested batch {i // batch_size + 1}/{total_batches}")

        print(f"Seeded {len(documents)} foods into ChromaDB")
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
