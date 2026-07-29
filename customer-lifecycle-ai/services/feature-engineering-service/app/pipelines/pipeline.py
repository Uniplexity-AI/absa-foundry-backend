"""
Feature Pipeline Orchestrator — runs all domain generators in dependency order.

Pipeline DAG:
    Phase 1 SQL (repo.compute_batch) — transaction aggregates
        ↓
    7 domain generators (single shared connection, independent commits).

    Domain 5 (RelationshipGenerator) now includes 5 stages across 5 clean tables:
        customers_clean → rel_customer_status
        accounts_clean  → rel_accounts_active, rel_has_savings, rel_products_owned
        loans_clean     → rel_has_loan
        cards_clean     → rel_has_card, rel_card_count, rel_has_unactivated_card,
                           rel_card_expiring_30d, rel_card_types
        digital_engagement_clean → eng_login_count_7d/30d, eng_platform_preference,
                                     eng_avg_session_duration_30d

    Idempotent by design — re-running produces identical results.
"""

from __future__ import annotations

import logging
import time
from datetime import date

import psycopg2

from app.repository.repository import FeatureRepository
from app.features.customer.generator import CustomerProfileGenerator
from app.features.behaviour.generator import BehaviourGenerator
from app.features.financial.generator import FinancialGenerator
from app.features.channel.generator import ChannelGenerator
from app.features.temporal.generator import TemporalGenerator
from app.features.risk.generator import RiskGenerator
from app.features.relationship.generator import RelationshipGenerator

logger = logging.getLogger("feature_engineering.pipeline")


def _run_quality_check(repo: FeatureRepository, as_of_date: date) -> dict:
    """Post-run: scan for dead features (ALL_ZERO or 100% NULL).

    Returns a summary dict with flagged_features count and list.
    Does NOT block the pipeline — failures are logged, not raised.
    """
    try:
        conn = repo._connect()
        cur = conn.cursor()
        table = "customer_features"  # TODO: use shared config

        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = %s AND table_schema = 'public' "
            "AND data_type IN ('integer','bigint','smallint','numeric','real','double precision')",
            (table,),
        )
        all_cols = {r[0] for r in cur.fetchall()}

        skip = {"customer_id", "as_of_date", "created_at", "updated_at", "computed_at"}
        flagged = []

        for col in sorted(all_cols - skip):
            cur.execute(f"""
                SELECT
                    COUNT(*) FILTER (WHERE "{col}" IS NULL) AS nulls,
                    COUNT(*) FILTER (WHERE "{col}" = 0) AS zeros,
                    COUNT(*) AS total
                FROM {table}
                WHERE as_of_date = %s
            """, (as_of_date,))
            nulls, zeros, total = cur.fetchone()
            if total == 0:
                continue
            if nulls == total:
                flagged.append({"feature": col, "issue": "ALL_NULL"})
            elif zeros == total:
                flagged.append({"feature": col, "issue": "ALL_ZERO"})

        conn.close()

        if flagged:
            logger.warning(
                "Quality check: %d dead features detected on %s: %s",
                len(flagged), as_of_date,
                ", ".join(f["feature"] for f in flagged[:10]),
            )
        else:
            logger.info("Quality check: all features populated on %s", as_of_date)

        return {
            "scanned": len(all_cols) - len(skip),
            "dead_features": len(flagged),
            "flagged": flagged,
        }
    except Exception as e:
        logger.warning("Quality check skipped: %s", e)
        return {"scanned": 0, "dead_features": 0, "flagged": [], "error": str(e)}


class FeaturePipeline:
    """Orchestrates all domain generators in dependency order."""

    def __init__(self, repo: FeatureRepository) -> None:
        self._repo = repo

    def run(self, as_of_date: date | None = None) -> dict:
        """Execute the full feature pipeline.

        Each stage commits independently (idempotent by design).
        If a stage fails, previous stages remain committed — re-running
        the pipeline will skip already-computed features and complete
        the remaining stages.

        Args:
            as_of_date: Date to compute features as-of (default: today).

        Returns:
            Dict with timing and row counts per stage.
        """
        effective_date = as_of_date or date.today()
        t0 = time.time()
        stages = {}
        logger.info("Pipeline started for %s", effective_date.isoformat())

        # Stage 0: Phase 1 transaction aggregates (existing)
        t_start = time.time()
        phase1 = self._repo.compute_batch(effective_date)
        stages["phase1"] = {**phase1, "duration_seconds": round(time.time() - t_start, 2)}
        logger.info("  Phase 1: %d customers, %d upserted (%.1fs)",
                     phase1.get("customers_processed", 0),
                     phase1.get("rows_upserted", 0),
                     stages["phase1"]["duration_seconds"])

        # Stages 1-7: Domain generators (single shared connection)
        conn = psycopg2.connect(self._repo._conn_str)
        try:
            generators = {
                "profile":      CustomerProfileGenerator(conn),
                "behaviour":    BehaviourGenerator(conn),
                "financial":    FinancialGenerator(conn),
                "channel":      ChannelGenerator(conn),
                "temporal":     TemporalGenerator(conn),
                "risk":         RiskGenerator(conn),
                "relationship": RelationshipGenerator(conn),
                # Note: Card + Engagement features are folded into RelationshipGenerator
                # (Stages 4 & 5) since they read from cards_clean + digital_engagement_clean.
            }

            for name, gen in generators.items():
                t_start = time.time()
                try:
                    row_counts = gen.generate(effective_date)
                except Exception as e:
                    logger.error("  %s FAILED: %s — rolling back", name, e)
                    conn.rollback()
                    stages[name] = {
                        "error": str(e),
                        "duration_seconds": round(time.time() - t_start, 2),
                    }
                    continue

                stages[name] = {
                    **row_counts,
                    "duration_seconds": round(time.time() - t_start, 2),
                }
                logger.info("  %s: %s (%.1fs)", name, row_counts, stages[name]["duration_seconds"])
        finally:
            conn.close()

        total_dur = round(time.time() - t0, 2)
        has_errors = any("error" in s for s in stages.values())
        logger.info("Pipeline complete: %s (%.1fs)", "PARTIAL" if has_errors else "COMPLETED", total_dur)

        # ── Post-run: feature quality summary ──
        quality = _run_quality_check(self._repo, effective_date)

        return {
            "as_of_date": effective_date.isoformat(),
            "status": "PARTIAL" if has_errors else "COMPLETED",
            "total_duration_seconds": total_dur,
            "stages": stages,
            "quality": quality,
        }
