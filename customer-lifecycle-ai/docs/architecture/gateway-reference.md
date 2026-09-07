# API Gateway — Architecture & Reference

> **Service:** `customer-lifecycle-ai/gateway/`  
> **Port:** 8080  
> **Framework:** FastAPI  
> **Auth:** JWT (LDAP) + RBAC (4 roles) + API Keys  
> **Database:** PostgreSQL 16 (async via SQLAlchemy 2.0 + asyncpg)  
> **Cache:** Redis (optional, with in-memory fallback)

---

## 1. Request Lifecycle (Middleware Chain)

```
┌─────────────────────────────────────────────────────────┐
│ 1. Request Logging Middleware                           │
│    Logs: method, path, status, duration, caller, IP     │
├─────────────────────────────────────────────────────────┤
│ 2. CORS Middleware                                      │
│    allow_origins=["*"], credentials, methods, headers   │
├─────────────────────────────────────────────────────────┤
│ 3. RBAC Middleware                                      │
│    Checks request.state.user.roles against permissions  │
│    Skips: /auth/*, /health, /docs, /openapi, /redoc     │
│    Returns 403 with required_roles + user_roles         │
├─────────────────────────────────────────────────────────┤
│ 4. Route Handler                                        │
│    Thin routes → Service → Repository → Database        │
└─────────────────────────────────────────────────────────┘
```

**Note:** JWT validation, rate limiting, and API key validation are NOT global middleware — they're invoked as FastAPI `Depends()` dependencies in individual route handlers. This gives routes fine-grained control over which auth mechanisms apply.

---

## 2. Directory Structure

```
gateway/
├── main.py                  # App factory + entry point
├── dependencies.py          # FastAPI Depends() callables (auth, RBAC, API key)
├── Dockerfile               # Production Docker image
├── requirements.txt         # Python dependencies
├── __init__.py              # Package marker
│
├── middleware/
│   ├── auth.py              # JWT validation → UserContext
│   ├── rbac.py              # Role-based access → 403 on mismatch
│   ├── api_key.py           # X-API-Key header → ServiceContext
│   ├── logging.py           # Request/response structured logging
│   ├── rate_limit.py        # Redis sliding-window rate limiter
│   └── cors.py              # STUB (CORS handled inline in main.py)
│
├── routes/
│   ├── auth_routes.py       # /auth/login, /auth/refresh, /auth/logout, /auth/me
│   ├── admin_routes.py      # /admin/users, /admin/roles
│   ├── api_key_routes.py    # /admin/api-keys CRUD
│   ├── etl_routes.py        # /api/etl/runs (FR-OPS-01/02/03)
│   ├── health.py            # STUB
│   └── proxy.py             # STUB
│
├── services/
│   └── etl_service.py       # ETL dashboard business logic
│
├── schemas/
│   └── etl_schemas.py       # Pydantic v2 response models for ETL API
│
├── app/                     # STUB (intended for app factory)
├── config/                  # STUB (settings come from shared/)
└── tests/                   # Empty
```

---

## 3. Route Reference

### 3.1 Authentication (`/auth`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/auth/login` | Public | LDAP login, returns JWT + refresh token |
| `POST` | `/auth/refresh` | Public | Token rotation, revokes old pair |
| `POST` | `/auth/logout` | Public | Blacklists JWT, revokes all refresh tokens |
| `GET` | `/auth/me` | JWT | Returns current user profile |

**Login flow:** Rate limit → Lockout check → Password policy → LDAP bind (or dev-mode) → Sync user to IAM → Issue JWT → Audit log

**Security features:**
- Account lockout: 5 failed attempts → 15-minute lock
- Password policy: 8+ chars, uppercase, digit
- Exponential backoff: 1s → 2s → 4s → 8s max
- Token blacklist: Redis-backed (memory fallback)
- Refresh token rotation: old revoked on each refresh

### 3.2 Admin (`/admin`)

| Method | Path | Roles | Description |
|--------|------|-------|-------------|
| `GET` | `/admin/users` | ADMIN | List all users with roles |
| `POST` | `/admin/users` | ADMIN | Create user (defined, not implemented) |
| `GET` | `/admin/users/{id}` | ADMIN | Get single user (defined, not implemented) |
| `PUT` | `/admin/users/{id}` | ADMIN | Update user (defined, not implemented) |
| `DELETE` | `/admin/users/{id}` | ADMIN | Delete user (defined, not implemented) |
| `GET` | `/admin/roles` | ADMIN | List all roles |
| `POST` | `/admin/roles` | ADMIN | Create role (defined, not implemented) |
| `GET` | `/admin/api-keys` | ADMIN | List API keys (without secrets) |
| `POST` | `/admin/api-keys` | ADMIN | Create API key (returns secret once) |
| `DELETE` | `/admin/api-keys/{id}` | ADMIN | Revoke API key |

