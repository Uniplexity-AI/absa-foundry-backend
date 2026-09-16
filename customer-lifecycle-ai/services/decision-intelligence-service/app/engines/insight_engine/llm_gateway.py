"""LLM Gateway — connects to Ollama for natural language generation.

ADR-005: the LLM is an ADVISOR — it only narrates a decision that was already
made by the deterministic rule engine (ActionGenerator -> RankingEngine ->
RoutingEngine). It never chooses, ranks or overrides an action.

Configuration (repo-root .env via shared.config.settings; real environment
variables take precedence):
    OLLAMA_URL                 default http://localhost:11434
    LLM_MODEL                  default qwen2.5-coder:7b  (4.7 GB, ~90-120s/narration on CPU)
                               gemma3:1b is ~10x faster if a shorter narrative is acceptable
    LLM_MAX_TOKENS             default 300
    LLM_TIMEOUT_SECONDS        default 180
"""
from __future__ import annotations

import logging
from pathlib import Path

import httpx

from shared.config.settings import settings

logger = logging.getLogger("decision.insight.llm")

_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "prompts"
_OLLAMA_URL = settings.ollama_url.rstrip("/")
_DEFAULT_MODEL = settings.llm_model
_MAX_TOKENS = settings.llm_max_tokens
_TIMEOUT = settings.llm_timeout_seconds


class LLMGateway:
    """LLM inference gateway via Ollama (narration only — ADR-005)."""

    def __init__(self, model: str | None = None) -> None:
        self._model = model or _DEFAULT_MODEL
        self._available = self._check_ollama()

    def _check_ollama(self) -> bool:
        try:
            resp = httpx.get(f"{_OLLAMA_URL}/api/tags", timeout=5.0)
            if resp.status_code == 200:
                models = [m["name"] for m in resp.json().get("models", [])]
                if self._model in models:
                    logger.info("Ollama connected: %s", self._model)
                    return True
                logger.warning("Model %s not found in %s", self._model, models)
        except Exception:
            logger.info("Ollama not running — deterministic fallback only")
        return False

    @property
    def is_available(self) -> bool:
        return self._available

    def explain_decision(
        self, customer_id: str, customer_state: str, health_score: float,
        churn_probability: float, top_action: str, reason_codes: list[str],
    ) -> str:
        """Generate RM-friendly explanation of a decision."""
        if not self._available:
            return self._fallback(customer_id, customer_state, health_score, churn_probability, top_action)

        prompt = self._fill_template("explain_decision", {
            "customer_id": customer_id,
            "customer_state": customer_state,
            "health_score": f"{health_score:.0f}",
            "churn_probability": f"{churn_probability:.0%}",
            "top_action": top_action,
            "reason_codes": ", ".join(reason_codes),
        })
        return self._generate(prompt)

    def executive_summary(
        self, period: str, total: int, at_risk: int, at_risk_pct: float,
        dormant: int, dormant_pct: float, churned: int, churned_pct: float,
        drivers: str,
    ) -> str:
        """Generate executive portfolio summary."""
        if not self._available:
            return f"Portfolio: {total:,} | At Risk: {at_risk} ({at_risk_pct:.1f}%) | Dormant: {dormant} | Churned: {churned} | LLM offline"

        prompt = self._fill_template("executive_summary", {
            "period": period,
            "total_customers": str(total),
            "at_risk_count": str(at_risk),
            "at_risk_pct": f"{at_risk_pct:.1f}",
            "dormant_count": str(dormant),
            "dormant_pct": f"{dormant_pct:.1f}",
            "churned_count": str(churned),
            "churned_pct": f"{churned_pct:.1f}",
            "churn_drivers": drivers,
            "segment_analysis": "See Churn Intelligence dashboard.",
        })
        return self._generate(prompt, max_tokens=400)

    def _generate(self, prompt: str, max_tokens: int | None = None) -> str:
        num_predict = max_tokens or _MAX_TOKENS
        try:
            resp = httpx.post(
                f"{_OLLAMA_URL}/api/generate",
                json={
                    "model": self._model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": num_predict, "temperature": 0.3},
                },
                timeout=_TIMEOUT,
            )
            if resp.status_code == 200:
                return resp.json().get("response", "").strip()
        except Exception as e:
            logger.warning("LLM generate failed: %s", e)
        return "LLM generation failed. Contact administrator."

    def _fill_template(self, name: str, ctx: dict) -> str:
        path = _PROMPTS_DIR / f"{name}.txt"
        if not path.exists():
            return f"Prompt '{name}' not found."
        text = path.read_text(encoding="utf-8")
        for k, v in ctx.items():
            text = text.replace(f"{{{k}}}", v)
        return text

    def _fallback(self, cid: str, state: str, health: float, churn: float, action: str) -> str:
        return (
            f"Customer {cid} is {state} with health {health:.0f}/100 "
            f"and {churn:.0%} churn risk. Recommended: {action}. "
            f"(LLM offline — deterministic summary)"
        )

    @property
    def health(self) -> dict:
        return {"available": self._available, "model": self._model, "url": _OLLAMA_URL}
