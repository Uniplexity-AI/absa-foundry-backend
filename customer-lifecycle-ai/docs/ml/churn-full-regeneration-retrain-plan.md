# Churn Model — Full Regeneration + Retrain (Option 1)

> **Status:** Planned — to be executed later
> **Date:** 2026-08-19
> **Companion:** `synthetic-data-forensic-investigation.md` (root-cause report this plan acts on)
> **Goal:** Validate the **entire** churn pipeline end-to-end on a single, consistent,
> behaviourally-driven synthetic dataset — the raw generator, the ~64-feature
> point-in-time SQL, the 3-date snapshot construction, and the customer-disjoint
> train/holdout split.

---

## 1. Why this option (and what it proves)

The forensic investigation concluded the model and feature SQL are **not** broken —
the data is. The three bug classes were:

1. **Label generation** — churn was randomly assigned and uncorrelated with behaviour.
2. **Snapshot construction** — the 07-17 snapshot was computed from a *different,
   sparser* transaction generation than 07-22/07-27 (the source of the PSI 9.51 "drift").
3. **Validation split** — the holdout shared customers with train (memorisation → 0.81 AUC).

Two of these are already fixed in code:
- `scripts/generate_synthetic_feature_store_data.py` now generates **behaviourally-driven
  churn** (`customers()` emits a `status` column with ~5% `Closed`; `transactions()`
  gives churned customers a 90+ day activity gap).
- `scripts/train_models.py` now uses a **customer-disjoint 80/20 split** + GroupKFold OOF
  + shared-bin PSI.

What remains is the **data** — the live `etl_clean` still holds the old, stale,
inconsistent generation (4,998 customers, 42 future-dated rows, an 11-year transaction
span, and a stale 07-17 snapshot). Option 1 wipes it and rebuilds from one consistent
generation, then retrains. It is the **only** option that exercises the real 64-feature
SQL and the 3-date point-in-time snapshot construction end-to-end (the 4-feature toy
experiment only proved the *training* code can learn when signal exists).

**Out of scope:** model hyperparameter tuning (deferred until the data is trustworthy),
real-data onboarding, and any change to the feature SQL / leakage guard.

---

## 2. Baseline to beat (current honest metrics)

Recorded from the last retrain against the *broken* data — these are the numbers that
must improve:

| Metric | Current (broken data) | Meaningful target |
|--------|----------------------|-------------------|
| Holdout AUC | 0.4737 | **> 0.70** (causal recency signal exists) |
| 5-fold OOF CV AUC | 0.4623 | **aligned with holdout (±0.05)** |
| LogLoss test / train | 0.6140 / 0.5819 | test ≈ train, no diverging gap |
| Accuracy @ optimal thr | 0.9000 | not a signal — class imbalance only |
| PSI (shared-bin) | ~0.35 | **< 0.10** (consistent snapshots) |
| Churn label ↔ behaviour | uncorrelated | **churned customers must be measurably inactive** |

---

## 3. Pipeline being validated (data flow)

```mermaid
flowchart LR
    G["generate_synthetic_feature_store_data.py<br/>(behavioural churn, run ONCE @ 07-27)"] --> R
    subgraph R["etl_clean — raw source tables"]
        C["customers_clean (status col)"]
        T["customer_transactions_clean"]
        A["accounts_clean / loans_clean / cards_clean"]
        D["digital_engagement_clean / demographics_clean"]
    end
    R --> M["customer_id_mapping"]
    R --> F["FeaturePipeline.run(as_of_date)<br/>Phase 1 SQL (repo.compute_batch) + 7 domain generators"]
    F --> FS["customer_features<br/>(~64 features × 3 as_of_date snapshots)"]
    FS --> S["seed_states.py → customer_states / state_transitions"]
    FS --> TR["train_models.py<br/>(customer-disjoint split, GroupKFold OOF, shared-bin PSI)"]
    TR --> MDL["models/champion/churn/ + models/registry.json"]
```

Key point-in-time invariant (enforced by the SQL in
`services/feature-engineering-service/app/repository/repository.py`):
**every feature computes `transaction_date <= as_of_date`**. The three snapshots
(07-17, 07-22, 07-27) must therefore be three views of the **same** transaction table,
not three separate generations.

---

## 4. Prerequisites / pre-flight

