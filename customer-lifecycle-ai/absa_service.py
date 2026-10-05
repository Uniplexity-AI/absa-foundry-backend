"""
ABSA AI Backend - Windows Service wrapper.

Supervises the 6 uvicorn microservices as child processes of a single Windows Service:
  * Starting the service starts all 6; stopping it kills all 6 (whole process tree).
  * If a microservice crashes, it is restarted automatically.
  * All children live in a Windows Job Object, so if this supervisor itself dies,
    Windows kills the children too (no orphaned processes holding ports).

Why it is registered the way it is (see install_service.ps1):
  pywin32's pythonservice.exe cannot see packages inside a uv-created .venv
  ("No module named 'servicemanager'" -> Error 1053). So Windows runs the *base*
  interpreter directly on this script, and we add the .venv's site-packages below.

Usage:
  python absa_service.py console   # run the supervisor in the foreground (testing, Ctrl+C to stop)
  (Install / remove: run install_service.ps1 / uninstall_service.ps1 as Administrator.)

Logs:
  logs/service/supervisor.log      # start/stop/crash/restart events
  logs/service/<Name>.log          # stdout/stderr of each microservice
"""
import logging
import logging.handlers
import os
import site
import subprocess
import sys
import time

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_DIR = os.path.join(ROOT_DIR, ".venv")
VENV_SITE_PACKAGES = os.path.join(VENV_DIR, "Lib", "site-packages")
VENV_PYTHON = os.path.join(VENV_DIR, "Scripts", "python.exe")
LOG_DIR = os.path.join(ROOT_DIR, "logs", "service")

# Must run before importing pywin32: processes pywin32.pth (adds win32, win32\lib and the DLL dir).
site.addsitedir(VENV_SITE_PACKAGES)

import servicemanager  # noqa: E402
import win32api  # noqa: E402
import win32event  # noqa: E402
import win32job  # noqa: E402
import win32service  # noqa: E402
import win32serviceutil  # noqa: E402

RESTART_DELAY_SECONDS = 10     # wait before restarting a crashed microservice
HEALTH_CHECK_INTERVAL_MS = 5000

SERVICES = [
    {"name": "Gateway",    "dir": ROOT_DIR,                                                         "app": ["gateway.main:create_app", "--factory"], "port": 8080},
    {"name": "Feature",    "dir": os.path.join(ROOT_DIR, "services", "feature-engineering-service"),   "app": ["main:app"], "port": 8002},
    {"name": "State",      "dir": os.path.join(ROOT_DIR, "services", "customer-state-service"),        "app": ["main:app"], "port": 8003},
    {"name": "Prediction", "dir": os.path.join(ROOT_DIR, "services", "prediction-service"),            "app": ["main:app"], "port": 8004},
    {"name": "Decision",   "dir": os.path.join(ROOT_DIR, "services", "decision-intelligence-service"), "app": ["main:app"], "port": 8015},
    {"name": "Model",      "dir": os.path.join(ROOT_DIR, "services", "model-management-service"),      "app": ["main:app"], "port": 8006},
]


