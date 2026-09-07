#!/usr/bin/env python3
"""
ABSA Pilot Backend — Windows Service (pywin32)
================================================

Runs the five backend services (gateway + feature-engineering +
customer-state + prediction + decision-intelligence) as supervised child
uvicorn processes, from a single Windows service.

This is an ALTERNATIVE to scripts/pilot_start.ps1 for the pilot Windows box and
is kept ALONGSIDE it — only one should run at a time, because both bind the
same ports (gateway 8080, feature 8002, state 8003, prediction 8004,
decision 8005).

Admin install / manage (run in an ELEVATED PowerShell, from the repo root):

    cd <repo>\\customer-lifecycle-ai

    # one-time: register pywin32 service runtime DLLs for this interpreter
    .\\.venv\\Scripts\\python.exe .\\.venv\\Scripts\\pywin32_postinstall.py -install

    # install the service (auto-start at boot)
    .\\.venv\\Scripts\\python.exe scripts\\pilot_service.py install

    # control it
    .\\.venv\\Scripts\\python.exe scripts\\pilot_service.py start      # or: sc start AbsaPilotBackend
    .\\.venv\\Scripts\\python.exe scripts\\pilot_service.py stop       # or: sc stop  AbsaPilotBackend
    .\\.venv\\Scripts\\python.exe scripts\\pilot_service.py restart
    .\\.venv\\Scripts\\python.exe scripts\\pilot_service.py remove

Non-admin helpers (no service registration / no admin required):

    .\\.venv\\Scripts\\python.exe scripts\\pilot_service.py --check     # print resolved config, do NOT spawn
    .\\.venv\\Scripts\\python.exe scripts\\pilot_service.py run         # foreground; Ctrl+C to stop (for testing)
    .\\.venv\\Scripts\\python.exe scripts\\pilot_service.py status      # list child PIDs from the pids file

Logs: logs/pilot/<name>.log and logs/pilot/<name>.err.log (same convention as
pilot_start.ps1). Child PIDs are written to logs/pilot/service_children.txt.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
LOG_DIR = ROOT / "logs" / "pilot"
PIDS_FILE = LOG_DIR / "service_children.txt"
SERVICE_LOG = LOG_DIR / "service.log"

# venv python that runs each uvicorn child (same interpreter as the scripts)
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"

# Service metadata
SERVICE_NAME = "AbsaPilotBackend"
SERVICE_DISPLAY = "ABSA Customer Lifecycle Pilot Backend"
SERVICE_DESCRIPTION = (
    "Runs the ABSA pilot backend (gateway, feature engineering, customer state, "
    "prediction, decision intelligence) as supervised child uvicorn processes."
)

# name, app target, factory (gateway uses create_app), env port key, default port, working subdir
_SERVICE_DEFS = [
    ("gateway",    "gateway.main:create_app", True,  "GATEWAY_PORT",                   8080, "."),
    ("feature",    "main:app",                False, "FEATURE_ENGINEERING_SERVICE_PORT", 8002, "services/feature-engineering-service"),
    ("state",      "main:app",                False, "CUSTOMER_STATE_SERVICE_PORT",      8003, "services/customer-state-service"),
    ("prediction", "main:app",                False, "PREDICTION_SERVICE_PORT",          8004, "services/prediction-service"),
    ("decision",   "main:app",                False, "DECISION_INTELLIGENCE_SERVICE_PORT", 8005, "services/decision-intelligence-service"),
]


def _log(message: str) -> None:
    """Append a timestamped line to the service log file."""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with SERVICE_LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {message}\n")
    except Exception:  # noqa: BLE001 - never break the service for a log write
        pass


def load_env() -> dict[str, str]:
    """Parse .env into a dict (keys as-is)."""
    env: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    return env


def resolve_python() -> Path:
    """Prefer the project venv python; fall back to the current interpreter."""
    return PYTHON if PYTHON.exists() else Path(sys.executable)


def build_specs() -> list[dict]:
    """Resolve the concrete run spec for each service (no side effects)."""
    env = load_env()

    def port(key: str, default: int) -> int:
        raw = env.get(key, "")
        return int(raw) if raw.isdigit() else default

    python = resolve_python()
    specs = []
    for name, app, factory, env_key, default, subdir in _SERVICE_DEFS:
        cmd = [str(python), "-m", "uvicorn", app, "--host", "0.0.0.0", "--port", str(port(env_key, default))]
        if factory:
            cmd.append("--factory")
        specs.append({
            "name": name,
            "port": port(env_key, default),
            "dir": (ROOT / subdir) if subdir != "." else ROOT,
            "cmd": cmd,
            "log": LOG_DIR / f"{name}.log",
            "err": LOG_DIR / f"{name}.err.log",
        })
    return specs


class Child:
    """One uvicorn subprocess plus its log handles."""

    def __init__(self, spec: dict) -> None:
        self.spec = spec
        self.proc: subprocess.Popen | None = None
        self._out = None
        self._err = None
        self.starts = 0
        self.spawn()

    def spawn(self) -> None:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT)
        env.setdefault("PYTHONIOENCODING", "utf-8")
        self._out = self.spec["log"].open("ab")
        self._err = self.spec["err"].open("ab")
        self.proc = subprocess.Popen(
            self.spec["cmd"],
            cwd=str(self.spec["dir"]),
            env=env,
            stdout=self._out,
            stderr=self._err,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
        self.starts += 1
        _log(f"started {self.spec['name']} on :{self.spec['port']} (pid {self.proc.pid}, start #{self.starts})")

    def stop(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception:  # noqa: BLE001
                pass
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    self.proc.kill()
                except Exception:  # noqa: BLE001
                    pass
        for fh in (self._out, self._err):
            if fh is not None:
                try:
                    fh.close()
                except Exception:  # noqa: BLE001
                    pass
        _log(f"stopped {self.spec['name']}")


def _write_pids(children: list[Child]) -> None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with PIDS_FILE.open("w", encoding="utf-8") as fh:
            for ch in children:
                if ch.proc is not None and ch.proc.poll() is None:
                    fh.write(f"{ch.spec['name']}={ch.proc.pid}\n")
    except Exception:  # noqa: BLE001
        pass


def start_children() -> list[Child]:
    children = [Child(spec) for spec in build_specs()]
    _write_pids(children)
    return children


def stop_children(children: list[Child]) -> None:
    for ch in children:
        ch.stop()
    try:
        PIDS_FILE.unlink()
    except OSError:
        pass


def supervise(children: list[Child], stop_event: threading.Event) -> None:
    """Watch the children and auto-restart any that crash while we're running."""
    while not stop_event.is_set():
        for ch in children:
            if ch.proc is not None and ch.proc.poll() is not None:
                _log(f"{ch.spec['name']} exited rc={ch.proc.returncode} — restarting")
                ch.spawn()
        _write_pids(children)
        stop_event.wait(2)


