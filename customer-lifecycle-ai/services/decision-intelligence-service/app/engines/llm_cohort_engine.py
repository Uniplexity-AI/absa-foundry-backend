import json
import logging
from typing import Any
import ollama

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are an expert AI Marketing Strategist and Decision Engine for ABSA Bank Zambia.
Your task is to analyze a cohort of customers and generate optimal campaign strategies.

INPUT:
You will receive a JSON list of customer profiles (containing segments, churn probabilities, and CLV).

OUTPUT:
You MUST output ONLY valid JSON matching the exact schema below. Do not include markdown blocks or any other text.

SCHEMA:
{
  "cohort_drivers": [
    {
      "icon": "signal_cellular_nodata", // Material symbols: signal_cellular_nodata, account_balance_wallet, cancel_schedule_send, trending_down, warning
      "label": "Brief driver name",
      "contribution": 35, // Integer percentage contribution
      "desc": "1 short sentence including actual numerical values from data (e.g. 'Average CLV of K 15,000 indicates moderate balance')"
    }
  ],
  "campaigns": [
    {
      "id": "campaign-1",
      "rank": 1,
      "tag": "RECOMMENDED", // RECOMMENDED, HIGH VALUE, or EXPERIMENTAL
      "tagClass": "bg-green-100 text-green-700", // bg-green-100 text-green-700, bg-amber-100 text-amber-700, or bg-gray-100 text-gray-600
      "title": "Campaign Title",
      "channel": "SMS + Push Notification",
      "channelIcon": "smartphone", // smartphone, call, mark_email_unread
      "description": "1 concise sentence explaining the campaign incentive.",
      "upliftScore": 65, // Integer 1-100
      "successRate": "60%",
      "aumProtected": "K 15.5M", // Estimate based on cohort size/CLV
      "confidence": 85, // Integer 1-100
      "duration": "14 days",
      "cost": "Low" // Low, Medium, High
    }
  ]
}

