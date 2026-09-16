# Pilot Environment — Synthetic Data Migration Runbook

> **Purpose:** Reproduce the ABSA Foundry pilot environment on the **pilot machine** with a full
> synthetic dataset (5,000 customers, behavioural churn labels), using the same process that was
> built and validated locally.
> **Audience:** Operator / developer running the migration **on the pilot machine**.
> **Version:** 2026-09-04
> **Branch:** `poc-90day`

---

## 1. What this runbook does

On a fresh or previously-loaded pilot environment, this runbook:

1. Stops all backend services (no schema changes while running).
2. **Truncates** every `etl_clean` table (feature store, states, raw clean tables, **pilot action log/state**) — full reset.
3. **Applies all DB migrations** (IAM → **local-auth columns** → ETL audit → **clean data tables** → feature store → states → **pilot actions** → **market segment**), then seeds the IAM demo accounts.
4. **Generates and loads** 5,000 synthetic customers + ~348k transactions + products/cards/engagement/demographics
   into `etl_clean` (with behaviourally-driven churn: ~5% `Closed` with a 90-day activity gap).
5. Restarts all backend services.
6. Verifies row counts, API health, and that the pilot action-log tables are wired (see §5.4).

> ⚠️ **The `002_clean_data_tables.sql` migration is the source of truth for the clean-table DDL.**
> The data generator (`generate_synthetic_feature_store_data.py`) does **NOT** apply DDL anymore —
> it only inserts rows. Running the generator without running migrations first will fail with
> `UndefinedColumn: column "full_name" of relation "customers_clean" does not exist`.

---

## 2. Prerequisites

| Requirement | Check |
|---|---|
| Repo cloned to a stable path on the pilot machine | `C:\absa\absa-foundry-backend\customer-lifecycle-ai` (example) |
| Branch `poc-90day` checked out | `git checkout poc-90day && git pull` |
| Python `.venv` present | `customer-lifecycle-ai\.venv\Scripts\python.exe` exists |
| PostgreSQL running, DBs `etl_validation` + `etl_clean` exist | `psql -U postgres -l` |
| Dependencies installed | `requirements.txt` + all service `requirements.txt` (see `pilot_setup.ps1`) |
| `psql` available, or use the python migration runner | `psql` OR `.venv` python (preferred) |

**If this is a brand-new machine**, run the one-time setup first:

```powershell
cd C:\path\to\absa-foundry-backend\customer-lifecycle-ai
powershell -ExecutionPolicy Bypass -File scripts\pilot_setup.ps1
```

---

## 3. Configure `.env` (CRITICAL — do this once)

Edit `.env` in `customer-lifecycle-ai\` and set the **pilot** DB credentials. Because the pilot
PostgreSQL is on the pilot machine itself, it is normally `localhost` / `127.0.0.1`:

```ini
# ---- PostgreSQL Source (etl_validation — raw) ----
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_DB=etl_validation
POSTGRES_USER=postgres
POSTGRES_PASSWORD=<PILOT_DB_PASSWORD>
DATABASE_URL=postgresql://postgres:<PILOT_DB_PASSWORD>@127.0.0.1:5432/etl_validation

# ---- PostgreSQL Target (etl_clean — clean/features) ----
POSTGRES_TARGET_HOST=127.0.0.1
POSTGRES_TARGET_PORT=5432
POSTGRES_TARGET_DB=etl_clean
POSTGRES_TARGET_USER=postgres
POSTGRES_TARGET_PASSWORD=<PILOT_DB_PASSWORD>
```

> The python runners (`pilot_migrate.py`, feature/prediction services) read `.env`, so they will
> connect to the correct database automatically. The `psql` commands below set `PGPASSWORD` explicitly.

---

## 4. Standard path — run all commands on the pilot machine

Open a PowerShell terminal on the **pilot machine** and run each block below in order.

```powershell
# ── Convenience variables ──────────────────────────────────────────────────
$proj = "C:\path\to\absa-foundry-backend\customer-lifecycle-ai"   # ← change to real path
$py   = "$proj\.venv\Scripts\python.exe"
$env:PGPASSWORD = "<PILOT_DB_PASSWORD>"                            # ← change to real password
Set-Location $proj
```

### Step 4.1 — Stop all backend services

```powershell
powershell -ExecutionPolicy Bypass -File scripts\pilot_stop.ps1
```

Confirm nothing is listening on the service ports:

```powershell
Get-NetTCPConnection -State Listen -LocalPort 8002,8003,8004,8005,8080 -ErrorAction SilentlyContinue |
  Select-Object LocalPort, OwningProcess
