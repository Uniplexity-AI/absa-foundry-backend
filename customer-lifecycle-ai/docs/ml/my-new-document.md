# Functional Requirements: Intelligence Module Backend APIs

**Date:** 2026-08-27
**Target Audience:** Backend Developers (Feature Engineering, Prediction, Decision Intelligence services)
**Frontend Pages:**
- Customer Value Intelligence (`/dashboard/customer-value`)
- Balance Forecast (`/dashboard/balance-forecast`)
- Business Outcomes & ROI (`/dashboard/business-outcomes`)
- Customer Lifecycle Prediction (`/dashboard/lifecycle`)

---

## 1. Overview & Objectives

This document outlines the functional requirements for new and updated backend APIs to support the Intelligence Module in the frontend. The primary goal is to provide rich, data-driven insights into customer value, lifecycle prediction, financial forecasting, and business performance metrics.

The backend needs to expose data through the API Gateway (`:8080`) that feeds these frontend pages, integrating with existing services (Feature Engineering `[:8002]`, Customer State `[:8003]`, Prediction `[:8004]`, Decision Intelligence `[:8005]`).

---

## 2. General API Requirements

-   All new endpoints should be exposed via the **API Gateway** (`:8080`).
-   Authentication and RBAC must be enforced (e.g., `DATA_SCIENTIST`, `BRANCH_MANAGER`, `RELATIONSHIP_MANAGER`).
-   Responses should be JSON.
-   All `as_of_date` parameters should default to the current date if not provided.
-   Error handling should return meaningful HTTP status codes and messages (e.g., 404 for not found, 500 for internal errors).

---

## 3. Frontend Page: Customer Value Intelligence (`/dashboard/customer-value`)

**Description:** This page provides a portfolio-level view of customer value, including CLV scoring, value segmentation (Platinum, Gold, Silver, Bronze), churn-adjusted priority analysis, and a Priority Matrix (CLV vs. Churn Probability).

### 3.1. API Endpoints

#### 3.1.1. `GET /api/v1/intelligence/clv-summary`

*   **Purpose:** Provide aggregate CLV metrics for the entire portfolio.
*   **Service:** Decision Intelligence Service (`:8005`) - Needs to aggregate CLV data from the Prediction Service.
*   **Parameters:**
    *   `as_of_date: date` (Query, Optional)
*   **Expected Response (JSON):**
    ```json
    {
      "total_clv": 7980000000.00, // Total churn-adjusted CLV for the portfolio
      "avg_customer_clv": 41280.00, // Average CLV per customer
      "platinum_gold_count": 1500, // Count of Platinum + Gold customers
      "clv_at_risk": 312000000.00, // CLV of high-value, high-churn customers
      "value_protected_mtd": 48600000.00, // Value protected Month-to-Date via interventions
      "churn_adjusted_clv": 7980000000.00, // Total expected realised value
      "bands": [ // CLV distribution by value band
        {
          "band": "Platinum",
          "threshold": "> 90%ile",
          "count": 500,
          "pct": 10.0,
          "avg_clv": 200000.00,
          "avg_churn_prob": 0.05,
          "total_aum": 100000000.00,
          "at_risk_count": 50
        },
        // ... Gold, Silver, Bronze bands
      ],
      "top_customers": [ // Top 10 customers by CLV (for scatter plot table)
        {
          "customer_id": "CUST00001",
          "name": "Customer 00001",
          "segment": "MASS_AFFLUENT",
          "clv": 250000.00,
          "churn_prob": 0.05,
          "churn_confidence": "\u00b1 0.02",
          "churn_drivers": ["INACTIVE_EXTENDED", "LOW_ENGAGEMENT"],
          "band": "Platinum"
        }
      ]
    }
    ```

### 3.2. Data Requirements & Logic

*   **CLV Calculation:** The Prediction Service already exposes `clv_percentile` per customer. The Decision Intelligence Service will need to map these percentiles to value bands (Platinum, Gold, Silver, Bronze) and aggregate total/average CLV.
*   **Churn-adjusted:** Use `churn_probability` from the Prediction Service to weight CLV for "at risk" calculations.
*   **Value Protected:** Requires tracking of `DECISION_OUTCOMES` where interventions (e.g., FEE_WAIVER, LOYALTY_REWARD) resulted in customer retention. This implies a need for a `DecisionMemory` or `OutcomeRepository` in the Decision Intelligence Service.
*   **Top Customers:** Retrieve customers with their `clv_percentile` and `churn_probability` from the Prediction Service, along with their segment from the Feature Engineering Service.
*   **Quadrant Mapping:** The frontend performs quadrant mapping (PROTECT, MAINTAIN, MONITOR, OBSERVE). The backend should provide the raw CLV and Churn Probabilities.

