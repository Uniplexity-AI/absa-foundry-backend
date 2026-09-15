import sys, os
sys.path.insert(0, 'c:/Users/ADMIN/Desktop/uniplexity-ai/ABSA/absa-foundry-backend/customer-lifecycle-ai')
sys.path.insert(0, 'c:/Users/ADMIN/Desktop/uniplexity-ai/ABSA/absa-foundry-backend/customer-lifecycle-ai/services/prediction-service')
from dotenv import load_dotenv
load_dotenv('c:/Users/ADMIN/Desktop/uniplexity-ai/ABSA/absa-foundry-backend/customer-lifecycle-ai/.env')
from app.services.service import PredictionService
from datetime import date
svc = PredictionService()
try:
    result = svc.lifecycle_forecast(date(2026,7,17))
    import json
    print(json.dumps(result)[:500])
except Exception as e:
    import traceback
    traceback.print_exc()
