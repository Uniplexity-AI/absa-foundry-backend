import re

with open('c:/Users/ADMIN/Desktop/uniplexity-ai/ABSA/absa-foundry-backend/customer-lifecycle-ai/services/prediction-service/app/services/service.py', 'r', encoding='utf-8') as f:
    content = f.read()

new_method = """
    def portfolio_scores(self, as_of_date: date | None = None) -> dict:
        t0 = time.perf_counter()

        if as_of_date is None:
            as_of_date = self._repo.latest_feature_date()
            if as_of_date is None:
                return {"as_of_date": None, "count": 0, "scores": [],
                        "duration_seconds": 0.0, "status": "NO_DATA"}

        features_list, clv_percentiles = self._get_feature_snapshot(as_of_date)
        if not features_list:
            return {"as_of_date": as_of_date.isoformat(), "count": 0, "scores": [],
                    "duration_seconds": round(time.perf_counter() - t0, 2),
                    "status": "NO_DATA"}

        def _churn_by_id(horizon: int) -> dict[str, float | None]:
            if not self._lifecycle.is_loaded(horizon):
                return {}
            results = self._lifecycle.predict_batch(features_list, horizon)
            return {
                r["customer_id"]: r["probabilities"].get("CHURNED")
                for r in results
            }
        
        c90_dict = _churn_by_id(90)
        c30_dict = _churn_by_id(30)
        c14_dict = _churn_by_id(14)
        
        from app.models.balance_growth_predictor import BalanceGrowthPredictor
        bg_pred = BalanceGrowthPredictor()
        clv_preds = self._clv.predict_batch(features_list)
        bg_preds = bg_pred.predict_batch(features_list)

        scores = []
        for i, row in enumerate(features_list):
            cid = row["customer_id"]
            c90 = c90_dict.get(cid)
            c30 = c30_dict.get(cid)
            c14 = c14_dict.get(cid)
            churn_val = c90 if c90 is not None else (c30 if c30 is not None else (c14 if c14 is not None else 0.0))
            
            scores.append({
                "customer_id": cid,
                "churn_probability": round(churn_val, 4) if churn_val is not None else None,
                "churn_probability_14d": round(c14, 4) if c14 is not None else None,
                "churn_probability_30d": round(c30, 4) if c30 is not None else None,
                "churn_probability_90d": round(c90, 4) if c90 is not None else None,
                "clv_percentile": round(self._clv.get_percentile(cid, clv_percentiles), 4),
                "clv": round(clv_preds[i], 2) if clv_preds else None,
                "balance_growth_pct": round(bg_preds[i], 4) if bg_preds else 0.0,
            })

        duration = round(time.perf_counter() - t0, 2)
        return {
            "as_of_date": as_of_date.isoformat(),
            "count": len(scores),
            "scores": scores,
            "churn_model": "lifecycle_90d",
            "duration_seconds": duration,
            "status": "COMPLETED",
        }
"""

old_method_regex = re.compile(r'    def portfolio_scores\(.*?\).*?return {[^}]+}', re.DOTALL)
content = old_method_regex.sub(new_method.strip('\n'), content)

with open('c:/Users/ADMIN/Desktop/uniplexity-ai/ABSA/absa-foundry-backend/customer-lifecycle-ai/services/prediction-service/app/services/service.py', 'w', encoding='utf-8') as f:
    f.write(content)
