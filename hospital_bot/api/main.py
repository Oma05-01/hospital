import os
import json
import logging
import shutil
from pathlib import Path
from typing import AsyncIterator, Optional, List
from contextlib import asynccontextmanager

import httpx
import PyPDF2
from fastapi import FastAPI, HTTPException, File, UploadFile, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field

from inference import engine, GenerationConfig
from rag import rag

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

API_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = API_DIR.parent

# ── Config ──────────
CHECKPOINT_PATH = os.getenv("CHECKPOINT_PATH", str(PROJECT_ROOT / "checkpoints" / "medical_instruct_final_2.pt"))
TOKENIZER_PATH  = os.getenv("TOKENIZER_PATH",  str(PROJECT_ROOT / "tokenizer_latest.json"))

VALID_DOMAINS = {"hospital"}

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# ── Lifespan ────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Starting up — loading inference engine...")
    try:
        engine.load()
        logger.info("Inference engine ready.")
    except Exception as e:
        logger.error(f"Model load failed: {e}")
        raise

    logger.info("Loading RAG engine...")
    try:
        rag.load()
        logger.info("RAG engine ready.")
    except Exception as e:
        logger.error(f"RAG load failed: {e}")
        raise

    yield
    logger.info("Shutting down.")

# ── SINGLE APP INSTANCE ──
app = FastAPI(
    title="MedEdu Chatbot API",
    description="Hospital and Education chatbot powered by a custom Transformer LM + RAG.",
    version="0.1.0",
    lifespan=lifespan,
)

# ── SINGLE CORS MIDDLEWARE ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Request / Response schemas ────────────────────────────────────────────────
class ChatMessage(BaseModel):
    role: str      # Will be either "user" or "assistant"
    content: str   # The text of what was said

class ChatRequest(BaseModel):
    """Incoming chat message from the frontend."""
    message: str = Field(..., min_length=1, max_length=1000)
    domain:  str = Field("hospital")
    context: Optional[str] = Field(None)
    patient_username: str = ""
    patient_name: Optional[str] = "Patient"

    # Add the memory array! default_factory=list means it starts empty safely.
    history: List[ChatMessage] = Field(default_factory=list)

    temperature:    Optional[float] = Field(None, ge=0.1, le=2.0)
    max_new_tokens: Optional[int]   = Field(None, ge=10,  le=2048)
    top_k:          Optional[int]   = Field(None, ge=1,   le=200)
    top_p:          Optional[float] = Field(None, ge=0.1, le=1.0)


# ── Helper: build GenerationConfig from request ───────────────────────────────
def _make_cfg(req: ChatRequest) -> GenerationConfig:
    cfg = GenerationConfig()
    if req.temperature    is not None: cfg.temperature    = req.temperature
    if req.max_new_tokens is not None: cfg.max_new_tokens = req.max_new_tokens
    if req.top_k          is not None: cfg.top_k          = req.top_k
    if req.top_p          is not None: cfg.top_p          = req.top_p
    return cfg


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def root():
    return {"message": "MedEdu Chatbot API is running. See /docs for endpoints."}


@app.get("/health", tags=["System"])
async def health():
    """Liveness + readiness check."""
    return {
        "status": "ok" if engine.ready else "loading",
        "ready": engine.ready
    }


@app.get("/benchmark", tags=["System"])
async def benchmark(n_tokens: int = 50):
    """
    Run a quick speed benchmark.
    Returns tokens/sec and estimated latency.
    """
    if not engine.ready:
        raise HTTPException(status_code=503, detail="Model not ready yet.")
    return engine.benchmark(n_tokens=n_tokens)


async def rewrite_query(history: List[ChatMessage], latest_message: str) -> str:
    """Uses a fast LLM to rewrite contextual queries into standalone search terms."""
    if not history:
        return latest_message

    recent_history = history[-4:]
    history_text = "\n".join([f"{msg.role.capitalize()}: {msg.content}" for msg in recent_history])

    sys_prompt = (
        "You are  a medical search query rewriter. Your ONLY job is to rewrite the "
        "User's Latest Message into a standalone query using the Chat History. "
        "Replace pronouns (it, they, he, she) with the actual nouns they refer to. "
        "DO NOT answer the question. ONLY output the rewritten sentence."
    )

    prompt = f"Chat History:\n{history_text}\n\nLatest Message: {latest_message}\n\nRewritten Query:"

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        logger.error("GROQ_API_KEY is missing! Cannot rewrite query.")
        return latest_message

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "llama-3.1-8b-instant",
                    "messages": [
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.0,
                    # THE FIX: Removed response_format to prevent the 400 Bad Request error
                    "max_tokens": 60
                },
                timeout=4.0
            )
            resp.raise_for_status()

            rewritten = resp.json()["choices"][0]["message"]["content"].strip()

            if rewritten.startswith('"') and rewritten.endswith('"'):
                rewritten = rewritten[1:-1]

            return rewritten

    except Exception as e:
        logger.error(f"Query rewrite failed: {e}. Falling back to original.")
        return latest_message


