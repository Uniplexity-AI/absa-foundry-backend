import json
import logging
import pdfplumber
import docx
import ollama

logger = logging.getLogger(__name__)

def extract_text_from_pdf(file_path: str) -> str:
    text = ""
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text

def extract_text_from_docx(file_path: str) -> str:
    doc = docx.Document(file_path)
    return "\n".join([paragraph.text for paragraph in doc.paragraphs])

async def extract_catalog_entities(text: str, entity_type: str = "campaign") -> list[dict]:
    """Uses LLM to extract structured entities from unstructured document text."""
    
    schema = """
    {
      "items": [
        {
          "title": "String - Name of the campaign or product",
          "description": "String - Detailed description and incentives",
          "target_segment": "String - e.g. MASS_MARKET, WEALTH, YOUTH, SME",
          "channel": "String - e.g. Email, SMS, Branch, Digital",
          "expires": "String - Expiry date in YYYY-MM-DD format, or empty string",
          "tags": ["Array", "of", "strings"]
        }
      ]
    }
    """
    
    prompt = f"""You are an expert data extractor. Carefully read the text below and extract EVERY distinct {entity_type} mentioned.
    If there are multiple {entity_type}s, you MUST extract all of them into separate objects.
    If NO {entity_type}s are found in the text, you MUST return an empty array: {{"items": []}}.
    
    Return ONLY a valid JSON object containing an "items" array, exactly matching this schema:
    {schema}
    
    TEXT TO ANALYZE:
    {text}
    """
    
    try:
        client = ollama.AsyncClient()
        response = await client.chat(
            model="absa-nba",
            messages=[{"role": "user", "content": prompt}],
            format="json",
            options={"num_predict": 2048}
        )
        content = response['message']['content']
        data = json.loads(content)
        
        # Handle the wrapping structure we requested
        if isinstance(data, dict) and "items" in data:
            return data["items"]
        elif isinstance(data, list):
            return data
        elif isinstance(data, dict):
            return [data]
            
        return []
    except Exception as e:
        logger.error(f"Failed to extract entities: {e}")
        return []
