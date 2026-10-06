import sys

with open('run_historical_etl.ps1', 'r', encoding='utf-8') as f:
    code = f.read()

target = '.venv\Scripts\python.exe run_etl.py --models shared,churn,clv,lifecycle,balance --snapshot  --force'
replacement = '.venv\Scripts\python.exe run_etl.py --models shared,churn,clv,lifecycle,balance --snapshot  --source-type denodo --force'

code = code.replace(target, replacement)

with open('run_historical_etl.ps1', 'w', encoding='utf-8') as f:
    f.write(code)