async def classify_intent(history: list, message: str) -> str:
    """
    Uses the 8B micro-brain to determine if the user's message is
    conversational small-talk (CASUAL) or a retrieval request (MEDICAL).
    """
    formatted_history = ""
    for msg in history[-3:]:
        role = "User" if msg.role == "user" else "Assistant"
        content = msg.content or ""
        try:
            data = json.loads(content)
            content = data.get("summary", content)
        except:
            pass
        formatted_history += f"{role}: {content}\n"

    system_prompt = (
        "You are an intent classification routing agent for a hospital clinic AI.\n"
        "Analyze the user's latest message considering the short history, and classify it into exactly one of two categories:\n\n"
        "1. 'CASUAL': If the message is a greeting, thank you, acknowledgment (e.g., 'alright', 'ok', 'got it'), closing statement, or casual small talk.\n"
        "2. 'MEDICAL': If the message is asking for specific factual information, medical guidelines, hospital protocols, directories, or data retrieval.\n\n"
        # ✅ ADD THIS HERE where it actually routes things
        "CRITICAL: Any message asking about the patient's own records, assigned doctors, "
        "appointments, lab results, or personal medical data MUST be classified as 'MEDICAL', "
        "even if the phrasing sounds conversational or polite.\n\n"
        "CRITICAL: Output ONLY the single uppercase word 'CASUAL' or 'MEDICAL'. Do not include punctuation, spaces, or explanatory text."
    )

    user_prompt = f"History:\n{formatted_history}\nLatest User Message: '{message}'\nClassification:"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                json={
                    "model": "llama-3.1-8b-instant",  # The fast micro-brain
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.0,
                    "max_tokens": 10
                },
                timeout=10.0
            )
            resp.raise_for_status()
            data = resp.json()

            classification = data["choices"][0]["message"]["content"].strip().upper()

            if "CASUAL" in classification:
                return "CASUAL"
            return "MEDICAL"

    except Exception as e:
        logger.error(f"Intent classification failed: {e}", exc_info=True)
        return "MEDICAL"  # Fallback to RAG safely if the classifier errors out


