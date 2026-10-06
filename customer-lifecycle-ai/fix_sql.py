import glob
import re

for file in glob.glob('banking_ml_python/sql/*.sql'):
    with open(file, 'r') as f:
        content = f.read()
    
    # Fix %(var)s::date -> CAST(%(var)s AS DATE)
    content = re.sub(r'%\(([a-zA-Z0-9_]+)\)s::date', r'CAST(%(\1)s AS DATE)', content)
    
    # Fix COALESCE(bus_date, posting_date)::date -> CAST(COALESCE(...) AS DATE)
    content = content.replace('COALESCE(bus_date, posting_date)::date', 'CAST(COALESCE(bus_date, posting_date) AS DATE)')
    
    # Fix DATE_TRUNC('month', ...)::date -> CAST(DATE_TRUNC(...) AS DATE)
    content = content.replace("DATE_TRUNC('month', COALESCE(event_start_date, load_date))::date", "CAST(DATE_TRUNC('month', COALESCE(event_start_date, load_date)) AS DATE)")
    content = content.replace("DATE_TRUNC('month', cb.customer_since_date)::date", "CAST(DATE_TRUNC('month', cb.customer_since_date) AS DATE)")
    
    # Fix (%(snapshot_month)s::date + INTERVAL '1 month' - INTERVAL '1 day')::date
    content = content.replace("(CAST(%(snapshot_month)s AS DATE) + INTERVAL '1 month' - INTERVAL '1 day')::date", "CAST((CAST(%(snapshot_month)s AS DATE) + INTERVAL '1 month' - INTERVAL '1 day') AS DATE)")
    content = content.replace("(%(snapshot_month)s::date + INTERVAL '1 month' - INTERVAL '1 day')::date", "CAST((CAST(%(snapshot_month)s AS DATE) + INTERVAL '1 month' - INTERVAL '1 day') AS DATE)")

    # Fix p.churn_horizon_days || ' days'::interval 
    content = re.sub(r"\(p\.([a-zA-Z0-9_]+) \|\| ' days'\)::interval", r"CAST((p.\1 || ' days') AS INTERVAL)", content)
    
    with open(file, 'w') as f:
        f.write(content)
