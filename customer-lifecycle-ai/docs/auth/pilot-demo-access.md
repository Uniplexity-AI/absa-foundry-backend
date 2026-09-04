# Pilot Demo — Authentication & Role Access (2026-09-02)

Summary of the auth work for the stakeholder review. No Redis is used anywhere
in the pilot/local stack (in-process JWT blacklist, DB-backed lockout, in-memory
rate limit).

## Demo accounts (username / password: `Pilot@2025`)
Seeded by `scripts/seed_iam.py` (from repo root). Re-run to reset passwords/locks.

| Username  | Display name                 | Role                | Sees |
|-----------|------------------------------|---------------------|------|
| `admin`   | System Administrator         | ADMIN               | **Everything** (full-access bypass) |
| `rm.demo` | Relationship Manager (Demo)  | RELATIONSHIP_MANAGER | Customer analytics / NBA / portfolio pages |
| `ds.demo` | Data Scientist (Demo)        | DATA_SCIENTIST      | Model Performance + feature endpoints (lands on `/dashboard/models`) |
| `ops.demo`| Operations Analyst (Demo)    | OPERATIONS          | ETL run history + config manager + monitoring (lands on `/dashboard/etl-run-history`) |

Change the demo password: `python scripts/seed_iam.py --password 'YourPw'`
List users: `python scripts/seed_iam.py --list` · Skip demo users: `--skip-demo`

## Backend enforcement (gateway :8080)
- **Every non-public route requires a valid JWT** — enforced by the
  `auth_rbac_middleware` HTTP middleware in `gateway/main.py` (no token → 401,
  wrong role → 403, OPTIONS preflight passes through to CORS).
- `shared/auth/permissions.py`:
  - **ADMIN = full-access bypass** (`has_permission` returns True whenever
    `ADMIN` is in the user's roles).
  - Area-based matrix (wildcard `**`): RM → `/api/v1/{customers,predictions,
    recommendations,forecasts,churn-intel,insights,intelligence,outcomes,pilot/actions}`;
    DS → `/api/v1/models`, `/features`; OPS → `/api/v1/monitoring`, `/api/etl`;
    `/admin/**` ADMIN-only.
- Public (no token): `/auth/login`, `/auth/refresh`, `/health`, `/docs`,
  `/openapi.json`, `/redoc`. `/auth/me` + `/auth/logout` require a valid token
  but any authenticated role may call them.
- CORS: `allow_origins=["*"]` with **credentials disabled** (Bearer-header auth;
  `allow_credentials=True` + `"*"` is rejected by browsers on preflight).
- Migration `011_local_auth.sql` (source DB) added `password_hash`,
  `must_change_pwd`, `failed_attempts`, `locked_until` to `iam.users`; lockout is
  DB-backed and survives restarts. Passwords: salted `pbkdf2_sha256`
  (`shared/auth/password.py`, iterations `settings.password_hash_iterations`).

## Frontend (absa-foundry-frontend, dev :3000)
- Login writes ABSA contract keys: `token`, `refresh_token`, `user_id`, `email`,
  `role` (primary), `roles` (JSON array), `userName` (= `display_name`).
  Legacy fork keys (`company_name`, `tenant_id`, sub-account/branches) removed.
- `decodeJWT.js` reads `roles[]`, `display_name`/`username`, `sub`, `branch_code`
  (falls back to legacy `role`/`name` for DEV payloads).
- Role-based landing after login: ADMIN/RM → `/dashboard/portfolio`,
  DS → `/dashboard/models`, OPS → `/dashboard/etl-run-history`.
- Router guard (`src/router/index.js`) requires a token on all `/dashboard*`,
  `/portfolio`, `/customer/*` and redirects out-of-area navigation to the role's
  home page. `?ub_impersonate=` token injection removed.
- `DashboardLayout.vue` nav is role-gated: analytics pages (Dashboard, Branch
  Manager, INTELLIGENCE) for RM+ADMIN; **Model Performance** for DS+ADMIN;
  **Run History / ETL Config Manager** for OPS+ADMIN. Header shows real
  `display_name` + role label (Administrator / Relationship Manager / Data
  Scientist / Operations Analyst). `Models.vue` "Request Retrain" hidden unless
  ADMIN/DATA_SCIENTIST.

## Known issues / follow-ups (Phase D)
- `GET /api/v1/models` returns **500** from the downstream registry even with a
  valid ADMIN/DS token (affects the DS demo page) — investigate the models
  registry backend before the review.
- Dashboard KPIs can read **0 / empty** if a data endpoint is not reachable or
  not yet generated for the selected `as_of_date` snapshot — confirm the feature
  pipeline/snapshots exist for the demo dates.
- `App.vue` still calls legacy dead endpoints at boot (`/currency/*`,
  `/preferences/`, `/rbac/*`, `/modules-manager/*`) → harmless 401/404 console
  noise on the ABSA gateway; can be removed from the boot sequence when legacy
  screens are retired.
