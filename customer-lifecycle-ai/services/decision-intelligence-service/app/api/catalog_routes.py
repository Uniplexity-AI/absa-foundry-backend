import os
import tempfile
import uuid
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from typing import List, Optional

from app.services.vector_store import get_campaign_collection, get_product_collection
from app.services.document_parser import extract_text_from_pdf, extract_text_from_docx, extract_catalog_entities

router = APIRouter()

class CatalogItem(BaseModel):
    title: str
    description: str
    target_segment: str = "MASS_MARKET"
    channel: str = "Any"
    expires: Optional[str] = "2026-12-31"
    tags: List[str] = []

@router.post("/campaigns")
async def add_campaign(item: CatalogItem):
    collection = get_campaign_collection()
    doc_id = str(uuid.uuid4())
    
    # Store stringified metadata alongside the document
    text_content = f"{item.title}: {item.description}"
    
    collection.add(
        documents=[text_content],
        metadatas=[{
            "title": item.title,
            "target_segment": item.target_segment,
            "channel": item.channel,
            "expires": item.expires,
            "type": "campaign"
        }],
        ids=[doc_id]
    )
    return {"status": "success", "id": doc_id, "item": item.model_dump()}

@router.post("/campaigns/upload")
async def upload_campaign_document(file: UploadFile = File(...)):
    # Save file temporarily
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".pdf", ".docx", ".txt", ".csv"]:
        raise HTTPException(status_code=400, detail="Unsupported file format")
        
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
        
    try:
        if ext == ".pdf":
            text = extract_text_from_pdf(tmp_path)
        elif ext == ".docx":
            text = extract_text_from_docx(tmp_path)
        else:
            with open(tmp_path, "r", encoding="utf-8") as f:
                text = f.read()
                
        # Extract structured entities via LLM
        entities = await extract_catalog_entities(text, "campaign")
        
        # Save to Chroma
        collection = get_campaign_collection()
        saved_items = []
        for entity in entities:
            doc_id = str(uuid.uuid4())
            title = entity.get("title", "Unknown Campaign")
            desc = entity.get("description", "")
            seg = entity.get("target_segment", "MASS_MARKET")
            channel = entity.get("channel", "Digital")
            expires = entity.get("expires", "2026-12-31")
            
            collection.add(
                documents=[f"{title}: {desc}"],
                metadatas=[{
                    "title": title,
                    "target_segment": seg,
                    "channel": channel,
                    "expires": expires,
                    "type": "campaign"
                }],
                ids=[doc_id]
            )
            saved_items.append(entity)
            
        return {"status": "success", "extracted_count": len(saved_items), "items": saved_items}
        
    finally:
        os.unlink(tmp_path)

@router.delete("/campaigns/{campaign_id}")
def delete_campaign(campaign_id: str):
    collection = get_campaign_collection()
    collection.delete(ids=[campaign_id])
    return {"status": "success"}

@router.put("/campaigns/{campaign_id}")
def update_campaign(campaign_id: str, item: CatalogItem):
    collection = get_campaign_collection()
    text_content = f"{item.title}: {item.description}"
    collection.update(
        ids=[campaign_id],
        documents=[text_content],
        metadatas=[{
            "title": item.title,
            "target_segment": item.target_segment,
            "channel": item.channel,
            "expires": item.expires,
            "type": "campaign"
        }]
    )
    return {"status": "success"}

@router.get("/campaigns")
def list_campaigns():
    collection = get_campaign_collection()
    results = collection.get()
    
    items = []
    if results and results["ids"]:
        for i in range(len(results["ids"])):
            meta = results["metadatas"][i] if results["metadatas"] else {}
            doc = results["documents"][i] if results["documents"] else ""
            title = meta.get("title", "Untitled")
            
            desc = doc
            if desc.startswith(f"{title}: "):
                desc = desc[len(title) + 2:]
                
            items.append({
                "id": results["ids"][i],
                "title": title,
                "description": desc,
                "target_segment": meta.get("target_segment", ""),
                "channel": meta.get("channel", ""),
                "expires": meta.get("expires", "2026-12-31")
            })
    return items

@router.post("/products")
async def add_product(item: CatalogItem):
    collection = get_product_collection()
    doc_id = str(uuid.uuid4())
    text_content = f"{item.title}: {item.description}"
    
    collection.add(
        documents=[text_content],
        metadatas=[{
            "title": item.title,
            "target_segment": item.target_segment,
            "type": "product"
        }],
        ids=[doc_id]
    )
    return {"status": "success", "id": doc_id, "item": item.model_dump()}

@router.post("/products/upload")
async def upload_product_document(file: UploadFile = File(...)):
    # Save file temporarily
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".pdf", ".docx", ".txt", ".csv"]:
        raise HTTPException(status_code=400, detail="Unsupported file format")
        
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
        
    try:
        if ext == ".pdf":
            text = extract_text_from_pdf(tmp_path)
        elif ext == ".docx":
            text = extract_text_from_docx(tmp_path)
        else:
            with open(tmp_path, "r", encoding="utf-8") as f:
                text = f.read()
                
        # Extract structured entities via LLM
        entities = await extract_catalog_entities(text, "product")
        
        # Save to Chroma
        collection = get_product_collection()
        saved_items = []
        for entity in entities:
            doc_id = str(uuid.uuid4())
            title = entity.get("title", "Unknown Product")
            desc = entity.get("description", "")
            seg = entity.get("target_segment", "MASS_MARKET")
            
            collection.add(
                documents=[f"{title}: {desc}"],
                metadatas=[{
                    "title": title,
                    "target_segment": seg,
                    "type": "product"
                }],
                ids=[doc_id]
            )
            saved_items.append(entity)
            
        return {"status": "success", "extracted_count": len(saved_items), "items": saved_items}
        
    finally:
        os.unlink(tmp_path)


@router.get("/products")
def list_products():
    collection = get_product_collection()
    results = collection.get()
    
    items = []
    if results and results["ids"]:
        for i in range(len(results["ids"])):
            meta = results["metadatas"][i] if results["metadatas"] else {}
            doc = results["documents"][i] if results["documents"] else ""
            title = meta.get("title", "Untitled")
            desc = doc
            if desc.startswith(f"{title}: "):
                desc = desc[len(title) + 2:]
            items.append({
                "id": results["ids"][i],
                "title": title,
                "description": desc,
                "target_segment": meta.get("target_segment", "")
            })
    return items

@router.delete("/products/{product_id}")
def delete_product(product_id: str):
    collection = get_product_collection()
    collection.delete(ids=[product_id])
    return {"status": "success"}

@router.put("/products/{product_id}")
def update_product(product_id: str, item: CatalogItem):
    collection = get_product_collection()
    text_content = f"{item.title}: {item.description}"
    collection.update(
        ids=[product_id],
        documents=[text_content],
        metadatas=[{
            "title": item.title,
            "target_segment": item.target_segment,
            "type": "product"
        }]
    )
    return {"status": "success"}
