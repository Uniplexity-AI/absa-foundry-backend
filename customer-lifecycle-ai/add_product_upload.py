import os

path = r'services/decision-intelligence-service/app/api/catalog_routes.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

product_upload_route = '''
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
            from app.services.document_parser import extract_text_from_pdf
            text = extract_text_from_pdf(tmp_path)
        elif ext == ".docx":
            from app.services.document_parser import extract_text_from_docx
            text = extract_text_from_docx(tmp_path)
        else:
            with open(tmp_path, "r", encoding="utf-8") as f:
                text = f.read()
                
        # Extract structured entities via LLM
        from app.services.document_parser import extract_catalog_entities
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
'''

# Find the end of add_product
search_str = 'return {"status": "success", "id": doc_id, "item": item.model_dump()}'
idx = content.find(search_str, content.find('@router.post("/products")'))

if idx != -1:
    insert_pos = idx + len(search_str)
    new_content = content[:insert_pos] + '\n' + product_upload_route + content[insert_pos:]
    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("Added /products/upload endpoint")
else:
    print("Could not find insertion point")
