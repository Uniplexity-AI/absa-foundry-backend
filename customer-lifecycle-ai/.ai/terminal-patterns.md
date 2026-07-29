# Terminal & Tool Patterns — Lessons Learned

> **Purpose:** Document recurring issues encountered when running scripts, terminal commands, and edits in this workspace so they aren't repeated.
> **Last updated:** 2026-07-29
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

---

## 1. PowerShell Terminal Patterns

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

### ❌ Port 8004 "already in use"

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

## 2. `replace_string_in_file` Patterns

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

## 3. File Creation Patterns

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

## 4. Database Patterns

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
