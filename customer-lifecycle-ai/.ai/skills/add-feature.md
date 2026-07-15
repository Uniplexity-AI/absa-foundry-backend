# Skill: Adding a Feature to the Feature Store

Applies to: `feature-engineering-service/app/features/`

## Steps

1. **Identify the Domain** — Choose the correct subdirectory:
   - `customer/` — demographics, tenure, profile completeness
   - `transactions/` — frequency, recency, monetary value, trends
   - `products/` — product holdings, cross-sell indicators
   - `loans/` — loan balances, repayment behavior, delinquency
   - `cards/` — card usage, utilization, payment patterns
   - `digital/` — login frequency, mobile app usage, feature adoption
   - `behaviour/` — complaint history, service requests, branch visits
   - `clv/` — revenue, margin, cost-to-serve, relationship duration

2. **Create Feature Generator** — `features/<domain>/generator.py`
   - Implement a class with `compute(customer_id: str) -> dict[str, float]` method
   - Use repository for data access
   - Return typed feature dict with feature names as keys

3. **Add to Pipeline** — `pipelines/pipeline.py`
   - Register the new generator in the feature computation pipeline
   - Set computation frequency (batch vs real-time)

4. **Add Feature Metadata** — update `models/feature_metadata/`
   - Feature name, type, description, computation method
   - Drift monitoring configuration

5. **Add Validator** — `validators/validator.py`
   - Range checks, null checks, distribution checks
   - Alert on feature drift

## Rules

- All feature generators must be idempotent (running twice = same result)
- Feature names: snake_case, prefixed with domain (`txn_`, `cust_`, `loan_`)
- Store feature computation timestamp for freshness tracking
- Never compute features in API routes — always through the pipeline
