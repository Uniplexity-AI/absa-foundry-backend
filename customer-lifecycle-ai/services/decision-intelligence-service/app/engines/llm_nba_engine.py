import json
import logging
from typing import Dict, Any, List

import ollama

logger = logging.getLogger(__name__)

class LLMNBAEngine:
    """
    Next Best Action (NBA) Engine utilizing the local Ollama model.
    Connects to the 'absa-nba' model to evaluate context and determine the optimal action.
    """
    
    def __init__(self, model_name: str = "absa-nba"):
        self.model_name = model_name

    async def determine_next_best_action_async(
        self, 
        customer_context: Dict[str, Any], 
        candidate_actions: List[str]
    ) -> Dict[str, Any]:
        """
        Asynchronous wrapper to call the model (useful for FastAPI routes).
        """
        client = ollama.AsyncClient()
        prompt = self._build_prompt(customer_context, candidate_actions)

        messages = [{"role": "user", "content": prompt}]

        try:
            logger.info(f"Generating NBA using model {self.model_name} for customer {customer_context.get('customer_id')}")
            
            response = await client.chat(
                model=self.model_name,
                messages=messages,
                format='json'
            )
            
            content = response['message']['content']
            return json.loads(content)

        except Exception as e:
            logger.error(f"Error calling Ollama API asynchronously: {e}")
            raise

    def determine_next_best_action(
        self, 
        customer_context: Dict[str, Any], 
        candidate_actions: List[str]
    ) -> Dict[str, Any]:
        """
        Synchronous call to the local absa-nba model.
        """
        prompt = self._build_prompt(customer_context, candidate_actions)
        messages = [{"role": "user", "content": prompt}]

        try:
            logger.info(f"Generating NBA using model {self.model_name} for customer {customer_context.get('customer_id')}")
            
            response = ollama.chat(
                model=self.model_name,
                messages=messages,
                format='json'
            )
            
            content = response['message']['content']
            return json.loads(content)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from LLM: {e}")
            return {"error": "Invalid JSON returned by the model.", "raw_output": content}
        except Exception as e:
            logger.error(f"Error calling Ollama API: {e}")
            return {"error": str(e)}

    def _build_prompt(self, context: Dict[str, Any], candidates: List[str]) -> str:
        """
        Formats the customer context and candidates into a structured prompt.
        """
        # --- RAG Retrieval Step ---
        retrieved_campaigns = []
        try:
            from app.services.vector_store import get_campaign_collection
            coll = get_campaign_collection()
            # Search using customer profile string
            query_str = f"Segment: {context.get('segment', 'Unknown')}, Risk: {context.get('churn_probability', 'Unknown')}, Needs: {context.get('engagement', 'Unknown')}"
            results = coll.query(query_texts=[query_str], n_results=3)
            if results and results["documents"] and len(results["documents"][0]) > 0:
                retrieved_campaigns = results["documents"][0]
        except Exception as e:
            logger.warning(f"Failed to retrieve campaigns from ChromaDB: {e}")

        prompt = "Please determine the Next Best Action for the following customer:\n\n"
        
        prompt += "**Customer Context & Predictions:**\n"
        for key, value in context.items():
            if isinstance(value, dict):
                prompt += f"- {key}:\n"
                for k, v in value.items():
                    prompt += f"  - {k}: {v}\n"
            else:
                prompt += f"- {key}: {value}\n"
            
        prompt += "\n**Available Approved Campaigns (from Knowledge Base):**\n"
        if retrieved_campaigns:
            for c in retrieved_campaigns:
                prompt += f"- {c}\n"
            prompt += "\nIMPORTANT: You must select the best strategy from the Approved Campaigns listed above.\n"
        else:
            prompt += "No uploaded campaigns found. Please recommend a generic best action.\n"

        prompt += "\n**Candidate Actions:**\n"
        if not candidates:
            prompt += "No pre-filtered candidates.\n"
        else:
            for idx, action in enumerate(candidates, 1):
                prompt += f"{idx}. {action}\n"
                
        return prompt
