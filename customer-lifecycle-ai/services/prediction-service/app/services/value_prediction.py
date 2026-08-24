import logging
import pickle
import numpy as np

logger = logging.getLogger("prediction.value_prediction")

class ValuePredictionService:
    def __init__(self, erosion_model_path="models/value_erosion_v1.pkl", forecast_model_path="models/value_forecast_v1.pkl"):
        self.erosion_model = None
        self.forecast_model = None
        self.features = None
        
        try:
            with open(erosion_model_path, "rb") as f:
                data = pickle.load(f)
                self.erosion_model = data['model']
                self.features = data['features']
            logger.info(f"Loaded erosion model from {erosion_model_path}")
        except Exception as e:
            logger.warning(f"Failed to load erosion model: {e}")
            
        try:
            with open(forecast_model_path, "rb") as f:
                data = pickle.load(f)
                self.forecast_model = data['model']
            logger.info(f"Loaded forecast model from {forecast_model_path}")
        except Exception as e:
            logger.warning(f"Failed to load forecast model: {e}")

    def predict(self, feature_row: dict) -> dict:
        """
        Predict erosion probability and future value.
        """
        if not self.erosion_model or not self.forecast_model or not self.features:
            return {
                "erosion_probability": 0.0,
                "erosion_risk_level": "Unknown",
                "predicted_future_value": 0.0,
                "top_factors": ["Models not loaded"]
            }
            
        # Extract features in the correct order
        x = []
        for f in self.features:
            val = feature_row.get(f)
            # handle None or missing
            if val is None:
                val = 0.0
            x.append(float(val))
            
        X_arr = np.array([x])
        
        # 1. Predict Erosion
        erosion_prob = float(self.erosion_model.predict_proba(X_arr)[0, 1])
        if erosion_prob > 0.7:
            risk_level = "High"
        elif erosion_prob > 0.4:
            risk_level = "Medium"
        else:
            risk_level = "Low"
            
        # 2. Predict Future Value
        future_val_log = float(self.forecast_model.predict(X_arr)[0])
        future_val = np.expm1(future_val_log)
        
        # 3. Explainability (Mocked for now since shap is missing)
        # A real implementation would use shap.TreeExplainer(self.erosion_model).shap_values(X_arr)
        # and map the highest magnitude features to human-readable strings.
        top_factors = []
        if risk_level in ["High", "Medium"]:
            # naive mock based on generic heuristics for the PoC
            if feature_row.get('txn_count_90d', 0) < 5:
                top_factors.append("Transaction frequency dropped")
            if feature_row.get('total_amount_90d', 0) < 1000:
                top_factors.append("Low overall deposit volume")
            if not top_factors:
                top_factors.append("Overall engagement is declining")
                
        return {
            "erosion_probability": round(erosion_prob, 4),
            "erosion_risk_level": risk_level,
            "predicted_future_value": round(future_val, 2),
            "top_factors": top_factors
        }
