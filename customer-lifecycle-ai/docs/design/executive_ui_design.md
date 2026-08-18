# Frontend UI/UX Design: Executive & Marketing View

> **Document version:** 1.0  
> **Phase:** PoC Month 2  
> **Target Audience:** Executives, Marketing Leaders, Regional Managers  
> **Design Authority:** ABSA Canonical Design System (`PortfolioOverview.vue`)  

---

## 1. Vision & Architecture

The **Executive View** is the high-level, macro-intelligence layer of the platform. While the Ops view focuses on technical accuracy, this view focuses entirely on **Business Value at Risk, Portfolio Health, and Campaign ROI**. It is designed to be clean, visually striking, and immediately actionable for decision-makers.

### 1.1 Layout Structure (`ExecutiveLayout.vue`)
* **Global Background:** `global-mesh-bg` with full-width container (`w-full min-h-screen`).
* **Sidebar (`ExecutiveSidebar.vue`):** 
  * *Theme:* Light mode (`bg-surface text-on-surface`) to feel premium, open, and business-focused. Active state uses a left border of Passion Red (`#DC0037`).
  * *Navigation Items:* 
    * 📈 Portfolio Overview (The 30,000 ft view)
    * 🏦 Branch & Segment Heatmaps
    * 🎯 Campaign ROI Estimator
    * 🧠 Global AI Insights (Why are we losing clients?)

---

## 2. Core Pages & UI Patterns

### 2.1 Portfolio Overview (`PortfolioOverview.vue`)
**Purpose:** Instantly show the health of the entire customer base and the total value at risk.

**Top KPI Strip (The Canonical Box Pattern):**
Four core metric cards spanning the top of the page.
```html
<div class="bg-surface rounded border border-outline-variant global-dotted-bg shadow-sm">
  <div class="flex justify-between items-center mb-2">
    <p class="text-xs text-on-surface-variant font-label uppercase font-semibold">Value at Risk (90 Days)</p>
    <span class="text-[10px] font-bold px-2 py-1 bg-red-50 text-red-700 rounded">CRITICAL</span>
  </div>
  <!-- Value displayed prominently in ABSA Passion Red -->
  <span class="text-3xl font-headline font-bold text-primary">R452.3M</span>
</div>
```
*Other KPI Cards:* Total Active Customers, Net Migration (Upgraded vs Downgraded), Total CLV.

**The Markov Portfolio State Chart:**
* A wide horizontal layout containing a Doughnut Chart (Chart.js) showing the distribution of customers across the 6 states (`NEW`, `ACTIVE`, `GROWING`, `AT_RISK`, `DORMANT`, `CHURNED`).
* Uses ABSA brand colors: Passion Red (`#DC0037`) for At Risk/Churned, Enrich Black (`#131010`) for Dormant, and neutral grays for Active/New.

### 2.2 Branch & Segment Heatmap
**Purpose:** Identify localized deterioration (e.g., "Why is the Sandton branch bleeding VIP clients?").

**The Canonical Table Pattern (Enhanced):**
* **Columns:** Branch Name | Total Customers | Net Growth (M/M) | High-Risk Concentration | Recommended Intervention
* **Styling:** The "Net Growth" column uses green/red text coloring based on positive/negative values. The "High-Risk Concentration" column uses a small inline mini-bar chart (CSS based) to visually indicate severity.

### 2.3 Campaign ROI Estimator
**Purpose:** Translate ML predictions into expected marketing revenue.

**Split Panel Layout:**
* **Left Panel (Campaign Selector):** A list of active system-recommended campaigns (e.g., *Waive Account Fees for At-Risk Mass Retail*, *Offer Premium Card to Growing VIPs*).
* **Right Panel (ROI Calculator Widget):** 
  * Displays the mathematical Expected Value: $\mathbb{E}[\text{Revenue}] = P(\text{Acceptance}) \times \text{Margin} - \text{Cost}$.
  * A large `bg-surface-container-low` shaded box highlighting the **Estimated Revenue Lift** in bold typography.
  * **Action Button:** A prominent `bg-primary text-on-primary` button labeled **"Approve & Route to Channels"**, linking the insight directly to execution.

### 2.4 Global AI Insights (The 'Why' Page)
**Purpose:** Answer the Executive question: *"Why are customers leaving?"*

**Insight Cards:**
* Uses the canonical Box pattern but tailored for natural language.
* Example: A card titled **"Top Churn Driver: August 2026"** containing a bold, LLM-generated sentence: *"74% of churning customers experienced a 20% drop in salary deposits over the preceding 3 months."*

---

## 3. Typography & Styling Rules

To maintain the ABSA brand's premium feel for executives, the UI relies heavily on typography hierarchy and whitespace:

| Element | Class to Use | Hex Reference |
| :--- | :--- | :--- |
| **Headline Numbers (Rands/Millions)** | `font-headline font-black text-3xl text-primary` | Passion Red (`#DC0037`) |
| **Section Titles** | `font-headline font-semibold text-xl text-on-surface` | Enrich Black (`#131010`) |
| **Card Labels (Subtle)** | `font-label text-xs uppercase text-on-surface-variant` | Light Gray Text |
| **Call to Action Buttons** | `bg-primary text-on-primary shadow-sm` | Passion Red (`#DC0037`) |

---

## 4. Interaction Design (Micro-interactions)

1. **Date Snapshots:** The top of the dashboard must feature a sleek date dropdown (`Snapshot: 30 July 2026`). Changing this triggers a smooth opacity transition (`transition-opacity duration-300`) as the KPI numbers update, making the dashboard feel incredibly responsive.
2. **Chart Hover States:** Hovering over a segment in the Doughnut chart triggers a clean, minimalist tooltip showing the exact Rand value of that segment, completely avoiding default, ugly browser tooltips.
3. **Empty States:** Executives should never see technical errors. If data is missing, display a polished message: *"Portfolio metrics are currently being compiled."*
