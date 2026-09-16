import re

with open('c:/Users/ADMIN/Desktop/uniplexity-ai/ABSA/absa-foundry-backend/customer-lifecycle-ai/services/prediction-service/app/services/service.py', 'r', encoding='utf-8') as f:
    content = f.read()

new_method = """
    def lifecycle_forecast(self, as_of_date: date | None = None) -> dict:
        import time
        t0 = time.perf_counter()
        
        if as_of_date is None:
            as_of_date = self._repo.latest_feature_date()
            if as_of_date is None:
                return {"as_of_date": None, "count": 0, "status": "NO_DATA", "forecast": [], "horizons": {}, "duration_seconds": 0.0}

        features_list = self._repo.load_features(as_of_date)
        if not features_list:
            return {"as_of_date": as_of_date.isoformat(), "count": 0, "status": "NO_DATA", "forecast": [], "horizons": {}, "duration_seconds": 0.0}

        def _predict(h: int):
            if not self._lifecycle.is_loaded(h):
                return [], "MODEL_UNAVAILABLE"
            return self._lifecycle.predict_batch(features_list, h), "OK"
        
        preds_14, status_14 = _predict(14)
        preds_30, status_30 = _predict(30)
        preds_90, status_90 = _predict(90)
        
        horizons_status = {
            "14": status_14,
            "30": status_30,
            "90": status_90
        }
        
        forecast_dict = {}
        for row in features_list:
            cid = row["customer_id"]
            forecast_dict[cid] = {}
            
        for r in preds_14:
            forecast_dict[r["customer_id"]]["14"] = {"stage": r["stage"], "confidence": r["confidence"], "probabilities": r["probabilities"]}
        for r in preds_30:
            forecast_dict[r["customer_id"]]["30"] = {"stage": r["stage"], "confidence": r["confidence"], "probabilities": r["probabilities"]}
        for r in preds_90:
            forecast_dict[r["customer_id"]]["90"] = {"stage": r["stage"], "confidence": r["confidence"], "probabilities": r["probabilities"]}
            
        forecast_list = []
        for cid, horiz in forecast_dict.items():
            forecast_list.append({
                "customer_id": cid,
                "horizons": horiz
            })
            
        return {
            "as_of_date": as_of_date.isoformat(),
            "count": len(forecast_list),
            "status": "COMPLETED",
            "forecast": forecast_list,
            "horizons": horizons_status,
            "duration_seconds": round(time.perf_counter() - t0, 2)
        }
"""

insert_pos = content.find("    def _get_feature_snapshot(")
if insert_pos == -1:
    print("Could not find insert pos")
else:
    new_content = content[:insert_pos] + new_method + "\n" + content[insert_pos:]
    with open('c:/Users/ADMIN/Desktop/uniplexity-ai/ABSA/absa-foundry-backend/customer-lifecycle-ai/services/prediction-service/app/services/service.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("Patched service.py")
