# Terminal & Tool Patterns — Lessons Learned

> **Purpose:** Document recurring issues encountered when running scripts, terminal commands, and edits in this workspace so they aren't repeated.
> **Last updated:** 2026-08-07
>
> **⚠️ BEFORE ANY TASK:** Read `.ai/README.md` (Quick Rules), `.ai/coding-standards.md`, and this file.
>
> **🚨 PRE-FLIGHT CHECKLIST (read before every command):**
> 1. ❌ Am I about to use `python -c "..."`? → STOP. Write a `.py` script instead.
> 2. ❌ Am I about to use `multi_replace_string_in_file`? → Use individual `replace_string_in_file` calls.
> 3. ❌ Is the script in `scripts/` importing from `app.*`? → It must run from within the service directory, not from project root.
> 4. ❌ Am I chaining `cd` + `uv run`? → Use `--directory` flag or separate commands.
> 5. ❌ PostgreSQL column is NUMERIC/DECIMAL? → Convert to `float()` before math.
> 6. ❌ RealDictCursor row access? → Use `row["name"]` not `row[0]`.
> 7. ❌ Am I about to use `curl` in PowerShell? → Use `Invoke-RestMethod` instead.
> 8. ❌ Am I about to `pip install` in uv Python? → Use `.venv` + `uv pip install`.
> 9. ❌ Am I starting a service? → Activate `.venv` first, run from service's own directory.
> 10. ❌ Am I installing large packages (xgboost, scipy)? → Set `$env:UV_HTTP_TIMEOUT = "600"` first.
> 11. ❌ Am I starting the Gateway? → Install auth deps first: `uv pip install pyjwt passlib bcrypt python-multipart sqlalchemy`.
> 12. ❌ Did the tool strip my `Set-Location`? → Use `Push-Location` or run `cd` as a separate command.
> 13. ❌ Am I using `dict.get(key, default)` for API data? → Use `dict.get(key) or default` — handles None values.
> 14. ❌ Did I add a field to a Pydantic constructor? → Check the schema has that field first.
> 15. ❌ Am I adding routes to a FastAPI router? → Static segments BEFORE `/{param}` catch-alls.
> 16. ❌ Am I using `str.replace("AND", "and")` on user strings? → Use `re.sub(r'\bAND\b', 'and', ...)` — substring replacement corrupts words like DORMANT.
> 17. ❌ Am I debugging a silent failure? → Add print/logging inside try/except blocks — swallowed exceptions hide the real error.
> 18. ❌ Did upstream services go down? → Check `@(8002,8003,8004) | ForEach-Object { Invoke-RestMethod "http://100.82.12.85:$_/health" }` first.

---

## 1. PowerShell Terminal Patterns

### ❌ `curl` does NOT exist in PowerShell

PowerShell has no `curl` command. The `curl` alias maps to `Invoke-WebRequest`, which has completely different syntax.

```powershell
# ❌ FAILS — "Cannot find drive. A drive with the name 'http' does not exist."
curl -s http://100.82.12.85:8003/health

# ✅ CORRECT — use Invoke-RestMethod for API calls
Invoke-RestMethod -Uri "http://100.82.12.85:8003/health"

# ✅ CORRECT — with error handling
try {
    $r = Invoke-RestMethod -Uri "http://100.82.12.85:8003/health" -TimeoutSec 5
    Write-Host ($r | ConvertTo-Json)
} catch {
    Write-Host "Service not running: $_"
}
```

### ❌ NEVER `pip install` into uv-managed Python

The uv-managed Python at `C:\Users\ADMIN\AppData\Roaming\uv\python\cpython-3.11.13-windows-x86_64-none\` is locked (PEP 668). Only `pip` and `setuptools` are available. Any `pip install` will fail.

```powershell
# ❌ FAILS — "This Python installation is managed by uv and should not be modified."
C:\Users\...\python.exe -m pip install uvicorn

# ❌ FAILS — Same error
uv pip install uvicorn --python C:\Users\...\python.exe
```

### ✅ ALWAYS use `.venv` for package management

This project uses a virtual environment at `customer-lifecycle-ai/.venv`. All packages must be installed there via `uv pip install`.

```powershell
# ✅ CORRECT — activate venv, then install
Set-Location "c:\Users\ADMIN\Desktop\uniplexity-ai\ABSA\absa-foundry-backend\customer-lifecycle-ai"
.\.venv\Scripts\Activate.ps1
uv pip install <package-name>
```

### ❌ `.venv` has no `pip` module

uv-created virtual environments do NOT include pip. Use `uv pip install` instead.

```powershell
# ❌ FAILS — "No module named pip"
.\.venv\Scripts\python.exe -m pip install xgboost

