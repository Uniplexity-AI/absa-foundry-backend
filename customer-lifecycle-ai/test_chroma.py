import sys
sys.path.insert(0, '.')
import os
import chromadb
client = chromadb.PersistentClient(path='database/chroma_test')
collection = client.get_or_create_collection('test_coll')
collection.add(documents=['hello'], ids=['1'])
print('Success!')