### 3.3 ETL Operations (`/api/etl`)

| Method | Path | Roles | Description |
|--------|------|-------|-------------|
| `GET` | `/api/etl/runs?page=&limit=&status=` | ADMIN, OPERATIONS | Paginated run history + dashboard KPIs |

**Response shape:**
```json
{
  "kpis": {
    "todays_runs": 6, "successful_runs": 6, "failed_runs": 0,
    "running_runs": 0, "avg_quality": 100.0,
    "avg_duration": "09m 27s", "success_rate": 100.0
  },
  "status": {
    "current_status": "Operational",
    "last_successful_run": "audit-uuid",
    "latest_quality": 100.0,
    "sla_threshold": 95.0,
    "last_failure_run": null
  },
  "quality_trend": [
    { "label": "14:30", "value": 100.0, "rows": "15K", "rejected": "0", "failed": false }
  ],
  "runs": [
    {
      "runId": "audit-uuid", "batchId": "batch-uuid",
      "duration": "00m 09s", "rowsReceived": "15K", "rowsValid": "15K",
      "rowsLoaded": "15K", "rowsRejected": 0,
      "qualityScore": 100.0, "qualityClass": "good",
      "status": "COMPLETED", "statusClass": "completed"
    }
  ],
  "total_runs": 6, "page": 1, "limit": 25
}
```

### 3.4 Health

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | Public | `{"status": "healthy", "service": "api-gateway"}` |

---

## 4. Middleware Reference

### 4.1 `gateway/middleware/auth.py` — JWTAuthMiddleware

**Singleton:** `auth_middleware`

**Flow:**
1. Extract `Authorization: Bearer <token>` header
2. If route is in `PUBLIC_ROUTES` → return `None` (skip)
3. Decode JWT via `TokenService`
4. Check Redis blacklist (with memory fallback)
5. Build `UserContext(user_id, username, display_name, email, roles, branch_code)`
6. Inject into `request.state.user`

**Public routes:** `POST /auth/login`, `GET /health`, `GET /docs`, `GET /openapi.json`, `GET /redoc`

### 4.2 `gateway/middleware/rbac.py` — RBACMiddleware

**Singleton:** `rbac_middleware`

**Flow:**
1. Skip if route is in `SKIP_RBAC` or starts with `/docs`/`/openapi`
2. Get `request.state.user` (set by JWTAuthMiddleware)
3. Call `has_permission(user.roles, method, path)`
4. If denied → 403 with `{error, required_roles, user_roles}`

### 4.3 `gateway/middleware/api_key.py` — ApiKeyMiddleware

**Singleton:** `api_key_middleware`

**Flow:**
1. Only activates for routes in `API_KEY_ROUTES`
2. Extract `X-API-Key` header
3. SHA-256 hash the key
4. Validate via `UserRepository.validate_api_key()`
5. Inject `ServiceContext(service_id, service_name, scopes)` into `request.state.service`

**API key routes:** `POST /internal/predict`, `POST /internal/features`, `POST /internal/etl-trigger`

### 4.4 `gateway/middleware/rate_limit.py` — RateLimiter

**Singleton:** `rate_limiter` (no Redis client passed yet — memory-only)

**Default rules:**
| Method | Path | Max Requests | Window |
|--------|------|-------------|--------|
| `POST` | `/auth/login` | 5 | 15 min |
| `POST` | `/auth/refresh` | 30 | 1 min |
| `*` | `/admin/*` | 60 | 1 min |

**Backend:** Redis sorted-set sliding window, with in-memory list fallback.

### 4.5 `gateway/middleware/logging.py` — RequestLoggingMiddleware

Logs every request with: timestamp, level, method, path, status code, duration (ms), caller identity (username or service_name), client IP.

---

## 5. Dependency Injection (`gateway/dependencies.py`)

| Dependency | What It Does | Use Case |
|---|---|---|
| `get_current_user` | JWT validation only | `/auth/me`, `/auth/logout` |
| `require_auth` | JWT + RBAC check | All protected routes |
| `require_role("ROLE")` | JWT + specific role check | Role-gated endpoints |
| `get_current_service` | API key validation | `/internal/*` routes |
| `get_etl_service` | Constructs ETLService with DB session | `/api/etl/runs` |

---

## 6. RBAC Matrix — 4 Roles

Defined in `shared/auth/permissions.py` (30 rules across 5 route areas).