# Expect: no output (all stopped)
```

### Step 4.2 — Truncate `etl_clean` (full reset)

Order matters (FK dependencies). `CASCADE` handles the rest:

```sql
TRUNCATE customer_states, state_transitions RESTART IDENTITY CASCADE;
TRUNCATE customer_features RESTART IDENTITY CASCADE;
TRUNCATE customer_id_mapping RESTART IDENTITY CASCADE;
TRUNCATE customer_transactions_clean, customers_clean, accounts_clean,
         loans_clean, cards_clean, digital_engagement_clean, demographics_clean
  RESTART IDENTITY CASCADE;
```

Run via `psql`:

```powershell
psql -h 127.0.0.1 -p 5432 -U postgres -d etl_clean -c "TRUNCATE customer_states, state_transitions RESTART IDENTITY CASCADE;"
psql -h 127.0.0.1 -p 5432 -U postgres -d etl_clean -c "TRUNCATE customer_features RESTART IDENTITY CASCADE;"
psql -h 127.0.0.1 -p 5432 -U postgres -d etl_clean -c "TRUNCATE customer_id_mapping RESTART IDENTITY CASCADE;"
psql -h 127.0.0.1 -p 5432 -U postgres -d etl_clean -c "TRUNCATE customer_transactions_clean, customers_clean, accounts_clean, loans_clean, cards_clean, digital_engagement_clean, demographics_clean RESTART IDENTITY CASCADE;"
```

Expected output: a `TRUNCATE TABLE` confirmation for each table. If a table does not exist yet
(e.g., `demographics_clean` on a very first run before migrations), that error is **expected and fine** —
the next step creates it.

The pilot action-log/state tables (`pilot_action_log`, `pilot_customer_state`) are **also** in `etl_clean`.
On a re-seed (not a very first run) clear any RM activity recorded during earlier testing:

```powershell
psql -h 127.0.0.1 -U postgres -d etl_clean -c "TRUNCATE pilot_action_log, pilot_customer_state RESTART IDENTITY CASCADE;"
```

### Step 4.3 — Apply database migrations

```powershell
& $py scripts\pilot_migrate.py
```

Expected output:

```
Applying database/iam/001_initial_schema.sql -> etl_validation
Applying database/migrations/011_local_auth.sql -> etl_validation
Applying database/migrations/001_etl_schema.sql -> etl_clean
Applying database/migrations/002_clean_data_tables.sql -> etl_clean
Applying database/feature_store/001_customer_features.sql -> etl_clean
Applying database/state_engine/001_customer_states.sql -> etl_clean
Applying database/migrations/009_pilot_actions.sql -> etl_clean
Applying database/migrations/010_market_segment.sql -> etl_clean

All migrations applied successfully.
```

> If `pilot_migrate.py` fails with `InvalidForeignKey ... customers_clean`, the clean tables already
> exist with an older conflicting schema (e.g., `customers_clean(id bigint PK)`). Run **Step 6
> (Schema repair)** below, then repeat Step 4.2 → 4.3.

**Seed the IAM auth store** (needs the `011` columns above). Creates the four demo login users
(`admin` / `rm.demo` / `ds.demo` / `ops.demo`, password `Pilot@2025`) plus the service-account API
keys. Idempotent — safe to re-run to reset passwords/locks:

```powershell
& $py scripts\seed_iam.py
# list users:  & $py scripts\seed_iam.py --list
# custom password: & $py scripts\seed_iam.py --password 'YourPw'
```

> ⚠️ The gateway now **enforces authentication**: every route except `/auth/login`, `/auth/refresh`,
> `/health`, `/docs` returns `401` without a Bearer token; ADMIN has full access. See
> `docs/auth/pilot-demo-access.md` for the role/route map.

### Step 4.4 — Generate and load synthetic data

```powershell
& $py scripts\generate_synthetic_feature_store_data.py `
  --load --customers 5000 --as-of-date 2026-07-27 --seed 42 `
  --database-url postgresql://postgres:<PILOT_DB_PASSWORD>@127.0.0.1:5432/etl_clean