# ===========================================================================
# pywin32 Windows Service
# ===========================================================================

try:
    import servicemanager
    import win32serviceutil
    import win32service
except Exception as exc:  # noqa: BLE001 - pywin32 not installed yet
    servicemanager = None  # type: ignore[assignment]
    win32serviceutil = None  # type: ignore[assignment]
    win32service = None  # type: ignore[assignment]
    _PYWIN32_IMPORT_ERROR = exc
else:
    _PYWIN32_IMPORT_ERROR = None


class PilotBackendService(win32serviceutil.ServiceFramework):  # type: ignore[misc,index]
    """Supervises the five ABSA pilot backend uvicorn processes."""

    _svc_name_ = SERVICE_NAME
    _svc_display_name_ = SERVICE_DISPLAY
    _svc_description_ = SERVICE_DESCRIPTION
    _exe_name_ = str(Path(sys.executable).with_name("pythonw.exe"))

    def __init__(self, args):
        super().__init__(args)
        self._children: list[Child] = []
        self._stop_event = threading.Event()

    def SvcDoRun(self) -> None:
        if servicemanager is not None:
            servicemanager.LogMsg(
                servicemanager.EVENTLOG_INFORMATION_TYPE,
                servicemanager.PYS_SERVICE_STARTED,
                (self._svc_name_, ""),
            )
        _log("=== service starting ===")
        self._stop_event.clear()
        try:
            self._children = start_children()
            supervise(self._children, self._stop_event)
        except Exception as exc:  # noqa: BLE001
            _log(f"service error: {exc}")
            if servicemanager is not None:
                servicemanager.LogErrorMsg(f"pilot_service: {exc}")
            raise
        finally:
            stop_children(self._children)
            _log("=== service stopped ===")
            if servicemanager is not None:
                servicemanager.LogMsg(
                    servicemanager.EVENTLOG_INFORMATION_TYPE,
                    servicemanager.PYS_SERVICE_STOPPED,
                    (self._svc_name_, ""),
                )

    def SvcStop(self) -> None:
        _log("stop requested")
        self._stop_event.set()
        stop_children(self._children)
        if servicemanager is not None:
            servicemanager.LogMsg(
                servicemanager.EVENTLOG_INFORMATION_TYPE,
                servicemanager.PYS_SERVICE_STOPPED,
                (self._svc_name_, ""),
            )

    def SvcShutdown(self) -> None:
        self.SvcStop()


