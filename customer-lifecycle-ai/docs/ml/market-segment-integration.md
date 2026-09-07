# Bank Market-Segment Integration

> **BANK-PROVIDED BUSINESS LOGIC.** The market-segment mapping is authoritative
> source/master data supplied by the bank. It must **not** be modified or
> re-derived by the ML system without bank/business-owner confirmation.
>
> | Metadata | Value |
> |---|---|
> | Name | `bank_market_segment_mapping` |
> | Source | Bank customer master |
> | Source field | `market_segment_code` |
> | Version | **TBD / Not provided** |
> | Effective date | **TBD / Not provided** |
> | Owner | **TBD / Not provided** |
> | Change procedure | TBD — escalate to bank data governance |
> | Status | 2026-09-02 · Synthetic dev integration (pilot-ready, no data modified) |

---

## 1. Authoritative Mapping

Single source of truth: `shared/constants/market_segments.py`
(no duplicated SQL CASE / dict / API mapping).

| `market_segment_code` | `market_segment` | Meaning |
|---|---|---|
| 30 | `CIB` | Corporate & Investment Banking |
| 40 | `BB` | Business Banking |
| 45 | `SME` | Small & Medium Enterprise |
| 50 | `Enterprise` | Enterprise |
| 60 | `Prestige` | Prestige |
| 65 | `Personal` | Personal |
| 75 | `Mass` | Mass |
| 85 | `Premier` | Premier |
| 90 | `Staff` | Staff |
| 99 | `Internal` | Internal |
| anything else / NULL / blank / non-numeric | `Other` | Unmapped / other |

**NULL / missing handling (documented decision, spec §10):** any missing, blank,
non-numeric, or unknown code resolves deterministically to `Other`; the original
raw source value is **preserved** in `market_segment_code` and is observable for
data-quality monitoring (`unknown_market_segment_count` / `..._rate` via
`is_unknown()`). Nothing is silently discarded.

---

## 2. Where the field enters & how it flows

```
Bank customer master (market_segment_code)
        │
        ▼
customers_clean.market_segment_code   ← raw code preserved (migration 010)
        │
        ▼
customer_features.market_segment_code  ← copied by CustomerProfileGenerator
customer_features.market_segment       ← resolved via shared mapping (Python)
        │
        ▼
Analytics / ML feature pipeline        ← downstream contract unchanged
```

- **Entry point:** `customers_clean.market_segment_code` (nullable, additive —
  existing synthetic rows are untouched; they have NULL until real bank data).
- **Transformation:** `services/feature-engineering-service/app/features/customer/generator.py`
  Stage-1 copies the code; Stage-1b resolves the label in Python via the single
  authoritative module. **No SQL CASE is introduced.**
- **Reach:** `customer_features` carries both `market_segment_code` (raw) and
  `market_segment` (label). Existing `customer_segment` (from `customer_type`)
  semantics are **left untouched** for backward compatibility (see §4).

---

## 3. Code / schema changes

| File | Change | Reason |
|---|---|---|
| `shared/constants/market_segments.py` *(new)* | Authoritative map + `resolve_market_segment`, `is_official_code`, `is_unknown`, metadata | Single source of truth; deterministic, auditable |
| `shared/constants/__init__.py` *(new)* | Package init | Importable as `shared.constants.market_segments` |
| `database/migrations/010_market_segment.sql` *(new)* | Add nullable `market_segment_code`/`market_segment` to `customers_clean` + `customer_features`; `market_segment_code` on `demographics_clean` (guarded by `to_regclass`) | Carry bank field into clean + feature layers; idempotent/additive |
| `scripts/pilot_migrate.py` | Register `010_market_segment.sql` | Pilot DB applies the columns |
| `services/feature-engineering-service/app/features/customer/generator.py` | Copy `market_segment_code`; resolve `market_segment` label in Python | Deterministic label into feature store; single mapping |
| `services/feature-engineering-service/app/schemas/schemas.py` | Add `market_segment_code`, `market_segment` fields | API snapshot can expose the new fields |
| `tests/test_market_segments.py` *(new)* | 24 mapping/NULL/unknown/lineage tests | Spec §11 acceptance |

### Schema changes (summary)
- `customers_clean`: `market_segment_code VARCHAR(16) NULL`, `market_segment VARCHAR(32) NULL`
- `customer_features`: `market_segment_code VARCHAR(16) NULL`, `market_segment VARCHAR(32) NULL`
- `demographics_clean`: `market_segment_code VARCHAR(16) NULL` (applied only if table exists)

All columns are `NULL` on existing rows — **no existing synthetic data rewritten**.

---

## 4. Compatibility assessment — existing `customer_segment`

