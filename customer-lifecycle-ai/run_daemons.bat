@echo off
set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "PYTHONPATH=%ROOT%"
set "PY=%ROOT%\.venv\Scripts\python.exe"

cd /d "%ROOT%"
start "Gateway" /B "%PY%" -m uvicorn gateway.main:create_app --factory --host 0.0.0.0 --port 8080 --reload
cd /d "%ROOT%\services\feature-engineering-service"
start "FE" /B "%PY%" -m uvicorn main:app --host 0.0.0.0 --port 8002 --reload
cd /d "%ROOT%\services\customer-state-service"
start "State" /B "%PY%" -m uvicorn main:app --host 0.0.0.0 --port 8003 --reload
cd /d "%ROOT%\services\prediction-service"
start "Prediction" /B "%PY%" -m uvicorn main:app --host 0.0.0.0 --port 8004 --reload
cd /d "%ROOT%\services\decision-intelligence-service"
start "Decision" /B "%PY%" -m uvicorn main:app --host 0.0.0.0 --port 8005 --reload
cd /d "%ROOT%\services\model-management-service"
start "Model" /B "%PY%" -m uvicorn main:app --host 0.0.0.0 --port 8006 --reload
cd /d "%ROOT%"