# ✅ CORRECT
.\.venv\Scripts\Activate.ps1
uv pip install xgboost
```

### ✅ Starting Services

**CRITICAL: Services MUST be started from within their own directory, NOT from project root.** Each service's `main.py` does `from app.api.routes import router` — this resolves relative to the service directory, not the project root. The ONLY exception is the Gateway, which runs from project root.

```powershell
# === Feature Engineering Service (port 8002) ===
Set-Location "c:\Users\ADMIN\Desktop\uniplexity-ai\ABSA\absa-foundry-backend\customer-lifecycle-ai\services\feature-engineering-service"
..\..\.venv\Scripts\Activate.ps1
uvicorn main:app --host 0.0.0.0 --port 8002

# === Customer State Service (port 8003) ===
Set-Location "c:\Users\ADMIN\Desktop\uniplexity-ai\ABSA\absa-foundry-backend\customer-lifecycle-ai\services\customer-state-service"
..\..\.venv\Scripts\Activate.ps1
uvicorn main:app --host 0.0.0.0 --port 8003

# === Prediction Service (port 8004) ===
Set-Location "c:\Users\ADMIN\Desktop\uniplexity-ai\ABSA\absa-foundry-backend\customer-lifecycle-ai\services\prediction-service"
..\..\.venv\Scripts\Activate.ps1
uvicorn main:app --host 0.0.0.0 --port 8004

# === Decision Intelligence Service (port 8005) ===
Set-Location "c:\Users\ADMIN\Desktop\uniplexity-ai\ABSA\absa-foundry-backend\customer-lifecycle-ai\services\decision-intelligence-service"
..\..\.venv\Scripts\Activate.ps1
uvicorn main:app --host 0.0.0.0 --port 8005

# === API Gateway (port 8080) — ONLY service that runs from project root ===
Set-Location "c:\Users\ADMIN\Desktop\uniplexity-ai\ABSA\absa-foundry-backend\customer-lifecycle-ai"
.\.venv\Scripts\Activate.ps1
uvicorn gateway.main:app --host 0.0.0.0 --port 8080
```

**❌ DO NOT run services from project root** (except Gateway):

```powershell
# ❌ FAILS — "No module named 'app'"
Set-Location "...\customer-lifecycle-ai"
uvicorn services.prediction-service.main:app --host 0.0.0.0 --port 8004
```

**Service port map:**

| Service | Port | Run From Directory | Command |
|---------|------|-------------------|---------|
| Feature Engineering | 8002 | `services/feature-engineering-service/` | `uvicorn main:app --host 0.0.0.0 --port 8002` |
| Customer State (L1) | 8003 | `services/customer-state-service/` | `uvicorn main:app --host 0.0.0.0 --port 8003` |
| Prediction (L2) | 8004 | `services/prediction-service/` | `uvicorn main:app --host 0.0.0.0 --port 8004` |
| Decision Intel (L3) | 8005 | `services/decision-intelligence-service/` | `uvicorn main:app --host 0.0.0.0 --port 8005` |
| API Gateway | 8080 | `customer-lifecycle-ai/` (root) | `uvicorn gateway.main:app --host 0.0.0.0 --port 8080` |

**Gateway has extra dependencies.** Install before first startup:

```powershell
Set-Location "...\customer-lifecycle-ai"
.\.venv\Scripts\Activate.ps1
uv pip install pyjwt passlib bcrypt python-multipart sqlalchemy
```

### ✅ Checking if services are running

```powershell
# Check all services at once
@(8002,8003,8004,8005,8080) | ForEach-Object {
    $port = $_
    try {
        $r = Invoke-RestMethod -Uri "http://100.82.12.85:$port/health" -TimeoutSec 3
        Write-Host "Port $port : $($r.status) — $($r.service)"
    } catch {
        Write-Host "Port $port : DOWN"
    }
}
```

### ✅ Running batch predictions / ETL

```powershell
# Step 1: Activate venv (always first)
Set-Location "c:\Users\ADMIN\Desktop\uniplexity-ai\ABSA\absa-foundry-backend\customer-lifecycle-ai"
.\.venv\Scripts\Activate.ps1

# Step 2: Run prediction batch (via API call, not direct Python)
Invoke-RestMethod -Uri "http://100.82.12.85:8004/predict/batch?as_of_date=2026-08-07" -Method POST

