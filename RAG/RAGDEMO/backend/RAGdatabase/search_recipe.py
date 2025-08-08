import chromadb
import arabic_reshaper
from bidi.algorithm import get_display
from fuzzywuzzy import fuzz
from chromadb.utils import embedding_functions
import re

# === Config ===
model_name = "akhooli/Arabic-SBERT-100K"
collection_name = "recipestest"

# === Diacritics removal ===
def remove_diacritics(text):
    arabic_diacritics = re.compile(r'[\u064B-\u0652]')
    return arabic_diacritics.sub('', text)

# === Load embedding function ===
sentence_transformer_ef = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name=model_name
)

# === Connect to ChromaDB ===
chroma_client = chromadb.HttpClient(host='localhost', port=8000)
collection = chroma_client.get_collection(
    name=collection_name,
    embedding_function=sentence_transformer_ef
)

# === Search function ===
def search_recipe(query_text: str, top_k: int = 5):
    query_text = query_text.strip()
    if "وصفة" not in query_text:
        query_text = "وصفة " + query_text

    # ✅ Normalize user query (remove diacritics before embedding)
    stripped_query = remove_diacritics(query_text)

    results = collection.query(
        query_texts=[stripped_query],
        n_results=5,
        include=["metadatas", "documents", "distances"]
    )

    scored = []
    for doc, meta, distance in zip(results["documents"], results["metadatas"], results["distances"]):
        title = meta[0].get("title", "")         # original diacritized title
        full_text = meta[0].get("full_text", "") # original diacritized body

        fuzzy_title = fuzz.partial_ratio(query_text, title)
        fuzzy_body = fuzz.partial_ratio(query_text, full_text)
        max_fuzzy = max(fuzzy_title, fuzzy_body)

        scored.append({
            "title": title,
            "full_text": full_text,
            "total_fuzzy_score": max_fuzzy,
            "semantic_distance": distance[0]
        })

    # Sort: fuzzy DESC, distance ASC
    sorted_results = sorted(scored, key=lambda x: (-x["total_fuzzy_score"], x["semantic_distance"]))

    print("🔎 Suggested Recipes:")
    for i, r in enumerate(sorted_results[:top_k], 4):
        reshaped_title = get_display(arabic_reshaper.reshape(r["title"]))
        print(f"{i}. {reshaped_title} (🎯 fuzzy={r['total_fuzzy_score']}, 🧠 distance={r['semantic_distance']:.4f})")

# === Example usage ===
search_recipe("يلنجى")
