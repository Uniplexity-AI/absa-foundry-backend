# Frontend UI/UX Design: Model Ops View

> **Document version:** 1.0  
> **Phase:** PoC Month 2  
> **Target Audience:** Data Scientists, IT Operations, AI Governance  
> **Design Authority:** `ETLRunHistory.vue` canonical patterns  

---

## 1. Vision & Architecture

The **Model Ops View** consolidates all technical, data, and ML pipeline monitoring into a single unified workspace. It is designed to prove to the bank that the platform is hitting the PoC KPIs (e.g., $\ge 80\%$ prediction accuracy) and maintaining 100% data governance.

### 1.1 Layout Structure (`ModelOpsLayout.vue`)
* **Global Background:** `global-mesh-bg` with full-width container (`w-full min-h-screen`).
* **Sidebar (`ModelOpsSidebar.vue`):** 
  * *Theme:* Dark mode (`bg-[#131010] text-surface`) to distinguish it from the front-office Executive/RM views.
  * *Navigation Items:* 
    * 📊 Model Performance (KPI Tracker)
    * ⚙️ ETL Pipeline Manager
    * 📄 Batch Audit Trails
    * 🛠️ Config Editor (YAML)

---

## 2. Core Pages & UI Patterns

### 2.1 Model Performance Dashboard (`Models.vue`)
**Purpose:** Track the $\ge 80\%$ accuracy KPI and monitor ML drift.

**Top KPI Strip (The Canonical Box Pattern):**
```html
<!-- Example: Churn Prediction Accuracy -->
<div class="bg-surface rounded border border-outline-variant global-dotted-bg shadow-sm">
  <div class="flex justify-between items-center mb-2">
    <p class="text-xs text-on-surface-variant font-label uppercase font-semibold">Churn Accuracy</p>
    <!-- Green badge if >= 80%, Red if below -->
    <span class="text-[10px] font-bold px-2 py-1 bg-green-100 text-green-800 rounded">TARGET MET</span>
  </div>
  <span class="text-3xl font-headline font-bold text-primary">82.4%</span>
</div>
```

**Feature Drift Table:**
Uses the canonical Table pattern with PSI (Population Stability Index) alerts.
* **Columns:** Feature Name | Baseline Mean | Current Mean | PSI Score | Status
* **Status Alert Pattern:** If PSI > 0.2, show a pulsing Energy (`#FF780F`) warning badge indicating the model needs retraining.

### 2.2 ETL Pipeline Manager (`ETLRunHistory.vue`)
*This page remains the canonical design authority for the system.*

**Infrastructure Health Cards:**
* Display live ping status for PostgreSQL, Redis, and API Gateway.
* Uses the canonical status badge component (`w-1.5 h-1.5 rounded-full animate-pulse bg-amber-500` for `RUNNING`).

**Manual Trigger Modal:**
* Instead of navigating away, triggering a pipeline opens a sleek, centered overlay.
* **Button:** `bg-primary text-on-primary hover:bg-primary-container shadow-sm` (ABSA Passion Red `#DC0037`).

### 2.3 Batch Execution Audit (`BatchExecutionDetail.vue`)
**Purpose:** Provide 100% compliance traceability for every data point ingested.

**Execution Timeline Component:**
* A vertical stepping timeline showing data flow: `Extraction -> Validation -> Feature Store -> Inference`.
* Each node uses the ABSA brand colors to show success (Serene/White node) or failure (Energy/Orange node).

**Rejection Analysis (Split View):**
* Left side: Donut chart (Chart.js) showing error categories (e.g., Null Values, Format Mismatch).
* Right side: Canonical table listing the top 5 failing extraction rules.

### 2.4 ETL Config Manager (`EtlConfigManager.vue`)
**Purpose:** Allow Data Scientists to update extraction logic without deploying code.

**Inline Code Editor UI:**
* **Header:** Breadcrumb navigation (e.g., `Configs / customer_extraction_v2.yaml`).
* **Editor:** A monospace text area with syntax highlighting for YAML.
* **Action Bar:** Floating at the bottom right.
  * *Cancel:* Secondary Button (`bg-surface text-on-surface border border-outline-variant`)
  * *Deploy Config:* Primary Button (`bg-[#131010] text-white hover:bg-gray-800`) — Note: Using black (Enrich) here instead of red to denote a highly technical/structural save action.

---

## 3. Typography & Styling Rules

To maintain the ABSA brand within this technical view, strictly adhere to these CSS variables:

| Element | Class to Use | Hex Reference |
| :--- | :--- | :--- |
| **Primary Actions (Run/Deploy)** | `bg-primary text-on-primary` | Passion Red (`#DC0037`) |
| **Technical Warnings (Drift/Fails)** | `text-orange-600 bg-orange-50` | Energy Orange (`#FF780F`) |
| **Card Backgrounds** | `bg-surface` | Serene White (`#FFFFFF`) |
| **Data Grid Borders** | `border-outline-variant` | Light Gray |
| **Log Output Text** | `font-mono text-xs text-on-surface-variant` | Enrich Black (`#131010/70`) |

---

## 4. Interaction Design (Micro-interactions)

1. **Table Rows:** Hovering over an ETL run or Prediction log in the canonical table must trigger `hover:bg-surface-container-low transition-colors` to highlight the row without jarring the eye.
2. **Empty States:** If a pipeline hasn't run yet, a centered block with `text-body-md text-secondary` stating "No pipeline executions found" must be displayed. Do not leave empty grids.
3. **Data Loading:** When fetching heavy model metrics or 10,000-row logs, the `LoadingSkeleton.vue` must replace the exact shape of the cards/table to prevent layout shift.