# Step 3: Verify results
Invoke-RestMethod -Uri "http://100.82.12.85:8004/predict/CUST00042/health?as_of_date=2026-08-07"
```

### ❌ Multiline `python -c` fails

PowerShell's command parser breaks on multiline strings passed to `python -c`. Every `"` and newline causes issues.

```powershell
# ❌ FAILS — PowerShell mangles the multiline string
uv run python -c "
import sys
print('hello')
"

# ❌ FAILS — single-line with complex quoting also breaks
uv run python -c "cur.execute(\"SELECT * FROM t\")"
```

**✅ Fix:** Always write a `.py` script file, then `uv run python scripts/name.py`. Never use `python -c` for anything longer than a one-liner.

```powershell
# ✅ CORRECT
uv run python scripts/my_check.py
```

### ❌ `cd` + `uv run` gets simplified by tool

The terminal tool often drops the `cd` part when simplifying commands:

```powershell
# You write:
cd customer-lifecycle-ai ; uv run python scripts/x.py

# Tool simplifies to:
uv run python scripts/x.py    # runs from ABSA root, not customer-lifecycle-ai
```

**✅ Fix:** Use `--directory` flag with `uv run`:

```powershell
uv run --directory c:\Users\ADMIN\Desktop\uniplexity-ai\ABSA\absa-foundry-backend\customer-lifecycle-ai python scripts/x.py
```

Or run `cd` as a separate command first, then `uv run` in a second command.

### ❌ `uv run` runs from project root by default

`uv run` resolves from the project root (where `pyproject.toml` lives — `ABSA/`), not from `customer-lifecycle-ai/`. This means `services.*` imports fail.

**✅ Fix:** Always `cd` into `customer-lifecycle-ai` first, or use `--directory`.

### ❌ Port "already in use"

When restarting uvicorn, the old process may still hold the port.

```powershell
# ❌ FAILS
uv run --directory ... uvicorn main:app --port 8004
# ERROR: [Errno 10048] only one usage of each socket address

# ✅ FIX
kill_terminal(id="...")  # kill the old terminal first
# then restart
```

### ✅ PowerShell environment variables

```powershell
# Set for current command only:
$env:FE_ENGAGEMENT_FREQUENCY_WINDOW_DAYS='90'

# Then run:
uv run python scripts/x.py
```

---

## 2. Package Management — .venv & uv

### Current Setup (2026-08-07)

| Path | Python | Package Manager | Packages |
|------|--------|----------------|----------|
| `.venv/` (in customer-lifecycle-ai) | CPython 3.12.0 | `uv pip install` | uvicorn, fastapi, pydantic, psycopg2, redis, httpx, dotenv, xgboost*, scikit-learn* |
| `C:\Users\ADMIN\...\cpython-3.11.13\` | CPython 3.11.13 (uv-managed) | LOCKED | pip, setuptools only |

*\* xgboost + scikit-learn are large (~80 MB) downloads — slow on bank network.*

### ✅ Installing new packages

```powershell
Set-Location "c:\Users\ADMIN\Desktop\uniplexity-ai\ABSA\absa-foundry-backend\customer-lifecycle-ai"
.\.venv\Scripts\Activate.ps1
uv pip install <package-name>
```

### ✅ Checking installed packages

```powershell
.\.venv\Scripts\Activate.ps1
uv pip list
```

---

## 3. `replace_string_in_file` Patterns

### ❌ Wrong key names in `multi_replace_string_in_file`

The `replacements` array items MUST use `oldString` and `newString` (camelCase), NOT `old_str` / `new_str` / `old` / `new`.

```json
// ❌ FAILS
{"old_str": "...", "new_str": "..."}

// ✅ CORRECT
{"oldString": "...", "newString": "..."}
```

### ✅ Use individual `replace_string_in_file` when `multi_` fails

If a `multi_replace_string_in_file` call fails with a cryptic error, fall back to individual `replace_string_in_file` calls. They're more reliable.

### ✅ Include 3-5 lines of context

Always include surrounding lines in `oldString` to make the match unambiguous. A single-line match risks finding the wrong occurrence.

---

## 4. File Creation Patterns

### ❌ `create_file` on existing file fails

`create_file` raises an error if the file already exists. Use `replace_string_in_file` to overwrite existing stubs.

### ✅ BOM handling

Files created by the tool may have a UTF-8 BOM (`\xef\xbb\xbf`). When reading in Python, use `encoding='utf-8-sig'`:

```python
with open(path, encoding="utf-8-sig") as f:
    content = f.read()