# ===========================================================================
# CLI helpers (non-service)
# ===========================================================================

def cmd_check() -> int:
    """Print the resolved service config WITHOUT starting anything."""
    if _PYWIN32_IMPORT_ERROR is not None:
        print(f"pywin32 import failed: {_PYWIN32_IMPORT_ERROR}")
        print("Install it into the venv: uv pip install --python .venv pywin32")
        return 1
    py = resolve_python()
    print(f"Service name : {SERVICE_NAME}")
    print(f"Python       : {py}")
    print(f"Env file     : {ENV_FILE}  (present={ENV_FILE.exists()})")
    print(f"Log dir      : {LOG_DIR}")
    print("Children:")
    for spec in build_specs():
        print(f"  - {spec['name']:<10s} :{spec['port']:<6} {' '.join(spec['cmd'][1:])}")
    print("OK — config resolved, nothing started.")
    return 0


def cmd_status() -> int:
    if not PIDS_FILE.exists():
        print("No service_children.txt — the pilot service is not running.")
        return 1
    print("Child processes (from service_children.txt):")
    for line in PIDS_FILE.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            name, pid = line.split("=", 1)
            print(f"  {name:<10s} pid {pid}")
    return 0


def cmd_run() -> int:
    """Foreground run (no service registration). Ctrl+C to stop."""
    _log("=== foreground run starting ===")
    stop_event = threading.Event()
    children = start_children()
    try:
        print("Children started. Ctrl+C to stop.")
        for ch in children:
            print(f"  {ch.spec['name']:<10s} :{ch.spec['port']} pid {ch.proc.pid}")
        supervise(children, stop_event)
    except KeyboardInterrupt:
        print("\nStopping children...")
        stop_event.set()
    finally:
        stop_children(children)
    _log("=== foreground run stopped ===")
    return 0


def main() -> int:
    argv = [a for a in sys.argv[1:]]
    if not argv:
        print(__doc__)
        return 1

    if argv[0] == "--check":
        return cmd_check()
    if argv[0] == "status":
        return cmd_status()
    if argv[0] == "run":
        return cmd_run()

    if win32serviceutil is None:
        print(f"pywin32 not available: {_PYWIN32_IMPORT_ERROR}")
        print("Install it into the venv: uv pip install --python .venv pywin32")
        return 1

    # Delegate service verbs (install/start/stop/restart/remove/update/...) to pywin32
    win32serviceutil.HandleCommandLine(PilotBackendService, argv=argv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
