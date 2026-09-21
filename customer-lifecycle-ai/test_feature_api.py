import requests, json
r = requests.post('http://localhost:8080/auth/login', json={'username':'admin','password':'Pilot@2025'})
token = r.json()['access_token']
headers = {'Authorization': f'Bearer {token}'}

# Test /features/{customer_id}/latest
r2 = requests.get('http://localhost:8080/features/000000222/latest', headers=headers)
print('STATUS:', r2.status_code)
print('BODY:', json.dumps(r2.json(), indent=2, default=str)[:2000])
