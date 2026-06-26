print("=== ENTERING RAG.PY ===")

import os
print("RAG 1: os loaded")

import re
print("RAG 2: re loaded")

import logging
print("RAG 3: logging loaded")

import hashlib
print("RAG 4: hashlib loaded")

from pathlib import Path
print("RAG 5: pathlib loaded")

from typing import Optional
print("RAG 6: typing loaded")

print("RAG 10: About to load sentence_transformers...")
from sentence_transformers import SentenceTransformer, CrossEncoder
print("RAG 11: sentence_transformers loaded")

print("RAG 7: About to load chromadb...")
import chromadb
print("RAG 8: chromadb loaded")

from chromadb.config import Settings
print("RAG 9: chromadb Settings loaded")

logger = logging.getLogger(__name__)


# ── Config ────────────────────────────────────────────────────────────────────
CHROMA_DIR      = os.getenv("CHROMA_DIR",       "chroma_db")
EMBED_MODEL     = os.getenv("EMBED_MODEL",       "all-MiniLM-L6-v2")
CHUNK_SIZE      = int(os.getenv("CHUNK_SIZE",    "300"))   # words per chunk
CHUNK_OVERLAP   = int(os.getenv("CHUNK_OVERLAP", "50"))    # word overlap between chunks
TOP_K_RETRIEVE  = int(os.getenv("TOP_K_RETRIEVE","3"))     # how many chunks to retrieve
MAX_CONTEXT_LEN = int(os.getenv("MAX_CONTEXT_LEN","400"))  # max words in injected context

VALID_DOMAINS = {"hospital", "education"}


