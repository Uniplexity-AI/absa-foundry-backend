
import urllib.request
import json
data = json.dumps({"username": "admin", "password": "password"}).encode()
req = urllib.request.Request("http://localhost:8080/auth/login", data=data, headers={"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req) as response:
        login_res = json.loads(response.read().decode())
        print("Login OK")
        token = login_res["access_token"]
        
        req_roles = urllib.request.Request("http://localhost:8080/auth/admin/roles", headers={"Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(req_roles) as roles_response:
                print("Roles OK:", roles_response.read().decode())
        except urllib.error.HTTPError as e:
            print("Roles Error:", e.code, e.read().decode())
except urllib.error.HTTPError as e:
    print("Login Error:", e.code, e.read().decode())

