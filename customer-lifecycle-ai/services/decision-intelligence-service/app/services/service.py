"""Decision Service — orchestrates the full decision pipeline.

Context → Eligibility → Rules → Actions → Rank → Strategy → Optimize → Route → Approve → Compose
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime

from app.context.builder import build_decision_context
from app.engines.eligibility_engine import EligibilityEngine
from app.engines.business_rules_engine import BusinessRulesEngine
from app.engines.action_generator import ActionGenerator
from app.engines.ranking_engine_lgbm import LGBMRankingEngine
from app.engines.strategy_layer import StrategyLayer
from app.engines.optimization_engine import OptimizationEngine
from app.engines.routing_engine import RoutingEngine
from app.engines.approval_workflow import ApprovalWorkflow
from app.engines.composer import DecisionComposer
from app.schemas.schemas import (
    BatchDecisionResponse, CandidateAction, DecisionPackage, PolicyResult,
)

logger = logging.getLogger("decision.service")

ALL_CUSTOMER_IDS = [f"CUST{i:05d}" for i in range(1, 4999)]


class DecisionService:
    """Orchestrates the full decision pipeline."""

    def __init__(self) -> None:
        self._eligibility = EligibilityEngine()
        self._rules = BusinessRulesEngine()
        self._action_gen = ActionGenerator()
        self._ranking = LGBMRankingEngine()
        self._strategy = StrategyLayer()
        self._optimization = OptimizationEngine()
        self._routing = RoutingEngine()
        self._approval = ApprovalWorkflow()
        self._composer = DecisionComposer()
        logger.info("DecisionService initialized — 9 engines loaded")

    def compute_for_customer(
        self, customer_id: str, as_of_date: date | None = None, strategy: str = "BALANCED"
    ) -> DecisionPackage | None:
        if as_of_date is None:
            as_of_date = date.today()

        context = build_decision_context(customer_id, as_of_date)

        eligibility = self._eligibility.evaluate(context)
        if not eligibility.is_eligible:
            return DecisionPackage(
                customer_id=customer_id, as_of_date=as_of_date,
                decision_id=f"DEC-INELIGIBLE-{customer_id}",
                status="REJECTED", reason_codes=eligibility.reasons,
                strategy=strategy, computed_at=datetime.utcnow(),
            )

        policy = self._rules.apply(context)
        all_candidates = self._action_gen.generate()
        eligible = self._filter(all_candidates, eligibility, policy, context)

        ranked = self._ranking.rank(eligible, context, top_n=5)
        self._strategy.set_strategy(strategy)
        ranked = self._strategy.apply(ranked)
        ranked = self._optimization.optimize(ranked, context)

        routing = self._routing.route(ranked[0], context) if ranked else None
        approval = self._approval.check(context, ranked[0]) if ranked else None

        return self._composer.compose(context, ranked, routing, approval, strategy)

    def compute_batch(
        self, as_of_date: date | None = None, strategy: str = "BALANCED",
        max_customers: int | None = None,
    ) -> BatchDecisionResponse:
        if as_of_date is None:
            as_of_date = date.today()
        t0 = time.perf_counter()
        customers = ALL_CUSTOMER_IDS[:max_customers] if max_customers else ALL_CUSTOMER_IDS
        generated = 0
        for cid in customers:
            try:
                result = self.compute_for_customer(cid, as_of_date, strategy)
                if result and result.status != "REJECTED":
                    generated += 1
            except Exception:
                logger.exception("Failed for %s", cid)
        duration = round(time.perf_counter() - t0, 2)
        return BatchDecisionResponse(
            as_of_date=as_of_date, customers_processed=len(customers),
            decisions_generated=generated, duration_seconds=duration, strategy=strategy,
        )

    def _filter(self, candidates, eligibility, policy: PolicyResult, context):
        blocked = set(policy.blocked_actions)
        filtered = []
        for c in candidates:
            if c.action in blocked or c.category in blocked:
                continue
            if c.category == "cross_sell" and self._already_owns(c.action, context):
                continue
            filtered.append(c)
        return filtered

    @staticmethod
    def _already_owns(action: str, context) -> bool:
        mapping = {
            "OFFER_CREDIT_CARD": "credit_card", "OFFER_PERSONAL_LOAN": "loan",
            "OFFER_MORTGAGE": "mortgage", "OFFER_INSURANCE": "insurance",
            "OFFER_INVESTMENT": "investment", "OFFER_OVERDRAFT": "overdraft",
        }
        key = mapping.get(action)
        return bool(key and context.products.get(key))