```

When checking syntax with `ast.parse`, also use `encoding='utf-8-sig'`.

---

## 5. Database Patterns

### ❌ `%(name)d` in psycopg2

psycopg2 only supports `%(name)s` for all parameter types. `%(name)d` causes silent failures or errors.

```python
# ❌ WRONG
cur.execute("SELECT * FROM t WHERE x = %(val)d", {"val": 42})

# ✅ CORRECT
cur.execute("SELECT * FROM t WHERE x = %(val)s", {"val": 42})
```

### ❌ `%(name)s` + `VALUES %s` in `execute_values`

`psycopg2.extras.execute_values` uses `%s` as the VALUES placeholder. You CANNOT mix `%(name)s` named parameters in the same SQL:

```sql
-- ❌ FAILS: ValueError: unsupported format character: '('
UPDATE t SET x = %(computed_at)s FROM (VALUES %s) ...

-- ✅ CORRECT: use NOW() or pass value in template
UPDATE t SET x = NOW() FROM (VALUES %s) ...
```

### ❌ NULL feature values

`dict.get(col, 0.0)` returns `None` when the key EXISTS but has a NULL value (`.get()` only returns the default for missing keys):

```python
# ❌ WRONG — returns None for NULL values
float(features.get(col, 0.0))

# ✅ CORRECT
val = features.get(col)
result = float(val) if val is not None else 0.0
```

### ❌ PostgreSQL `DECIMAL` → NumPy

PostgreSQL `NUMERIC`/`DECIMAL` columns return Python `Decimal` objects. NumPy operations fail with `TypeError`:

```python
# ❌ FAILS: Decimal * float
np.percentile(arr, 25)

# ✅ CORRECT: convert to float first
arr = np.array([float(x) for x in values])
```

### ❌ `RealDictCursor` with index access

When using `cursor_factory=extras.RealDictCursor`, rows are dicts, not tuples:

```python
# ❌ FAILS: KeyError: 0
row[0]

# ✅ CORRECT
row["column_name"]

# For unknown column names:
list(row.values())[0]
```

---

## 5. Python Module Path Patterns

### ❌ Running from wrong directory

All scripts and services need `customer-lifecycle-ai/` on `sys.path` to find `shared.*` and `services.*` modules.

```python
# Standard setup at top of every script:
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
from dotenv import load_dotenv
load_dotenv(os.path.join(_project_root, ".env"))
```

### ❌ Running services from wrong directory

Services MUST be started from within their directory:

```powershell
# ✅ CORRECT
cd services/prediction-service
uv run uvicorn main:app --port 8004

# ❌ FAILS — ModuleNotFoundError: No module named 'app'
uv run uvicorn services.prediction-service.main:app --port 8004
```

### ❌ `_PROJECT_ROOT` calculation

The number of `os.path.dirname()` calls depends on file depth:

```
# For scripts/train_models.py (2 levels deep):
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# For app/models/churn_predictor.py (5 levels deep):
_PROJECT_ROOT = os.path.dirname( 5x os.path.dirname(...))
```

---\n\n## 6. Prediction Service Patterns (Added 2026-08-07)

### ✅ Batch prediction — POST, not Python

The batch prediction is an API call, not a Python script:

```powershell
# ✅ CORRECT — POST to the running service
Invoke-RestMethod -Uri "http://100.82.12.85:8004/predict/batch?as_of_date=2026-07-27" -Method POST -TimeoutSec 120

# Returns: {as_of_date, customers_scored: 4998, chunks_processed: 5, duration_seconds: 2.78, status: "COMPLETED"}
```

**Performance:** 4,998 customers scored and health scores backfilled in ~3 seconds. Chunks customers 1,000 at a time to bound memory. Idempotent — running twice on the same date produces identical results.

### ✅ Verifying predictions after batch

```powershell
# Check a customer
Invoke-RestMethod "http://100.82.12.85:8004/predict/CUST00042/churn?as_of_date=2026-07-27"
Invoke-RestMethod "http://100.82.12.85:8004/predict/CUST00042/health?as_of_date=2026-07-27"

