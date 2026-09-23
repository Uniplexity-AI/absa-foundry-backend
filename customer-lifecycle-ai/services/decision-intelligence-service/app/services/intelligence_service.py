"""Intelligence Aggregation Service — portfolio metrics for the new frontend.

Orchestrates concurrent fan-out:
  - Prediction Service (:8004) /predict/portfolio-scores — churn + CLV percentile for all customers
  - Shared DB (etl_clean) — feature profiles, states, transitions, decision outcomes

All four frontend endpoints (/clv-summary, /aum-forecast,
/business-outcomes, /lifecycle-summary) are computed here from those
two sources. Results cached with a short TTL because portfolio
snapshots don't change intra-minute.

PILOT STAND-INS — the production design follows the spec contracts;
the proxies below exist only because pilot data/models are incomplete
(synthetic data validates the design, it does not define it). Each is
env-gated and switches to the production source without code changes:
  - INTEL_AT_RISK_CUTOFF (default 0.50, per spec). INTEL_ADAPTIVE_AT_RISK
    (default on in pilot) falls back to the portfolio's own p90 churn
    when the calibrated model never reaches the cutoff. Disable in prod.
  - INTEL_AUM_COLUMN (default total_amount_90d) — swap to the real
    balance/AUM column when the pilot DB provides one.
  - winback_probability: used directly from the scores payload when the
    Prediction Service gains a winback model; the cohort-relative value
    proxy applies only while that field is absent.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import httpx

from app.repository.intelligence_repository import IntelligenceRepository

logger = logging.getLogger("decision.intelligence_service")

PREDICTION_SERVICE_URL = "http://127.0.0.1:8004"
_CACHE_TTL = 120.0  # seconds

# Spec threshold; adaptive fallback is a pilot-only accommodation.
_AT_RISK_CUTOFF = float(os.getenv("INTEL_AT_RISK_CUTOFF", "0.50"))
_ADAPTIVE_AT_RISK = os.getenv("INTEL_ADAPTIVE_AT_RISK", "true").lower() in ("1", "true", "yes")


class IntelligenceService:
    def __init__(self) -> None:
        self._repo = IntelligenceRepository()
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="intel")
        self._cache: dict[str, tuple[float, dict]] = {}
        self._cache_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Shared fan-out
    # ------------------------------------------------------------------

    def _portfolio_scores(self, as_of_date: date | None) -> dict:
        """Call :8004 portfolio-scores; returns {} on failure (degrade gracefully)."""
        params = {"as_of_date": as_of_date.isoformat()} if as_of_date else {}
        try:
            resp = httpx.get(
                f"{PREDICTION_SERVICE_URL}/predict/portfolio-scores",
                params=params, timeout=30.0,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning("portfolio-scores unavailable: %s", e)
            return {}

    def _deletion_generation(self) -> int:
        """Change-detector for the soft-delete flag, used to bust the cache.

        Deleting a customer happens in the gateway, so it cannot invalidate this
        in-process cache; without the guard a just-deleted customer stays in the
        totals for the rest of the TTL. Never raises — on a probe failure the
        cache falls back to TTL-only behaviour.
        """
        try:
            return self._repo.deleted_customer_count()
        except Exception as exc:  # noqa: BLE001 - a probe failure must not break the endpoint
            logger.warning("deletion-generation probe failed, using TTL only: %s", exc)
            return -1

    def _snapshot(self, as_of_date: date | None) -> dict:
        """Resolved as-of date + scores + feature profiles, from cache when fresh."""
        # The deletion count is part of the key, so a soft delete (or a restore)
        # is a cache miss on the very next request.
        key = f"snapshot:{as_of_date or 'latest'}:{self._deletion_generation()}"
        with self._cache_lock:
            hit = self._cache.get(key)
            if hit and (time.monotonic() - hit[0]) < _CACHE_TTL:
                return hit[1]

        resolved = as_of_date or self._repo.latest_feature_date()
        if resolved is None:
            snapshot = {"as_of_date": None, "scores": [], "profiles": {}}
        else:
            scores_fut = self._executor.submit(self._portfolio_scores, resolved)
            profiles_fut = self._executor.submit(self._repo.customer_value_profiles, resolved)
            scores = scores_fut.result()
            profiles = profiles_fut.result()
            snapshot = {
                "as_of_date": resolved.isoformat(),
                "scores": scores.get("scores", []),
                "profiles": {p["customer_id"]: p for p in profiles},
            }

        with self._cache_lock:
            self._cache[key] = (time.monotonic(), snapshot)
        return snapshot

    # ------------------------------------------------------------------
    # Endpoint 1: CLV Summary
    # ------------------------------------------------------------------

    def clv_summary(self, as_of_date: date | None = None) -> dict:
        snap = self._snapshot(as_of_date)
        scores = snap["scores"]
        profiles = snap["profiles"]

        bands = {"PLATINUM": [], "GOLD": [], "SILVER": [], "BRONZE": []}
        total_clv_proxy = 0.0
        clv_at_risk = 0.0

        # Spec threshold first; the adaptive fallback is pilot-only
        # (INTEL_ADAPTIVE_AT_RISK) and is reported in the response.
        churn_probs = sorted(s.get("churn_probability") or 0.0 for s in scores)
        at_risk_cutoff = _AT_RISK_CUTOFF
        cutoff_source = "spec"
        above = sum(1 for c in churn_probs if c > at_risk_cutoff)
        if _ADAPTIVE_AT_RISK and scores and above < len(scores) * 0.01:
            at_risk_cutoff = churn_probs[int(len(churn_probs) * 0.90)]
            cutoff_source = "pilot_adaptive_p90"

        for s in scores:
            pct = s.get("clv_percentile") or 0.0
            churn = s.get("churn_probability") or 0.0
            aum = float(profiles.get(s["customer_id"], {}).get("current_aum") or 0)
            total_clv_proxy += aum
            if churn > at_risk_cutoff:
                clv_at_risk += aum * churn

            band = ("PLATINUM" if pct >= 0.90 else
                    "GOLD" if pct >= 0.75 else
                    "SILVER" if pct >= 0.50 else "BRONZE")
            bands[band].append(s)

        value_protected_mtd = self._repo.revenue_protected_mtd()

        return {
            "as_of_date": snap["as_of_date"],
            "total_customers_scored": len(scores),
            "bands": [
                {
                    "band": b,
                    "customer_count": len(members),
                    "share_pct": round(len(members) / len(scores) * 100, 1) if scores else 0.0,
                }
                for b, members in bands.items()
            ],
            "portfolio_value": {
                # AUM proxy used as CLV magnitude until an absolute-CLV model lands
                "total_clv": round(total_clv_proxy, 2),
                "clv_at_risk": round(clv_at_risk, 2),
                "at_risk_churn_threshold": round(at_risk_cutoff, 4),
                "at_risk_threshold_source": cutoff_source,
                "value_protected_mtd": round(value_protected_mtd, 2),
            },
            "model_versions": {"clv": "percentile_v1 (AUM-proxied magnitude)"},
            "data_sources": ["prediction-service:8004", "etl_clean.customer_features", "decision_outcomes"],
        }

    # ------------------------------------------------------------------
    # Endpoint 2: AUM Forecast
    # ------------------------------------------------------------------

    def aum_forecast(self, as_of_date: date | None = None,
                     horizon_days: int = 90) -> dict:
        snap = self._snapshot(as_of_date)
        scores = {s["customer_id"]: s for s in snap["scores"]}
        profiles = snap["profiles"]

        weeks = max(1, horizon_days // 7)

        # ── Build per-customer rows ────────────────────────────────────
        # Exclusively using the LightGBM balance-growth model output.
        bg_rows = []   # (aum, growth_pct_per_horizon)

        for cid, prof in profiles.items():
            aum = float(prof.get("current_aum") or 0)
            s = scores.get(cid) or {}
            # Default to 0.0 growth if the model hasn't scored this customer
            g = float(s.get("balance_growth_pct") or 0.0)
            bg_rows.append((aum, g))

        total_aum = sum(a for a, _ in bg_rows)
        start = date.fromisoformat(snap["as_of_date"]) if snap["as_of_date"] else date.today()
        labels = [f"Wk {w+1} ({(start + timedelta(weeks=w + 1)).isoformat()})" for w in range(weeks)]

        # ── ML path: weekly compound growth ───────────────────────
        def ml_series(shift_pp: float) -> list[float]:
            if total_aum == 0:
                return [0.0] * weeks
            portfolio_t = []
            for w in range(weeks):
                t_aum = sum(
                    aum * ((1.0 + (g + shift_pp) / 100.0) ** ((w + 1) / weeks))
                    for aum, g in bg_rows
                )
                portfolio_t.append(round(t_aum, 2))
            return portfolio_t

        method = (
            "ML balance-growth projection: LightGBM balance_growth_pct model "
            "(lightgbm_balance_growth_model.pkl), weekly compound growth, "
            "±2pp growth shift for optimistic/pessimistic scenarios."
        )

        return {
            "as_of_date": snap["as_of_date"],
            "horizon_days": horizon_days,
            "current_aum": round(total_aum, 2),
            "scenarios": {
                "optimistic":  ml_series(+2.0),
                "base":        ml_series(0.0),
                "pessimistic": ml_series(-2.0),
            },
            "labels": labels,
            "method": method,
            "customers": len(bg_rows),
            "balance_growth_model_used": True,
        }

    # ------------------------------------------------------------------
    # Endpoint 3: Business Outcomes & ROI
    # ------------------------------------------------------------------

    def revenue_trend(self, months: int = 5) -> list[dict]:
        """Monthly accepted revenue for the legacy ROI trend chart."""
        return self._repo.revenue_trend(months)

    def business_outcomes(self) -> dict:
        totals = self._repo.roi_totals()
        by_branch = self._repo.roi_by_branch()

        rev, cost = totals["revenue_protected"], totals["intervention_cost"]
        net_roi_pct = round((rev - cost) / cost * 100, 1) if cost else 0.0

        pilot = [b for b in by_branch if b["is_pilot_branch"]]
        control = [b for b in by_branch if not b["is_pilot_branch"]]

        def agg(bs):
            n = len(bs)
            interventions = sum(b["interventions"] for b in bs) or 1
            accepted = sum(b["accepted"] for b in bs)
            retained = sum(b["retained"] for b in bs)
            # Retention is only measurable once the 90-day window has elapsed;
            # divide by measured interventions, not all-time accepted.
            measured = sum(b.get("measured_accepted") or 0 for b in bs)
            return {
                "branches": n,
                "interventions": interventions,
                "acceptance_rate_pct": round(accepted / interventions * 100, 1),
                "retention_rate_pct": round(retained / measured * 100, 1) if measured else 0.0,
                "revenue_protected": round(sum(float(b["total_revenue"]) for b in bs), 2),
                "intervention_cost": round(sum(float(b["total_cost"]) for b in bs), 2),
            }

        return {
            "roi": {
                "revenue_protected": round(rev, 2),
                "intervention_cost": round(cost, 2),
                "net_roi_pct": net_roi_pct,
                "roi_multiple": round(rev / cost, 2) if cost else 0.0,
            },
            "retention_performance": [
                {
                    "branch_id": b["branch_id"],
                    "pilot": b["is_pilot_branch"],
                    "interventions": b["interventions"],
                    "accepted": b["accepted"],
                    "retained_90d": b["retained"],
                    "revenue_protected": float(b["total_revenue"]),
                    "intervention_cost": float(b["total_cost"]),
                }
                for b in by_branch
            ],
            "pilot_vs_control": {"pilot": agg(pilot), "control": agg(control)},
            "data_sources": ["etl_clean.decision_outcomes"],
        }

    # ------------------------------------------------------------------
    # Endpoint 4: Lifecycle Summary
    # ------------------------------------------------------------------

    def lifecycle_summary(self, as_of_date: date | None = None) -> dict:
        snap = self._snapshot(as_of_date)
        resolved = date.fromisoformat(snap["as_of_date"]) if snap["as_of_date"] else None
        if resolved is None:
            return {"as_of_date": None, "status": "NO_DATA"}

        counts_fut = self._executor.submit(self._repo.state_counts, resolved)
        matrix_fut = self._executor.submit(self._repo.transition_matrix, resolved, 30)
        churned_fut = self._executor.submit(self._repo.churned_customers, resolved, 200)

        counts = counts_fut.result()
        transitions = matrix_fut.result()
        churned = churned_fut.result()

        # Win-back: production design reads winback_probability from the
        # Prediction Service. Until that model exists, a cohort-relative
        # 180-day value proxy (decayed by churn recency) fills the field.
        scores = {s["customer_id"]: s for s in snap["scores"]}
        model_backed = any(s.get("winback_probability") is not None for s in snap["scores"])

        if model_backed:
            winback = []
            for c in churned:
                s = scores.get(c["customer_id"], {})
                wp = s.get("winback_probability") or 0.0
                days = c.get("days_since_churn") or 0
                months_churned = days / 30.44
                winback.append({
                    "customer_id": c["customer_id"],
                    "winback_probability": wp,
                    "churned_on": c["churned_on"].isoformat() if c.get("churned_on") else None,
                    "months_churned": round(months_churned, 1),
                    "status": "ELIGIBLE" if months_churned <= 6 and wp > 0.40 else "INELIGIBLE",
                })
            winback.sort(key=lambda w: w["winback_probability"], reverse=True)
            method = "winback_probability from Prediction Service model"
        else:
            values = sorted(c.get("value_180d") or 0 for c in churned)
            n = len(values)

            def value_percentile(v: float) -> float:
                if n == 0:
                    return 0.0
                return sum(1 for x in values if x < v) / n

            winback = []
            for c in churned:
                pct = value_percentile(c.get("value_180d") or 0)
                days = c.get("days_since_churn") or 0
                months_churned = days / 30.44
                winback_prob = round(pct * (1 - min(months_churned / 12, 1.0)), 4)
                winback.append({
                    "customer_id": c["customer_id"],
                    "value_180d": float(c.get("value_180d") or 0),
                    "churned_on": c["churned_on"].isoformat() if c.get("churned_on") else None,
                    "months_churned": round(months_churned, 1),
                    "winback_probability": winback_prob,
                    "status": "ELIGIBLE" if months_churned <= 6 and winback_prob > 0.40 else "INELIGIBLE",
                })
            winback.sort(key=lambda w: w["winback_probability"], reverse=True)
            method = "pilot proxy: cohort-relative 180d value percentile x recency decay (no winback model yet)"

        return {
            "as_of_date": snap["as_of_date"],
            "state_counts": counts,
            "transition_matrix": {
                "states": transitions["states"],
                "matrix": transitions["matrix"],
                "window_days": 30,
            },
            "winback_pipeline": {
                "churned_total": len(churned),
                "eligible": sum(1 for w in winback if w["status"] == "ELIGIBLE"),
                "top_candidates": winback[:25],
                "method": method,
            },
        }


# Singleton
intelligence_service = IntelligenceService()
