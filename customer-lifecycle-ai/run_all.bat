@echo off
set PYTHONPATH=C:\Users\ADMIN\Desktop\uniplexity-ai\ABSA\absa-foundry-backend\customer-lifecycle-ai
set PY=C:\Users\ADMIN\Desktop\uniplexity-ai\ABSA\absa-foundry-backend\customer-lifecycle-ai\.venv\Scripts\python.exe

start "Gateway" /B %PY% -m uvicorn gateway.main:create_app --factory --host 0.0.0.0 --port 8080 --reload
cd services\feature-engineering-service
start "FE" /B %PY% -m uvicorn main:app --host 0.0.0.0 --port 8002 --reload
cd ..\customer-state-service
start "State" /B %PY% -m uvicorn main:app --host 0.0.0.0 --port 8003 --reload
cd ..\prediction-service
start "Prediction" /B %PY% -m uvicorn main:app --host 0.0.0.0 --port 8004 --reload
cd ..\decision-intelligence-service
start "Decision" /B %PY% -m uvicorn main:app --host 0.0.0.0 --port 8005 --reload
cd ..\model-management-service
start "Model" /B %PY% -m uvicorn main:app --host 0.0.0.0 --port 8006 --reload
