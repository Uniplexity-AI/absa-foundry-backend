# Frontend Functional Requirements — Decision Intelligence Module (Live Data Wiring)

**Audience:** Frontend team wiring the Decision Intelligence dashboard components to real backend data.
**Status:** Implemented and verified live (2026-08-27). Replaces the mock/fallback payloads previously served for these views.

---

## 1. Endpoints & Base URLs

All intelligence data is served through the API Gateway (`:8080`). Direct service access (`:8005`) exists for debugging only — **the frontend must use the gateway**.

| # | View | Gateway route (GET) | Backend service |
|---|------|--------------------|-----------------|
| 1 | Customer Value Intelligence | `/api/v1/intelligence/clv-summary` | Decision Intelligence (`:8005`) |
| 2 | AUM Balance Forecast | `/api/v1/intelligence/aum-forecast` | Decision Intelligence (`:8005`) |
| 3 | Business Outcomes & ROI Tracker | `/api/v1/intelligence/business-outcomes` | Decision Intelligence (`:8005`) |
| 4 | Lifecycle Prediction & Win-Back | `/api/v1/intelligence/lifecycle-summary` | Decision Intelligence (`:8005`) |

- Gateway base: `http://<host>:8080` (remote deployments use the Tailscale IP).
- Gateway timeout is 60s; expect **502** if the backend service is down and **504** if aggregation exceeds the timeout. Handle both with the existing error state UI.
- Response format: JSON, `Content-Type: application/json`. All money values are **decimal numbers (ZMW)**, *not* strings. Chart-ready series are in **millions** where noted.

---

## 2. Endpoint 1 — `GET /api/v1/intelligence/clv-summary`

**Query params**

| Param | Type | Required | Notes |
|---|---|---|---|
| `as_of_date` | ISO date (`YYYY-MM-DD`) | No | Defaults to the latest snapshot with data. Omit in normal use. |

**Response (verified live values)**

```json
{
  "as_of_date": "2026-07-27",
  "total_customers_scored": 4998,
  "bands": [
    { "band": "PLATINUM", "customer_count": 500,  "share_pct": 10.0 },
    { "band": "GOLD",     "customer_count": 750,  "share_pct": 15.0 },
    { "band": "SILVER",   "customer_count": 1249, "share_pct": 25.0 },
    { "band": "BRONZE",   "customer_count": 2499, "share_pct": 50.0 }
  ],
  "portfolio_value": {
    "total_clv": 606843947.85,
    "clv_at_risk": 312242.12,
    "at_risk_churn_threshold": 0.0507,
    "at_risk_threshold_source": "pilot_adaptive_p90",
    "value_protected_mtd": 25664.52
  },
  "model_versions": { "clv": "percentile_v1 (AUM-proxied magnitude)" },
  "data_sources": ["prediction-service:8004", "etl_clean.customer_features", "decision_outcomes"]
}
```

**Frontend wiring**

- `bands` → CLV band donut/stacked bar. `band` enum is **always** `PLATINUM | GOLD | SILVER | BRONZE`, in that order. Use `share_pct` for labels; `customer_count` for tooltips.
- `portfolio_value.total_clv` / `clv_at_risk` / `value_protected_mtd` → the three summary cards. Format as `ZMW 606.8M` / `ZMW 312.2K`.
- `at_risk_churn_threshold` + `at_risk_threshold_source` are **diagnostic fields** — render only in a "model info" tooltip, never in the primary cards. `at_risk_threshold_source` enum: `spec` (production) or `pilot_adaptive_p90` (pilot-only fallback; show an "Advisory" tag when this value appears).
- Empty portfolio (no scored data): `total_customers_scored = 0`, all band counts `0`. Render the empty state; do not treat as an error.

---

## 3. Endpoint 2 — `GET /api/v1/intelligence/aum-forecast`

**Query params**

| Param | Type | Required | Notes |
|---|---|---|---|
| `as_of_date` | ISO date | No | Defaults to latest snapshot. |
| `horizon_days` | int | No | Default `90`. Constraints: `7–365`. Weeks = `horizon_days / 7`. |

**Response (12-week default)**

```json
{
  "as_of_date": "2026-07-27",
  "horizon_days": 90,
  "current_aum": 606843947.85,
  "scenarios": {
    "optimistic":  [605.4, "…12 values"],
    "base":        [604.2, 601.6, 599.0, "…"],
    "pessimistic": [603.0, "…12 values"]
  },
  "labels": ["Wk 1 (2026-08-03)", "Wk 2 (2026-08-10)", "…"],
  "method": "Deterministic churn-decay projection: AUM_i x (1 - P(churn_i))^t per scenario band (±2pp churn), weekly intervals.",
  "customers": 4998
}
```

**Frontend wiring**

- Line chart with 3 series. Scenario keys are **always** `optimistic | base | pessimistic` — use those keys, not array order.
- **Series values are in millions** (e.g. `604.2` = ZMW 604.2M). `current_aum` is in **absolute ZMW** — divide by 1e6 before plotting it on the same axis.
- `labels` pair with series index 1:1; each label embeds the ISO week-end date — use it for the x-axis tooltip, display the `Wk n` part on the axis.
- All three series start from the same portfolio total; the first-week values may look nearly identical — that is correct behavior (±2pp churn compounding weekly).

---

## 4. Endpoint 3 — `GET /api/v1/intelligence/business-outcomes`

**Query params:** none.

**Response (verified live values)**

