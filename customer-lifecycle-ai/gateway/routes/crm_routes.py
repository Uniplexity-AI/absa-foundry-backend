"""
Gateway CRM Routes — Endpoints for CRM functionality.
"""
from __future__ import annotations
import os

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
import json
import requests
import chromadb
from llama_cpp import Llama
import numpy as np
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


_EMBEDDER = None
def get_embedder():
    global _EMBEDDER
    if _EMBEDDER is None:
        blob_path = "C:/Users/ADMIN/.ollama/models/blobs/sha256-2bada8a7450677000f678be90653b85d364de7db25eb5ea54136ada5f3933730"
        print(f"Loading native llama-cpp embedder from {blob_path}...")
        _EMBEDDER = Llama(
            model_path=blob_path,
            embedding=True,
            n_ctx=1024,
            n_threads=4,
            verbose=False
        )
        print("Embedder loaded.")
    return _EMBEDDER

router = APIRouter(prefix="/api/v1/crm", tags=["CRM"])

# Dummy schemas for requests/responses
class CaseCreate(BaseModel):
    customer_id: str
    case_type: str
    assigned_agent_id: Optional[str] = None

class InteractionCreate(BaseModel):
    interaction_channel: str
    notes: Optional[str] = None

class PromiseCreate(BaseModel):
    promise_type: str
    promise_date: datetime
    amount: Optional[float] = None

@router.get("/cases")
async def list_cases():
    """List all engagement cases."""
    # In a real implementation, you would query the DB using shared.database.session
    return {"cases": []}

@router.post("/cases")
async def create_case(case: CaseCreate):
    """Create a new engagement case."""
    return {"status": "success", "case": case.dict()}

@router.post("/cases/{case_id}/interactions")
async def add_interaction(case_id: int, interaction: InteractionCreate):
    """Add a new interaction to a case."""
    return {"status": "success", "case_id": case_id, "interaction": interaction.dict()}

@router.post("/cases/{case_id}/promises")
async def add_promise(case_id: int, promise: PromiseCreate):
    """Add a new promise (e.g. promise-to-pay) to a case."""
    return {"status": "success", "case_id": case_id, "promise": promise.dict()}

@router.get("/reports/promise-to-fund")
async def promise_to_fund_report():
    """Get a report on promises to fund."""
    return {"report": []}


_EMBEDDER = None
def get_embedder():
    global _EMBEDDER
    if _EMBEDDER is None:
        from llama_cpp import Llama
        blob_path = "C:/Users/ADMIN/.ollama/models/blobs/sha256-2bada8a7450677000f678be90653b85d364de7db25eb5ea54136ada5f3933730"
        print(f"Loading native llama-cpp embedder from {blob_path}...")
        _EMBEDDER = Llama(
            model_path=blob_path,
            embedding=True,
            n_ctx=1024,
            n_threads=4,
            verbose=False
        )
        print("Embedder loaded.")
    return _EMBEDDER

@router.post("/faqs/upload")
async def upload_faq(file: UploadFile = File(...)):
    """Upload an FAQ document, chunk it, embed it using native llama-cpp Qwen, and save it."""
    try:
        content_bytes = await file.read()
        text = content_bytes.decode('utf-8', errors='ignore')
        
        chunks = [c.strip() for c in text.split("Q:") if c.strip()]
        if not chunks:
            chunks = [text[i:i+500] for i in range(0, len(text), 500)]
            
        import psycopg2
        import os
        import numpy as np
        
        # Connect to DB (Save Blob)
        conn = psycopg2.connect("postgresql://postgres:wamulehi@localhost:5432/absa_dw")
        conn.autocommit = True
        cur = conn.cursor()
        
        cur.execute(
            "INSERT INTO faq_documents (filename, mime_type, file_data) VALUES (%s, %s, %s) RETURNING id",
            (file.filename, file.content_type, psycopg2.Binary(content_bytes))
        )
        doc_id = cur.fetchone()[0]
        
        # Initialize ChromaDB client
        chroma_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "database", "chroma_db"))
        import chromadb
        chroma_client = chromadb.PersistentClient(path=chroma_path)
        collection = chroma_client.get_or_create_collection(name="crm_faq_bot")

        embeddings_count = 0
        embedder = get_embedder()
        
        for i, chunk in enumerate(chunks):
            chunk_text = "Q: " + chunk if chunk.startswith("How") or "?" in chunk[:50] else chunk
            
            try:
                resp = embedder.create_embedding(chunk_text)
                emb_raw = resp["data"][0]["embedding"]
                
                if len(emb_raw) > 0 and isinstance(emb_raw[0], list):
                    embedding = np.mean(emb_raw, axis=0).tolist()
                else:
                    embedding = emb_raw
                
                if embedding:
                    collection.add(
                        embeddings=[embedding],
                        documents=[chunk_text],
                        ids=[f"{doc_id}_chunk_{i}"],
                        metadatas=[{"document_id": str(doc_id), "chunk_index": i}]
                    )
                    embeddings_count += 1
            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f"Embedding failed for chunk {i}: {e}")
                
        cur.close()
        conn.close()
        
        return {
            "status": "success", 
            "message": f"Parsed {len(chunks)} chunks, successfully embedded and stored {embeddings_count} FAQs.",
            "document_id": str(doc_id)
        }
    except Exception as e:
        
        import traceback
        with open("crm_crash.log", "w") as crash_log:
            crash_log.write(traceback.format_exc())
        
        import traceback
        with open("crm_crash_api.log", "w") as crash_log:
            crash_log.write(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))