def _setup_logging() -> logging.Logger:
    os.makedirs(LOG_DIR, exist_ok=True)
    logger = logging.getLogger("absa_service")
    if not logger.handlers:
        handler = logging.handlers.RotatingFileHandler(
            os.path.join(LOG_DIR, "supervisor.log"), maxBytes=5_000_000, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


log = _setup_logging()


_PROCESS_JOB = None


def _get_process_job():
    """Put this process (and therefore every child it spawns) into a kill-on-close Job Object.

    The handle is kept in a module-level global on purpose: it must stay open until the
    process itself exits. If it were closed earlier (e.g. when a Supervisor object is
    garbage-collected after SvcDoRun returns), Windows would kill *this* process too,
    before pywin32 reports SERVICE_STOPPED -> "Error 1067: process terminated unexpectedly".
    """
    global _PROCESS_JOB
    if _PROCESS_JOB is None:
        try:
            job = win32job.CreateJobObject(None, "")
            info = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
            info["BasicLimitInformation"]["LimitFlags"] |= win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            win32job.SetInformationJobObject(job, win32job.JobObjectExtendedLimitInformation, info)
            win32job.AssignProcessToJobObject(job, win32api.GetCurrentProcess())
            _PROCESS_JOB = job
        except Exception:
            log.warning("Could not create Job Object; children may survive a supervisor crash.", exc_info=True)
    return _PROCESS_JOB


class Supervisor:
    """Starts, watches and stops the microservices. Independent of the Windows Service API."""

    def __init__(self):
        self.procs = {}          # name -> subprocess.Popen
        self.log_files = {}      # name -> open file handle
        self.next_restart = {}   # name -> earliest time a crashed service may be restarted
        self.job = _get_process_job()



    def _start(self, svc):
        name = svc["name"]
        cmd = [VENV_PYTHON, "-m", "uvicorn", *svc["app"], "--host", "0.0.0.0", "--port", str(svc["port"])]
        env = os.environ.copy()
        env["PYTHONPATH"] = ROOT_DIR
        env["PYTHONUNBUFFERED"] = "1"

        old = self.log_files.pop(name, None)
        if old:
            old.close()
        out = open(os.path.join(LOG_DIR, f"{name}.log"), "ab", buffering=0)
        out.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} starting {name} on :{svc['port']} =====\n".encode())
        self.log_files[name] = out

        self.procs[name] = subprocess.Popen(
            cmd,
            cwd=svc["dir"],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        log.info("Started %s (pid %s) on port %s", name, self.procs[name].pid, svc["port"])

    def start_all(self):
        log.info("Starting %d microservices using %s", len(SERVICES), VENV_PYTHON)
        for svc in SERVICES:
            try:
                self._start(svc)
            except Exception:
                log.exception("Failed to start %s", svc["name"])
                self.next_restart[svc["name"]] = time.time() + RESTART_DELAY_SECONDS

    def check_and_restart(self):
        """Restart any microservice that has exited."""
        now = time.time()
        for svc in SERVICES:
            name = svc["name"]
            proc = self.procs.get(name)
            if proc is not None and proc.poll() is None:
                continue  # still running
            if proc is not None and name not in self.next_restart:
                log.error("%s exited with code %s; restarting in %ss (see %s.log)",
                          name, proc.returncode, RESTART_DELAY_SECONDS, name)
                self.next_restart[name] = now + RESTART_DELAY_SECONDS
            if now >= self.next_restart.get(name, 0):
                self.next_restart.pop(name, None)
                try:
                    self._start(svc)
                except Exception:
                    log.exception("Failed to restart %s", name)
                    self.next_restart[name] = now + RESTART_DELAY_SECONDS

    def stop_all(self):
        log.info("Stopping all microservices")
        for name, proc in self.procs.items():
            if proc.poll() is None:
                # /T kills the whole tree (the venv python.exe launches a child interpreter).
                subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW)
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    log.warning("%s (pid %s) did not exit in time", name, proc.pid)
            log.info("Stopped %s", name)
        for f in self.log_files.values():
            f.close()
        self.procs.clear()
        self.log_files.clear()


class ABSABackendService(win32serviceutil.ServiceFramework):
    _svc_name_ = "ABSABackend"
    _svc_display_name_ = "ABSA AI Backend Service"
    _svc_description_ = "Manages and runs the 6 ABSA microservices (gateway, feature, state, prediction, decision, model)."

    def __init__(self, args):
        super().__init__(args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING, waitHint=30000)
        win32event.SetEvent(self.stop_event)

    def SvcDoRun(self):
        # pywin32's SvcRun has already reported SERVICE_RUNNING to Windows at this point.
        log.info("Windows service starting")
        supervisor = Supervisor()
        try:
            supervisor.start_all()
            while win32event.WaitForSingleObject(self.stop_event, HEALTH_CHECK_INTERVAL_MS) != win32event.WAIT_OBJECT_0:
                supervisor.check_and_restart()
        except Exception:
            log.exception("Supervisor crashed")
            raise
        finally:
            supervisor.stop_all()
            log.info("Windows service stopped")


def run_console():
    """Foreground mode for testing without the Service Control Manager."""
    print(f"Running supervisor in console mode. Logs: {LOG_DIR}  (Ctrl+C to stop)")
    supervisor = Supervisor()
    supervisor.start_all()
    try:
        while True:
            time.sleep(HEALTH_CHECK_INTERVAL_MS / 1000)
            supervisor.check_and_restart()
    except KeyboardInterrupt:
        pass
    finally:
        supervisor.stop_all()


if __name__ == "__main__":
    if len(sys.argv) == 1:
        # Launched by the Windows Service Control Manager.
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(ABSABackendService)
        servicemanager.StartServiceCtrlDispatcher()
    elif sys.argv[1] == "console":
        run_console()
    else:
        win32serviceutil.HandleCommandLine(ABSABackendService)
