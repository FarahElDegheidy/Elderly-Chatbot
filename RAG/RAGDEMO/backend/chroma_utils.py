import chromadb
from chromadb.utils import embedding_functions

chroma_client = chromadb.HttpClient(host='localhost', port=8000)

model_name = "akhooli/Arabic-SBERT-100K"
sentence_transformer_ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=model_name)

def retrieve_data(query, include_scores=False):
    try:
        collection = chroma_client.get_collection("recipestest", embedding_function=sentence_transformer_ef)
    except chromadb.errors.InvalidCollectionException:
        return []

    include_fields = ["documents", "metadatas"]
    if include_scores:
        include_fields.append("distances")

    results = collection.query(
        query_texts=[query],
        n_results=7,
        include=include_fields
    )

    structured_results = []
    for i, (doc, metadata) in enumerate(zip(results["documents"][0], results["metadatas"][0])):
        entry = {
            "title": metadata.get("title", "وصفة بدون عنوان"),
            "document": doc,
        }
        if include_scores:
            entry["distance"] = results["distances"][0][i]
        structured_results.append(entry)

    return structured_results

def is_recipe_in_kb(query_result: str, threshold: float = 0.35) -> bool:
    """
    Returns True if query_result matches a known recipe in the KB based on embedding similarity.
    Lower distance = more similar. Typical SBERT cosine distance thresholds: 0.2–0.3
    """
    results = retrieve_data(query_result, include_scores=True)

    if not results:
        return False

    top_result = results[0]
    top_distance = top_result.get("distance", 1)  # fallback to 1.0 = far

    print(f"🔎 Top title: {top_result['title']}, distance: {top_distance:.3f}")

    return top_distance <= threshold