Run from `customer-lifecycle-ai` (project root). Interpreter is the project venv
(no `pip` inside it — use `uv pip install --python .venv` for any new dependency).

- [ ] PostgreSQL reachable at `localhost:5432`, databases `etl_clean` (target) and
      `etl_validation` (source) exist; user `postgres` / password from `.env`.
- [ ] `faker` present in venv (generator dependency — already installed, v40.36.0).
- [ ] `psycopg2`, `xgboost`, `sklearn`, `joblib` present (all used by training).
- [ ] `.env` present and correct (target DB = `etl_clean`).
- [ ] `git status` clean on branch `poc-90day` before starting (so a rollback is a
      `git` revert away — though data is not in git, so see §9).

---

## 5. Step-by-step plan

### Phase 0 — Snapshot & record baseline

1. Record the current honest metrics (table in §2) somewhere durable — they are the
   "before" numbers.
2. Dump the current feature store for forensic comparison if ever needed:
   ```
   .\.venv\Scripts\python.exe -c "import psycopg2; c=psycopg2.connect('postgresql://postgres:wamulehi@localhost:5432/etl_clean'); cur=c.cursor(); cur.execute('COPY (SELECT as_of_date, count(*), count(*) FILTER (WHERE rel_customer_status=''Closed'') FROM customer_features GROUP BY 1 ORDER BY 1) TO STDOUT WITH CSV'); print(cur.fetchall())"
   ```
   (Simpler: keep the existing `docs/ml/synthetic-data-forensic-investigation.md` as the record.)

### Phase 1 — Reset the affected tables

Truncate (or drop+recreate) everything downstream of the generator so no stale rows
survive. **Order matters** due to foreign keys.

```sql
-- in etl_clean
TRUNCATE customer_states, state_transitions RESTART IDENTITY CASCADE;
TRUNCATE customer_features RESTART IDENTITY CASCADE;
TRUNCATE customer_id_mapping RESTART IDENTITY CASCADE;
TRUNCATE customer_transactions_clean, customers_clean,
         accounts_clean, loans_clean, cards_clean,
         digital_engagement_clean, demographics_clean RESTART IDENTITY CASCADE;
```

- [ ] Confirm zero rows in all 9 tables after truncate.
- [ ] Keep DDL (tables, indexes, `customer_features` UNIQUE constraint) intact —
      the generator applies `CREATE TABLE IF NOT EXISTS` + `ADD COLUMN IF NOT EXISTS`
      and is safe to re-run over existing schema.

### Phase 2 — Regenerate raw data (ONE consistent generation)

Run the generator **once**, anchored to the latest snapshot date, loading into
`etl_clean`. ⚠️ The default `DATABASE_URL` points at `etl_validation` (the wrong DB),
so the URL **must** be passed explicitly:

```
.\.venv\Scripts\python.exe scripts/generate_synthetic_feature_store_data.py `
  --load --customers 5000 --as-of-date 2026-07-27 --seed 42 `
  --database-url postgresql://postgres:wamulehi@localhost:5432/etl_clean
```

Why once, anchored at 07-27: the 3 snapshots must see the **same** transaction history
(07-17 / 07-22 / 07-27 = three point-in-time views). The generator already produces a
0–180 day window; the churned-customer 90+ day gap guarantees an inactivity signal.

- [ ] Verify: `customers_clean` = 5,000 rows, ~250 (`5%`) with `status = 'Closed'`.
- [ ] Verify: `customer_transactions_clean` has **no** `transaction_date > 2026-07-27`
      and no 2035 rows (the old data had 42 future-dated rows).
- [ ] Verify: churned customers' `MAX(transaction_date)` is ≥ 90 days before 07-27.

### Phase 3 — Rebuild `customer_id_mapping`

The relationship generator joins accounts/loans/cards/engagement to features via
`customer_id_mapping(source_customer_id → features_customer_id)`. The generator now
emits a single uniform `CUST00001…CUST05000` format across all tables, so the mapping
is an identity join. Rebuild it:

```sql
INSERT INTO customer_id_mapping (source_table, source_customer_id, features_customer_id)
SELECT 'customers_clean', customer_id, customer_id FROM customers_clean;
```
(or reuse whatever insert produced the original 7,832-row mapping, adjusted to the
uniform ID format).

- [ ] Confirm `customer_features.customer_id` will equal the raw-table `customer_id`
      (no zero-padding mismatch), or the `RIGHT(id, 5)` join in
      `relationship/generator.py` will silently drop matches.