```json
{
  "roi": {
    "revenue_protected": 2020586.71,
    "intervention_cost": 47252.05,
    "net_roi_pct": 4176.2,
    "roi_multiple": 42.76
  },
  "retention_performance": [
    {
      "branch_id": "B005", "pilot": true,
      "interventions": 63, "accepted": 41, "retained_90d": 23,
      "revenue_protected": 284354.6, "intervention_cost": 6120.4
    }
  ],
  "pilot_vs_control": {
    "pilot":   { "branches": 6, "interventions": 371, "acceptance_rate_pct": 65.2, "retention_rate_pct": 77.5, "revenue_protected": 284354.6, "intervention_cost": 30208.14 },
    "control": { "branches": 2, "interventions": 129, "acceptance_rate_pct": 41.1,  "retention_rate_pct": 50.0,  "revenue_protected": 41173.04, "intervention_cost": 9843.91 }
  },
  "data_sources": ["etl_clean.decision_outcomes"]
}
```

**Frontend wiring**

- `roi` → headline ROI card: `net_roi_pct` (display as `%`), `roi_multiple` (display as `x`, e.g. `42.8x`), `revenue_protected` and `intervention_cost` as ZMW amounts.
- `retention_performance` → branch table. `pilot` is a **boolean** — render a Pilot/Control badge from it. `retained_90d` counts only customers whose 90-day window has elapsed; interventions younger than 90 days are excluded from retention math by design.
- `pilot_vs_control` → the comparison panel. `pilot` and `control` objects are **always present** (zeros when a group has no data — render `0` / `—`, not an error). Rates are already percentages with 1 decimal; do not re-multiply.

---

## 5. Endpoint 4 — `GET /api/v1/intelligence/lifecycle-summary`

**Query params**

| Param | Type | Required | Notes |
|---|---|---|---|
| `as_of_date` | ISO date | No | Defaults to latest snapshot. |

**Response (verified live values)**

```json
{
  "as_of_date": "2026-07-27",
  "state_counts": { "CHURNED": 290, "DORMANT": 2417, "AT_RISK": 2291 },
  "transition_matrix": {
    "states": ["NEW", "ACTIVE", "GROWING", "AT_RISK", "DORMANT", "CHURNED"],
    "matrix": [[0,0,0,0,0,0], [0,0,0,277,0,0], ["…"]],
    "window_days": 30
  },
  "winback_pipeline": {
    "churned_total": 200,
    "eligible": 119,
    "top_candidates": [
      {
        "customer_id": "CUST00473",
        "value_180d": 1940098.32,
        "churned_on": "2026-07-27",
        "months_churned": 0.0,
        "winback_probability": 0.995,
        "status": "ELIGIBLE"
      }
    ],
    "method": "winback_probability from Prediction Service model | pilot proxy: cohort-relative 180d value percentile x recency decay (no winback model yet)"
  }
}
```

**Frontend wiring**

- `state_counts` → lifecycle distribution. Keys are a **subset** of `NEW | ACTIVE | GROWING | AT_RISK | DORMANT | CHURNED` — only states with ≥1 customer appear. Iterate the canonical `transition_matrix.states` order for display and default missing states to `0`.
- `transition_matrix.matrix[i][j]` = moves from `states[i]` to `states[j]` over the trailing `window_days` (30). Heat-map cells: `null`-safe — indices always align with `states`. Row = from, column = to.
- `winback_pipeline.top_candidates` → ranked win-back list (max 25 rows). `status` enum: `ELIGIBLE | INELIGIBLE` (eligibility = churned ≤ 6 months AND winback_probability > 0.40). `winback_probability` is `0–1` — multiply by 100 for display. `value_180d` appears only in the pilot-proxy mode (absent when the real model lands); treat it as optional in types.
- `churned_total` is capped at the 200 most recent — display "top 200" if `churned_total == 200`.

---

## 6. Cross-cutting requirements

1. **Caching / polling:** the backend caches each aggregation for **120 seconds**. Poll at ≥120s intervals or refresh on user action; more frequent polling returns identical cached payloads.
2. **Field stability:** fields documented here are the contract. `at_risk_threshold_source`, `model_versions`, `data_sources`, and `method` are diagnostic/advisory metadata — the frontend must tolerate their absence and must not branch business logic on them.
3. **Degraded mode:** if an upstream dependency fails, endpoints still return **200** with reduced data (e.g. `total_customers_scored: 0`, empty bands, `as_of_date: null`). Render empty/zero states rather than surfacing errors, except for gateway `502/504`.
4. **Date semantics:** `as_of_date` is the ETL snapshot date, *not* "today". Display it as "Data as of …" in every view header.
5. **Money formatting:** absolute ZMW amounts (cards, tables); millions for forecast series only.
6. **Types:** all numeric fields are JSON numbers (some may serialize as `0`); `pilot` is boolean; dates are ISO strings.

---

## 7. Pilot-vs-production notes (backend-managed, frontend-transparent)

The backend currently fills three data gaps with disclosed stand-ins; each switches to the production source via backend configuration **without any frontend change**:

| Gap | Pilot stand-in | Production source |
|---|---|---|
| AUM per customer | 90-day transaction volume | Real balance/AUM column (backend env) |
| Win-back probability | Cohort-relative 180d value × recency decay | Prediction Service winback model (auto-detected) |
| At-risk cutoff | Adaptive p90 (disclosed via `at_risk_threshold_source`) | Spec threshold 0.50 |

The frontend contract (field names, types, enums, shapes above) is stable across that switchover.