---

## 4. Frontend Page: Balance Forecast (`/dashboard/balance-forecast`)

**Description:** This page provides a portfolio-level forecast of Assets Under Management (AUM) under different churn scenarios (optimistic, base, pessimistic), including confidence intervals and segment-level breakdowns.

### 4.1. API Endpoints

#### 4.1.1. `GET /api/v1/intelligence/aum-forecast`

*   **Purpose:** Provide portfolio-level AUM forecast data for various churn scenarios and a specific horizon.
*   **Service:** Decision Intelligence Service (`:8005`) - Needs to integrate with the Prediction Service for churn probabilities and potentially a dedicated "Forecast Engine."
*   **Parameters:**
    *   `as_of_date: date` (Query, Optional)
    *   `horizon_days: int` (Query, Default: 90)
*   **Expected Response (JSON):**
    ```json
    {
      "current_aum": 4570000000.00, // Current AUM
      "base_scenario_aum_90d": 4300000000.00, // Projected AUM for base churn in 90 days
      "aum_at_risk": 274000000.00, // Delta between current and base scenario
      "best_case_aum_90d": 4780000000.00, // Projected AUM if churn improves by 2pp
      "forecast_labels": ["Wk 1", "Wk 2", ...], // Labels for the time series chart
      "scenarios": {
        "optimistic": [4.57, 4.60, ...], // Optimistic AUM trajectory (in Billions)
        "base": [4.57, 4.54, ...],       // Base AUM trajectory (in Billions)
        "pessimistic": [4.57, 4.51, ...]  // Pessimistic AUM trajectory (in Billions)
      },
      "ci_checkpoints": [ // Confidence Interval Checkpoints
        { "label": "Current",  "p10": 4.57, "base": 4.57, "p90": 4.57 },
        { "label": "Month 1",  "p10": 4.45, "base": 4.49, "p90": 4.53 },
        // ... Month 2, Month 3
      ],
      "by_segment": [ // AUM forecast breakdown by segment
        {
          "segment": "Prestige",
          "current_aum": 1820000000.00,
          "projected_remaining": 1720000000.00,
          "aum_at_risk": 100000000.00,
          "projected_exits": 412,
          "pct_change": -5.5
        }
        // ... other segments
      ],
      "sensitivity": [ // Churn Sensitivity Analysis
        {
          "scenario": "Very Low Churn",
          "churn_assumption": "3.0% / mo",
          "projected_aum": 4780000000.00,
          "delta": 210000000.00,
          "pct_change": 4.6,
          "is_base": false
        }
        // ... other scenarios
      ]
    }
    ```

### 4.2. Data Requirements & Logic

*   **Forecast Engine:** A new "Forecast Engine" (within Decision Intelligence or a dedicated service) is required to simulate AUM trajectories under different churn assumptions (optimistic, base, pessimistic). This would likely involve Monte Carlo simulations of customer churn and value.
*   **Current AUM:** Needs to retrieve total AUM for the portfolio, likely from the Feature Engineering Service or a dedicated Data Warehouse component.
*   **Churn Scenarios:** The forecast engine needs to model different churn rates (e.g., base churn from Prediction Service, \u00b1 X% for optimistic/pessimistic).
*   **Confidence Intervals:** Monte Carlo simulation is explicitly mentioned for 80% CI (P10-P90).
*   **Segment Breakdown:** The forecast needs to be disaggregated by customer segment. This requires segment information (from Feature Engineering) and segment-specific churn/value models/assumptions.

---

## 5. Frontend Page: Business Outcomes & ROI (`/dashboard/business-outcomes`)

**Description:** This page tracks the business value generated by AI interventions, including revenue protected, customers retained, intervention costs, and Net ROI. It also tracks success criteria against agreed targets and compares pilot branches vs. control branches.

### 5.1. API Endpoints

