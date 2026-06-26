import chromadb
from sentence_transformers import SentenceTransformer

# 1. Connect to your existing database
client = chromadb.PersistentClient(path="chroma_db")
collection = client.get_collection(name="hospital")

# 2. Load the embedder
embedder = SentenceTransformer("all-MiniLM-L6-v2")

# 3. Prepare your NEW or UPDATED document
new_text = "Updated 2026 Protocol: Ibuprofen is strictly prohibited for ulcer patients."
doc_id = "ulcer_protocol_chunk_1" # The predictable ID!
metadata = {"source": "ulcer_protocol_v2.pdf", "updated": "2026-05-14"}

# 4. Convert to math
embedding = embedder.encode([new_text]).tolist()

# 5. UPSERT it into the database
collection.upsert(
    ids=[doc_id],
    embeddings=embedding,
    documents=[new_text],
    metadatas=[metadata]
)

print(f"Successfully updated {doc_id}!")