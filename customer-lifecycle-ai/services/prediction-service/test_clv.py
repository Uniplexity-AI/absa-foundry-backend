from datetime import date
from app.services.service import PredictionService
svc = PredictionService()
print(svc.clv_batch(date(2026,7,17)))