| Question | Finding |
|---|---|
| Where does `customer_segment` come from? | Copied from `customers_clean.customer_type` in the FE profile generator (`generator.py`). |
| Is it synthetic? | The synthetic generator does **not** emit `customer_type`, so `customer_segment` is NULL on synthetic feature rows today (a known pre-existing data-drift gap). |
| Inferred or assigned? | Explicitly assigned by ETL/feature copy from the customer master field (bank `market_segment` → `customer_type` alias in ETL specs). |
| Encoding | Text (VARCHAR). |
| Model expectation | Listed in `registry.json` training features; at train/inference non-numeric strings collapse to `0.0` via `_safe_float`, so it currently contributes ~no signal. |
| Downstream API dependency | Yes — state portfolio CLV-summary groups by `customer_segment`; decision context falls back `customer_segment` → `"MASS_MARKET"`. |
| Impact of renaming/removing | Would break FE generator tests (assert `Retail`/`Corporate`), state portfolio grouping, and decision-context fallback. |

**Decision:** `customer_segment` is **retained unchanged** (backward compatible).
The new **`market_segment`** field is additive and is the bank-authoritative
normalised representation. Reconciliation of the legacy `customer_segment`/
wealth taxonomy with the bank's authoritative segments is a **pilot design item**,
not done here.

---

## 5. ML impact analysis (evaluated, not assumed)

- `market_segment` / `market_segment_code` are **available as candidate features**
  but were **not added to the training feature list** and **no model was retrained**
  or promoted as part of this integration.
- Because all synthetic rows have NULL `market_segment_code`/`market_segment`,
  adding them to training now would be a constant/missing feature — no value, and
  it would only mask the synthetic-vs-bank distribution gap.
- **Leakage status:** not leakage when the code is available at prediction time
  (source master data, not a label-derived value). Final verification required
  once the real pilot feature timeline is confirmed (spec §15).

**Governance row (feature metadata):**

| Field | Value |
|---|---|
| feature_name | `market_segment` |
| source | Bank customer master |
| source_field | `market_segment_code` |
| business_definition | Bank market-segment classification |
| transformation | Deterministic bank-provided mapping (`shared.constants.market_segments`) |
| allowed_values | CIB, BB, SME, Enterprise, Prestige, Personal, Mass, Premier, Staff, Internal, Other |
| availability_timestamp | TBD (real pilot) |
| data_owner | TBD / Not provided |
| ML_usage | Candidate feature — not yet in training feature list |
| leakage_status | Not leakage if available at prediction time (verify at pilot) |

---

## 6. Staff / Internal segments — flag for business-owner review

Codes `90 → Staff` and `99 → Internal` represent operationally distinct
populations. **No business decision is made here.** Technical implications to
confirm with the bank/business owner:

- Should Staff/Internal participate in churn scoring?
- Should they be excluded from customer-facing interventions?
- Should they be separately monitored / require special governance?

(Spec §14 — flagged, not decided.)

---

## 7. Data lineage path

A reviewer can answer *"why was this customer classified as SME?"*:

```
Customer
  └─ market_segment_code = 45            (raw, preserved in customers_clean + customer_features)
      └─ bank mapping (shared/constants/market_segments.py)
          └─ market_segment = 'SME'      (deterministic)
              └─ feature vector → model prediction (future pilot)
source = bank customer data
transformation = bank-provided deterministic mapping (v TBD / Not provided)
```

---

## 8. Synthetic data integrity — explicit confirmation

- ✅ Synthetic customer records were **NOT** modified.
- ✅ Synthetic churn labels were **NOT** modified (`rel_customer_status` untouched).
- ✅ Synthetic transactions were **NOT** modified.
- ✅ Synthetic behaviour was **NOT** modified.
- ✅ No existing model artifact was silently changed; no model retrained/promoted.

The synthetic dataset simply has no bank market-segment field, so these columns
are NULL. When real bank data arrives, the observed segment distribution should
be compared to synthetic expectations as a **pilot data-quality / domain-shift
finding** — not "fixed" by editing synthetic data (spec §16).

---

## 9. Pilot readiness — what must happen with real bank data

1. Land `market_segment_code` into `customers_clean.market_segment_code`
   (bank ETL/file load) — migration `010` already provides the column.
2. Run the feature pipeline — `CustomerProfileGenerator` copies the code and
   resolves `market_segment` label deterministically.
3. Fill in mapping metadata (version / effective date / owner) once the bank
   provides it (currently TBD).
4. Run data-quality monitors: `unknown_market_segment_count/rate`, per-segment
   population vs bank expectation.
5. Decide Staff/Internal treatment with the business owner (§6).
6. Only then evaluate adding `market_segment` to training via the existing
   model-validation / feature-governance process (spec §12, §15) — **no
   automatic retrain/promotion**.

---

## 10. Tests

`pytest tests/test_market_segments.py -q` → **24 passed** (all official codes,
unknown/NULL/blank/non-numeric → `Other`, code preservation, normalised pairing).