#### 5.1.1. `GET /api/v1/intelligence/business-outcomes`

*   **Purpose:** Provide key ROI metrics, retention performance by branch, success criteria tracking, and pilot vs. control group comparison.
*   **Service:** Decision Intelligence Service (`:8005`) - Needs to pull data from `DecisionMemory` / `OutcomeRepository`, and potentially integrate with a `MonitoringService` or `AnalyticsService`.
*   **Parameters:** (None specified in frontend, but `as_of_date` or `period` could be useful)
*   **Expected Response (JSON):**
    ```json
    {
      "roi": {
        "revenue_protected": 48600000.00,
        "customers_retained": 1284,
        "intervention_cost": 3200000.00,
        "net_roi_pct": 1418.0,
        "system_roi_multiple": 15.2,
        "trend": [ // Monthly trend for revenue protected
          { "month": "Feb", "revenue": 3200000 },
          // ... up to current month
        ]
      },
      "retention_performance": [ // By branch/entity
        {
          "entity": "Sandton City",
          "at_risk": 312,
          "contacted": 290,
          "retained": 218,
          "churned_despite": 72,
          "revenue_protected": 8400000.00,
          "retention_rate": 75
        }
        // ... other branches
      ],
      "success_criteria": [ // Tracker against targets
        {
          "criterion": "Reduce monthly portfolio churn rate from 6.8% to below 6.0% within 90 days...",
          "target": "< 6.0%",
          "current": "5.1%",
          "delta": "-0.9pp",
          "status": "MET"
        }
        // ... other criteria
      ],
      "pilot_vs_control": {
        "pilot_branches": {
          "branches_count": 6,
          "monthly_churn": 0.051,
          "retention_rate": 0.74,
          "aum_change_pct": -0.012,
          "rm_contacts_per_month": 28
        },
        "control_branches": {
          "branches_count": 7,
          "monthly_churn": 0.078,
          "retention_rate": 0.58,
          "aum_change_pct": -0.048,
          "rm_contacts_per_month": 11
        },
        "comparison_metrics": [ // Table for comparison
          { "metric": "Monthly Churn Rate", "pilot": "5.1%", "control": "7.8%", "delta": "-2.7pp", "significance": "p < 0.05" }
          // ... other metrics
        ]
      }
    }
    ```

### 5.2. Data Requirements & Logic

*   **ROI Metrics:** Requires tracking of actions taken (`TakeAction.vue` saves to local storage, but needs backend persistence) and their outcomes (accepted/declined, actual revenue, product adopted). The Decision Intelligence Service would need to query its `DecisionMemory` or an `OutcomeRepository` to aggregate this.
*   **Intervention Cost:** Needs a way to define and track costs associated with different interventions (e.g., campaign costs, RM time). This could be configurable in the Decision Intelligence Service.
*   **Customers Retained:** Based on linking interventions to subsequent customer behavior (e.g., not churning within X days after intervention).
*   **Retention Performance by Branch:** Requires customer data (including branch info from Feature Engineering), intervention data, and churn outcomes.
*   **Success Criteria Tracker:** A configurable list of success criteria with current status, target, and delta. This could be managed within the Decision Intelligence Service's configuration.
*   **Pilot vs. Control:** Requires a mechanism to identify pilot vs. control branches (e.g., a branch configuration in Feature Engineering or Decision Intelligence) and aggregate all the above metrics separately for each group. Statistical significance testing for delta values.

---

## 6. Frontend Page: Customer Lifecycle Prediction (`/dashboard/lifecycle`)

**Description:** This page visualizes portfolio-level customer lifecycle stage distribution, transition analysis (heatmap), onboarding health, and a win-back pipeline for churned customers.

### 6.1. API Endpoints

#### 6.1.1. `GET /api/v1/intelligence/lifecycle-summary`

*   **Purpose:** Provide portfolio-level lifecycle stage distribution, transition matrix, onboarding health metrics, and win-back pipeline data.
*   **Service:** Decision Intelligence Service (`:8005`) - Needs to integrate with Customer State Service (`:8003`) for state data and Markov matrices, and potentially Prediction Service for win-back probabilities.
*   **Parameters:**
    *   `as_of_date: date` (Query, Optional)
