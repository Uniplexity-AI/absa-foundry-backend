"""
Feature Pipeline Orchestrator — runs all 4 domain generators in dependency order.

Pipeline DAG:
    Phase 1 SQL (repo.compute_batch) — transaction aggregates
        ↓
    Generator 1: Customer Profile (customers_clean → features)
        ↓
    Generator 2: Behaviour (transactions + features → features)
        ↓
    Generator 3: Financial (transactions + features → features)
        ↓
    Generator 4: Channel (transactions → features)

Stages 2, 3, 4 can run in parallel after Stage 0 (future optimization).
"""

from __future__ import annotations

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


class FeaturePipeline:
    """Orchestrates all domain generators in dependency order."""

    def __init__(self, repo: FeatureRepository) -> None:
        self._repo = repo

    def run(self, as_of_date: date | None = None) -> dict:
        """Execute the full feature pipeline.

        Args:
            as_of_date: Date to compute features as-of (default: today).

        Returns:
            Dict with timing and row counts per stage.
        """
        effective_date = as_of_date or date.today()
        t0 = time.time()
        stages = {}

        # Stage 0: Phase 1 transaction aggregates (existing)
        t_start = time.time()
        phase1 = self._repo.compute_batch(effective_date)
        stages["phase1"] = {**phase1, "duration_seconds": round(time.time() - t_start, 2)}

        # Stages 1-4: Domain generators (single shared connection)
        conn = psycopg2.connect(self._repo._conn_str)
        try:
            generators = {
                "profile":   CustomerProfileGenerator(conn),
                "behaviour": BehaviourGenerator(conn),
                "financial": FinancialGenerator(conn),
                "channel":   ChannelGenerator(conn),
                "temporal":  TemporalGenerator(conn),
                "risk":      RiskGenerator(conn),                "relationship": RelationshipGenerator(conn),            }

            for name, gen in generators.items():
                t_start = time.time()
                row_counts = gen.generate(effective_date)
                stages[name] = {
                    **row_counts,
                    "duration_seconds": round(time.time() - t_start, 2),
                }
        finally:
            conn.close()

        return {
            "as_of_date": effective_date.isoformat(),
            "status": "COMPLETED",
            "total_duration_seconds": round(time.time() - t0, 2),
            "stages": stages,
        }