```

Expected output (counts may vary slightly with generator version):

```
Generated batch synthetic_2026-07-27_XXXXXXXX for 5,000 customers (as of 2026-07-27).
  customers_clean: 5,000 rows
  customer_transactions_clean: 348,250 rows
  accounts_clean: 5,749 rows
  loans_clean: 2,028 rows
  cards_clean: 4,993 rows
  digital_engagement_clean: 73,195 rows
  demographics_clean: 5,000 rows
Validated 81,059 recent transactions across 4,757 customers.
```

> ⚠️ If this fails with `UndefinedColumn: column "full_name" ...`, the generator ran before the
> migrations created the correct schema. Re-run Step 4.2 → 4.3 → 4.4 in order (never the generator alone).

### Step 4.5 — Restart backend services

```powershell
powershell -ExecutionPolicy Bypass -File scripts\pilot_start.ps1
```

Wait ~15s, then confirm all six services are listening:

```powershell
Start-Sleep 15
foreach ($port in 8002,8003,8004,8005,8006,8080) {
  $r = Test-NetConnection -ComputerName 127.0.0.1 -Port $port -WarningAction SilentlyContinue
  "$port : $($r.TcpTestSucceeded)"
}
# Expect: 8002:True ... 8080:True
```

> **Alternative:** the backend can run as a Windows service via pywin32 (`scripts/pilot_service.py`)
> instead of `pilot_start.ps1` — see `docs/pilot-service.md`. Only one of the two runs at a time
> (they share ports 8080/8002-8006).

---

## 5. Verification

### 5.1 Row counts (source of truth)

```powershell
psql -h 127.0.0.1 -U postgres -d etl_clean -c "SELECT 'customers' t, count(*) FROM customers_clean
UNION ALL SELECT 'transactions', count(*) FROM customer_transactions_clean
UNION ALL SELECT 'accounts', count(*) FROM accounts_clean
UNION ALL SELECT 'cards', count(*) FROM cards_clean
UNION ALL SELECT 'engagement', count(*) FROM digital_engagement_clean;"
```

Expect approximately: customers **5,000**, transactions **~348k**, accounts ~5.7k, cards ~5k, engagement ~73k.

### 5.2 API health

```powershell
Invoke-RestMethod http://127.0.0.1:8080/health
Invoke-RestMethod http://127.0.0.1:8005/health
Invoke-RestMethod http://127.0.0.1:8006/health   # model management (models page data)
```

### 5.3 Feature store populated

Once the feature engine runs (batch or on-demand), confirm snapshots:

```powershell
psql -h 127.0.0.1 -U postgres -d etl_clean -c "SELECT as_of_date, count(*) FROM customer_features GROUP BY 1 ORDER BY 1;"
```

> The synthetic generator only writes **raw** clean tables. The `customer_features` table is populated
> by the Feature Engineering Service (feature pipeline) — run the feature pipeline / prediction batch if
> the dashboards need scores populated, or they will show placeholders.

### 5.4 Pilot action-log wiring (frontend write buttons)

The frontend action buttons (Assign RM, Enrol/Launch Campaign, Acknowledge alert, NBA Override, Save
Action Plan, Record Action) persist through the gateway → decision service → `etl_clean`. After a fresh
load these tables exist and are empty:

```powershell
psql -h 127.0.0.1 -U postgres -d etl_clean -c "SELECT to_regclass('public.pilot_action_log') AS log, to_regclass('public.pilot_customer_state') AS state;"
psql -h 127.0.0.1 -U postgres -d etl_clean -c "SELECT count(*) FROM pilot_action_log; SELECT count(*) FROM pilot_customer_state;"
# Expect: both regclass columns non-NULL; both counts 0 after a fresh seed
```

Smoke-test the write path end-to-end. The gateway now enforces auth, so grab an **admin** token first
(demo password `Pilot@2025`):

```powershell
# 0. Login as admin for a token
$login = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8080/auth/login" -ContentType "application/json" -Body '{"username":"admin","password":"Pilot@2025"}'
$h = @{ Authorization = "Bearer $($login.access_token)" }