# ── RAG Engine ────────────────────────────────────────────────────────────────
class RAGEngine:

    def __init__(self):
        self._embedder  = None
        self._client    = None
        self._cols      = {}   # {"hospital": Collection, "education": Collection}
        self.ready      = False

    # ── Initialisation ────────────────────────────────────────────────────────

    def load(self, chroma_dir: str = CHROMA_DIR, embed_model: str = EMBED_MODEL):
        """
        Load the embedding model and connect to ChromaDB.
        Call once at startup (alongside engine.load() in main.py lifespan).
        """
        logger.info(f"Loading embedding model: {embed_model} ...")
        self._embedder = SentenceTransformer(embed_model)

        logger.info("Loading Re-Ranker model (Cross-Encoder)...")
        self.reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

        logger.info(f"Connecting to ChromaDB at: {chroma_dir}")
        Path(chroma_dir).mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(
            path=chroma_dir,
            settings=Settings(anonymized_telemetry=False),
        )

        # Create or load both domain collections
        for domain in VALID_DOMAINS:
            self._cols[domain] = self._client.get_or_create_collection(
                name=domain,
                metadata={"hnsw:space": "cosine"},  # cosine similarity
            )
            count = self._cols[domain].count()
            logger.info(f"  Collection '{domain}': {count} chunks loaded")

        self.ready = True
        logger.info("RAG engine ready.")

    def _assert_ready(self):
        if not self.ready:
            raise RuntimeError("RAGEngine not loaded. Call rag.load() first.")

    def _assert_domain(self, domain: str):
        if domain not in VALID_DOMAINS:
            raise ValueError(f"Invalid domain '{domain}'. Use: {VALID_DOMAINS}")

    # ── Text chunking ─────────────────────────────────────────────────────────

    def _chunk_text(self, text: str) -> list[str]:
        """
        Split text into overlapping word-based chunks.
        Overlap ensures context isn't cut off at chunk boundaries.

        Example with CHUNK_SIZE=300, CHUNK_OVERLAP=50:
            chunk 0: words 0–299
            chunk 1: words 250–549   (50 word overlap)
            chunk 2: words 500–799
            ...
        """
        # Clean whitespace
        text = re.sub(r"\s+", " ", text.strip())
        words = text.split()

        if not words:
            return []

        chunks = []
        step   = CHUNK_SIZE - CHUNK_OVERLAP
        start  = 0

        while start < len(words):
            end   = min(start + CHUNK_SIZE, len(words))
            chunk = " ".join(words[start:end])
            chunks.append(chunk)
            if end == len(words):
                break
            start += step

        return chunks

    def _doc_id(self, text: str, source: str, chunk_index: int) -> str:
        raw = f"{source}::{chunk_index}::{text[:100]}"
        return hashlib.md5(raw.encode()).hexdigest()

    # ── Ingestion ─────────────────────────────────────────────────────────────

    def ingest_text(
        self,
        text: str,
        domain: str,
        metadata: Optional[dict] = None,
    ) -> int:
        self._assert_ready()
        self._assert_domain(domain)

        if metadata is None:
            metadata = {}

        source = metadata.get("source", "unknown")
        chunks = self._chunk_text(text)

        if not chunks:
            logger.warning("ingest_text called with empty text — skipped.")
            return 0

        logger.info(f"Ingesting {len(chunks)} chunks into '{domain}' from '{source}'")

        # Embed all chunks at once — much faster than one by one
        embeddings = self._embedder.encode(chunks, show_progress_bar=False).tolist()

        ids       = [self._doc_id(c, source, i) for i, c in enumerate(chunks)]
        metadatas = [{**metadata, "chunk_index": i} for i in range(len(chunks))]

        # Upsert — safe to re-ingest the same document without duplicates
        self._cols[domain].upsert(
            ids=ids,
            documents=chunks,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        logger.info(f"Ingested {len(chunks)} chunks successfully.")
        return len(chunks)

    def ingest_file(self, filepath: str, domain: str, metadata: Optional[dict] = None) -> int:

        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {filepath}")

        if path.suffix.lower() != ".txt":
            raise ValueError(f"Only .txt files supported for now. Got: {path.suffix}")

        text = path.read_text(encoding="utf-8")
        meta = {"source": path.name, **(metadata or {})}
        return self.ingest_text(text, domain, meta)

    def ingest_batch(self, documents: list[dict]) -> dict:

        counts = {"hospital": 0, "education": 0}
        for doc in documents:
            n = self.ingest_text(
                text=doc["text"],
                domain=doc["domain"],
                metadata=doc.get("metadata"),
            )
            counts[doc["domain"]] = counts.get(doc["domain"], 0) + n
        return counts

    # ── Retrieval ─────────────────────────────────────────────────────────────

    def retrieve(
            self,
            query: str,
            domain: str,
            top_k: int = 3,
            min_relevance: float = -5.0,  # <-- CHANGED TO -5.0
    ) -> Optional[str]:

        self._assert_ready()
        self._assert_domain(domain)

        col = self._cols[domain]

        if col.count() == 0:
            logger.warning(f"Collection '{domain}' is empty — no context retrieved.")
            return None

        # ── PHASE 1: BROAD SEARCH (Get top 15 from Chroma) ────────
        query_embedding = self._embedder.encode([query], show_progress_bar=False).tolist()

        results = col.query(
            query_embeddings=query_embedding,
            n_results=min(15, col.count()),  # We pull a wide net of 15 chunks
            include=["documents", "distances", "metadatas"],
        )

        docs = results["documents"][0]
        metadatas = results["metadatas"][0]

        if not docs:
            logger.info(f"No chunks found for query: '{query[:60]}'")
            return None

        # ── PHASE 2: RE-RANKING (The Logical Judge) ───────────────
        # Pair the exact question with every chunk we found
        cross_inp = [[query, doc] for doc in docs]

        # The Judge scores them (0.0 to 10.0+ usually, though it depends on the model)
        scores = self.reranker.predict(cross_inp)

        # Zip everything together and sort by the Judge's score (Highest to Lowest)
        scored_results = sorted(zip(docs, scores, metadatas), key=lambda x: x[1], reverse=True)

        # ── PHASE 3: FILTER & FORMAT ──────────────────────────────
        context_parts = []
        word_count = 0
        MAX_CONTEXT_LEN = 800  # Assuming you have this defined somewhere!

        for doc, score, meta in scored_results:
            logger.info(f"Cross-Encoder Score: {score:.2f} | Chunk: '{doc[:40]}...'")
            # Stop if we have gathered our top_k chunks
            if len(context_parts) >= top_k:
                break

            # If the logic score is too low, skip it! (You can tweak this threshold later)
            if score < min_relevance:
                continue

            source = meta.get("source", "unknown")
            # We use the new logic score instead of the old cosine distance
            snippet = f"[Source: {source} | Logic Score: {score:.2f}]\n{doc}"
            words = len(doc.split())

            if word_count + words > MAX_CONTEXT_LEN:
                # Truncate this chunk to fit within the limit
                remaining = MAX_CONTEXT_LEN - word_count
                if remaining > 30:
                    truncated = " ".join(doc.split()[:remaining])
                    context_parts.append(f"[Source: {source}]\n{truncated}")
                break

            context_parts.append(snippet)
            word_count += words

        if not context_parts:
            logger.info(f"RAG Re-Ranker: No chunks passed the logic threshold for query: '{query[:60]}'")
            return None

        context = "\n\n".join(context_parts)
        logger.info(
            f"Retrieved and Re-Ranked {len(context_parts)} chunks ({word_count} words) "
            f"for query: '{query[:60]}'"
        )
        return context

    # ── Collection management ─────────────────────────────────────────────────

    def stats(self) -> dict:
        """
        Returns chunk counts per domain collection.
        Useful for the /ingest status endpoint.
        """
        self._assert_ready()
        return {
            domain: self._cols[domain].count()
            for domain in VALID_DOMAINS
        }

    def delete_document(self, source: str, domain: str) -> int:

        self._assert_ready()
        self._assert_domain(domain)

        col = self._cols[domain]

        # Find all chunks with this source
        results = col.get(where={"source": source}, include=["metadatas"])
        ids_to_delete = results["ids"]

        if not ids_to_delete:
            logger.info(f"No chunks found for source '{source}' in '{domain}'")
            return 0

        col.delete(ids=ids_to_delete)
        logger.info(f"Deleted {len(ids_to_delete)} chunks from '{source}' in '{domain}'")
        return len(ids_to_delete)

    def clear_domain(self, domain: str) -> None:
        """
        Wipe all documents from a domain collection.
        Use with caution — this is irreversible.
        """
        self._assert_ready()
        self._assert_domain(domain)

        self._client.delete_collection(domain)
        self._cols[domain] = self._client.get_or_create_collection(
            name=domain,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(f"Collection '{domain}' cleared.")


# ── Module-level singleton ────────────────────────────────────────────────────
rag = RAGEngine()


# ── Self-test ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("Loading RAG engine...")
    rag.load()

    # ── Test hospital ingestion ───────────────────────────────────────────────
    print("\n── Ingesting hospital documents ─────────────────")

    hospital_docs = [
        {
            "text": (
                "Ibuprofen is a non-steroidal anti-inflammatory drug (NSAID) used to reduce "
                "fever, pain, and inflammation. The standard adult dose is 200 to 400 milligrams "
                "taken every four to six hours as needed. The maximum daily dose without medical "
                "supervision is 1200 milligrams. Ibuprofen should be taken with food or milk to "
                "reduce stomach irritation. It is not recommended for patients with kidney disease, "
                "stomach ulcers, or those taking blood thinners. Common side effects include "
                "nausea, stomach pain, and dizziness."
            ),
            "domain": "hospital",
            "metadata": {"source": "WHO Drug Guide", "topic": "ibuprofen", "category": "medication"},
        },
        {
            "text": (
                "Paracetamol, also known as acetaminophen, is a common analgesic and antipyretic. "
                "The recommended adult dose is 500 to 1000 milligrams every four to six hours. "
                "The maximum daily dose is 4000 milligrams, or 3000 milligrams for elderly patients "
                "and those with liver conditions. Paracetamol overdose is a leading cause of acute "
                "liver failure. Patients should not take paracetamol alongside other products "
                "containing it. It is generally safe during pregnancy when used as directed."
            ),
            "domain": "hospital",
            "metadata": {"source": "WHO Drug Guide", "topic": "paracetamol", "category": "medication"},
        },
        {
            "text": (
                "Hospital triage classifies patients by urgency of care. Level 1 (Resuscitation) "
                "requires immediate life-saving intervention. Level 2 (Emergent) must be seen within "
                "15 minutes — examples include chest pain, difficulty breathing, altered consciousness. "
                "Level 3 (Urgent) should be seen within 30 minutes — examples include high fever, "
                "severe pain, vomiting. Level 4 (Less Urgent) can wait up to one hour. Level 5 "
                "(Non-Urgent) includes minor issues such as rashes or prescription refills."
            ),
            "domain": "hospital",
            "metadata": {"source": "Hospital Protocol Manual", "topic": "triage", "category": "procedure"},
        },
        {
            "text": (
                "A migraine is a neurological condition that can cause multiple symptoms. "
                "It is frequently characterized by intense, debilitating, throbbing pain on one "
                "side of the head. Common symptoms include severe nausea, vomiting, difficulty "
                "speaking, numbness or tingling, and extreme sensitivity to light and sound. "
                "Migraines often run in families and affect all ages. The most common triggers "
                "include stress, hormonal changes, and certain foods."
            ),
            "domain": "hospital",
            "metadata": {"source": "Neurology Textbook", "topic": "migraine", "category": "condition"},
        },
    ]

    result = rag.ingest_batch(hospital_docs)
    print(f"Ingested: {result}")

    # ── Test education ingestion ──────────────────────────────────────────────
    print("\n── Ingesting education documents ────────────────")

    education_docs = [
        {
            "text": (
                "The Pythagorean theorem states that in a right-angled triangle, the square of the "
                "length of the hypotenuse equals the sum of the squares of the other two sides. "
                "Written as a formula: a squared plus b squared equals c squared, where c is the "
                "hypotenuse. For example, if a triangle has sides of length 3 and 4, the hypotenuse "
                "is the square root of 9 plus 16, which is the square root of 25, which equals 5. "
                "This is called a Pythagorean triple. The theorem is fundamental to geometry and is "
                "used in engineering, architecture, and navigation."
            ),
            "domain": "education",
            "metadata": {"source": "Mathematics Textbook Grade 9", "topic": "Pythagorean theorem", "subject": "maths"},
        },
        {
            "text": (
                "Photosynthesis is the process by which green plants, algae, and some bacteria convert "
                "light energy into chemical energy stored as glucose. The overall equation is: "
                "six molecules of carbon dioxide plus six molecules of water, in the presence of light "
                "energy, produces one molecule of glucose and six molecules of oxygen. "
                "Photosynthesis occurs in the chloroplasts of plant cells. The green pigment chlorophyll "
                "absorbs light, primarily in the red and blue parts of the spectrum. The process has two "
                "main stages: the light-dependent reactions and the Calvin cycle."
            ),
            "domain": "education",
            "metadata": {"source": "Biology Textbook Grade 10", "topic": "photosynthesis", "subject": "biology"},
        },
    ]

    result = rag.ingest_batch(education_docs)
    print(f"Ingested: {result}")

    # ── Test retrieval ────────────────────────────────────────────────────────
    print("\n── Retrieval tests ──────────────────────────────")

    queries = [
        ("What is the correct dose of ibuprofen for an adult?",   "hospital"),
        ("How urgent is chest pain at the hospital?",             "hospital"),
        ("Explain the Pythagorean theorem with an example.",      "education"),
        ("How do plants make food from sunlight?",                "education"),
        ("What is the maximum paracetamol dose per day?",         "hospital"),
    ]

    for query, domain in queries:
        print(f"\nQuery  : {query}")
        print(f"Domain : {domain}")
        context = rag.retrieve(query, domain)
        if context:
            # Show first 300 chars of retrieved context
            preview = context[:300].replace("\n", " ")
            print(f"Context: {preview}...")
        else:
            print("Context: (nothing retrieved)")

    # ── Stats ─────────────────────────────────────────────────────────────────
    print("\n── Collection stats ─────────────────────────────")
    print(rag.stats())

    print("\nRAG self-test complete.")