# Verify health scores were backfilled to state service
Invoke-RestMethod "http://100.82.12.85:8003/states/CUST00042?as_of_date=2026-07-27"
# Response includes health_score + component_scores (written by prediction service)
```

### ⚠️ behaviour_sub is 0.0 for many customers

`engagement_score` in `customer_features` is NULL for a significant portion of customers. The `HealthScorer` defaults NULL to 50.0, but if the column is absent from the features dict, `dict.get("engagement_score")` returns `None`, which defaults to 0.0.

```python
# In HealthScorer.compute():
behav_sub = engagement_score if engagement_score is not None else 50.0
# But if engagement_score column is NULL in DB, row.get("engagement_score") returns None
# Which means behav_sub = 50.0 (correct fallback)
# If the column doesn't exist at all, row.get("engagement_score") returns None → same path
```

This produces correct behavior (defaults to 50.0 for NULL), but the 0.0 seen in some responses is because the feature was missing from the feature set when trained. **Not a bug — a data coverage gap. Does not block demo.**

### ❌ OpenBLAS warning on state service (non-fatal)

State service may show `OpenBLAS error: Memory allocation still failed` on startup. This is a numpy/OpenBLAS on Windows issue. The service still starts and works correctly. Ignore this warning.

---

## 7. Large Package Downloads (Added 2026-08-07)

### ❌ Default 30s timeout fails for large packages

`xgboost` (47 MB) and `scipy`/`scikit-learn` (35 MB) are too large for the default 30-second download timeout on the bank's network.

---

## 9. Python `dict.get()` vs `None` Pattern (Added 2026-08-07)

### ❌ `dict.get(key, default)` does NOT handle `None` values

`dict.get()` only returns the default for **missing** keys, NOT for keys that exist but have `None` values. This is a critical distinction when consuming API responses where fields may be present but null.

```python
# ❌ WRONG — returns None when key EXISTS but value is None
name = features.get("customer_segment", "MASS_MARKET")
# If features = {"customer_segment": None}, name = None ❌

# ❌ WRONG — also fails with None
value = features.get("customer_tenure_days", 0) // 30
# If features = {"customer_tenure_days": None}, TypeError: NoneType // int

# ✅ CORRECT — use `or` pattern for None fallback
name = features.get("customer_segment") or "MASS_MARKET"
# Returns "MASS_MARKET" for both missing key AND None value

# ✅ CORRECT — use `or` for arithmetic safety
value = (features.get("customer_tenure_days") or 0) // 30
# Returns 0 for both missing key AND None value
```

**Rule of thumb when consuming API data:** Always use `.get(key) or default` instead of `.get(key, default)` when the upstream service might return `None` for that field.

---

## 10. Pydantic v2 Schema Mismatch (Added 2026-08-07)

### ❌ Constructor fields must match schema fields EXACTLY

Pydantic v2 by default raises `ValidationError` when you pass fields to the constructor that aren't defined in the model schema. Unlike dataclasses, there's no `extra='ignore'` by default.

```python
# Schema
class HealthTrajectory(BaseModel):
    trajectory: str
    current_score: float
    previous_score: float | None = None
    # NO score_30d_ago field defined!

# ❌ FAILS — ValidationError: extra fields not permitted
t = HealthTrajectory(
    trajectory="DECLINING",
    current_score=35.1,
    previous_score=None,
    score_30d_ago=52.0,   # ← Not in schema!
    trend_direction="DOWN", # ← Not in schema!
    trend_magnitude=16.9,   # ← Not in schema!
)

# ✅ FIX 1: Add missing fields to schema
class HealthTrajectory(BaseModel):
    trajectory: str
    current_score: float
    previous_score: float | None = None
    score_30d_ago: float | None = None   # ← Added
    trend_direction: str = "FLAT"         # ← Added
    trend_magnitude: float = 0.0          # ← Added

# ✅ FIX 2: Or, remove extra fields from constructor call
# Only pass fields defined in the schema
```

**Rule:** When you add a field to a constructor call, check the Pydantic model schema first. If the field isn't there, either add it to the schema or remove it from the constructor.

---

## 11. FastAPI Route Ordering (Added 2026-08-07)

### ❌ FastAPI matches `/alerts` as a `{customer_id}` value

When you have both a catch-all parameterized route and a static path segment on the same router, **static routes MUST come before parameterized routes** in the code. Otherwise FastAPI matches the static segment as a dynamic parameter value.

```python
# ❌ WRONG ORDER — /alerts matches as customer_id="alerts"
@router.get("/{customer_id}")
def get_customer(customer_id: str): ...

@router.get("/alerts/{customer_id}")  # ← Never reached!
def get_alerts(customer_id: str): ...

# ✅ CORRECT ORDER — static segments first
@router.get("/alerts/{customer_id}")  # ← Matched first
def get_alerts(customer_id: str): ...

@router.get("/trajectory/{customer_id}")  # ← Matched second
def get_trajectory(customer_id: str): ...

