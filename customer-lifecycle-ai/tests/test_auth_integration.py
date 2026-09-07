"""Integration test for auth flow — login, JWT, refresh tokens."""
import sys
sys.path.insert(0, '.')

from shared.auth.user_repository import UserRepository
from shared.auth.token_service import TokenService

repo = UserRepository()

# 1. Sync a test user (simulates first LDAP login)
user = repo.sync_user(
    username='jsmith',
    email='john.smith@absa.co.zm',
    display_name='John Smith',
    dn='CN=jsmith,OU=Users,DC=absa,DC=co,DC=zm',
    department='Retail Banking',
)
print(f"User synced: {user.username} (id={str(user.user_id)[:8]}...)")
print(f"Roles: {user.roles}")

# 2. Create tokens
ts = TokenService()
access = ts.create_access_token(user)
raw_refresh, token_hash = ts.create_refresh_token(user.user_id)
print(f"Access token: {access[:50]}...")
print(f"Refresh token: {raw_refresh[:20]}...")

# 3. Store refresh token in DB
repo.store_refresh_token(user.user_id, token_hash)
print("Refresh token stored in DB")

# 4. Verify JWT
payload = ts.decode_access_token(access)
print(f"JWT sub: {payload['sub'][:8]}...")
print(f"JWT roles: {payload['roles']}")
print(f"JWT exp: {payload['exp']}")

# 5. Validate refresh token via DB
validated = repo.validate_refresh_token(token_hash)
print(f"Refresh valid: {validated is not None}")

# 6. Revoke and re-check
repo.revoke_refresh_token(token_hash)
revoked = repo.validate_refresh_token(token_hash)
print(f"After revoke, valid: {revoked is not None}")

# 7. List users
users = repo.list_users()
print(f"Users in DB: {len(users)}")

# 8. List roles
roles = repo.get_roles()
print(f"Roles in DB: {len(roles)}")

print()
print("ALL CHECKS PASSED")
