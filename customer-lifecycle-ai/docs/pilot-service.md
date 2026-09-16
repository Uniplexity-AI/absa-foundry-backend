# Pilot Backend as a Windows Service (pywin32)

For the pilot Windows box the backend can run as a single **Windows service**
that supervises the six uvicorn services (gateway 8080, feature 8002, state
8003, prediction 8004, decision 8005, model management 8006). This is an alternative to
`scripts/pilot_start.ps1` and lives **alongside** it — only one should run at a
time because they bind the same ports.

- Service name: `AbsaPilotBackend`
- Supervisor script: `scripts/pilot_service.py`
- Dependency: `pywin32` (added to `absa-foundry-backend/requirements.txt`,
  Windows-only marker; already installed in `.venv` as `pywin32==312`)
- Child logs: `logs/pilot/<name>.log` + `.err.log`
- Child PIDs: `logs/pilot/service_children.txt`

## Install & start (ELEVATED PowerShell, from `customer-lifecycle-ai`)

```powershell
# one-time per interpreter: register pywin32 service DLLs
.\.venv\Scripts\python.exe .\.venv\Scripts\pywin32_postinstall.py -install

# register the service (use --startup=manual if you don't want auto-start at boot)
.\.venv\Scripts\python.exe scripts\pilot_service.py install
# or:  ... install --startup=manual

# start / stop / remove
.\.venv\Scripts\python.exe scripts\pilot_service.py start
.\.venv\Scripts\python.exe scripts\pilot_service.py stop
.\.venv\Scripts\python.exe scripts\pilot_service.py remove
# equivalent native commands:
#   sc start AbsaPilotBackend / sc stop AbsaPilotBackend / sc delete AbsaPilotBackend
```

## No-admin helpers

```powershell
.\.venv\Scripts\python.exe scripts\pilot_service.py --check   # resolved config, starts nothing
.\.venv\Scripts\python.exe scripts\pilot_service.py status    # shows child PIDs from the pids file
.\.venv\Scripts\python.exe scripts\pilot_service.py run       # foreground run (Ctrl+C to stop) — for testing only
```

## Switching between the service and the PowerShell scripts

The service does **not** touch `logs/pilot/pids.txt`, so it can coexist with
`pilot_start.ps1`/`pilot_stop.ps1`. Before starting one, stop the other:

```powershell
# service -> scripts
sc stop AbsaPilotBackend
.\scripts\pilot_stop.ps1
.\scripts\pilot_start.ps1        # wait ~15s, check /health

# scripts -> service
.\scripts\pilot_stop.ps1
sc start AbsaPilotBackend        # wait ~15s, check /health
```

The service auto-restarts any child that crashes while it is running and kills
all children on stop/shutdown.
