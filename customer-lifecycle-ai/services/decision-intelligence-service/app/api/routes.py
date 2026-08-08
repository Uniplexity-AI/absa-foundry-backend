"""Decision Intelligence Platform — API Routes v3.0.

Decision Engine (/decisions) + Customer Intelligence (/customer-intel).
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query

from app.schemas.schemas import (
    BatchDecisionResponse, CustomerIntelligence, DecisionPackage,
    ExecutionRequest, OutcomeRequest,
)
from app.services.service import DecisionService
from app.services.customer_intelligence_service import customer_intel_service

router = APIRouter(prefix="/decisions", tags=["decisions"])
customer_intel_router = APIRouter(prefix="/customer-intel", tags=["customer-intel"])
_service = DecisionService()


# ===========================================================================
# Decision Engine
# ===========================================================================

@router.post("/compute", response_model=BatchDecisionResponse)
def compute_batch(
    as_of_date: date | None = Query(default=None),
    strategy: str = Query(default="BALANCED"),
    max_customers: int | None = Query(default=None),
) -> BatchDecisionResponse:
    return _service.compute_batch(as_of_date, strategy, max_customers)


@router.get("/digital-retention")
def get_digital_retention(limit: int = Query(default=20)):
    """Which customers can be retained digitally vs need RM attention?"""
    from app.context.builder import build_decision_context
    from app.engines.action_generator import ActionGenerator
    from app.engines.ranking_engine import RankingEngine
    from app.engines.routing_engine import RoutingEngine

    action_gen = ActionGenerator(); ranker = RankingEngine(); router = RoutingEngine()
    digital, rm_required = [], []
    for cid in [f"CUST{i:05d}" for i in range(1, min(limit + 1, 500))]:
        try:
            ctx = build_decision_context(cid, date.today())
            if ctx.kyc_expired or ctx.aml_flag: continue
            candidates = action_gen.generate()
            eligible = [c for c in candidates if c.category != "passive"]
            if not eligible: continue
            ranked = ranker.rank(eligible, ctx, top_n=3)
            r = router.route(ranked[0], ctx)
            entry = {"customer_id": cid, "state": ctx.customer_state, "health_score": ctx.health_score,
                     "churn_probability": round(ctx.churn_probability, 3), "top_action": ranked[0].action,
                     "segment": ctx.segment, "channel": r.channel, "reason": r.reason}
            if r.channel in ("DIGITAL", "MARKETING"): digital.append(entry)
            elif r.channel in ("RM_DIRECT", "RM_CALL"): rm_required.append(entry)
        except Exception: pass

    total = len(digital) + len(rm_required)
    return {
        "total_evaluated": min(limit + 1, 500),
        "digital_retention_candidates": len(digital),
        "rm_attention_required": len(rm_required),
        "digital_customers": digital[:10],
        "rm_customers": rm_required[:5],
        "recommendation": f"Of evaluated: {len(digital)} digital-retainable, {len(rm_required)} need RM. Digital = ~{round(len(digital)/total*100) if total else 0}% workload reduction.",
    }


@router.get("/queue/{rm_id}")
def get_queue(rm_id: str, limit: int = Query(default=20)):
    batch = _service.compute_batch(None, "BALANCED", max_customers=limit)
    return {"rm_id": rm_id, "queue_size": batch.decisions_generated, "limit": limit}


@router.get("/{customer_id}", response_model=DecisionPackage)
def get_decision(
    customer_id: str,
    as_of_date: date = Query(...),
    strategy: str = Query(default="BALANCED"),
) -> DecisionPackage:
    result = _service.compute_for_customer(customer_id, as_of_date, strategy)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No decision for {customer_id}")
    return result


@router.get("/queue/{rm_id}")
def get_queue(rm_id: str, limit: int = Query(default=20)):
    batch = _service.compute_batch(None, "BALANCED", max_customers=limit)
    return {"rm_id": rm_id, "queue_size": batch.decisions_generated, "limit": limit}


@router.post("/{customer_id}/execute")
def execute_decision(customer_id: str, body: ExecutionRequest):
    return {"status": "logged", "customer_id": customer_id, "rm_id": body.rm_id}


@router.patch("/{decision_id}/outcome")
def record_outcome(decision_id: str, body: OutcomeRequest):
    return {"status": "recorded", "decision_id": decision_id, "outcome": body.outcome}


@router.get("/strategies/list")
def list_strategies():
    from app.engines.strategy_layer import StrategyLayer
    return {"strategies": StrategyLayer.list_strategies()}


# ===========================================================================
# Customer Intelligence
# ===========================================================================

@customer_intel_router.get("/alerts/{customer_id}")
def get_alerts(customer_id: str, as_of_date: date | None = Query(default=None)):
    result = customer_intel_service.analyze(customer_id, as_of_date)
    if result is None:
        raise HTTPException(status_code=404)
    return {"customer_id": customer_id, "count": len(result.alerts),
            "alerts": [a.model_dump() for a in result.alerts]}


@customer_intel_router.get("/trajectory/{customer_id}")
def get_trajectory(customer_id: str, as_of_date: date | None = Query(default=None)):
    result = customer_intel_service.analyze(customer_id, as_of_date)
    if result is None:
        raise HTTPException(status_code=404)
    ht = result.health_trajectory
    return {"trajectory": ht.trajectory if ht else "UNKNOWN",
            "score": ht.current_score if ht else 0}


# ===========================================================================
# Recommendation Engine (NBO)
# ===========================================================================

recommendation_router = APIRouter(prefix="/recommendations", tags=["recommendations"])

from app.engines.recommendation_engine.product_propensity import ProductPropensityScorer
from app.engines.recommendation_engine.cross_sell_logic import CrossSellLogic
from app.engines.recommendation_engine.upsell_logic import UpsellLogic
from app.engines.recommendation_engine.campaign_mapper import CampaignMapper
from app.schemas.schemas import RecommendationResponse, CampaignTargetList

_propensity = ProductPropensityScorer()
_cross_sell = CrossSellLogic()
_upsell = UpsellLogic()
_campaigns = CampaignMapper()


@recommendation_router.get("/{customer_id}", response_model=RecommendationResponse)
def get_recommendations(
    customer_id: str,
    as_of_date: date = Query(...),
) -> RecommendationResponse:
    """Generate product recommendations for one customer."""
    from app.context.builder import build_decision_context
    ctx = build_decision_context(customer_id, as_of_date)

    # Step 1: Base propensity scores
    scored = _propensity.score(ctx)

    # Step 2: Apply cross-sell rules
    scored, cross_sell_applied = _cross_sell.apply(scored, ctx)

    # Step 3: Apply upsell logic
    scored = _upsell.apply(scored, ctx)

    # Step 4: Map to campaigns
    enriched = _campaigns.map_recommendations(scored, ctx)

    return RecommendationResponse(
        customer_id=customer_id,
        as_of_date=as_of_date,
        recommendations=[dict(r) for r in enriched],
        cross_sell_rules_applied=cross_sell_applied,
    )


@recommendation_router.get("/campaigns/list", response_model=CampaignTargetList)
def get_campaign_targets(
    segment: str | None = Query(default=None),
    limit: int = Query(default=1000),
) -> CampaignTargetList:
    """List active campaigns with target audience info."""
    campaigns = _campaigns.get_campaign_target_list(segment, limit)
    return CampaignTargetList(campaigns=campaigns, total_campaigns=len(campaigns))


# ===========================================================================
# Insight & Explanation Engine
# ===========================================================================

insight_router = APIRouter(prefix="/insights", tags=["insights"])

from app.engines.insight_engine.reason_code_generator import ReasonCodeGenerator
from app.engines.insight_engine.explanation_composer import ExplanationComposer
from app.schemas.schemas import ExplanationResponse

_reason_gen = ReasonCodeGenerator()
_explainer = ExplanationComposer()


@insight_router.get("/reason-codes/{customer_id}")
def get_reason_codes(
    customer_id: str,
    as_of_date: date = Query(...),
):
    """Get structured reason codes for a customer."""
    from app.context.builder import build_decision_context
    ctx = build_decision_context(customer_id, as_of_date)
    codes = _reason_gen.generate(ctx)
    return {"customer_id": customer_id, "reason_codes": [c.model_dump() for c in codes]}


@insight_router.get("/explain-decision/{decision_id}")
def explain_decision(decision_id: str):
    """Explain a previously computed decision."""
    result = _explainer.explain(decision_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No decision: {decision_id}")
    return result


@insight_router.get("/llm-explain/{customer_id}")
def llm_explain_customer(
    customer_id: str,
    as_of_date: date = Query(...),
):
    """Generate LLM explanation for a customer's situation."""
    from app.context.builder import build_decision_context
    from app.engines.insight_engine.llm_gateway import LLMGateway

    ctx = build_decision_context(customer_id, as_of_date)
    llm = LLMGateway()

    # Generate reason codes first (deterministic)
    reason_codes = _reason_gen.generate(ctx)
    code_names = [c.code for c in reason_codes]

    # Get decision (NBA)
    result = _service.compute_for_customer(customer_id, as_of_date)
    top_action = result.top_actions[0].action if result and result.top_actions else "MONITOR"
    top_action_score = result.top_actions[0].score if result and result.top_actions else 0

    # Generate LLM explanation
    explanation = llm.explain_decision(
        customer_id=customer_id,
        customer_state=ctx.customer_state,
        health_score=ctx.health_score,
        churn_probability=ctx.churn_probability,
        top_action=f"{top_action} (score: {top_action_score:.0f})",
        reason_codes=code_names,
    )

    return {
        "customer_id": customer_id,
        "as_of_date": as_of_date,
        "llm_available": llm.is_available,
        "model": "qwen2.5-coder:7b",
        "deterministic_codes": [c.model_dump() for c in reason_codes],
        "llm_explanation": explanation,
        "top_action": top_action,
        "top_action_score": top_action_score,
    }


