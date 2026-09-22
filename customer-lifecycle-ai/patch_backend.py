import sys
import os

repo_path = 'services/feature-engineering-service/app/repository/repository.py'
with open(repo_path, 'r') as f:
    repo_content = f.read()

NEAREST_SQL = '''
NEAREST_SQL = \"\"\"
SELECT customer_id, as_of_date,
       days_since_last_txn, days_since_first_txn,
       txn_count_30d, txn_count_90d, txn_count_180d, txn_count_365d,
       avg_days_between_txn,
       total_amount_90d, avg_amount_90d, total_amount_180d,
       amount_growth_ratio,
       credit_sum_30d, debit_sum_30d, credit_to_debit_ratio_90d,
       balance_trend_90d, has_salary_credit, monthly_income_estimate,
       distinct_channels_90d, distinct_txn_types_90d,
       dominant_channel, amount_stddev_90d,
       computed_at
FROM customer_features
WHERE customer_id = %s AND as_of_date <= %s
ORDER BY as_of_date DESC
LIMIT 1
\"\"\"

ACTIVITY_SQL = \"\"\"
SELECT COUNT(*) as txn_count, COALESCE(SUM(amount), 0) as total_amount
FROM customer_transactions_clean
WHERE customer_id = %s AND transaction_date >= %s AND transaction_date < %s
\"\"\"
'''

repo_content = repo_content.replace('LATEST_SQL = """', NEAREST_SQL + '\nLATEST_SQL = """')

repo_methods = '''
    def get_nearest(self, customer_id: str, as_of_date: date) -> dict | None:
        """Fetch the most recent feature snapshot on or before a date."""
        conn = self._connect()
        try:
            cur = conn.cursor(cursor_factory=extras.RealDictCursor)
            cur.execute(NEAREST_SQL, (customer_id, as_of_date))
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_gap_activity(self, customer_id: str, start_date: date, end_date: date) -> dict:
        """Fetch transaction counts/amounts in a date range."""
        conn = self._connect()
        try:
            cur = conn.cursor(cursor_factory=extras.RealDictCursor)
            cur.execute(ACTIVITY_SQL, (customer_id, start_date, end_date))
            row = cur.fetchone()
            return dict(row) if row else {"txn_count": 0, "total_amount": 0}
        finally:
            conn.close()
'''

repo_content = repo_content.replace('    def get_latest(self, customer_id: str) -> dict | None:', repo_methods + '\n    def get_latest(self, customer_id: str) -> dict | None:')

with open(repo_path, 'w') as f:
    f.write(repo_content)

schema_path = 'services/feature-engineering-service/app/schemas/schemas.py'
with open(schema_path, 'r') as f:
    schema_content = f.read()

schema_content += '''
class GapActivityResponse(BaseModel):
    txn_count: int
    total_amount: float
'''

with open(schema_path, 'w') as f:
    f.write(schema_content)

service_path = 'services/feature-engineering-service/app/services/service.py'
with open(service_path, 'r') as f:
    service_content = f.read()

service_methods = '''
    def get_nearest(self, customer_id: str, as_of_date: date) -> FeatureSnapshot | None:
        row = self._repo.get_nearest(customer_id, as_of_date)
        return FeatureSnapshot(**row) if row else None

    def get_gap_activity(self, customer_id: str, start_date: date, end_date: date) -> dict:
        return self._repo.get_gap_activity(customer_id, start_date, end_date)
'''

service_content = service_content.replace('    def get_latest(self, customer_id: str) -> FeatureSnapshot | None:', service_methods + '\n    def get_latest(self, customer_id: str) -> FeatureSnapshot | None:')

with open(service_path, 'w') as f:
    f.write(service_content)

routes_path = 'gateway/routes/feature_routes.py'
with open(routes_path, 'r') as f:
    routes_content = f.read()

routes_content = routes_content.replace('from app.schemas.schemas import FeatureSnapshot, ComputeBatchResponse', 'from app.schemas.schemas import FeatureSnapshot, ComputeBatchResponse, GapActivityResponse')

routes_methods = '''
@router.get("/{customer_id}/nearest", response_model=FeatureSnapshot)
def get_nearest(
    customer_id: str,
    as_of_date: date = Query(..., description="Date to find snapshot before or on"),
    user: UserContext = Depends(require_auth),
) -> FeatureSnapshot:
    result = _service.get_nearest(customer_id, as_of_date)
    if result is None:
        raise HTTPException(status_code=404, detail="No snapshot found before date")
    return result

@router.get("/{customer_id}/gap-activity", response_model=GapActivityResponse)
def get_gap_activity(
    customer_id: str,
    start_date: date = Query(...),
    end_date: date = Query(...),
    user: UserContext = Depends(require_auth),
) -> GapActivityResponse:
    result = _service.get_gap_activity(customer_id, start_date, end_date)
    return result

'''
routes_content = routes_content.replace('# ===========================================================================\n# GET /features/{customer_id}/latest', routes_methods + '\n# ===========================================================================\n# GET /features/{customer_id}/latest')

with open(routes_path, 'w') as f:
    f.write(routes_content)

print("Patched backend successfully.")
