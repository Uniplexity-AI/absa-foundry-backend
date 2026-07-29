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

        return {
            "as_of_date": effective_date.isoformat(),
            "status": "PARTIAL" if has_errors else "COMPLETED",
            "total_duration_seconds": total_dur,
            "stages": stages,
        }