@customer_intel_router.get("/{customer_id}", response_model=CustomerIntelligence)
def get_customer_intelligence(
    customer_id: str,
    as_of_date: date | None = Query(default=None),
) -> CustomerIntelligence:
    result = customer_intel_service.analyze(customer_id, as_of_date)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No data for {customer_id}")
    return result


# ===========================================================================
# Churn Intelligence
# ===========================================================================

churn_intel_router = APIRouter(prefix="/churn-intel", tags=["churn-intel"])


@churn_intel_router.get("/drivers")
def get_churn_drivers(as_of_date: date | None = Query(default=None)):
    """Top churn drivers across the portfolio."""
    from app.engines.churn_intelligence.root_cause import analyze_root_causes
    drivers = analyze_root_causes(as_of_date)
    return {"as_of_date": as_of_date or date.today(), "drivers": [d.model_dump() for d in drivers]}


@churn_intel_router.get("/segments")
def get_segment_analysis(as_of_date: date | None = Query(default=None)):
    """Segment-level churn deterioration analysis."""
    from app.engines.churn_intelligence.segment_analyzer import analyze_segments
    segments = analyze_segments(as_of_date)
    return {"as_of_date": as_of_date or date.today(), "segments": segments}


@churn_intel_router.get("/branches")
def get_branch_analysis(as_of_date: date | None = Query(default=None)):
    """Branch-level churn performance rankings."""
    from app.engines.churn_intelligence.branch_analyzer import analyze_branches
    branches = analyze_branches(as_of_date)
    return {"as_of_date": as_of_date or date.today(), "branches": branches}


# ===========================================================================
# Forecast
# ===========================================================================

forecast_router = APIRouter(prefix="/forecasts", tags=["forecasts"])


@forecast_router.get("/churn")
def get_churn_forecast(as_of_date: date | None = Query(default=None), horizon_days: int = Query(default=90)):
    """Portfolio churn forecast for the given horizon."""
    from app.engines.forecast_engine.churn_forecast import forecast_churn
    return forecast_churn(as_of_date, horizon_days)


@forecast_router.get("/revenue-at-risk")
def get_revenue_at_risk(as_of_date: date | None = Query(default=None), horizon_days: int = Query(default=90)):
    """Estimated revenue at risk (ZMW) from projected churn."""
    from app.engines.forecast_engine.revenue_at_risk import forecast_revenue_at_risk
    return forecast_revenue_at_risk(as_of_date, horizon_days)
