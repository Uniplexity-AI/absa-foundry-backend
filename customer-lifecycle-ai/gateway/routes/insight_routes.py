"""Gateway route — proxies /api/v1/insights/* to Decision Intelligence (:8005).

``/llm-explain`` is the Ollama narration path. On CPU it takes ~90-120s for a
7B model, so it uses its own long timeout instead of the 30s default.
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

from shared.config.settings import settings

router = APIRouter(prefix="/api/v1/insights", tags=["insights"])

_URL = "http://127.0.0.1:8005"

# CPU narration of ~300 tokens with a 7B model needs well over the default 30s
_LLM_TIMEOUT = settings.llm_gateway_timeout_seconds


@router.get("/reason-codes/{customer_id}")
async def proxy_reason_codes(request: Request, customer_id: str):
    """Forward reason code generation query."""
    return await _forward(request, f"/insights/reason-codes/{customer_id}")


@router.get("/explain-decision/{decision_id}")
async def proxy_explain(request: Request, decision_id: str):
    """Forward decision explanation query."""
    return await _forward(request, f"/insights/explain-decision/{decision_id}")


@router.get("/llm-explain/{customer_id}")
async def proxy_llm_explain(request: Request, customer_id: str):
    """Forward the LLM narration request.

    ADR-005: the LLM only narrates the already-decided action; the rule engine
    remains the decision-maker. Expect ~1-2 min on CPU with the 7B model.
    """
    return await _forward(
        request, f"/insights/llm-explain/{customer_id}", timeout=_LLM_TIMEOUT
    )


async def _forward(
    request: Request, target_path: str, timeout: float = 30.0
) -> JSONResponse:
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            body = await request.body() if request.method in ("POST", "PUT") else None
            params = dict(request.query_params)
            resp = await client.request(
                method=request.method,
                url=f"{_URL}{target_path}",
                params=params if params else None,
                content=body,
                headers={k: v for k, v in request.headers.items()
                         if k.lower() not in ("host", "content-length")},
            )
            return JSONResponse(
                content=resp.json() if resp.content else None,
                status_code=resp.status_code,
            )
        except httpx.ConnectError:
            raise HTTPException(status_code=502, detail="Insight Engine unavailable")
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Insight Engine timed out")
