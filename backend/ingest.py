import pandas as pd
import chromadb
import os

# Load USDA data
food_df = pd.read_csv("data/food.csv")

# Take first 1000 rows, clean it up
food_df = food_df[["fdc_id", "description"]].dropna().head(1000)

# Set up ChromaDB local persistent storage
client = chromadb.PersistentClient(path="./chroma_db")

# Create or get collection
collection = client.get_or_create_collection(name="usda_foods")

# Ingest
collection.add(
    documents=food_df["description"].tolist(),
    ids=[str(i) for i in food_df["fdc_id"].tolist()]
)

print(f"Ingested {len(food_df)} foods into ChromaDB")