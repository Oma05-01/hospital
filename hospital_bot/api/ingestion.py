import os
import re
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
import PyPDF2
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 1. Setup paths and models
PDF_FOLDER = "hospital_pdfs"
os.makedirs(PDF_FOLDER, exist_ok=True)

logger.info("Loading Embedder & Connecting to ChromaDB...")
embedder = SentenceTransformer("all-MiniLM-L6-v2")

# UPDATE 1: Mute ChromaDB Telemetry to stop log errors
client = chromadb.PersistentClient(
    path="chroma_db",
    settings=Settings(anonymized_telemetry=False)
)
collection = client.get_or_create_collection(name="hospital")

# UPDATE 2: Clean weird PDF line breaks and spaces
def clean_text(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()

# UPDATE 3: Overlapping chunks so context isn't cut in half
def get_overlapping_chunks(text: str, chunk_size: int = 150, overlap: int = 30):
    words = text.split()
    chunks = []
    # Step by (chunk_size - overlap) so the end of Chunk 1 is the start of Chunk 2
    for i in range(0, len(words), chunk_size - overlap):
        chunk = " ".join(words[i:i + chunk_size])
        chunks.append(chunk)
        if i + chunk_size >= len(words):
            break
    return chunks

def process_pdfs():
    files = [f for f in os.listdir(PDF_FOLDER) if f.endswith(".pdf")]

    if not files:
        logger.warning(f"No PDFs found in the '{PDF_FOLDER}' directory!")
        return

    for filename in files:
        filepath = os.path.join(PDF_FOLDER, filename)
        logger.info(f"Processing: {filename}")

        # Extract text from the PDF
        reader = PyPDF2.PdfReader(filepath)
        full_text = ""
        for page in reader.pages:
            text = page.extract_text()
            if text:
                full_text += text + " "

        # Clean the text before chunking
        full_text = clean_text(full_text)

        # Generate overlapping chunks
        chunks = get_overlapping_chunks(full_text, chunk_size=150, overlap=30)

        # Prepare for ChromaDB
        ids = []
        documents = []
        metadatas = []

        for index, chunk in enumerate(chunks):
            chunk_id = f"{filename}_chunk_{index}"
            ids.append(chunk_id)
            documents.append(chunk)
            metadatas.append({"source": filename, "chunk": index})

        # UPSERT: Convert to math and inject!
        logger.info(f"Generating math vectors for {len(chunks)} chunks...")
        embeddings = embedder.encode(documents).tolist()

        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )
        logger.info(f"Successfully synced {filename} to the AI Brain!\n")

if __name__ == "__main__":
    logger.info("Starting Ingestion Pipeline...")
    process_pdfs()
    logger.info("Pipeline Complete. Database is up to date!")