| Role | Description | Access |
|---|---|---|
| **ADMIN** | Full system access | All routes |
| **RELATIONSHIP_MANAGER** | Customer dashboard + NBA | `/dashboard/*` |
| **DATA_SCIENTIST** | Model training, evaluation | `/models/*` |
| **OPERATIONS** | Monitoring, ETL dashboards | `/monitoring/*`, `/api/etl/**` |

**How It Works:**
- JWT payload contains `roles: ["RELATIONSHIP_MANAGER"]`
- RBAC middleware matches request path against `PERMISSIONS` list
- Wildcard support: `/api/etl/**` matches `/api/etl/runs`, `/api/etl/runs/batch/123`, etc.
- Empty role list `[]` = public endpoint (no auth needed)

---

## 7. Layer Architecture (ETL Example)

```
┌──────────────────────────────────────────────┐
│ Route: etl_routes.py                         │
│ @router.get("/runs")                         │
│ → service: ETLService = Depends(get_etl_...) │
│ THIN — one-line delegation                   │
└──────────────────┬───────────────────────────┘
                   │
┌──────────────────▼───────────────────────────┐
│ Service: etl_service.py                      │
│ ETLService.get_dashboard()                   │
│ → calls 4 repo methods                       │
│ → formats durations, row counts              │
│ → maps dict → Pydantic response              │
│ ALL business logic here                      │
└──────────────────┬───────────────────────────┘
                   │
┌──────────────────▼───────────────────────────┐
│ Repository: etl_repository.py                │
│ ETLRepository — raw SQL via sqlalchemy.text()│
│ → get_todays_kpis()                          │
│ → get_status_panel()                         │
│ → get_quality_trend()                        │
│ → get_runs()                                 │
│ ALL data access here                         │
└──────────────────┬───────────────────────────┘
                   │
┌──────────────────▼───────────────────────────┐
│ Database: etl_clean (target DB)              │
│ etl.etl_audit — 6 records, 15,200 rows each  │
└──────────────────────────────────────────────┘
```

---

## 8. Shared Dependencies

The gateway imports from these `shared/` packages:

| Shared Package | Purpose |
|---|---|
| `shared.config.settings` | Environment configuration (DB URLs, ports, secrets) |
| `shared.database.session` | Async session factory + `get_target_session()` dependency |
| `shared.auth.models` | Pydantic models: UserContext, ServiceContext, LoginRequest, etc. |
| `shared.auth.permissions` | RBAC matrix: PERMISSIONS list + has_permission() |
| `shared.auth.token_service` | JWT create/verify/refresh/blacklist |
| `shared.auth.user_repository` | IAM user/role/API key persistence (psycopg2 sync) |
| `shared.auth.authenticator` | LDAP/AD bind (optional, degrades gracefully) |
| `shared.auth.audit` | Auth audit trail: iam.auth_audit |

The gateway also imports from `etl/`:
- `etl.repositories.etl_repository.ETLRepository`
- (Future: `etl.models.*` for ORM queries)

---

## 9. Database Connections

| Connection | URL | Used By |
|---|---|---|
| **Source DB** | `postgresql+asyncpg://clp_user:***@localhost:5432/customer_lifecycle` | Auth routes (IAM schema) |
| **Target DB** | `postgresql+asyncpg://postgres:@localhost:5432/etl_clean` | ETL routes (etl.etl_audit) |

The `UserRepository` uses **sync psycopg2** (not async SQLAlchemy) for IAM operations.

---

## 10. Known Gaps & TODOs

| # | Severity | Gap |
|---|---|---|
| 1 | 🔴 | **User CRUD missing:** POST/PUT/DELETE `/admin/users/{id}` defined in permissions but no handlers |
| 2 | 🔴 | **No `remove_role()`** in UserRepository — can't unassign a role |
| 3 | 🔴 | **No `get_user()`** in UserRepository — can't fetch single user |
| 4 | 🟠 | **Dashboard/Model/Monitoring routes don't exist** — permissions defined but no route files |
| 5 | 🟠 | **Rate limiter has no Redis** — only in-memory fallback, not production-ready |
| 6 | 🟠 | **Dockerfile CMD** references `main:app` instead of `gateway.main:app` |
| 7 | 🟡 | **CORS allow_origins=["*"]** — needs restriction for production |
| 8 | 🟡 | **`/auth/me`** returns `created_at=None, last_login_at=None` — not loaded from DB |
| 9 | 🟡 | **API key `expires_at=None`** — `expires_in_days` not computed |
| 10 | 🟢 | **Stubs:** `gateway/app/`, `gateway/config/`, `routes/health.py`, `routes/proxy.py`, `middleware/cors.py` |
| 11 | 🟢 | **No tests** — `gateway/tests/` directory is empty |
