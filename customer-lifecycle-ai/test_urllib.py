import urllib.request
import json
import urllib.error

url = 'http://127.0.0.1:8005/catalog/campaigns'
data = json.dumps({'title': 'Test', 'description': 'Desc'}).encode('utf-8')
req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
try:
    with urllib.request.urlopen(req) as f:
        print('Status:', f.status)
        print('Response:', f.read().decode('utf-8'))
except urllib.error.HTTPError as e:
    print('HTTPError:', e.code)
    print('Body:', e.read().decode('utf-8'))
except Exception as e:
    print('Error:', e)