### Phase 4 — Run the feature pipeline for 3 dates

The canonical entry point is `FeaturePipeline.run(as_of_date)` (runs **Phase 1 SQL
`repo.compute_batch` + all 7 domain generators**). There is currently no 3-date loop —
`_run_generators.py` is hardcoded to 07-27 and *skips* Phase 1. **Create**
`scripts/run_full_pipeline_all_dates.py`:

```python
"""Run the full feature pipeline (Phase 1 + 7 generators) for all PoC snapshots."""
import sys, os
_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(_PROJ)
sys.path.insert(0, _PROJ)
sys.path.insert(0, os.path.join(_PROJ, "services", "feature-engineering-service"))

from datetime import date
from app.repository.repository import FeatureRepository
from app.pipelines.pipeline import FeaturePipeline

DATES = ["2026-07-17", "2026-07-22", "2026-07-27"]

repo = FeatureRepository()
for d in DATES:
    result = FeaturePipeline(repo).run(date.fromisoformat(d))
    print(f"{d}: {result['status']} — {result['stages']}")
    print(f"  quality: {result['quality']}")
```

Run it:

```
.\.venv\Scripts\python.exe scripts/run_full_pipeline_all_dates.py
```

- [ ] All 3 dates report `status=COMPLETED` (no `error` keys in stages).
- [ ] Quality check per date flags **0 dead features** (or only known-benign ones).
- [ ] `customer_features` has 3 × 5,000 rows; `_check_features.py` shows full population.

### Phase 5 — State engine seeding (optional but recommended)

Keep the state tables consistent with the new features (the state engine consumes
`rel_customer_status` and recency features):

```
.\.venv\Scripts\python.exe scripts/seed_states.py --as-of-date 2026-07-17
.\.venv\Scripts\python.exe scripts/seed_states.py --as-of-date 2026-07-22
.\.venv\Scripts\python.exe scripts/seed_states.py --as-of-date 2026-07-27
```

### Phase 6 — Data-quality gates (BLOCK retraining until all pass)

Run before training; these prove the fix actually fixed the data:

1. **Churn is behaviourally driven.** For each snapshot, churned (`Closed`) customers
   must differ from active on the *non-leaked* recency/frequency features:
   - `days_since_last_txn` (churned ≫ active) — note this feature is in `LEAKAGE_FEATURES`
     and is correctly excluded from training, but it must still be *correlated* with the
     label, otherwise the label has no behavioural meaning.
   - `txn_count_90d`, `txn_count_180d`, `total_amount_90d` lower for churned.
   - `engagement_score` lower for churned.
2. **Snapshots are consistent.** `avg_days_between_txn`, `txn_count_90d` means should
   drift smoothly (not step-change) across 07-17 → 07-22 → 07-27. Shared-bin PSI between
   consecutive snapshots should be **< 0.10**.
3. **No future-dated transactions** and no rows beyond the snapshot dates.
4. **Label distribution per snapshot** ≈ 5% `Closed`, static across snapshots but now
   *correlated* with inactivity (static labels + varying recency = realistic; the model
   learns the recency signal).
5. Re-run `scripts/analyze_leakage.py` to confirm no feature leaks the label.

> ⚠️ **Known nuance to verify at 07-17:** the generator anchors churned customers' gap
> at 90–181 days before 07-27, so at the 07-17 snapshot their inactivity is ~80–171 days.
> Active customers whose "recent" transactions fall in the 07-18..07-27 window may appear
> slightly less recent at 07-17. Confirm the churn/active separation is still clear at
> 07-17; if not, widen the generator gap to ≥ 120 days and regenerate.

### Phase 7 — Retrain

```
.\.venv\Scripts\python.exe scripts/train_models.py
```

The script already uses the customer-disjoint split, GroupKFold OOF, shared-bin PSI, and
now emits accuracy/loss metrics and plots (`loss_curve.png`, `accuracy_threshold.png`).

### Phase 8 — Validate results against success criteria (§6)

Check the log + `models/champion/churn/report.md` + PDF + `models/registry.json`:
- [ ] Holdout AUC > 0.70 (not 0.47).
- [ ] OOF CV AUC within ±0.05 of holdout AUC (no memorisation gap).
- [ ] `loss_curve.png`: train and holdout LogLoss both descend and do **not** diverge.
- [ ] Feature importance: recency/frequency/monetary features dominate, no label proxy.
- [ ] PSI (shared-bin) between snapshots < 0.10.
- [ ] Calibration curve and threshold analysis sane (no threshold collapse).

