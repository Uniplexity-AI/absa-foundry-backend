import sys
import os
import json
import asyncio

# Add the app directory to the path so we can import the engine
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.engines.llm_nba_engine import LLMNBAEngine

def test_sync_engine():
    print("Initializing LLM NBA Engine...")
    engine = LLMNBAEngine(model_name="absa-nba")
    
    customer_context = {
        "customer_id": "CUST00998",
        "segment": "Premium",
        "age": 42,
        "income_band": "High",
        "health_score": 45,
        "churn_probability": 0.78,
        "predicted_clv_zmw": 150000,
        "digital_usage_trend": "Declining"
    }
    
    candidate_actions = [
        "Offer Personal Loan (Campaign: PL_Q3)",
        "Offer Premium Credit Card (Campaign: CC_UPGRADE)",
        "Fee Waiver & Retention Call (Campaign: RET_PREMIUM)",
        "No Action"
    ]
    
    print("\nSending context to Ollama (Synchronous)...")
    try:
        decision = engine.determine_next_best_action(customer_context, candidate_actions)
        print("\n--- DECISION PACKAGE (SYNC) ---")
        print(json.dumps(decision, indent=2))
    except Exception as e:
        print(f"Error testing sync engine: {e}")
        print("Note: Ensure Ollama is running and the 'absa-nba' model is built.")

async def test_async_engine():
    print("\nSending context to Ollama (Asynchronous)...")
    engine = LLMNBAEngine(model_name="absa-nba")
    
    customer_context = {
        "customer_id": "CUST00221",
        "segment": "Mass Market",
        "health_score": 88,
        "churn_probability": 0.05,
    }
    candidate_actions = ["Promote Savings Plus", "No Action"]
    
    try:
        decision = await engine.determine_next_best_action_async(customer_context, candidate_actions)
        print("\n--- DECISION PACKAGE (ASYNC) ---")
        print(json.dumps(decision, indent=2))
    except Exception as e:
        print(f"Error testing async engine: {e}")

if __name__ == "__main__":
    test_sync_engine()
    
    # Test async wrapper
    asyncio.run(test_async_engine())