@app.post("/chat", tags=["Chat"])
async def chat(req: ChatRequest, authorization: Optional[str] = Header(None)):
    if not engine.ready:
        raise HTTPException(status_code=503, detail="Model not ready.")
    if req.domain not in VALID_DOMAINS:
        raise HTTPException(status_code=400, detail=f"Invalid domain.")

    cfg = _make_cfg(req)
    context = req.context

    # ── PHASE 2: SEMANTIC INTENT ROUTING ───────────────────────────────────

    # 1. Ask the Micro-Brain to classify the query intent
    intent = await classify_intent(req.history, req.message)
    logger.info(f"User Intent Classified As: {intent}")

    # 2. CASUAL ROUTE: Bypass RAG database completely
    if intent == "CASUAL":
        logger.info("Routing to Casual Agent (8B). Skipping vector search.")

        async def casual_token_generator():
            try:
                # 🛠️ UPDATE 1: Convert to an f-string and inject req.patient_name
                casual_system = (
                    "You are a friendly, professional medical desk assistant.\n"
                    f"IMPORTANT CONTEXT: You are speaking with {req.patient_name}. Greet them naturally if appropriate.\n"
                    "CRITICAL CONVERSATION RULE: If the user simply says 'thank you', 'okay', 'bye', asks you to 'wait' or 'hold on', or expresses basic pleasantries, you MUST respond warmly and concisely. DO NOT ask follow-up questions, DO NOT offer to help with anything else, and DO NOT pivot the conversation to clinic protocols or medical topics.\n"                    "Respond naturally to the user's statement.\n"
                    "Keep it brief and helpful.\n"
                    "You MUST wrap your response in this exact JSON schema:\n"
                    '{"summary": "Your friendly conversational sentence here.", "items": []}'
                )

                def _clean_content(msg):
                    content = msg.content
                    if msg.role == "assistant":
                        try:
                            return json.loads(content).get("summary", content)
                        except (json.JSONDecodeError, AttributeError):
                            return content
                    return content

                formatted_history = [
                    {"role": msg.role, "content": _clean_content(msg)}
                    for msg in req.history[-4:]
                ]

                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                        json={
                            "model": "llama-3.1-8b-instant",
                            "messages": [{"role": "system", "content": casual_system}] + formatted_history + [
                                {"role": "user", "content": req.message}],
                            "response_format": {"type": "json_object"},
                            "temperature": 0.5
                        },
                        timeout=10.0
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    raw_response = data["choices"][0]["message"]["content"]

                    try:
                        parsed_json = json.loads(raw_response)
                        safe_single_line_json = json.dumps(parsed_json)
                    except json.JSONDecodeError:
                        safe_single_line_json = json.dumps({"summary": raw_response.replace('\n', ' '), "items": []})

                yield f"data: {safe_single_line_json}\n\n"
                yield "data: [DONE]\n\n"


            except Exception as e:

                logger.error(f"Casual streaming error: {e}", exc_info=True)  # add exc_info=True

                fallback = json.dumps({"summary": "Sorry, I didn't catch that. Could you say that again?", "items": []})
                yield f"data: {fallback}\n\n"
                yield "data: [DONE]\n\n"

        return StreamingResponse(
            casual_token_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # 3. MEDICAL ROUTE: Proceed with Intelligent Retrieval Rewrite
    if context is None and rag.ready:
        search_query = req.message

        # If there is conversational history, rewrite the medical search query
        if len(req.history) > 0:
            search_query = await rewrite_query(req.history, req.message)

        logger.info(f"Original Medical Query: '{req.message}'")
        logger.info(f"Rewritten Search Query:  '{search_query}'")

        context = rag.retrieve(search_query, domain=req.domain)

    # ──────────────────────────────────────────────────────────────────────

    # 4. Standard Heavy LLM Generator (Runs for strict RAG queries & Tool Execution)
    async def token_generator():
        try:
            for token in engine.generate_stream(
                    prompt=req.message,
                    history=req.history,
                    context=context,
                    domain=req.domain,
                    patient_username=req.patient_username,
                    patient_name=req.patient_name,  # 🛠️ UPDATE 2: Pass it to the heavy engine
                    auth_token=authorization,
                    cfg=cfg,
            ):
                yield f"data: {token}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.error(f"Streaming error: {e}", exc_info=True)
            yield "data: [ERROR]\n\n"

    return StreamingResponse(
        token_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class IngestRequest(BaseModel):
    text:   str
    domain: str
    source: str = "manual"
    topic:  str = ""


@app.post("/api/admin/upload", tags=["Admin"])
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")

    # 1. Save the uploaded file
    pdf_dir = "hospital_pdfs"
    os.makedirs(pdf_dir, exist_ok=True)
    file_path = os.path.join(pdf_dir, file.filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # 2. Extract text and use the EXISTING RAG connection
    try:
        reader = PyPDF2.PdfReader(file_path)
        full_text = ""
        for page in reader.pages:
            text = page.extract_text()
            if text:
                cleaned_text = text.replace('\n', ' ')
                cleaned_text = " ".join(cleaned_text.split())
                full_text += cleaned_text + " \n\n"

        chunks_saved = rag.ingest_text(
            text=full_text,
            domain="hospital",
            metadata={"source": file.filename}
        )

        logger.info(f"Successfully ingested {chunks_saved} chunks from {file.filename}")
        return {"message": "Success", "filename": file.filename, "chunks": chunks_saved}

    except Exception as e:
        logger.error(f"Failed to ingest PDF: {e}")
        raise HTTPException(status_code=500, detail="Failed to update AI Brain.")


@app.get("/api/admin/documents", tags=["Admin"])
async def list_documents():
    """Returns a list of all unique documents currently in the AI's memory."""
    col = rag._cols["hospital"]
    results = col.get(include=["metadatas"])

    unique_sources = set()
    for meta in results.get("metadatas", []):
        if meta and "source" in meta:
            unique_sources.add(meta["source"])

    return {"documents": list(unique_sources)}


@app.delete("/api/admin/documents/{filename}", tags=["Admin"])
async def delete_document(filename: str):
    """Deletes a document from the Vector DB and removes the physical file."""
    try:
        # 1. Erase from the AI's memory (ChromaDB)
        deleted_count = rag.delete_document(source=filename, domain="hospital")

        # 2. Delete the physical file so it doesn't accidentally get re-ingested
        file_path = os.path.join("hospital_pdfs", filename)
        if os.path.exists(file_path):
            os.remove(file_path)

        logger.info(f"Permanently deleted {filename}. Removed {deleted_count} chunks.")
        return {"message": "Success", "deleted_chunks": deleted_count}
    except Exception as e:
        logger.error(f"Failed to delete document: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete document")


@app.post("/ingest", tags=["RAG"])
async def ingest_document(req: IngestRequest):
    if not rag.ready:
        raise HTTPException(status_code=503, detail="RAG engine not ready.")
    if req.domain not in VALID_DOMAINS:
        raise HTTPException(status_code=400, detail=f"Invalid domain.")

    n = rag.ingest_text(
        text=req.text,
        domain=req.domain,
        metadata={"source": req.source, "topic": req.topic},
    )
    return {"chunks_ingested": n, "domain": req.domain, "source": req.source}


@app.get("/ingest/stats", tags=["RAG"])
async def ingest_stats():
    if not rag.ready:
        raise HTTPException(status_code=503, detail="RAG engine not ready.")
    return rag.stats()


# ── Dev entry point ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    # Dynamically pull the port from the environment, defaulting to 8001
    port = int(os.environ.get("FASTAPI_PORT", 8001))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info",
    )