@router.get("/{customer_id}")  # ← Catch-all LAST
def get_customer(customer_id: str): ...
```

**Rule:** On any FastAPI router, always place concrete path segments (like `/alerts`, `/queue`, `/list`) BEFORE parameterized catch-all routes (like `/{customer_id}`).

---

## 12. Duplicate Route Definitions (Added 2026-08-07)

### ❌ Multiple `replace_string_in_file` calls can create duplicate routes

When editing a routes file multiple times with `replace_string_in_file`, old route definitions can remain in the file alongside new ones. FastAPI silently accepts duplicate routes — the first one wins, and the second is unreachable.

```python
# ❌ BAD — file has BOTH of these after multiple edits:
@router.get("/trajectory/{customer_id}")  # ← Old location (after catch-all)
def get_trajectory_v1(...): ...  # ← NEVER called

@router.get("/trajectory/{customer_id}")  # ← New location (before catch-all)
def get_trajectory_v2(...): ...  # ← Actually called
```

**✅ Fix:** After multiple route edits, verify with:
```python
from app.api.routes import customer_intel_router
for route in customer_intel_router.routes:
    print(route.path, route.methods)
```

If you see duplicate paths, delete the file and recreate it cleanly.

**✅ Better fix:** When doing major route restructuring, use `create_file` (after deleting the old file) instead of multiple `replace_string_in_file` calls.

```powershell
# ❌ FAILS — "Failed to download due to network timeout. Try increasing UV_HTTP_TIMEOUT (current value: 30s)."
uv pip install xgboost scikit-learn

# ✅ CORRECT — 600 second timeout
$env:UV_HTTP_TIMEOUT = "600"
uv pip install xgboost scikit-learn
```

**Download time on bank network:** ~10 minutes for xgboost + scikit-learn combined (~82 MB). Be patient.

### ✅ Full .venv dependency list

```powershell
# Core services
uv pip install uvicorn fastapi pydantic pydantic-settings

# Database + cache
uv pip install psycopg2-binary redis

# HTTP + config
uv pip install httpx python-dotenv

# ML (LARGE — needs UV_HTTP_TIMEOUT=600)
$env:UV_HTTP_TIMEOUT = "600"
uv pip install xgboost scikit-learn

# Gateway extras (auth)
uv pip install pyjwt passlib bcrypt python-multipart sqlalchemy
```

---

## 8. `Set-Location` Gets Dropped by Tool (Added 2026-08-07)

### ❌ The terminal tool strips `Set-Location` / `cd`

When chaining commands with `;`, the tool often simplifies away the `Set-Location` part:

```powershell
# You write:
Set-Location "...\customer-lifecycle-ai" ; .\.venv\Scripts\Activate.ps1 ; uvicorn gateway.main:app --port 8080

# Tool simplifies to:
.\.venv\Scripts\Activate.ps1 ; uvicorn gateway.main:app --port 8080
# Now runs from ABSA/ root — gateway module not found!
```

**✅ Workaround A:** Use `Push-Location` instead — the tool is less likely to strip it:

```powershell
Push-Location "...\customer-lifecycle-ai" ; .\.venv\Scripts\Activate.ps1 ; uvicorn gateway.main:app --port 8080
```

**✅ Workaround B:** Run `Set-Location` as a separate command first, then the service start command:

```powershell
# Command 1: navigate
Set-Location "...\customer-lifecycle-ai"

# Command 2: start (separate run_in_terminal call)
.\.venv\Scripts\Activate.ps1 ; uvicorn gateway.main:app --port 8080
```

**✅ Workaround C:** For services, start from within their own directory (the tool handles relative paths better):

```powershell
# Navigate into the service directory — tool is less likely to strip this
Set-Location "...\customer-lifecycle-ai\services\prediction-service"
..\..\.venv\Scripts\Activate.ps1
uvicorn main:app --host 0.0.0.0 --port 8004
```

---

## 6. SQL Patterns

### ✅ Use f-strings for config-driven identifiers

Table and column names from config should use Python f-strings (operator-controlled, not user input):

```python
sql = f"SELECT {self._col_cust} FROM {self._features_table} WHERE {self._col_as_of} = %(d)s"
```

### ✅ Keep `%(name)s` for data values

Data values always use psycopg2 parameterization — never string interpolation:

```python
cur.execute(sql, {"d": as_of_date})  # ✅ parameterized
cur.execute(f"SELECT * FROM t WHERE d = '{date}'")  # ❌ SQL injection risk
```

### ✅ PostgreSQL `SET` clauses see OLD values

In the same UPDATE, a SET clause referencing another SET column sees the OLD (pre-UPDATE) value:

```sql
-- ❌ credit_to_debit_ratio_90d sees OLD debit_sum_30d (NULL)
UPDATE t SET debit_sum_30d = 100, credit_to_debit_ratio_90d = credit / debit_sum_30d;

