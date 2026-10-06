with open(r'..\..\absa-foundry-frontend\src\views\Modules\datapipeline\EtlPipeline.vue', 'r', encoding='utf-8') as f:
    code = f.read()

target = "call: () => api.post('/api/etl/trigger', { config_name: 'customer_360.yaml', sync: true, source_type: 'denodo', snapshot: date, force: true })"
target2 = "call: () => api.post('/api/etl/trigger', { config_name: 'customer_360.yaml', sync: true }),"

replacement = "call: () => api.post('/api/etl/trigger', { config_name: 'customer_360.yaml', sync: true, source_type: 'denodo', snapshot: date, force: true, run_models: 'shared,churn,clv,lifecycle,balance' }),"

if target in code:
    code = code.replace(target, replacement)
elif target2 in code:
    code = code.replace(target2, replacement)

with open(r'..\..\absa-foundry-frontend\src\views\Modules\datapipeline\EtlPipeline.vue', 'w', encoding='utf-8') as f:
    f.write(code)
