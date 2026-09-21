import os
import chromadb

CHROMA_DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "database", "chroma_db")

client = chromadb.PersistentClient(path=CHROMA_DATA_PATH)

def get_campaign_collection():
    return client.get_or_create_collection(name="campaign_catalog_v2")

def get_product_collection():
    return client.get_or_create_collection(name="product_catalog_v2")
