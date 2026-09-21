import json
import logging
from typing import Any
import ollama

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are an expert AI Marketing Strategist and Decision Engine for a retail bank.
Your task is to analyze a cohort of customers and generate optimal campaign strategies.

INPUT:
You will receive a JSON list of customer profiles (containing segments, churn probabilities, and CLV).

OUTPUT:
You MUST output ONLY valid JSON matching the exact schema below. Do not include markdown blocks, explanations, or any other text.

SCHEMA:
{
  "cohort_drivers": [
    {
      "icon": "signal_cellular_nodata", // Use material symbols like: signal_cellular_nodata, account_balance_wallet, cancel_schedule_send, trending_down, warning
      "label": "Brief driver name (e.g., Digital Inactivity)",
      "contribution": 35, // Integer percentage contribution
      "desc": "Short explanation including the ACTUAL numerical values from the data (e.g. 'Average CLV of K 15,000' or 'Health score of 45%')"
    }
  ],
  "campaigns": [
    {
      "id": "campaign-1",
      "rank": 1,
      "tag": "RECOMMENDED", // RECOMMENDED, HIGH VALUE, or EXPERIMENTAL
      "tagClass": "bg-green-100 text-green-700", // bg-green-100 text-green-700, bg-amber-100 text-amber-700, or bg-gray-100 text-gray-600
      "title": "Campaign Title",
      "channel": "e.g., SMS + Push Notification",
      "channelIcon": "smartphone", // smartphone, call, mark_email_unread
      "description": "2-3 sentences explaining the campaign strategy and incentive.",
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
- Generate exactly 3 cohort drivers.
- The `desc` field of cohort_drivers MUST explicitly state the actual numerical values (e.g. exact average CLV, Health Score) from the input data AND provide a brief explanation of what those values mean in a business context.
- Generate exactly 3 campaigns.
- Rank 1 MUST be tag "RECOMMENDED" (green). Rank 2 "HIGH VALUE" (amber). Rank 3 "EXPERIMENTAL" (gray).
"""

class LLMCohortEngine:
    """Uses a local LLM to generate targeted cohort campaigns."""

    def __init__(self, model_name: str = "absa-nba"):
        self.model_name = model_name

    async def generate_campaigns_async(self, customers_data: list[dict[str, Any]]) -> dict[str, Any]:
        """Asynchronously evaluate a cohort to recommend campaigns."""
        # --- RAG Retrieval Step ---
        retrieved_campaigns = []
        try:
            from app.services.vector_store import get_campaign_collection
            coll = get_campaign_collection()
            # Construct a query summarizing the cohort
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

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]

        try:
            logger.info(f"Generating Cohort Campaigns using {self.model_name} for {len(customers_data)} customers")
            
            client = ollama.AsyncClient()
            response = await client.chat(
                model=self.model_name,
                messages=messages,
                format='json'
            )
            
            result_text = response['message']['content']
            return json.loads(result_text)
            
        except Exception as e:
            logger.error(f"Error in LLM Cohort Engine: {e}")
            # Fallback to safe dummy data so the UI doesn't break if LLM fails
            return {
                "cohort_drivers": [
                    {"icon": "warning", "label": "Model Error", "contribution": 100, "desc": "Failed to generate AI insights."}
                ],
                "campaigns": []
            }