*   **Expected Response (JSON):**
    ```json
    {
      "distribution": [ // Lifecycle stage distribution
        {
          "stage": "NEW",
          "label": "New Customers",
          "count": 500,
          "pct": 10.0,
          "mom_delta": 50, // Month-over-month delta
          "color": "text-green-500" // Tailwind class
        },
        // ... ACTIVE, GROWING, AT_RISK, DORMANT, CHURNED
      ],
      "transitions": { // Stage transition heatmap data
        "stages": ["NEW", "ACTIVE", "GROWING", "AT_RISK", "DORMANT", "CHURNED"],
        "matrix": [ // 2D array of transition counts
          [0, 50, 0, 0, 0, 0],
          [0, 200, 30, 20, 0, 0],
          // ...
        ]
      },
      "onboarding": { // Onboarding health metrics
        "total_new": 1000,
        "activated_30d": 750,
        "activated_60d": 800,
        "activated_90d": 850,
        "early_at_risk": 50,
        "avg_products": 1.5,
        "digital_enrolled": 70
      },
      "win_back": [ // Win-back pipeline for churned customers
        {
          "customer_id": "CUST00101",
          "name": "Customer 00101",
          "last_product": "Personal Loan",
          "months_churned": 3,
          "prob": 0.75, // Win-back probability
          "est_value": 15000.00, // Estimated value if won back
          "status": "ELIGIBLE" // ELIGIBLE, IN_CAMPAIGN, WON_BACK, LOST
        }
        // ... other churned customers
      ]
    }
    ```

### 6.2. Data Requirements & Logic

*   **Stage Distribution:** Requires portfolio-level counts and percentages for each lifecycle state. The Customer State Service already provides `/states/portfolio`. The Decision Intelligence Service needs to augment this with MoM deltas.
*   **Stage Transitions (Heatmap):** Needs historical state data to compute transitions between stages over a period (e.g., last 30 days). The Customer State Service stores state history in `customer_states` and `state_transitions`. Decision Intelligence needs to query this to build the matrix.
*   **Onboarding Health:** Requires historical data on new customers, their activation dates (first transaction, first login, product activation), product holdings, and early risk flags. This likely involves querying Feature Engineering data over time.
*   **Win-Back Pipeline:** Requires a list of churned customers (`customer_states`), their win-back probability (new model in Prediction Service or heuristic in Decision Intelligence), and estimated value (from CLV).
    *   **Win-back Probability Model:** A new model might be needed in the Prediction Service, or a heuristic can be developed in the Decision Intelligence Service, to predict the likelihood of winning back a churned customer. This would use features like months since churn, last product, and historical engagement.

---

## 7. Backend Implementation Notes

*   **Prediction Service (`:8004`)**:
    *   Needs to be updated to provide win-back probabilities (either a new model or exposing existing data for heuristic derivation).
*   **Decision Intelligence Service (`:8005`)**:
    *   This service will act as the primary aggregator and orchestrator for all these new intelligence APIs.
    *   It will query Feature Engineering (`:8002`), Customer State (`:8003`), and Prediction (`:8004`) services.
    *   It will contain the business logic for calculating CLV value bands, AUM forecasts, ROI metrics, and win-back eligibility.
    *   **New Components:** Consider dedicated internal components like `ForecastEngine`, `OutcomesAnalyzer`, `WinbackPipelineEngine` within the Decision Intelligence Service.
    *   **Persistence:** Some metrics (e.g., Value Protected, Success Criteria) will need to be persisted, either in a dedicated `intelligence_metrics` table or within the `DecisionMemory`/`OutcomeRepository`.
    *   **Configuration:** All thresholds, weights, and criteria (e.g., for CLV bands, SLA targets) should be configurable (e.g., via YAML files or database settings).
*   **Feature Engineering Service (`:8002`)**:
    *   Ensure all necessary historical data (transaction, balance, product, engagement) is available and easily queryable for time-series analysis (e.g., AUM trends, activation funnels).
    *   May need new features or aggregations to support the calculations (e.g., average product holdings for new customers).

---

## 8. Frontend `useIntelligenceStore`

The frontend already has `useIntelligenceStore` which currently fetches data from mock/fallback data. This store will be updated to call the new backend endpoints.

---

This document provides a detailed breakdown of the functional requirements. Please review and let me know if you have any questions or require further clarification.
