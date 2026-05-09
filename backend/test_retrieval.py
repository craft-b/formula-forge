import chromadb

client = chromadb.PersistentClient(path="./chroma_db")
collection = client.get_or_create_collection(name="usda_foods")

results = collection.query(
    query_texts=["hummus chickpea"],
    n_results=5
)

for doc in results["documents"][0]:
    print(doc)