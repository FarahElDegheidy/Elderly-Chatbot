import os
import re
import uuid
import chromadb
from chromadb.utils import embedding_functions

# === Configuration ===
model_name = "akhooli/Arabic-SBERT-100K"
recipe_dir = "recipes_from_pagebreaks"
collection_name = "recipestest"

# === Function to remove Arabic diacritics ===
def remove_diacritics(text):
    arabic_diacritics = re.compile(r'[\u064B-\u0652]')
    return arabic_diacritics.sub('', text)

# === Load embedding function ===
sentence_transformer_ef = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name=model_name
)

# === Connect to ChromaDB ===
chroma_client = chromadb.HttpClient(host='localhost', port=8000)

# === Create or get collection ===
collection = chroma_client.get_or_create_collection(
    name=collection_name,
    embedding_function=sentence_transformer_ef
)
print(f"Collection '{collection_name}' is ready.")

# === Prepare data ===
documents, metadatas, ids = [], [], []

for filename in os.listdir(recipe_dir):
    if not filename.endswith(".txt"):
        continue

    path = os.path.join(recipe_dir, filename)
    with open(path, "r", encoding="utf-8") as file:
        content = file.read().strip()

    if not content:
        continue

    lines = content.splitlines()
    title = lines[0].strip()      # ✅ Keep original title with diacritics
    body = content.strip()        # ✅ Keep original diacritized content

    # ✅ Remove diacritics before embedding
    body_no_diacritics = remove_diacritics(body)

    documents.append(body_no_diacritics)

    # ✅ Store diacritized title & body in metadata
    metadatas.append({
        "title": title,
        "full_text": body
    })

    ids.append(str(uuid.uuid4()))

# === Add to ChromaDB ===
collection.add(
    documents=documents,
    metadatas=metadatas,
    ids=ids
)

print(f"{len(documents)} recipes added to collection '{collection_name}'.")
