import os

path = r'services/decision-intelligence-service/app/api/catalog_routes.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('            from app.services.document_parser import extract_text_from_pdf\n', '')
content = content.replace('            from app.services.document_parser import extract_text_from_docx\n', '')
content = content.replace('        # Extract structured entities via LLM\n        from app.services.document_parser import extract_catalog_entities\n', '        # Extract structured entities via LLM\n')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Removed duplicate imports")