RULES:
- Generate exactly 3 cohort drivers. The `desc` MUST state actual numerical values in 1 short sentence.
- Generate exactly 3 campaigns.
- Rank 1 MUST be tag "RECOMMENDED" (green). Rank 2 "HIGH VALUE" (amber). Rank 3 "EXPERIMENTAL" (gray).
- Keep all descriptions to 1 concise sentence (max 15 words) so output is compact and complete.
"""

try:
    from app.engines.llm_nba_engine import get_llama_model, HAS_LLAMA_CPP
except ImportError:
    HAS_LLAMA_CPP = False
    get_llama_model = None

try:
    import ollama
    HAS_OLLAMA = True
except ImportError:
    HAS_OLLAMA = False

class LLMCohortEngine:
    """Uses local LLM (llama-cpp by default, with ollama fallback) to generate targeted cohort campaigns."""

    def __init__(self, model_name: str = "absa-nba", backend: str = "llama-cpp"):
        self.model_name = model_name
        if backend == "llama-cpp" and not HAS_LLAMA_CPP and HAS_OLLAMA:
            self.backend = "ollama"
        else:
            self.backend = backend

    async def generate_campaigns_async(self, customers_data: list[dict[str, Any]]) -> dict[str, Any]:
        """Asynchronously evaluate a cohort to recommend campaigns."""
        if self.backend == "ollama":
            return await self._generate_ollama_async(customers_data)
        else:
            import asyncio
            return await asyncio.to_thread(self._generate_llama_cpp_sync, customers_data)

    def _generate_llama_cpp_sync(self, customers_data: list[dict[str, Any]]) -> dict[str, Any]:
        prompt = self._build_prompt(customers_data)
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]

        try:
            logger.info(f"Generating Cohort Campaigns using llama-cpp for {len(customers_data)} customers")
            from app.engines.llm_nba_engine import _LLAMA_LOCK
            llm = get_llama_model()
            with _LLAMA_LOCK:
                response = llm.create_chat_completion(
                    messages=messages,
                    temperature=0.1,
                    top_p=0.9,
                    max_tokens=600,
                    stop=["<|im_start|>", "<|im_end|>"],
                    response_format={"type": "json_object"}
                )
            result_text = response["choices"][0]["message"]["content"]
            return self._parse_cohort_json(result_text, customers_data)
        except Exception as e:
            logger.error(f"Error in LLM Cohort Engine (llama-cpp): {e}")
            return self._fallback_cohort_data(customers_data)

    def _parse_cohort_json(self, text: str, customers_data: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """Robustly parse cohort JSON, recovering partially truncated outputs or filling defaults."""
        import re
        if not text:
            return self._fallback_cohort_data(customers_data)

        # 1. Direct standard parse
        try:
            data = json.loads(text)
            if isinstance(data, dict) and "campaigns" in data and len(data.get("campaigns", [])) > 0:
                return data
        except Exception:
            pass

        # 2. Resilient partial extraction
        drivers = []
        campaigns = []

        d_match = re.search(r'"cohort_drivers"\s*:\s*\[(.*?)\]', text, re.DOTALL)
        if d_match:
            try:
                drivers = json.loads("[" + d_match.group(1) + "]")
            except Exception:
                pass

        c_match = re.search(r'"campaigns"\s*:\s*\[', text)
        if c_match:
            c_part = text[c_match.end():]
            depth = 0
            start = -1
            for i, ch in enumerate(c_part):
                if ch == '{':
                    if depth == 0:
                        start = i
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0 and start != -1:
                        try:
                            camp = json.loads(c_part[start:i+1])
                            campaigns.append(camp)
                        except Exception:
                            pass

        if drivers or campaigns:
            fallback = self._fallback_cohort_data(customers_data)
            if not drivers:
                drivers = fallback["cohort_drivers"]
            if len(campaigns) < 3:
                for fb_c in fallback["campaigns"]:
                    if not any(c.get("rank") == fb_c["rank"] for c in campaigns):
                        campaigns.append(fb_c)
            campaigns.sort(key=lambda x: x.get("rank", 99))
            return {"cohort_drivers": drivers, "campaigns": campaigns}

        return self._fallback_cohort_data(customers_data)

    def _fallback_cohort_data(self, customers_data: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        avg_churn = 0.5
        avg_clv = 15000.0
        if customers_data:
            avg_churn = sum(c.get("churn_probability", 0.5) for c in customers_data) / max(1, len(customers_data))
            avg_clv = sum(c.get("clv", 15000.0) for c in customers_data) / max(1, len(customers_data))

        return {
            "cohort_drivers": [
                {
                    "icon": "trending_down",
                    "label": "Elevated Churn Risk",
                    "contribution": 45,
                    "desc": f"Cohort exhibits an average churn probability of {avg_churn:.1%}, requiring proactive engagement."
                },
                {
                    "icon": "account_balance_wallet",
                    "label": "Portfolio CLV at Risk",
                    "contribution": 35,
                    "desc": f"Average customer lifetime value of K {avg_clv:,.0f} represents significant balance retention potential."
                },
                {
                    "icon": "cancel_schedule_send",
                    "label": "Channel Engagement Drop",
                    "contribution": 20,
                    "desc": "Digital transaction cadence has decelerated over the trailing 60 days."
                }
            ],
            "campaigns": [
                {
                    "id": "campaign-rec",
                    "rank": 1,
                    "tag": "RECOMMENDED",
                    "tagClass": "bg-green-100 text-green-700",
                    "title": "Personalized Fixed Deposit Rate Booster",
                    "channel": "SMS + Push Notification",
                    "channelIcon": "smartphone",
                    "description": "Offer preferential 11.5% fixed deposit interest rate to lock in balances and prevent attrition.",
                    "upliftScore": 78,
                    "successRate": "62%",
                    "aumProtected": f"K {avg_clv * 2.5:,.0f}",
                    "confidence": 88,
                    "duration": "14 days",
                    "cost": "Low"
                },
                {
                    "id": "campaign-val",
                    "rank": 2,
                    "tag": "HIGH VALUE",
                    "tagClass": "bg-amber-100 text-amber-700",
                    "title": "Direct RM Advisory Consultation",
                    "channel": "RM Phone Call",
                    "channelIcon": "call",
                    "description": "Proactive relationship manager outreach to discuss tailored wealth and credit products.",
                    "upliftScore": 65,
                    "successRate": "54%",
                    "aumProtected": f"K {avg_clv * 1.8:,.0f}",
                    "confidence": 82,
                    "duration": "21 days",
                    "cost": "Medium"
                },
                {
                    "id": "campaign-exp",
                    "rank": 3,
                    "tag": "EXPERIMENTAL",
                    "tagClass": "bg-gray-100 text-gray-600",
                    "title": "Digital Banking Cash-Back Incentive",
                    "channel": "Mobile App Push",
                    "channelIcon": "smartphone",
                    "description": "Reward active mobile app utility payments with 2% instant cash-back vouchers.",
                    "upliftScore": 48,
                    "successRate": "42%",
                    "aumProtected": f"K {avg_clv * 1.0:,.0f}",
                    "confidence": 75,
                    "duration": "30 days",
                    "cost": "Low"
                }
            ]
        }

    async def _generate_ollama_async(self, customers_data: list[dict[str, Any]]) -> dict[str, Any]:
        prompt = self._build_prompt(customers_data)
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]

        try:
            logger.info(f"Generating Cohort Campaigns using Ollama model {self.model_name} for {len(customers_data)} customers")
            client = ollama.AsyncClient()
            response = await client.chat(
                model=self.model_name,
                messages=messages,
                format='json'
            )
            result_text = response['message']['content']
            return json.loads(result_text)
        except Exception as e:
            logger.error(f"Error in LLM Cohort Engine (ollama): {e}")
            return {
                "cohort_drivers": [
                    {"icon": "warning", "label": "Model Error", "contribution": 100, "desc": "Failed to generate AI insights."}
                ],
                "campaigns": []
            }

    def _build_prompt(self, customers_data: list[dict[str, Any]]) -> str:
        retrieved_campaigns = []
        try:
            from app.services.vector_store import get_campaign_collection
            coll = get_campaign_collection()
            if customers_data:
                sample = customers_data[0]
                query_str = f"Cohort Segment: {sample.get('segment', 'Unknown')}, Risk: {sample.get('churn_probability', 'Unknown')}"
                results = coll.query(query_texts=[query_str], n_results=3)
                if results and results["documents"] and len(results["documents"][0]) > 0:
                    retrieved_campaigns = results["documents"][0]
        except Exception as e:
            logger.warning(f"Failed to retrieve campaigns from ChromaDB: {e}")

        prompt = f"Analyze the following cohort of {len(customers_data)} customers:\n{json.dumps(customers_data, indent=2)}"
        if retrieved_campaigns:
            prompt += "\n\n**Available Approved Campaigns (from Knowledge Base):**\n"
            for c in retrieved_campaigns:
                prompt += f"- {c}\n"
            prompt += "\nIMPORTANT: You must select the best strategies from the Approved Campaigns listed above.\n"
        return prompt