### Phase 9 — Commit & push

```
cd C:\Users\ADMIN\Desktop\uniplexity-ai\ABSA\absa-foundry-backend
git add -A
git commit -m "churn: full synthetic regeneration + retrain (behavioural churn, consistent snapshots)"
git push origin poc-90day
```

- [ ] Commit includes the new runner script, updated registry/report, and any generator
      tweaks. DB contents are **not** versioned — document the commands in §5 as the
      reproducible "data lineage".

---

## 6. Success criteria (quantified)

| # | Criterion | Pass threshold |
|---|-----------|----------------|
| S1 | Holdout AUC | > 0.70 (baseline 0.4737) |
| S2 | OOF ↔ holdout agreement | \|OOF − AUC\| ≤ 0.05 |
| S3 | Loss curve convergence | test & train LogLoss both ↓, no gap growth |
| S4 | Snapshot consistency | consecutive-snapshot shared-bin PSI < 0.10 |
| S5 | Behavioural churn | churned vs active differ on ≥ 3 non-leaked features |
| S6 | Data hygiene | 0 future-dated rows; 0 dead features |
| S7 | Leakage | `analyze_leakage.py` reports no label leak |

If S1–S4 pass, the pipeline is validated and work proceeds to real-data onboarding.
If S1 fails but S5 passes, the *model* needs revisiting (unlikely — the toy experiment
already proved the training code learns when signal exists).

---

## 7. Risks & mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Generator loaded into `etl_validation` (wrong DB) | pipeline sees old data | pass `--database-url` explicitly; verify row counts in `etl_clean` |
| `RIGHT(id,5)` join drops matches after ID format change | relationship features NULL | rebuild `customer_id_mapping` in Phase 3; assert feature population |
| 07-17 separation blur (gap anchored at 07-27) | weak signal in earliest snapshot | widen gap to ≥ 120 days (Phase 6 gate catches this) |
| `_run_generators.py` skips Phase 1 SQL | missing 16 transaction-aggregate features | use new `run_full_pipeline_all_dates.py` (runs `compute_batch`) |
| Overfit to static label via a non-leaked proxy feature | inflated AUC | S2 (OOF alignment) + feature-importance review in Phase 8 |
| Truncating tables with FK dependencies | constraint errors | `TRUNCATE ... CASCADE` in correct order (Phase 1) |

---

## 8. Rollback

Data is not in git. To return to the pre-regeneration state:
- If the old generation was dumped in Phase 0, reload it.
- Otherwise: regenerate is idempotent — the broken-data baseline can be reproduced by
  re-running the *old* ETL CSV import path, or simply re-accept the new data (the old
  data was known-broken and has little forensic value beyond the written report).

---

## 9. Files touched / created

| File | Action | Purpose |
|------|--------|---------|
| `scripts/run_full_pipeline_all_dates.py` | **create** | 3-date Phase-1+generator loop |
| `scripts/generate_synthetic_feature_store_data.py` | already fixed | behavioural churn (status + 90-day gap) |
| `scripts/train_models.py` | already fixed | customer-disjoint split, shared-bin PSI, accuracy/loss plots |
| `models/registry.json`, `models/champion/churn/*` | regenerated | new model + report + plots |
| `docs/ml/synthetic-data-forensic-investigation.md` | reference | baseline / root-cause record |

---

## 10. Execution checklist (one pass)

- [ ] Phase 0 — record baseline metrics
- [ ] Phase 1 — truncate 9 tables
- [ ] Phase 2 — regenerate once @ 07-27 into `etl_clean` (explicit URL)
- [ ] Phase 3 — rebuild `customer_id_mapping`
- [ ] Phase 4 — create + run `run_full_pipeline_all_dates.py` (3 × COMPLETED)
- [ ] Phase 5 — seed states for 3 dates
- [ ] Phase 6 — data-quality gates pass (churn↔behaviour, snapshot consistency, hygiene)
- [ ] Phase 7 — retrain
- [ ] Phase 8 — success criteria S1–S7
- [ ] Phase 9 — commit + push to `poc-90day`
