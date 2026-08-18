# Frontend UI/UX Design: Frontline Engagement (Premier & Mass Market)

> **Document version:** 1.0  
> **Phase:** PoC Month 2  
> **Target Audience:** Premier Relationship Managers, Call Center Agents, Digital Ops  
> **Design Authority:** ABSA Canonical Design System (`CustomerDetail.vue` patterns)  

---

## 1. Vision & Architecture

Rather than building two entirely separate systems, the **Frontline Engagement View** combines both Premier (View 2A) and Mass Market (View 2B) operations into a single, unified interface architecture. The UI dynamically adjusts based on the logged-in user's role (e.g., `role === 'premier_rm'` vs `role === 'call_center_agent'`), revealing or restricting data depth while maintaining a consistent Absa brand experience.

### 1.1 Layout Structure (`FrontlineLayout.vue`)
* **Global Background:** `global-mesh-bg` with full-width container (`w-full min-h-screen`).
* **Sidebar (`FrontlineSidebar.vue`):** 
  * *Theme:* Serene Light mode (`bg-surface text-on-surface`) to keep the workspace feeling bright and focused for daily task execution.
  * *Dynamic Navigation:*
    * **If Premier RM:** 📋 My Portfolio (Assigned) | ⭐ VIP Priority Queue | 📁 Approvals
    * **If Call Center/Mass Ops:** 📞 Global Outbound Queue | 📱 Digital Routing Status | 📁 Escalations

---

## 2. Core Pages & UI Patterns

### 2.1 The Daily Priority Queue (Landing Page)
**Purpose:** Ensure the frontline knows exactly who to contact first, sorted by the AI's **Priority Score (0-100)**.

**The Queue Table (Canonical Table Pattern):**
* **Columns (Premier):** Client Name | CLV | Health Score | Next Best Action | Action Status
* **Columns (Mass Market):** Queue ID | At-Risk Value | Intervention Type (Script) | Action Status
* **Row Interaction:** Clicking a row slides in a full-height right-side drawer (or navigates to the detail page) without losing context of the queue.

### 2.2 The Customer Intelligence Card (Dynamic Detail View)
**Purpose:** Provide the context needed to execute the Next-Best-Action. The depth of this card changes based on the user's role.

#### **For the Premier RM (Deep Context):**
* **Health Score Gauge:** A circular or semi-circular gauge (Chart.js) showing Churn Probability.
* **State Timeline:** A horizontal timeline showing the customer's journey from `NEW` $\to$ `GROWING` $\to$ `AT_RISK`.
* **The AI Explanation (Crucial):** A `bg-surface-container-low` shaded box containing the LLM-generated rationale (e.g., *"Offer Premium Limit Increase: Client’s salary grew 20% over 6 months."*). This enables white-glove, unscripted conversations.

#### **For the Call Center Agent (Action-Focused):**
* **Simplified View:** Hides the deep Markov transition history and focuses purely on the immediate action.
* **The Approved Script:** Replaces the LLM rationale with a legally approved, deterministic script (e.g., *"Hello, we noticed you might benefit from waiving your monthly fee..."*).
* **Execution Buttons:** Prominent buttons to log the call outcome: `[Accepted]` (Green), `[Declined]` (Red), `[Follow Up]` (Orange).

### 2.3 The Digital Routing Status Board (Mass Ops Only)
**Purpose:** Give branch managers and marketing ops visibility into automated interventions.

**Digital Pipeline Tracker:**
* Uses canonical Box patterns to show the volume of actions sent to automated channels today.
* **Cards:** `SMS Interventions Sent`, `Email Campaigns Triggered`, `App Push Notifications Delivered`.
* **Routing Conversion Table:** Shows which automated interventions are actually succeeding (e.g., "Fee Waiver SMS - 12% Click Rate").

---

## 3. Typography & Styling Rules

The frontline views must be highly scannable to reduce cognitive load during 100+ daily interactions.

| Element | Class to Use | Hex Reference |
| :--- | :--- | :--- |
| **Priority Scores (High)** | `text-primary font-bold bg-red-50 px-2 py-1` | Passion Red (`#DC0037`) |
| **Action Outcome (Success)**| `bg-green-600 text-white shadow-sm` | Success Green |
| **Action Outcome (Decline)**| `bg-surface border-outline-variant text-on-surface`| Standard Outline Button |
| **Script/LLM Text** | `font-medium text-sm text-on-surface-variant` | Enrich Black (`#131010`) |

---

## 4. Interaction Design (Micro-interactions)

1. **Focus Mode (Queue Slide-over):** When a Call Center agent clicks a customer in the queue, instead of a full page load, a slide-over panel appears from the right. This allows them to execute the script and click "Next Customer" instantly, massively improving UI throughput.
2. **Approval Escalation:** If a Premier RM selects an action that requires a Branch Manager's signature (e.g., "Adjust Interest Rate by -1%"), the button immediately transitions into a `PENDING_APPROVAL` loading state (using the `animate-pulse bg-amber-500` pattern) to show the request is in flight.
3. **Queue Auto-Refresh:** The Mass Market shared pool auto-refreshes seamlessly via polling (or WebSockets), ensuring agents aren't calling the same churn-risk customer twice.
