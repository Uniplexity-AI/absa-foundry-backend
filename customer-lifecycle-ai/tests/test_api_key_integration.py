"""Phase 2 integration test — API key flow."""
import sys
sys.path.insert(0, '.')

import hashlib
from shared.auth.user_repository import UserRepository
from shared.auth.api_key_service import ApiKeyService

repo = UserRepository()

# 1. Create and validate an API key
raw_key, prefix, key_hash = ApiKeyService.generate_key('test_service')
repo.store_api_key('test_service', key_hash, prefix, 'test_key', ['read:test'])

validated = repo.validate_api_key(key_hash)
print(f"Create & validate: {validated is not None}")
print(f"  Service: {validated['service_name']}")
print(f"  Scopes: {validated['scopes']}")

# 2. Invalid key should fail
bad_hash = hashlib.sha256(b'invalid_key').hexdigest()
print(f"Invalid key rejected: {repo.validate_api_key(bad_hash) is None}")

# 3. Revoke and confirm
repo.revoke_api_key(str(validated["key_id"]))
print(f"After revoke invalid: {repo.validate_api_key(key_hash) is None}")

# 4. List all keys
keys = repo.list_api_keys()
print(f"\nTotal API keys: {len(keys)}")
for k in keys:
    scopes = list(k["scopes"]) if k["scopes"] else []
    print(f"  {k['key_prefix']}... [{k['service_name']}] active={k['is_active']} scopes={scopes}")

print("\nPHASE 2 COMPLETE")