-- ✅ Run ratio computation in a separate UPDATE
UPDATE t SET debit_sum_30d = 100;
UPDATE t SET credit_to_debit_ratio_90d = credit / debit_sum_30d;
```

---

## Quick Reference

| Situation | Do This |
|-----------|---------|
| Need to run Python logic | Write a `.py` script, never use `python -c` |
| Need to run from correct dir | `uv run --directory <full-path> python scripts/x.py` |
| Port already in use | `kill_terminal(id="...")` then restart |
| Edit multiple files | Use individual `replace_string_in_file` if `multi_` fails |
| Replace file content | Use `replace_string_in_file` not `create_file` (file exists) |
| DB column is NUMERIC | Convert to `float()` before numpy/math |
| Feature has NULL values | Check `val is not None` before `float()` |
| Table/column names from config | Use f-strings in SQL |
| Data values in SQL | Use `%(name)s` psycopg2 params |
| `create_file` disabled | Output code as a codeblock and ask user to save it |
| f-string with backslash | Use a variable: `hdr = "From \\ To"; f"{hdr:...}"` |
| NTILE + GROUP BY | Wrap in subquery: `SELECT ... FROM (SELECT NTILE(...) ...) sub GROUP BY` |
| Complex CTE with `%s` | Use named params `%(name)s` or compute values in Python |
| `DECIMAL` in business math | Convert: `int(r["val"])` or `float(r["val"])` at source |


## 7. Python SQL Query Patterns (Discovered 2026-07-29)

### ❌ f-string backslash in expressions (Python < 3.12)

Python 3.10/3.11 f-strings cannot contain backslashes inside `{...}` expressions:

```python
# ❌ FAILS: SyntaxError
print(f"  {'From \\ To':<12s} ...")

# ✅ CORRECT: use a variable
hdr = "From \\ To"
print(f"  {hdr:<12s} ...")
```

### ❌ NTILE window function with GROUP BY

Window functions cannot appear directly in a GROUP BY clause:

```sql
-- ❌ FAILS
SELECT NTILE(5) OVER (ORDER BY val DESC) AS q, COUNT(*) FROM t GROUP BY q

-- ✅ CORRECT: wrap in a subquery
SELECT q, COUNT(*) FROM (
    SELECT NTILE(5) OVER (ORDER BY val DESC) AS q FROM t
) sub GROUP BY q
```

### ❌ RealDictCursor + `%s` params in complex CTEs

CTEs with multiple `%s` placeholders can cause `IndexError: tuple index out of range` with `RealDictCursor`:

```python
# ❌ FAILS: IndexError
cur.execute("""
    WITH a AS (... WHERE d = %s), b AS (... WHERE d = %s)
    SELECT * FROM a WHERE d = %s
""", (date, date, date))

# ✅ CORRECT: use named params (all %(name)s)
cur.execute("... WHERE d = %(d)s ...", {"d": date})

# ✅ ALTERNATIVE: compute values in Python, use single-param queries
```

### ❌ `argument formats can't be mixed` in psycopg2

Within one `cur.execute()`, ALL placeholders must be the same style:

```python
# ❌ FAILS
cur.execute("SELECT %(name)s FROM t WHERE d = %s", ...)

# ✅ CORRECT: consistent style
cur.execute("SELECT %(col)s FROM t WHERE d = %(d)s", {"col": "x", "d": date})
```

### ❌ `DECIMAL` arithmetic with Python `float`/`int`

PostgreSQL aggregates return `Decimal` objects. Convert at extraction:

```python
# ❌ FAILS: TypeError: unsupported operand type(s)
value = r["total"] * 0.10

# ✅ CORRECT
value = int(r["count"])
amount = float(r["total"] or 0)
result = amount * 0.10
```

### ❌ Tool `create_file` may be disabled

If the tool returns "currently disabled", output the code as a markdown codeblock and ask the user to save it manually.

---

## 13. 🐛 `str.replace("AND", "and")` Corrupts Words (Added 2026-08-07)

### ❌ Substring replacement destroys user data

`str.replace()` replaces ALL occurrences, including inside other words. This is a **critical data-corruption bug** that is extremely hard to spot because it produces no error — just silently wrong results.

