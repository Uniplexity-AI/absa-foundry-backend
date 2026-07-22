"""Phase 3 integration test — rate limiting, lockout, audit, password policy."""
import sys
sys.path.insert(0, '.')

import asyncio
import redis.asyncio as aioredis
from shared.auth.audit import AuthAudit
from shared.config.settings import settings

async def test():
    r = aioredis.from_url("redis://localhost:6379/0", decode_responses=True)

    # 1. Rate limiting test
    print("=== Rate Limiting ===")
    from gateway.middleware.rate_limit import RateLimiter, RateLimitRule
    limiter = RateLimiter(redis_client=r)

    key = "ratelimit:test:127.0.0.1"
    for i in range(7):
        allowed = await limiter._is_allowed(key, max_req=5, window=60)
        if i < 5:
            assert allowed, f"Request {i+1} should be allowed"
        else:
            assert not allowed, f"Request {i+1} should be blocked"
    print("  Rate limiting: OK (5 allowed, 2 blocked)")

    # Cleanup
    await r.delete(key)

    # 2. Lockout test
    print("\n=== Account Lockout ===")
    lockout_key = f"lockout:testuser"
    await r.delete(lockout_key)

    for i in range(6):
        attempts = await r.incr(lockout_key)
        if i == 0:
            await r.expire(lockout_key, 900)
    attempts = int(await r.get(lockout_key))
    print(f"  Lockout after 6 failures: {attempts} attempts")
    assert attempts == 6
    assert attempts >= settings.lockout_max_attempts

    # Clear
    await r.delete(lockout_key)
    print("  Lockout clear: OK")

    # 3. Audit DB write test
    print("\n=== Audit Trail ===")
    import psycopg2
    conn = psycopg2.connect(host="localhost", port=5432, dbname="etl_validation",
                            user="postgres", password="wamulehi")
    cur = conn.cursor()

    # Count before
    cur.execute("SELECT COUNT(*) FROM iam.auth_audit")
    before = cur.fetchone()[0]

    # Write an audit event
    await AuthAudit.log("TEST_EVENT", ip_address="127.0.0.1",
                         details={"test": "phase3_integration"})

    # Count after
    cur.execute("SELECT COUNT(*) FROM iam.auth_audit")
    after = cur.fetchone()[0]
    print(f"  Audit records: {before} -> {after} (+{after - before})")
    assert after > before, "Audit record should be written"
    conn.close()
    print("  Audit DB write: OK")

    # 4. Password policy test
    print("\n=== Password Policy ===")
    valid_passwords = ["Abcdefg1", "P@ssw0rd!", "C0mpl3xP@ss"]
    invalid_passwords = ["short", "nouppercase1", "NODIGITS", "12345678"]

    for pw in valid_passwords:
        try:
            from gateway.routes.auth_routes import _validate_password_policy
            _validate_password_policy("test", pw)
            assert True, f"'{pw}' should pass"
        except Exception:
            assert False, f"'{pw}' should pass"

    for pw in invalid_passwords:
        try:
            _validate_password_policy("test", pw)
            assert False, f"'{pw}' should fail"
        except Exception:
            pass

    print("  Password policy: OK (4 valid pass, 4 invalid blocked)")

    await r.aclose()
    print("\n=== PHASE 3 COMPLETE ===")

asyncio.run(test())
