import os
import json
import logging
import asyncio
import threading
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Global thread lock for llama_cpp inference to ensure thread safety
_LLAMA_LOCK = threading.Lock()

# Try importing llama_cpp
try:
    from llama_cpp import Llama
    HAS_LLAMA_CPP = True
except ImportError:
    HAS_LLAMA_CPP = False

# Try importing ollama (kept intact)
try:
    import ollama
    HAS_OLLAMA = True
except ImportError:
    HAS_OLLAMA = False

# Global singleton so llama_cpp model stays loaded in RAM across requests
_GLOBAL_LLAMA_INSTANCE: Optional[Any] = None

def _resolve_default_model_path() -> str:
    """Finds available GGUF model path across local, project, or ollama cache."""
    env_path = os.getenv("NBA_MODEL_PATH")
    if env_path and os.path.exists(env_path):
        return env_path
        
    candidates = [
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "models", "llm", "qwen2.5-7b-instruct.gguf")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "models", "qwen2.5-7b-instruct.gguf")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "models", "llm", "qwen2.5-7b-instruct.gguf")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "models", "qwen2.5-7b-instruct.gguf")),
        os.path.expanduser("~/Desktop/absa-nba-package/models/qwen2.5-7b-instruct.gguf"),
        os.path.expanduser("~/.ollama/models/blobs/sha256-2bada8a7450677000f678be90653b85d364de7db25eb5ea54136ada5f3933730"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return candidates[0]

def get_llama_model(model_path: Optional[str] = None) -> Any:
    """Singleton loader for llama-cpp-python to keep model in RAM."""
    global _GLOBAL_LLAMA_INSTANCE
    with _LLAMA_LOCK:
        if _GLOBAL_LLAMA_INSTANCE is None:
            target_path = model_path or _resolve_default_model_path()
            logger.info(f"Loading llama-cpp model from: {target_path}")
            if not os.path.exists(target_path):
                raise FileNotFoundError(
                    f"GGUF model file not found at: {target_path}.\n"
                    f"Please place 'qwen2.5-7b-instruct.gguf' (4.7GB) into 'models/llm/' "
                    f"or set NBA_MODEL_PATH in .env to the model location."
                )
                
            # Optimal physical threads: 6 to 8 threads avoids core contention
            threads = min(8, max(4, (os.cpu_count() or 6) // 2))
            _GLOBAL_LLAMA_INSTANCE = Llama(
                model_path=target_path,
                n_ctx=4096,       # 4096 tokens is fast and keeps RAM under ~5 GB
                n_threads=threads,
                verbose=False
            )
            logger.info(f"llama-cpp model loaded successfully into memory with {threads} threads.")
    return _GLOBAL_LLAMA_INSTANCE


class LLMNBAEngine:
    """
    Next Best Action (NBA) Engine.
    Supports 'llama-cpp' (default, in-process, offline) and 'ollama' (kept intact).
    """
    
    SYSTEM_PROMPT = """You are the ABSA Decision Intelligence Agent. 
Your primary role is to evaluate customer data, upstream predictive analytics, and business context to determine the optimal Next Best Action (NBA) for the bank to take.

You operate as the final decision and explanation layer, prioritizing actions that:
- Reduce customer churn
- Increase product conversion
- Maximize Customer Lifetime Value (CLV)
- Drive customer engagement

You will receive input containing:
1. Customer Profile (Demographics, Segment)
2. Customer State & Behaviour (Health score, Engagement)
3. Predictions (Churn probability, Predicted CLV, Offer acceptance probability)
4. Candidate Actions (Actions that have passed deterministic business rules)

INSTRUCTIONS:
Analyze the provided context and select the absolute best action from the candidate list. You must explain your reasoning transparently.

OUTPUT FORMAT:
You must return your decision STRICTLY as a JSON object matching the schema below. Do not include markdown code blocks, backticks, or any conversational text outside of the JSON.

{
  "customer_id": "string",
  "next_best_action": "string",
  "priority_score": 90,
  "confidence": 0.95,
  "estimated_revenue": 1000.00,
  "estimated_churn_reduction": 0.15,
  "channel": "string (e.g., 'Relationship Manager', 'Digital', 'Branch')",
  "campaign": "string (The internal campaign code if applicable)",
  "reason_codes": ["string", "string"],
  "explanation": "string (A transparent, natural language explanation detailing why this action was chosen based on the customer's state and ML predictions)"
}
"""

    def __init__(
        self, 
        model_name: str = "absa-nba", 
        backend: str = "llama-cpp",
        model_path: Optional[str] = None
    ):
        self.model_name = model_name
        # Default to llama-cpp if available, fallback to ollama
        if backend == "llama-cpp" and not HAS_LLAMA_CPP and HAS_OLLAMA:
            logger.warning("llama-cpp-python not found; falling back to ollama.")
            self.backend = "ollama"
        else:
            self.backend = backend
        self.model_path = model_path

    async def determine_next_best_action_async(
        self, 
        customer_context: Dict[str, Any], 
        candidate_actions: List[str]
    ) -> Dict[str, Any]:
        """
        Asynchronous wrapper to call the model (useful for FastAPI routes).
        """
        if self.backend == "ollama":
            return await self._call_ollama_async(customer_context, candidate_actions)
        else:
            # llama-cpp is CPU/in-process; run in worker thread to keep event loop free
            return await asyncio.to_thread(
                self.determine_next_best_action, 
                customer_context, 
                candidate_actions
            )

    def determine_next_best_action(
        self, 
        customer_context: Dict[str, Any], 
        candidate_actions: List[str]
    ) -> Dict[str, Any]:
        """
        Synchronous call to the model using either llama-cpp or ollama.
        """
        if self.backend == "ollama":
            return self._call_ollama_sync(customer_context, candidate_actions)
        else:
            return self._call_llama_cpp(customer_context, candidate_actions)

    # -------------------------------------------------------------------------
    # llama-cpp-python Backend Implementation
    # -------------------------------------------------------------------------
    def _call_llama_cpp(
        self, 
        customer_context: Dict[str, Any], 
        candidate_actions: List[str]
    ) -> Dict[str, Any]:
        llm = get_llama_model(self.model_path)
        prompt = self._build_prompt(customer_context, candidate_actions)

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]

        try:
            logger.info(f"Generating NBA using llama-cpp for customer {customer_context.get('customer_id')}")
            
            with _LLAMA_LOCK:
                response = llm.create_chat_completion(
                    messages=messages,
                    temperature=0.1,
                    top_p=0.9,
                    max_tokens=350,
                    stop=["<|im_start|>", "<|im_end|>"],
                    response_format={"type": "json_object"}
                )
            
            content = response["choices"][0]["message"]["content"]
            return json.loads(content)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from LLM: {e}")
            return {"error": "Invalid JSON returned by the model.", "raw_output": content}
        except Exception as e:
            logger.error(f"Error calling llama-cpp: {e}")
            return {"error": str(e)}

    # -------------------------------------------------------------------------
    # Ollama Backend Implementation (Intact & Preserved)
    # -------------------------------------------------------------------------
    async def _call_ollama_async(
        self, 
        customer_context: Dict[str, Any], 
        candidate_actions: List[str]
    ) -> Dict[str, Any]:
        if not HAS_OLLAMA:
            raise RuntimeError("ollama package is not installed.")
        client = ollama.AsyncClient()
        prompt = self._build_prompt(customer_context, candidate_actions)
        messages = [{"role": "user", "content": prompt}]

        try:
            logger.info(f"Generating NBA using Ollama model {self.model_name} for customer {customer_context.get('customer_id')}")
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

    def _call_ollama_sync(
        self, 
        customer_context: Dict[str, Any], 
        candidate_actions: List[str]
    ) -> Dict[str, Any]:
        if not HAS_OLLAMA:
            raise RuntimeError("ollama package is not installed.")
        prompt = self._build_prompt(customer_context, candidate_actions)
        messages = [{"role": "user", "content": prompt}]

        try:
            logger.info(f"Generating NBA using Ollama model {self.model_name} for customer {customer_context.get('customer_id')}")
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

    # -------------------------------------------------------------------------
    # Shared Prompt Builder with RAG Hook
    # -------------------------------------------------------------------------
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
