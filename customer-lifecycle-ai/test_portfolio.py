import sys, os
sys.path.insert(0, 'c:/Users/ADMIN/Desktop/uniplexity-ai/ABSA/absa-foundry-backend/customer-lifecycle-ai')
sys.path.insert(0, 'c:/Users/ADMIN/Desktop/uniplexity-ai/ABSA/absa-foundry-backend/customer-lifecycle-ai/services/prediction-service')
from dotenv import load_dotenv
load_dotenv('c:/Users/ADMIN/Desktop/uniplexity-ai/ABSA/absa-foundry-backend/customer-lifecycle-ai/.env')
from app.services.service import PredictionService
from datetime import date
svc = PredictionService()
try:
    result = svc.portfolio_scores(date(2026,7,17))
    print('OK count:', result.get('count'))
    print('first:', result.get('scores',[])[0] if result.get('scores') else 'EMPTY')
except Exception as e:
    import traceback
    traceback.print_exc()
