# Authentication Flow — Customer Lifecycle Prediction System

**Document Status:** Complete — Phases 1–3 Implemented
**Target Environment:** Python 3.12+ | FastAPI | PostgreSQL 16 | Redis 7
**Last Updated:** 2026-07-21

---

## 1. Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                       Client (Browser / API)                      │
└──────────────┬──────────────────────────┬────────────────────────┘
               │ JWT (Authorization header)│ X-API-Key header
               ▼                          ▼
┌──────────────────────────────────────────────────────────────────┐
│                    API Gateway (:8080)                            │
│                                                                   │
│  Middleware chain (order matters):                                │
│  1. CORS                                                          │
│  2. Rate Limiter  ← Redis sliding window                         │
│  3. JWT Auth      ← decode + blacklist check                     │
│  4. RBAC           ← role vs route matrix                        │
│  5. API Key Auth   ← hash + DB lookup (service routes only)      │
│                                                                   │
│  Routes:                                                          │
│  /auth/*       — login, logout, refresh, me                      │
│  /admin/*      — users, roles, API keys (ADMIN only)             │
│  /internal/*   — service-to-service (API key auth)               │
└──────┬──────────────┬──────────────┬─────────────────────────────┘
       │              │              │
       ▼              ▼              ▼
┌──────────┐  ┌──────────┐  ┌──────────────┐
│PostgreSQL│  │  Redis   │  │  LDAP / AD    │
│          │  │          │  │  (optional)   │
│iam.users │  │blacklist │  │              │
│iam.roles │  │rate limit│  │  Bank AD     │
│iam.keys  │  │lockout   │  │  credentials │
│iam.audit │  │refresh   │  │              │
└──────────┘  └──────────┘  └──────────────┘
```

---

## 2. Configuration

All settings in `.env` or environment variables. Defaults in `shared/config/settings.py`.

```bash
# ---- JWT ----
JWT_SECRET_KEY=change-me-in-production-use-a-strong-random-key
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# ---- LDAP (optional — dev mode when disabled) ----
LDAP_ENABLED=false
LDAP_SERVER=ldap://ad.absa.co.zm:389
LDAP_BASE_DN=DC=absa,DC=co,DC=zm
LDAP_USER_DN_TEMPLATE=CN={username},OU=Users,DC=absa,DC=co,DC=zm
LDAP_BIND_DN=
LDAP_BIND_PASSWORD=
LDAP_TLS_ENABLED=false

# ---- Redis ----
REDIS_HOST=localhost
REDIS_PORT=6379

# ---- Security Hardening ----
LOCKOUT_MAX_ATTEMPTS=5
LOCKOUT_DURATION_MINUTES=15
PASSWORD_MIN_LENGTH=8
PASSWORD_REQUIRE_UPPERCASE=true
PASSWORD_REQUIRE_DIGIT=true

# ---- PostgreSQL ----
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=etl_validation
POSTGRES_USER=postgres
POSTGRES_PASSWORD=wamulehi
```

### Modes of Operation

| Mode | LDAP_ENABLED | Behavior |
|---|---|---|
| **Development** | `false` | Accept any username/password. Password policy enforced locally. |
| **Production** | `true` | Authenticate against bank AD. TLS required (`LDAP_TLS_ENABLED=true`). |

---

## 3. Login Flow

```
POST /auth/login
Content-Type: application/json

{
  "username": "jsmith",
  "password": "MyP@ssw0rd1"
}
```

### Step-by-step

```
Client              Gateway                           Redis          PostgreSQL       LDAP/AD
  │                    │                                │               │               │
  │  POST /auth/login  │                                │               │               │
  │───────────────────►│                                │               │               │
  │                    │                                │               │               │
  │                    │ 1. RATE LIMIT CHECK             │               │               │
  │                    │    key=ratelimit:POST:/auth/   │               │               │
  │                    │    login:{ip}                   │               │               │
  │                    │───────────────────────────────►│               │               │
  │                    │    zcard < 5? ✅                │               │               │
  │                    │◄───────────────────────────────│               │               │
  │                    │                                │               │               │
  │                    │ 2. LOCKOUT CHECK                │               │               │
  │                    │    GET lockout:{username}       │               │               │
  │                    │───────────────────────────────►│               │               │
  │                    │    attempts < 5? ✅              │               │               │
  │                    │◄───────────────────────────────│               │               │
  │                    │                                │               │               │
  │                    │ 3. PASSWORD POLICY              │               │               │
  │                    │    len >= 8, has upper, has digit ✅            │               │
  │                    │                                │               │               │
  │                    │ 4. LDAP BIND (if enabled)       │               │               │
  │                    │───────────────────────────────────────────────────────────────►│
  │                    │    ldap3: bind(dn, password)    │               │               │
  │                    │◄───────────────────────────────────────────────────────────────│
  │                    │    ✅ success                    │               │               │
  │                    │                                │               │               │
  │                    │  IF FAILURE:                    │               │               │
  │                    │    INCR lockout:{username}      │               │               │
  │                    │───────────────────────────────►│               │               │
  │                    │    SLEEP 2^(attempts-1) sec      │               │               │
  │                    │    RETURN 401                    │               │               │
  │                    │                                │               │               │
  │                    │ 5. USER SYNC (upsert)           │               │               │
  │                    │    INSERT INTO iam.users ...    │               │               │
  │                    │    ON CONFLICT (username)       │               │               │
  │                    │───────────────────────────────►│               │               │
  │                    │    RETURNING user_id, roles      │               │               │
  │                    │◄────────────────────────────────│               │               │
  │                    │                                │               │               │
  │                    │ 6. CLEAR LOCKOUT                │               │               │
  │                    │    DEL lockout:{username}       │               │               │
  │                    │───────────────────────────────►│               │               │
  │                    │                                │               │               │
  │                    │ 7. ISSUE TOKENS                 │               │               │
  │                    │    JWT (sub, roles, exp=15min)  │               │               │
  │                    │    Refresh (256-bit random)     │               │               │
  │                    │                                │               │               │
  │                    │    Store refresh:               │               │               │
  │                    │    SETEX refresh:{hash} 7d      │               │               │
  │                    │───────────────────────────────►│               │               │
  │                    │    INSERT iam.refresh_tokens    │               │               │
  │                    │───────────────────────────────►│               │               │
  │                    │                                │               │               │
  │                    │ 8. AUDIT                        │               │               │
  │                    │    INSERT iam.auth_audit        │               │               │
  │                    │    (LOGIN_SUCCESS)              │               │               │
  │                    │───────────────────────────────►│               │               │
  │                    │                                │               │               │
  │  200 OK            │                                │               │               │
  │  {                 │                                │               │               │
  │    "access_token": "eyJhbG...",                     │               │               │
  │    "refresh_token":"A6-pjCD...",                    │               │               │
  │    "token_type":   "bearer",                        │               │               │
  │    "expires_in":   900                               │               │               │
  │  }                 │                                │               │               │
  │◄───────────────────│                                │               │               │
```

### JWT Payload Structure

```json
{
  "sub": "a1417f36-1234-5678-9abc-def012345678",
  "username": "jsmith",
  "display_name": "John Smith",
  "email": "john.smith@absa.co.zm",
  "roles": ["RELATIONSHIP_MANAGER"],
  "branch_code": "B015",
  "iat": 1753152000,
  "exp": 1753152900,
  "jti": "bb8b19b7-1234-5678-9abc-def012345678",
  "type": "access"
}
```

| Field | Purpose |
|---|---|
| `sub` | User UUID — primary identity for all DB lookups |
| `roles` | Array of role names for RBAC checks |
| `branch_code` | Data scoping — branch managers see only their branch |
| `jti` | JWT ID — added to Redis blacklist on logout |
| `type` | Must be `"access"` — prevents refresh token reuse as access token |

---

## 4. Token Refresh Flow

```
POST /auth/refresh
Content-Type: application/json

{
  "refresh_token": "L1m0-7sAogow79wuEPbm..."
}
```

### Step-by-step

```
Client              Gateway                           Redis          PostgreSQL
  │                    │                                │               │
  │  POST /auth/refresh│                                │               │
  │───────────────────►│                                │               │
  │                    │ 1. Hash refresh token          │               │
  │                    │    SHA-256(raw_token)          │               │
  │                    │                                │               │
  │                    │ 2. Validate in DB              │               │
  │                    │    SELECT user_id FROM         │               │
  │                    │    iam.refresh_tokens          │               │
  │                    │    WHERE hash=X                │               │
  │                    │    AND revoked_at IS NULL      │               │
  │                    │    AND expires_at > NOW()      │               │
  │                    │───────────────────────────────►│               │
  │                    │    ✅ found                     │               │
  │                    │◄────────────────────────────────│               │
  │                    │                                │               │
  │                    │ 3. REVOKE old token             │               │
  │                    │    UPDATE revoked_at=NOW()     │               │
  │                    │───────────────────────────────►│               │
  │                    │    DEL refresh:{old_hash}      │               │
  │                    │───────────────────────────────►│               │
  │                    │                                │               │
  │                    │ 4. ISSUE new pair               │               │
  │                    │    New JWT (15 min)            │               │
  │                    │    New refresh (7 days)        │               │
  │                    │                                │               │
  │  200 OK            │                                │               │
  │  {access, refresh} │                                │               │
  │◄───────────────────│                                │               │
```

### Token Rotation

Every refresh call issues a **new refresh token** and **revokes the old one**. If a stolen refresh token is used after the legitimate user has already refreshed, it will be rejected (already revoked). This limits the window for refresh token replay attacks.

---

## 5. Logout Flow

```
POST /auth/logout
Authorization: Bearer eyJhbG...
```

### Step-by-step

```
Client              Gateway                           Redis          PostgreSQL
  │                    │                                │               │
  │  POST /auth/logout │                                │               │
  │───────────────────►│                                │               │
  │                    │ 1. Decode JWT, extract jti     │               │
  │                    │                                │               │
  │                    │ 2. BLACKLIST JWT                │               │
  │                    │    SETEX jwt_blacklist:{jti}   │               │
  │                    │    TTL=remaining_token_lifetime │               │
  │                    │───────────────────────────────►│               │
  │                    │                                │               │
  │                    │ 3. REVOKE ALL REFRESH TOKENS    │               │
  │                    │    UPDATE iam.refresh_tokens   │               │
  │                    │    SET revoked_at=NOW()        │               │
  │                    │    WHERE user_id=X              │               │
  │                    │───────────────────────────────►│               │
  │                    │                                │               │
  │                    │ 4. SCAN + DELETE Redis refresh  │               │
  │                    │    For each refresh:{hash}      │               │
  │                    │    where value = user_id → DEL  │               │
  │                    │───────────────────────────────►│               │
  │                    │                                │               │
  │                    │ 5. AUDIT (LOGOUT)              │               │
  │                    │───────────────────────────────►│               │
  │                    │                                │               │
  │  204 No Content    │                                │               │
  │◄───────────────────│                                │               │
```

---

## 6. Rate Limiting

**Mechanism:** Redis sorted-set sliding window.

### Default Rules

| Route | Limit | Window |
|---|---|---|
| `POST /auth/login` | 5 requests | 15 minutes |
| `POST /auth/refresh` | 30 requests | 1 minute |
| `* /admin/*` | 60 requests | 1 minute |

### Algorithm

```
For each request:
  1. ZREMRANGEBYSCORE key 0 (now - window)     # Remove expired entries
  2. ZCARD key                                   # Count current window
  3. IF count >= max: REJECT (HTTP 429)          # Rate limit exceeded
  4. ZADD key {now} {now}                        # Add current request
  5. EXPIRE key window                           # Auto-cleanup
```

### Response (429 Too Many Requests)

```json
{
  "detail": {
    "error": "Rate limit exceeded",
    "retry_after_seconds": 900
  }
}
```

### Fallback

If Redis is unavailable, rate limiting falls back to an in-memory list (not shared across processes, but prevents single-process abuse).

---

## 7. Account Lockout

**Mechanism:** Redis counter with TTL.

```
Configuration:
  LOCKOUT_MAX_ATTEMPTS=5
  LOCKOUT_DURATION_MINUTES=15
```

### Flow

```
On failed login:
  INCR lockout:{username}
  IF attempts == 1: EXPIRE lockout:{username} 900

On successful login:
  DEL lockout:{username}

On login attempt:
  GET lockout:{username}
  IF value >= 5: REJECT (HTTP 423 Locked)
```

### Exponential Backoff

Before returning 401, the gateway sleeps to slow automated attacks:

| Failed Attempt | Delay |
|---|---|
| 1 | 1 second |
| 2 | 2 seconds |
| 3 | 4 seconds |
| 4+ | 8 seconds (max) |

### Response (423 Locked)

```json
{
  "detail": "Account temporarily locked. Retry in 12 minutes."
}
```

---

## 8. Password Policy

Enforced when `LDAP_ENABLED=false` (development mode). In production, the AD domain controller enforces its own policy.

### Rules

| Rule | Config |
|---|---|
| Minimum length | `PASSWORD_MIN_LENGTH=8` |
| Uppercase letter | `PASSWORD_REQUIRE_UPPERCASE=true` |
| At least one digit | `PASSWORD_REQUIRE_DIGIT=true` |

### Response (400 Bad Request)

```json
{
  "detail": {
    "error": "Password policy violation",
    "rules": [
      "Minimum 8 characters",
      "At least one uppercase letter",
      "At least one digit"
    ]
  }
}
```

---

## 9. Role-Based Access Control (RBAC)

### Roles

| Role | Access |
|---|---|
| `ADMIN` | Full system — users, roles, API keys, models, config |
| `RELATIONSHIP_MANAGER` | Dashboard, NBA recommendations for assigned customers |
| `BRANCH_MANAGER` | Portfolio analytics across branch |
| `DATA_SCIENTIST` | Model training, evaluation, champion/challenger |
| `OPERATIONS` | Monitoring, pipeline status (read-only) |
| `SERVICE_ACCOUNT` | Machine-to-machine — internal APIs only |

### Permission Matrix (excerpt — 30 rules total)

| Method | Route | Roles |
|---|---|---|
| `GET` | `/admin/users` | `ADMIN` |
| `POST` | `/admin/users` | `ADMIN` |
| `GET` | `/admin/api-keys` | `ADMIN` |
| `GET` | `/dashboard/customers` | `ADMIN`, `RELATIONSHIP_MANAGER`, `BRANCH_MANAGER` |
| `POST` | `/models/train` | `ADMIN`, `DATA_SCIENTIST` |
| `GET` | `/monitoring/health` | `ADMIN`, `OPERATIONS` |
| `POST` | `/internal/predict` | `SERVICE_ACCOUNT` |

Full matrix: `shared/auth/permissions.py`

### Path Matching

Supports exact match, path parameters (`{id}`), and wildcards (`/admin/*`).

### Response (403 Forbidden)

```json
{
  "detail": {
    "error": "Insufficient permissions",
    "required_roles": ["ADMIN"],
    "user_roles": ["RELATIONSHIP_MANAGER"]
  }
}
```

---

## 10. API Key Authentication (Service-to-Service)

### Key Format

```
clp_sk_etl_engine_01_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2
│     │  │         │  └────────── 64-char hex secret ──────────────────────────┘
│     │  │         └── key version
│     │  └──────────── service short name
│     └─────────────── system prefix
└───────────────────── shared prefix for log scanning
```

### Request

```
POST /internal/predict
X-API-Key: clp_sk_etl_engine_01_a1b2...
```

### Validation

```
1. Extract X-API-Key header
2. SHA-256 hash the full key
3. SELECT from iam.api_keys WHERE hash = X
   JOIN iam.service_accounts
   WHERE key.is_active AND service.is_active
   AND (expires_at IS NULL OR expires_at > NOW())
4. UPDATE last_used_at = NOW()
5. Inject ServiceContext into request.state
```

### Seeded Service Accounts

| Service | Scopes |
|---|---|
| `etl_engine` | `read:source_db`, `write:target_db`, `trigger:etl` |
| `prediction_service` | `read:features`, `write:predictions`, `read:models` |
| `feature_engineering` | `read:source_db`, `write:feature_store`, `read:models` |
| `dashboard_service` | `read:customers`, `read:predictions`, `read:health_scores` |

---

## 11. Audit Trail

Every authentication event is logged to `iam.auth_audit` in PostgreSQL.

### Event Types

| Event | Trigger |
|---|---|
| `LOGIN_SUCCESS` | Successful authentication |
| `LOGIN_FAILED` | Invalid credentials |
| `LOGOUT` | User-initiated logout |
| `TOKEN_REFRESH` | Access token refreshed |
| `ACCOUNT_LOCKED` | Account locked after N failed attempts |
| `RATE_LIMITED` | Request blocked by rate limiter |

### Audit Record Structure

```sql
SELECT event_type, ip_address, user_agent, details, created_at
FROM iam.auth_audit
WHERE user_id = '...'
ORDER BY created_at DESC;
```

---

## 12. Database Schema

All tables in the `iam` schema within the `etl_validation` database.

| Table | Rows (typical) | Purpose |
|---|---|---|
| `iam.users` | 10–500 | User accounts synced from LDAP |
| `iam.roles` | 6 | Static role definitions |
| `iam.user_roles` | N:M | User ↔ Role assignments |
| `iam.service_accounts` | 4–20 | Machine identities |
| `iam.api_keys` | 1:N per service | Hashed API keys + scopes |
| `iam.refresh_tokens` | Transient | Active refresh tokens (7-day TTL) |
| `iam.auth_audit` | Growing | Immutable audit trail |

---

## 13. Error Codes

| HTTP | Meaning | When |
|---|---|---|
| `200` | Success | Login, refresh, `/auth/me` |
| `204` | No Content | Logout |
| `400` | Bad Request | Password policy violation, malformed JSON |
| `401` | Unauthorized | Invalid credentials, expired JWT, missing `Authorization` header |
| `403` | Forbidden | Insufficient RBAC role, blacklisted JWT, deactivated account |
| `404` | Not Found | API key not found, user not found |
| `423` | Locked | Account locked after too many failed attempts |
| `429` | Too Many Requests | Rate limit exceeded |
| `500` | Internal Server Error | DB failure, unexpected exception |
| `503` | Service Unavailable | LDAP/AD server unreachable |

---

## 14. Quick Start — Verify Auth is Working

```bash
# 1. Seed IAM (admin user + service accounts)
python scripts/seed_iam.py

# 2. Start the gateway
python -m uvicorn gateway.main:app --host 0.0.0.0 --port 8080

# 3. Login (dev mode — any credentials)
curl -X POST http://localhost:8080/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"Admin123!"}'

# 4. Use the token
curl http://localhost:8080/admin/users \
  -H "Authorization: Bearer eyJhbG..."

# 5. Test API key
curl http://localhost:8080/internal/predict \
  -H "X-API-Key: clp_sk_etl_engine_01_..."
```

---

## 15. File Reference

| File | Purpose |
|---|---|
| `shared/auth/models.py` | 12 Pydantic v2 request/response schemas |
| `shared/auth/token_service.py` | JWT + refresh token lifecycle |
| `shared/auth/authenticator.py` | LDAP/AD bind + attribute extraction |
| `shared/auth/permissions.py` | 30-rule RBAC matrix + path matching |
| `shared/auth/api_key_service.py` | API key generation + hashing |
| `shared/auth/user_repository.py` | PostgreSQL-backed user/role/key CRUD |
| `shared/auth/audit.py` | Audit event writer → `iam.auth_audit` |
| `gateway/middleware/auth.py` | JWT validation → `request.state.user` |
| `gateway/middleware/rbac.py` | Role enforcement → 403 on mismatch |
| `gateway/middleware/api_key.py` | API key validation → `request.state.service` |
| `gateway/middleware/rate_limit.py` | Redis sliding window rate limiter |
| `gateway/routes/auth_routes.py` | `/auth/login`, `/refresh`, `/logout`, `/me` |
| `gateway/routes/admin_routes.py` | `/admin/users`, `/admin/roles` |
| `gateway/routes/api_key_routes.py` | `/admin/api-keys` CRUD |
| `gateway/dependencies.py` | FastAPI `Depends()` — `get_current_user`, `get_current_service`, `require_role` |
| `gateway/main.py` | FastAPI app factory |
| `database/iam/001_initial_schema.sql` | Full IAM DDL — 7 tables, 6 seed roles |
| `scripts/seed_iam.py` | Admin user + 4 service account API keys |
| `shared/config/settings.py` | All auth configuration (JWT, LDAP, Redis, lockout) |
