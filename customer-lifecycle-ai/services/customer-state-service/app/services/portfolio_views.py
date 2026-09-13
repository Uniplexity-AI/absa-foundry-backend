"""Portfolio Views — live data for the frontend's CLV-summary and lifecycle-stages.

Replaces the hardcoded payloads previously returned by
/states/clv-summary and /states/lifecycle-stages. Composes:
  - Prediction Service (:8004) /predict/portfolio-scores (churn + CLV percentile)
  - Shared DB (etl_clean): customer_features, customer_states,
    state_transitions, decision_outcomes

PILOT STAND-INS (design is production-shaped; gaps are disclosed):
  - No customer names in the DB → name falls back to customer_id
  - No absolute CLV model → clv/AUM proxied by 90-day transaction volume
  - No winback model → cohort-relative 180d value × churn-recency decay
Response shapes match the frontend store contract exactly.
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from datetime import date, timedelta

import httpx
import psycopg2
from psycopg2 import extras

from shared.config.settings import settings
from shared.database.soft_delete import live_customer_filter

logger = logging.getLogger("state.portfolio_views")

PREDICTION_SERVICE_URL = os.getenv("PREDICTION_SERVICE_URL", "http://127.0.0.1:8004")
_AUM_COLUMN = os.getenv("INTEL_AUM_COLUMN", "total_amount_90d")
if not re.fullmatch(r"[a-z_][a-z0-9_]*", _AUM_COLUMN):
    raise ValueError(f"INTEL_AUM_COLUMN must be a plain identifier, got {_AUM_COLUMN!r}")

_AT_RISK_CUTOFF = float(os.getenv("INTEL_AT_RISK_CUTOFF", "0.50"))
_ADAPTIVE_AT_RISK = os.getenv("INTEL_ADAPTIVE_AT_RISK", "true").lower() in ("1", "true", "yes")

_CACHE_TTL = 120.0
#: Aggregate cache TTL for unchanged data. Bounded by ``_deletion_generation``:
#: a change to the soft-delete flag misses the cache on the next request, so
#: this only governs how long identical data may be reused.
_STAGE_META = {
    "NEW":      ("Onboarding", "text-gray-600",   "bg-gray-100",  "bg-gray-500"),
    "GROWING":  ("Growing",    "text-absa-passion", "bg-red-50",  "bg-absa-passion"),
    "ACTIVE":   ("Active",     "text-absa-enrich",  "bg-gray-50", "bg-absa-enrich"),
    "AT_RISK":  ("At Risk",    "text-absa-energy",  "bg-orange-50", "bg-absa-energy"),
    "DORMANT":  ("Dormant",    "text-absa-inspire", "bg-red-100", "bg-absa-inspire"),
    "CHURNED":  ("Churned",    "text-red-900",      "bg-red-100", "bg-red-900"),
}


def _fmt_k(v: float) -> str:
    if v >= 1_000_000:
        return f"K {v / 1_000_000:.1f}M"
    if v >= 1_000:
        return f"K {v / 1_000:.0f}K"
    return f"K {v:.0f}"


class PortfolioViews:
    def __init__(self) -> None:
        self._cache: dict[str, tuple[float, dict]] = {}
        self._lock = threading.Lock()
        self._conn_str = (
            f"host={settings.postgres_target_host} "
            f"port={settings.postgres_target_port} "
            f"dbname={settings.postgres_target_db} "
            f"user={settings.postgres_target_user} "
            f"password={settings.postgres_target_password}"
        )

    # ------------------------------------------------------------------
    # Data access
    # ------------------------------------------------------------------

    def _q(self, sql: str, params: dict, name: str) -> list[dict]:
        def _run():
            conn = psycopg2.connect(self._conn_str, connect_timeout=5,
                                    keepalives=1, keepalives_idle=30)
            try:
                cur = conn.cursor(cursor_factory=extras.RealDictCursor)
                cur.execute(sql, params)
                return [dict(r) for r in cur.fetchall()]
            finally:
                conn.close()
        return _run()

    def _scores(self, as_of: date) -> list[dict]:
        try:
            resp = httpx.get(f"{PREDICTION_SERVICE_URL}/predict/portfolio-scores",
                             params={"as_of_date": as_of.isoformat()}, timeout=30.0)
            resp.raise_for_status()
            return resp.json().get("scores", [])
        except Exception as e:
            logger.warning("portfolio-scores unavailable: %s", e)
            return []

    def _deletion_generation(self) -> int:
        """Change-detector for the soft-delete flag, used to bust the cache.

        Deleting a customer happens in the gateway, so it cannot invalidate this
        in-process cache. Without a guard the aggregates keep answering from a
        cached build for the rest of the TTL, and an operator who just deleted a
        customer still sees the old totals — the "deletion did not happen"
        report. Reading the deleted count is a single count on ~5k rows, so it
        is cheaper than rebuilding CLV (which calls the prediction service).

        Never raises: if the probe fails the cache simply falls back to
        TTL-only behaviour.
        """
        try:
            rows = self._q(
                "SELECT count(*) AS n FROM public.customers_clean WHERE is_deleted",
                {}, "deletion_generation",
            )
            return int(rows[0]["n"])
        except Exception as exc:  # noqa: BLE001 - a probe failure must not break the endpoint
            logger.warning("deletion-generation probe failed, using TTL only: %s", exc)
            return -1

    def _cached(self, key: str, build) -> dict:
        # The deletion count is part of the key, so a soft delete (or a restore)
        # is a cache miss on the very next request.
        tagged = (key, self._deletion_generation())
        with self._lock:
            hit = self._cache.get(tagged)
            if hit and (time.monotonic() - hit[0]) < _CACHE_TTL:
                return hit[1]
        val = build()
        with self._lock:
            self._cache[tagged] = (time.monotonic(), val)
        return val

    # ------------------------------------------------------------------
    # /states/clv-summary
    # ------------------------------------------------------------------

    def clv_summary(self, as_of: date) -> dict:
        return self._cached(f"clv:{as_of}", lambda: self._build_clv(as_of))

    def _build_clv(self, as_of: date) -> dict:
        rows = self._q(
            f"""
            SELECT customer_id,
                   COALESCE({_AUM_COLUMN}, 0) AS aum,
                   COALESCE(days_since_last_txn, 999) AS days_since_contact,
                   customer_segment
            FROM customer_features WHERE as_of_date = %(d)s
            {live_customer_filter("customer_features.customer_id")}
            """, {"d": as_of}, "clv_profiles")
        scores = {s["customer_id"]: s for s in self._scores(as_of)}
        total_protected = self._q(
            """
            SELECT COALESCE(SUM(revenue_protected_amount), 0) AS v
            FROM decision_outcomes
            WHERE accepted_flag
              AND date_trunc('month', created_at) = date_trunc('month', CURRENT_DATE)
            """, {}, "protected")[0]["v"]

        merged = []
        for r in rows:
            s = scores.get(r["customer_id"], {})
            merged.append({
                "customer_id": r["customer_id"],
                "aum": float(r["aum"]),
                "days_since_contact": int(r["days_since_contact"]),
                "segment": r["customer_segment"] or "Unclassified",
                "churn": s.get("churn_probability") or 0.0,
                "pct": s.get("clv_percentile") or 0.0,
            })

        churns = sorted(m["churn"] for m in merged)
        cutoff = _AT_RISK_CUTOFF
        if _ADAPTIVE_AT_RISK and churns and sum(1 for c in churns if c > cutoff) < len(churns) * 0.01:
            cutoff = churns[int(len(churns) * 0.90)]

        total_clv = sum(m["aum"] for m in merged)
        clv_at_risk = sum(m["aum"] * m["churn"] for m in merged if m["churn"] > cutoff)
        churn_adjusted = sum(m["aum"] * (1 - m["churn"]) for m in merged)

        band_defs = [
            ("Platinum", 0.90, "Top 10% by CLV percentile"),
            ("Gold",     0.75, "75th–90th CLV percentile"),
            ("Silver",   0.50, "50th–75th CLV percentile"),
            ("Bronze",   0.00, "Below 50th CLV percentile"),
        ]
        bands = []
        for label, lo, thr in band_defs:
            members = [m for m in merged if m["pct"] >= lo] if lo > 0 else \
                      [m for m in merged if m["pct"] < 0.50]
            n = len(members)
            bands.append({
                "band": label, "label": label, "threshold": thr,
                "count": n,
                "avg_clv": round(sum(m["aum"] for m in members) / n, 2) if n else 0.0,
                "avg_churn_prob": round(sum(m["churn"] for m in members) / n, 4) if n else 0.0,
                "total_aum": round(sum(m["aum"] for m in members), 2),
                "pct": round(n / len(merged) * 100, 1) if merged else 0.0,
            })

        top = sorted(merged, key=lambda m: (-m["churn"], -m["aum"]))[:8]
        top_customers = []
        for m in top:
            band = next((b["band"] for b, lo in zip(bands, (0.90, 0.75, 0.50, 0.0))
                         if m["pct"] >= lo), "Bronze")
            top_customers.append({
                "customer_id": m["customer_id"],
                "name": m["customer_id"],   # no name column in pilot DB
                "segment": m["segment"],
                "band": band,
                "clv": round(m["aum"], 2),  # AUM proxy until absolute-CLV model
                "churn_prob": m["churn"],
                "aum": _fmt_k(m["aum"]),
                "rm": None,
                "days_since_contact": m["days_since_contact"],
                "churn_confidence": None,
                "clv_confidence": None,
                "churn_drivers": [],        # per-customer reason codes: /insights/reason-codes/{id}
            })

        return {
            "summary": {
                "total_clv": round(total_clv, 2),
                "avg_clv": round(total_clv / len(merged), 2) if merged else 0.0,
                "high_value_count": sum(b["count"] for b in bands[:2]),
                "clv_at_risk": round(clv_at_risk, 2),
                "value_protected_mtd": round(float(total_protected), 2),
                "churn_adjusted_clv": round(churn_adjusted, 2),
                "at_risk_churn_threshold": round(cutoff, 4),
            },
            "bands": bands,
            "top_customers": top_customers,
            "data_sources": ["prediction-service:8004", "etl_clean.customer_features", "decision_outcomes"],
        }

    # ------------------------------------------------------------------
    # /states/lifecycle-stages
    # ------------------------------------------------------------------

    def lifecycle_stages(self, as_of: date) -> dict:
        return self._cached(f"life:{as_of}", lambda: self._build_lifecycle(as_of))

    def _build_lifecycle(self, as_of: date) -> dict:
        counts_rows = self._q(
            f"""
            SELECT state, COUNT(*) AS n FROM customer_states
            WHERE as_of_date = %(d)s
            {live_customer_filter("customer_states.customer_id")}
            GROUP BY state
            """,
            {"d": as_of}, "state_counts")
        counts = {r["state"]: int(r["n"]) for r in counts_rows}
        total = sum(counts.values()) or 1

        prev_rows = self._q(
            f"""
            SELECT state, COUNT(*) AS n FROM customer_states
            WHERE as_of_date = (SELECT MAX(as_of_date) FROM customer_states WHERE as_of_date < %(d)s)
            {live_customer_filter("customer_states.customer_id")}
            GROUP BY state
            """, {"d": as_of}, "prev_counts")
        prev = {r["state"]: int(r["n"]) for r in prev_rows}

        distribution = []
        for stage in ["NEW", "GROWING", "ACTIVE", "AT_RISK", "DORMANT", "CHURNED"]:
            label, color, bg, dot = _STAGE_META.get(stage, (stage.title(), "text-gray-600", "bg-gray-100", "bg-gray-500"))
            n = counts.get(stage, 0)
            distribution.append({
                "stage": stage, "label": label, "count": n,
                "pct": round(n / total * 100, 1),
                "mom_delta": n - prev.get(stage, 0),
                "color": color, "bg": bg, "dot": dot,
            })

        trows = self._q(
            f"""
            SELECT from_state, to_state, COUNT(*) AS n
            FROM state_transitions
            WHERE transition_date >= %(d)s - 30 AND transition_date <= %(d)s
            {live_customer_filter("state_transitions.customer_id")}
            GROUP BY from_state, to_state
            """, {"d": as_of}, "transitions")
        states = ["NEW", "GROWING", "ACTIVE", "AT_RISK", "DORMANT", "CHURNED"]
        idx = {s: i for i, s in enumerate(states)}
        matrix = [[0] * len(states) for _ in states]
        for r in trows:
            i, j = idx.get(r["from_state"]), idx.get(r["to_state"])
            if i is not None and j is not None:
                matrix[i][j] = int(r["n"])

        onboard = self._q(
            f"""
            SELECT
              COUNT(*) FILTER (WHERE customer_tenure_days <= 90) AS total_new,
              COUNT(*) FILTER (WHERE customer_tenure_days <= 90 AND txn_count_30d > 0) AS activated_30d,
              COUNT(*) FILTER (WHERE customer_tenure_days <= 90 AND txn_count_90d > 0) AS activated_90d,
              COALESCE(AVG(rel_products_owned), 0) AS avg_products,
              COUNT(*) FILTER (WHERE eng_login_count_30d > 0) AS digital_enrolled,
              COUNT(*) AS total_cust
            FROM customer_features WHERE as_of_date = %(d)s
            {live_customer_filter("customer_features.customer_id")}
            """, {"d": as_of}, "onboarding")[0]
        onboarding = {
            "total_new": int(onboard["total_new"]),
            "activated_30d": int(onboard["activated_30d"]),
            "activated_60d": int(onboard["activated_30d"]),  # 60d window not tracked; 30d repeated
            "activated_90d": int(onboard["activated_90d"]),
            "early_at_risk": counts.get("AT_RISK", 0),
            "avg_products": round(float(onboard["avg_products"]), 2),
            "digital_enrolled": round(
                int(onboard["digital_enrolled"]) / max(int(onboard["total_cust"]), 1) * 100, 1),
        }

        win_back = self._build_winback(as_of)

        return {
            "distribution": distribution,
            "transitions": {"stages": states, "matrix": matrix, "window_days": 30},
            "onboarding": onboarding,
            "win_back": win_back,
            "data_sources": ["etl_clean.customer_states", "etl_clean.state_transitions",
                             "etl_clean.customer_features"],
        }

    def _build_winback(self, as_of: date, limit: int = 20) -> list[dict]:
        rows = self._q(
            f"""
            SELECT cs.customer_id,
                   COALESCE((cs.as_of_date - st.transition_date), 0) AS days_since_churn,
                   COALESCE(f.total_amount_180d, 0) AS value_180d,
                   f.rel_products_owned
            FROM customer_states cs
            LEFT JOIN LATERAL (
                SELECT transition_date FROM state_transitions t
                WHERE t.customer_id = cs.customer_id AND t.to_state = 'CHURNED'
                ORDER BY transition_date DESC LIMIT 1
            ) st ON TRUE
            LEFT JOIN LATERAL (
                SELECT total_amount_180d, rel_products_owned FROM customer_features f
                WHERE f.customer_id = cs.customer_id AND f.as_of_date = cs.as_of_date LIMIT 1
            ) f ON TRUE
            WHERE cs.state = 'CHURNED' AND cs.as_of_date = %(d)s
            {live_customer_filter("cs.customer_id")}
            ORDER BY 3 DESC NULLS LAST
            LIMIT %(lim)s
            """, {"d": as_of, "lim": limit}, "winback")

        values = sorted(float(r["value_180d"] or 0) for r in rows)
        n = len(values)
        out = []
        for r in rows:
            v = float(r["value_180d"] or 0)
            pct = (sum(1 for x in values if x < v) / n) if n else 0.0
            months = (r["days_since_churn"] or 0) / 30.44
            prob = round(pct * (1 - min(months / 12, 1.0)), 4)
            out.append({
                "customer_id": r["customer_id"],
                "name": r["customer_id"],
                "last_product": r.get("rel_products_owned") or "Unknown",
                "months_churned": round(months, 1),
                "est_value": _fmt_k(v),
                "status": "ELIGIBLE" if months <= 6 and prob > 0.40 else "INELIGIBLE",
                "prob": prob,
            })
        out.sort(key=lambda w: -w["prob"])
        return out

    # ------------------------------------------------------------------
    # Branch Manager — At-Risk Case List
    # ------------------------------------------------------------------

    # Market segments that belong to RM-managed tracks in this pilot
    _RM_SEGMENTS: frozenset[int] = frozenset({30, 50, 60, 85})

    def at_risk_cases(self, as_of: date, limit: int = 50) -> list[dict]:
        """Top at-risk customers ranked by erosion_probability.

        JOINs customer_states → customers_clean → customer_features to
        surface branch_code, AUM proxy, and days_since_last_txn.
        Returns a track field: 'rm' for RM-managed segments, 'branch' for
        campaign-managed segments.
        """
        sql = f"""
            SELECT
                cs.customer_id,
                cs.state,
                cs.health_score,
                cs.erosion_probability,
                COALESCE(cc.branch_code, 'BR000') AS branch_code,
                COALESCE(CAST(NULLIF(cf.market_segment, '') AS INT), 0) AS segment_code,
                COALESCE(cf.total_amount_90d, 0)   AS total_amount_90d,
                COALESCE(cf.days_since_last_txn, 0) AS days_since_last_txn
            FROM customer_states cs
            LEFT JOIN customers_clean    cc ON cc.customer_id = cs.customer_id
            LEFT JOIN customer_features  cf ON cf.customer_id = cs.customer_id
                                           AND cf.as_of_date  = cs.as_of_date
            WHERE cs.as_of_date = %(as_of)s
              AND cs.state IN ('AT_RISK', 'DORMANT', 'CHURNED')
            {live_customer_filter("cs.customer_id")}
            ORDER BY cs.erosion_probability DESC NULLS LAST
            LIMIT %(limit)s
        """
        rows = self._q(sql, {"as_of": as_of, "limit": limit}, "at_risk_cases")
        out = []
        for r in rows:
            seg = int(r.get("segment_code") or 0)
            track = "rm" if seg in self._RM_SEGMENTS else "branch"
            ep    = float(r.get("erosion_probability") or 0.0)
            aum   = float(r.get("total_amount_90d") or 0.0)
            out.append({
                "id":               r["customer_id"],
                "name":             r["customer_id"],
                "state":            r["state"],
                "health_score":     float(r.get("health_score") or 0.0),
                "prob":             round(ep * 100, 1),          # 0-100 display
                "erosion_probability": round(ep, 4),
                "aum":              _fmt_k(aum),
                "aum_raw":          aum,
                "days_flagged":     int(r.get("days_since_last_txn") or 0),
                "branch_code":      r.get("branch_code") or "BR000",
                "track":            track,
                "segment_code":     seg,
            })
        return out

    # ------------------------------------------------------------------
    # Branch Manager — Unenrolled High-Risk Customers
    # ------------------------------------------------------------------

    def unenrolled_high_risk(self, as_of: date, limit: int = 20) -> list[dict]:
        """AT_RISK customers with no pilot_action_log entry (unenrolled).

        Uses LEFT JOIN with pilot_action_log — customers with no matching
        action are the unenrolled population.
        """
        sql = f"""
            SELECT
                cs.customer_id,
                cs.erosion_probability,
                cs.state,
                COALESCE(CAST(NULLIF(cf.market_segment, '') AS INT), 0) AS segment_code,
                COALESCE(cf.days_since_last_txn, 0) AS days_since_last_txn
            FROM customer_states cs
            LEFT JOIN customer_features  cf  ON cf.customer_id = cs.customer_id
                                             AND cf.as_of_date  = cs.as_of_date
            LEFT JOIN pilot_action_log   pal ON pal.customer_id = cs.customer_id
            WHERE cs.as_of_date = %(as_of)s
              AND cs.state       = 'AT_RISK'
              AND cs.erosion_probability > 0.35
              AND pal.customer_id IS NULL
            {live_customer_filter("cs.customer_id")}
            ORDER BY cs.erosion_probability DESC NULLS LAST
            LIMIT %(limit)s
        """
        rows = self._q(sql, {"as_of": as_of, "limit": limit}, "unenrolled_high_risk")
        out = []
        for r in rows:
            seg = int(r.get("segment_code") or 0)
            ep  = float(r.get("erosion_probability") or 0.0)
            out.append({
                "id":               r["customer_id"],
                "name":             r["customer_id"],
                "segment_code":     seg,
                "prob":             round(ep * 100, 1),
                "erosion_probability": round(ep, 4),
                "days_flagged":     int(r.get("days_since_last_txn") or 0),
                "state":            r["state"],
            })
        return out

    # ------------------------------------------------------------------
    # Branch Manager — Aggregate Priority Actions
    # ------------------------------------------------------------------

    def priority_actions(self, as_of: date) -> list[dict]:
        """Compute AI priority action summary from real aggregate data."""
        sql = f"""
            SELECT
                cs.state,
                COALESCE(CAST(NULLIF(cf.market_segment, '') AS INT), 0) AS segment_code,
                COUNT(*) AS cnt,
                AVG(cs.erosion_probability) AS avg_ep,
                COUNT(pal.customer_id) AS actioned_cnt
            FROM customer_states cs
            LEFT JOIN customer_features cf  ON cf.customer_id = cs.customer_id
                                           AND cf.as_of_date  = cs.as_of_date
            LEFT JOIN pilot_action_log  pal ON pal.customer_id = cs.customer_id
            WHERE cs.as_of_date = %(as_of)s
              AND cs.state IN ('AT_RISK', 'DORMANT')
            {live_customer_filter("cs.customer_id")}
            GROUP BY cs.state, segment_code
        """
        rows = self._q(sql, {"as_of": as_of}, "priority_actions")

        rm_unactioned = 0
        branch_unactioned = 0
        for r in rows:
            seg       = int(r.get("segment_code") or 0)
            cnt       = int(r.get("cnt") or 0)
            actioned  = int(r.get("actioned_cnt") or 0)
            unactioned = cnt - actioned
            if seg in self._RM_SEGMENTS:
                rm_unactioned += unactioned
            else:
                branch_unactioned += unactioned

        actions = []
        if rm_unactioned > 0:
            actions.append({
                "urgency":       "URGENT",
                "urgency_class": "bg-red-100 text-absa-passion",
                "title":         f"{rm_unactioned} RM-managed clients with no recorded action",
                "detail":        "High-value accounts at churn risk with no RM outreach logged. Assign immediately.",
                "meta":          f"{rm_unactioned} RM-managed",
            })
        if branch_unactioned > 0:
            actions.append({
                "urgency":       "HIGH",
                "urgency_class": "bg-amber-100 text-amber-700",
                "title":         f"{branch_unactioned} branch-managed customers with no campaign enrolment",
                "detail":        "At-risk branch-track customers not enrolled in any retention campaign.",
                "meta":          f"{branch_unactioned} branch-managed",
            })
        return actions


# Singleton
portfolio_views = PortfolioViews()
