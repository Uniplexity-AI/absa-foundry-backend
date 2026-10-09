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



# ============================================================
# TICKETS / CASES
# ============================================================

class TicketCreate(BaseModel):
    subject: str
    customer: str
    type: str = "Complaint"
    priority: str = "Low"
    channel: str = "In-Branch"
    assignedTo: str = "Unassigned"
    description: str = ""

@router.post("/tickets")
async def create_ticket(ticket: TicketCreate):
    import psycopg2
    import random
    from datetime import datetime
    try:
        conn = psycopg2.connect("postgresql://postgres:wamulehi@localhost:5432/absa_dw")
        conn.autocommit = True
        cur = conn.cursor()

        idNum = random.randint(5000, 9999)
        ticket_id = f"CASE-{idNum}"
        status = "Open"
        sla = "On Track"
        created = datetime.utcnow().strftime("%Y-%m-%d")
        created_at = datetime.utcnow()

        cur.execute(
            """INSERT INTO crm_tickets 
               (id, subject, customer, type, priority, channel, assigned_to, description, status, sla, created, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (ticket_id, ticket.subject, ticket.customer, ticket.type, ticket.priority, ticket.channel, ticket.assignedTo, ticket.description, status, sla, created, created_at)
        )
        cur.close()
        conn.close()

        return {
            "message": "Ticket created successfully",
            "ticket": {
                "id": ticket_id,
                "subject": ticket.subject,
                "customer": ticket.customer,
                "type": ticket.type,
                "priority": ticket.priority,
                "channel": ticket.channel,
                "assignedTo": ticket.assignedTo,
                "description": ticket.description,
                "status": status,
                "sla": sla,
                "created": created
            }
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tickets")
async def get_tickets():
    import psycopg2
    try:
        conn = psycopg2.connect("postgresql://postgres:wamulehi@localhost:5432/absa_dw")
        cur = conn.cursor()
        cur.execute("SELECT id, subject, customer, type, priority, channel, assigned_to, description, status, sla, created FROM crm_tickets ORDER BY created_at DESC LIMIT 1000")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        tickets = []
        for row in rows:
            tickets.append({
                "id": row[0],
                "subject": row[1],
                "customer": row[2],
                "type": row[3],
                "priority": row[4],
                "channel": row[5],
                "assignedTo": row[6],
                "description": row[7],
                "status": row[8],
                "sla": row[9],
                "created": row[10]
            })
        return tickets
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/tickets/{ticket_id}")
async def delete_ticket(ticket_id: str):
    import psycopg2
    try:
        conn = psycopg2.connect("postgresql://postgres:wamulehi@localhost:5432/absa_dw")
        conn.autocommit = True
        cur = conn.cursor()
        
        cur.execute("DELETE FROM crm_tickets WHERE id = %s", (ticket_id,))
        deleted_count = cur.rowcount
        
        cur.close()
        conn.close()
        
        if deleted_count == 0:
            raise HTTPException(status_code=404, detail="Ticket not found")
            
        return {"status": "success", "message": "Ticket deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

class TicketUpdate(BaseModel):
    subject: Optional[str] = None
    customer: Optional[str] = None
    type: Optional[str] = None
    priority: Optional[str] = None
    channel: Optional[str] = None
    assignedTo: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    sla: Optional[str] = None

@router.put("/tickets/{ticket_id}")
async def update_ticket(ticket_id: str, ticket: TicketUpdate):
    import psycopg2
    try:
        conn = psycopg2.connect("postgresql://postgres:wamulehi@localhost:5432/absa_dw")
        conn.autocommit = True
        cur = conn.cursor()
        
        # Build dynamic update query
        updates = []
        values = []
        update_data = ticket.dict(exclude_unset=True)
        
        # Map frontend camelCase to db snake_case
        field_mapping = {
            "assignedTo": "assigned_to"
        }
        
        for k, v in update_data.items():
            db_field = field_mapping.get(k, k)
            updates.append(f"{db_field} = %s")
            values.append(v)
            
        if not updates:
            return {"status": "success", "message": "No fields to update"}
            
        values.append(ticket_id)
        query = f"UPDATE crm_tickets SET {', '.join(updates)} WHERE id = %s"
        
        cur.execute(query, values)
        updated_count = cur.rowcount
        
        cur.close()
        conn.close()
        
        if updated_count == 0:
            raise HTTPException(status_code=404, detail="Ticket not found")
            
        return {"status": "success", "message": "Ticket updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
@router.get("/metrics")
async def get_crm_metrics():
    import psycopg2
    try:
        conn = psycopg2.connect("postgresql://postgres:wamulehi@localhost:5432/absa_dw")
        cur = conn.cursor()
        
        # dynamic base numbers
        cur.execute("SELECT count(*) FROM crm_tickets")
        total_tickets = cur.fetchone()[0]
        
        cur.execute("SELECT count(*) FROM crm_tickets WHERE priority = 'High'")
        escalations = cur.fetchone()[0]
        
        cur.execute("SELECT count(*) FROM crm_tickets WHERE status = 'Closed' OR status = 'Resolved'")
        resolved = cur.fetchone()[0]
        
        cur.close()
        conn.close()
        
        # Strict reality-based KPIs: if we don't have the data for it, it shows 0.
        if total_tickets > 0:
            fcr_rate = (resolved / total_tickets) * 100.0
        else:
            fcr_rate = 0.0
            
        return {
            "serviceLevel": "0.0",
            "avgSpeedAnswer": "0",
            "abandonmentRate": "0.0",
            "fcr": f"{fcr_rate:.1f}",
            "totalInteractions": str(total_tickets),
            "escalations": str(escalations),
            "avgHandleTime": "0m 0s"
        }
    except Exception as e:
        return {
            "serviceLevel": "0.0",
            "avgSpeedAnswer": "0",
            "abandonmentRate": "0.0",
            "fcr": "0.0",
            "totalInteractions": "0",
            "escalations": "0",
            "avgHandleTime": "0m 0s"
        }
