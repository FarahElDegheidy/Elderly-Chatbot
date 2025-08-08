import chromadb

# Config
collection_name = "recipestest"
chroma_client = chromadb.HttpClient(host="localhost", port=8000)
collection = chroma_client.get_collection(name=collection_name)

# Query all entries (up to 1000 at once)
results = collection.get(include=["metadatas"])

print("📋 Recipe Titles in ChromaDB:")
for i, meta in enumerate(results["metadatas"]):
    title = meta.get("title", "❌ Missing title")
    print(f"{i+1}. {title}")
