import re

with open('c:/Users/ADMIN/Desktop/uniplexity-ai/ABSA/absa-foundry-backend/customer-lifecycle-ai/services/prediction-service/app/services/service.py', 'r', encoding='utf-8') as f:
    content = f.read()

new_methods = """
    def clv_batch(self, as_of_date: date | None = None) -> dict:
        import time
        t0 = time.perf_counter()
        if as_of_date is None:
            as_of_date = self._repo.latest_feature_date()
        if as_of_date is None:
            return {"as_of_date": None, "customers_scored": 0, "status": "NO_DATA"}
        
        features_list = self._repo.load_features(as_of_date)
        if not features_list:
            return {"as_of_date": as_of_date.isoformat(), "customers_scored": 0, "status": "NO_DATA"}
            
        if not self._clv.is_model_loaded:
            return {"as_of_date": as_of_date.isoformat(), "customers_scored": 0, "status": "CLV_MODEL_NOT_LOADED"}
            
        preds = self._clv.predict_batch(features_list)
        return {
            "as_of_date": as_of_date.isoformat(),
            "customers_scored": len(preds),
            "status": "COMPLETED",
            "duration_seconds": round(time.perf_counter() - t0, 2),
        }

    def balance_growth_batch(self, as_of_date: date | None = None) -> dict:
        import time
        t0 = time.perf_counter()
        if as_of_date is None:
            as_of_date = self._repo.latest_feature_date()
        if as_of_date is None:
            return {"as_of_date": None, "customers_scored": 0, "status": "NO_DATA"}
            
        features_list = self._repo.load_features(as_of_date)
        if not features_list:
            return {"as_of_date": as_of_date.isoformat(), "customers_scored": 0, "status": "NO_DATA"}
            
        from app.models.balance_growth_predictor import BalanceGrowthPredictor
        bg_pred = BalanceGrowthPredictor()
        if not bg_pred.is_model_loaded:
            return {"as_of_date": as_of_date.isoformat(), "customers_scored": 0, "status": "MODEL_NOT_LOADED"}
            
        preds = bg_pred.predict_batch(features_list)
        return {
            "as_of_date": as_of_date.isoformat(),
            "customers_scored": len(preds),
            "status": "COMPLETED",
            "mean_growth": sum(preds)/len(preds) if preds else 0,
            "min_growth": min(preds) if preds else 0,
            "max_growth": max(preds) if preds else 0,
            "duration_seconds": round(time.perf_counter() - t0, 2)
        }
"""

insert_pos = content.find("    def _get_feature_snapshot(")
if insert_pos == -1:
    print("Could not find insert pos")
else:
    new_content = content[:insert_pos] + new_methods + "\n" + content[insert_pos:]
    with open('c:/Users/ADMIN/Desktop/uniplexity-ai/ABSA/absa-foundry-backend/customer-lifecycle-ai/services/prediction-service/app/services/service.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("Patched service.py")