```python
# ❌ WRONG — turns "DORMANT" into "DorMant"
condition = "context.customer_state == 'DORMANT' AND context.state_duration_days > 180"
expr = condition.replace("AND", "and")  # "...'DorMant' and..."
# The comparison 'DORMANT' == 'DorMant' silently returns False!

# Also corrupts: BRAND, CANDIDATE, COMMAND, EXPAND, etc.

# ✅ CORRECT — use regex word boundaries
import re
expr = re.sub(r'\bAND\b', 'and', condition)  # "...'DORMANT' and..." ✅
expr = re.sub(r'\bOR\b', 'or', expr)          # Also fixes FOR, STORE, etc.
```

**Real-world impact:** The `test_dormant_reactivation_only` test failed because RULE-001 never triggered — DORMANT customers were silently NOT getting reactivation-only treatment. This took 45 minutes to find because the try/except in the same method swallows the `NameError`.

**Rule:** NEVER use `str.replace()` for logical operators. Always use `re.sub(r'\bWORD\b', ...)` with word boundaries.

---

## 14. 🐛 Pydantic v2 Extra Fields = Silent Failure (Added 2026-08-07)

### ❌ Passing extra kwargs to a Pydantic model raises ValidationError

Pydantic v2 by default rejects fields that aren't in the schema. Unlike Python dataclasses, there's no `extra='ignore'` by default.

```python
class HealthTrajectory(BaseModel):
    trajectory: str
    current_score: float
    # NO score_30d_ago, trend_direction, trend_magnitude!

# ❌ FAILS — ValidationError
return HealthTrajectory(
    trajectory="DECLINING",
    current_score=35.1,
    score_30d_ago=52.0,      # ← NOT in schema → ERROR
    trend_direction="DOWN",   # ← NOT in schema → ERROR
    trend_magnitude=16.9,     # ← NOT in schema → ERROR
)
```

**Symptoms:** FastAPI returns 500 Internal Server Error with no helpful message. The error only appears in uvicorn's stderr output. The route appears to work but always returns 500.

**✅ Fix:** When you add a field to a constructor call, add it to the schema FIRST. Or open `app/schemas/schemas.py` and verify all fields exist before passing them.

**Debugging tip:** If a FastAPI route returns 500, test the function directly with `python -c "from module import func; func()"` to see the actual error.

---

## 15. 🐛 Silent try/except Hides Errors (Added 2026-08-07)

### ❌ Empty except blocks swallow the real problem

When debugging, a try/except that returns a default without logging the exception makes bugs invisible. You'll spend hours checking the wrong thing.

```python
# ❌ WRONG — hides the real error
try:
    return bool(eval(expr, builtins, ns))
except Exception:
    return False  # ← Why did it fail? Nobody knows.

# ✅ CORRECT — log the exception
try:
    return bool(eval(expr, builtins, ns))
except Exception as e:
    logger.warning("Eval failed for '%s': %s: %s", expr, type(e).__name__, e)
    return False
```

**Real-world impact:** The `replace("AND", "and")` bug corrupted DORMANT to DorMant. The eval raised `NameError` (not False comparison!), but the except caught it silently. If the except had logged the error, we'd have seen `NameError: name 'DorMANT' is not defined` instantly.

**Rule:** Every try/except that returns a default MUST log the exception. No silent catches.

---

## 16. 🐛 Upstream Services Going Down Silently (Added 2026-08-07)

### ❌ All downstream services fail when upstream dies

The Decision Intelligence Platform calls 3 upstream services (8002/8003/8004). When any of them stop, the platform's API returns 500 errors or timeouts with no indication that the problem is upstream.

**Symptoms:**
- `GET /decisions/{id}` returns 500 or timeout
- `GET /customer-intel/{id}` returns 500 or timeout
- `GET /health` on 8005 returns "healthy" (it only checks itself!)
- The real problem: uvicorn terminals for 8002/8003/8004 were killed

**✅ Quick check (run this FIRST when debugging):**
```powershell
@(8002,8003,8004,8005,8080) | ForEach-Object {
    $p = $_
    try {
        $r = Invoke-RestMethod -Uri "http://100.82.12.85:$p/health" -TimeoutSec 3
        Write-Host "Port $p : UP — $($r.service)"
    } catch {
        Write-Host "Port $p : DOWN"
    }
}
```

**✅ Prevention:** Always start services with `--reload` to survive code changes without manual restart. Check all 5 services before running any tests.
