import os
import pandas as pd
import chromadb

def ensure_db_populated():
    client = chromadb.PersistentClient(path="./chroma_db")
    collection = client.get_or_create_collection(name="usda_foods")
    if collection.count() == 0:
        print("ChromaDB empty — ingesting USDA data...")
        # For Render: use a small hardcoded sample since CSV won't be there
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
            "Greek yogurt, plain, nonfat"
        ]
        collection.add(
            documents=sample_foods,
            ids=[str(i) for i in range(len(sample_foods))]
        )
        print(f"Ingested {len(sample_foods)} seed foods")

ensure_db_populated()