# 1. Append an action-log row via the gateway
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8080/api/v1/pilot/actions/log" -Headers $h -ContentType "application/json" -Body '{"customer_id":"CUST00001","action_type":"RM_ASSIGNED","detail":"Smoke test","meta":{"rm":"N. Khumalo"},"actor":"admin"}'
# 2. Read it back
Invoke-RestMethod -Uri "http://127.0.0.1:8080/api/v1/pilot/actions?customer_id=CUST00001&limit=5" -Headers $h
# 3. Merge per-customer state and read it back
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8080/api/v1/pilot/actions/state/CUST00001" -Headers $h -ContentType "application/json" -Body '{"patch":{"rm":"N. Khumalo"}}'
Invoke-RestMethod -Uri "http://127.0.0.1:8080/api/v1/pilot/actions/state/CUST00001" -Headers $h
# 4. Clean up the smoke row
psql -h 127.0.0.1 -U postgres -d etl_clean -c "DELETE FROM pilot_action_log WHERE customer_id='CUST00001'; DELETE FROM pilot_customer_state WHERE customer_id='CUST00001';"
```

> **Frontend sync flag:** the frontend write-through is ON by default. Set `VITE_PILOT_SYNC=false` only for
> purely-local dev (no backend). For the pilot build leave it unset (or `true`) so clicks reach the backend.

### 5.5 Authentication & demo roles

The backend enforces JWT + RBAC. Login each demo account and confirm its role:

```powershell
$pw = "Pilot@2025"
foreach ($u in "admin","rm.demo","ds.demo","ops.demo") {
  $r = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8080/auth/login" -ContentType "application/json" -Body (@{username=$u;password=$pw} | ConvertTo-Json)
  $me = Invoke-RestMethod -Uri "http://127.0.0.1:8080/auth/me" -Headers @{ Authorization = "Bearer $($r.access_token)" }
  "{0,-10} -> {1} ({2})" -f $u, ($me.roles -join ','), $me.display_name
}
# Expect:
#   admin     -> ADMIN (System Administrator)
#   rm.demo   -> RELATIONSHIP_MANAGER (Relationship Manager (Demo))
#   ds.demo   -> DATA_SCIENTIST (Data Scientist (Demo))
#   ops.demo  -> OPERATIONS (Operations Analyst (Demo))
```

**Role access map + ADMIN full access:** `docs/auth/pilot-demo-access.md`.

---

## 6. Schema repair (only if migrations fail on existing clean tables)

On a machine where the clean tables were previously created by the **old generator DDL** (schema with
`customers_clean(id bigint PK)` and no `full_name`/`kyc_tier`/`nationality`/`status`), drop and recreate them:

```powershell
$env:PGPASSWORD="<PILOT_DB_PASSWORD>"
psql -h 127.0.0.1 -U postgres -d etl_clean -c "DROP TABLE IF EXISTS demographics_clean, digital_engagement_clean, cards_clean, loans_clean, accounts_clean, customer_transactions_clean, customers_clean CASCADE;"
```

Then re-run Step 4.2 (truncate remaining), 4.3 (migrations recreate clean tables with the correct
`customer_id`-primary-key schema), 4.4 (load).

---

## 7. Rollback

There is no destructive action that cannot be reversed:

- **Data only:** re-run Step 4.2 (truncate) then 4.4 (load) — fully reproducible with `--seed 42`.
- **Schema:** re-run Step 4.3 after Step 6. All migrations are `CREATE ... IF NOT EXISTS` / idempotent.
- **Services:** `scripts\pilot_stop.ps1` stops; `scripts\pilot_start.ps1` starts. Logs in `logs\pilot\`.

---

## 8. Troubleshooting quick reference

| Symptom | Cause | Fix |
|---|---|---|
| `UndefinedColumn: column "full_name" ...` | Generator ran before migrations created clean tables | Run Step 4.2 → 4.3 → 4.4 in order |
| `InvalidForeignKey ... customers_clean` | Stale conflicting clean-table schema | Step 6 (drop clean tables), then 4.3, 4.4 |
| `relation "demographics_clean" does not exist` on truncate | Table not created yet | Expected on first run — migrations create it |
| Generator validation: `No transactions in the 30-day window` | Wrong `--as-of-date` (too old) | Keep `--as-of-date 2026-07-27` (matches training/holdout dates) |
| Services don't start / port conflict | Stale process | `pilot_stop.ps1`, kill stray `python.exe` on ports, `pilot_start.ps1` |
| Empty `customer_features` | Feature pipeline not run after load | Run the feature pipeline / `POST /features/compute-batch` |
| `502 Decision Intelligence unavailable` on `/api/v1/pilot/actions/*` | Gateway can't reach decision service | Ensure `:8005` is up; gateway proxies to `127.0.0.1:8005` |
| `relation "pilot_action_log" does not exist` | Migration `009` not applied | Re-run `pilot_migrate.py` (Step 4.3) — confirms `009_pilot_actions.sql` in output |
| `401 Missing Authorization header` on `/api/*` | Gateway enforces JWT (no token sent) | Call `/auth/login` first, send `Authorization: Bearer <token>` (see §5.4/§5.5) |
| Demo login `invalid credentials` | IAM users not seeded / wrong password | Run `scripts\seed_iam.py` (Step 4.3); default password `Pilot@2025` |
| `column "password_hash" does not exist` | Migration `011_local_auth.sql` not applied | Re-run `pilot_migrate.py` — confirms `011_local_auth.sql -> etl_validation` in output |
| Panel shows "No RM actions yet" | No action clicked yet, or `VITE_PILOT_SYNC=false` | Click an action (Assign RM etc.) then Portfolio → Recent RM Activity → Refresh; verify env flag |

---

## 9. One-command quick replay (after first successful run)

If `.env` is correct and you just want to re-seed quickly:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\pilot_stop.ps1
$env:PGPASSWORD="<PILOT_DB_PASSWORD>"
$p = "C:\path\to\absa-foundry-backend\customer-lifecycle-ai"
$py = "$p\.venv\Scripts\python.exe"; Set-Location $p
psql -h 127.0.0.1 -U postgres -d etl_clean -c "TRUNCATE customer_states,state_transitions,customer_features,customer_id_mapping RESTART IDENTITY CASCADE;"
psql -h 127.0.0.1 -U postgres -d etl_clean -c "TRUNCATE customer_transactions_clean,customers_clean,accounts_clean,loans_clean,cards_clean,digital_engagement_clean,demographics_clean RESTART IDENTITY CASCADE;" 2>$null
psql -h 127.0.0.1 -U postgres -d etl_clean -c "TRUNCATE pilot_action_log, pilot_customer_state RESTART IDENTITY CASCADE;" 2>$null
& $py scripts\pilot_migrate.py
& $py scripts\seed_iam.py   # idempotent: demo users + service API keys (password Pilot@2025)
& $py scripts\generate_synthetic_feature_store_data.py --load --customers 5000 --as-of-date 2026-07-27 --seed 42 --database-url postgresql://postgres:<PILOT_DB_PASSWORD>@127.0.0.1:5432/etl_clean
powershell -ExecutionPolicy Bypass -File scripts\pilot_start.ps1
```