@router.get("/faqs")
async def list_faqs():
    """Retrieve all embedded FAQs from ChromaDB."""
    try:
        import os
        import chromadb
        chroma_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "database", "chroma_db"))
        chroma_client = chromadb.PersistentClient(path=chroma_path)
        collection = chroma_client.get_or_create_collection(name="crm_faq_bot")
        
        results = collection.get()
        faqs = []
        if results and results.get("documents"):
            for i, doc in enumerate(results["documents"]):
                meta = results["metadatas"][i] if results.get("metadatas") else {}
                faqs.append({
                    "id": results["ids"][i],
                    "text": doc,
                    "document_id": meta.get("document_id")
                })
        return {"status": "success", "faqs": faqs}
    except Exception as e:
        import traceback
        traceback.print_exc()
        
        import traceback
        with open("crm_crash_api.log", "w") as crash_log:
            crash_log.write(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


class FaqUpdate(BaseModel):
    text: str

@router.post("/faqs")
async def add_manual_faq(payload: FaqUpdate):
    try:
        import uuid
        import numpy as np
        import chromadb
        
        chroma_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "database", "chroma_db"))
        chroma_client = chromadb.PersistentClient(path=chroma_path)
        collection = chroma_client.get_or_create_collection(name="crm_faq_bot")
        
        embedder = get_embedder()
        resp = embedder.create_embedding(payload.text)
        emb_raw = resp["data"][0]["embedding"]
        if len(emb_raw) > 0 and isinstance(emb_raw[0], list):
            embedding = np.mean(emb_raw, axis=0).tolist()
        else:
            embedding = emb_raw
            
        new_id = f"manual_{uuid.uuid4().hex[:8]}"
        collection.add(
            embeddings=[embedding],
            documents=[payload.text],
            ids=[new_id],
            metadatas=[{"document_id": "manual"}]
        )
        return {"status": "success", "faq": {"id": new_id, "text": payload.text, "document_id": "manual"}}
    except Exception as e:
        import traceback
        traceback.print_exc()
        
        import traceback
        with open("crm_crash_api.log", "w") as crash_log:
            crash_log.write(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/faqs/{faq_id}")
async def update_faq(faq_id: str, payload: FaqUpdate):
    try:
        import numpy as np
        import chromadb
        
        chroma_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "database", "chroma_db"))
        chroma_client = chromadb.PersistentClient(path=chroma_path)
        collection = chroma_client.get_or_create_collection(name="crm_faq_bot")
        
        embedder = get_embedder()
        resp = embedder.create_embedding(payload.text)
        emb_raw = resp["data"][0]["embedding"]
        if len(emb_raw) > 0 and isinstance(emb_raw[0], list):
            embedding = np.mean(emb_raw, axis=0).tolist()
        else:
            embedding = emb_raw
            
        collection.update(
            ids=[faq_id],
            embeddings=[embedding],
            documents=[payload.text]
        )
        return {"status": "success"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        
        import traceback
        with open("crm_crash_api.log", "w") as crash_log:
            crash_log.write(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/faqs/{faq_id}")
async def delete_faq(faq_id: str):
    try:
        import chromadb
        chroma_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "database", "chroma_db"))
        chroma_client = chromadb.PersistentClient(path=chroma_path)
        collection = chroma_client.get_or_create_collection(name="crm_faq_bot")
        
        collection.delete(ids=[faq_id])
        return {"status": "success"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        
        import traceback
        with open("crm_crash_api.log", "w") as crash_log:
            crash_log.write(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

