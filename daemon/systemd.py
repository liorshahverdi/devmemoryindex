"""
Linux systemd --user integration for DevMemoryIndex daemon.

Installs/uninstalls a user service so the daemon starts automatically and
restarts if it crashes.

Service path: ~/.config/systemd/user/devmemory.service
Log path:     ~/.local/share/devmemory/daemon.log
"""

import shutil
import subprocess
import sys
from pathlib import Path

SERVICE_NAME = "devmemory.service"
SERVICE_PATH = Path.home() / ".config" / "systemd" / "user" / SERVICE_NAME
LOG_DIR = Path.home() / ".local" / "share" / "devmemory"


def _devmemory_bin() -> str:
    """Resolve the absolute path to the devmemory executable."""
    found = shutil.which("devmemory")
    if found:
        return found
    candidate = Path(sys.executable).parent / "devmemory"
    if candidate.exists():
        return str(candidate)
    raise RuntimeError(
        "Cannot locate 'devmemory' executable. "
        "Make sure the package is installed: uv pip install -e ."
    )


def service_unit() -> str:
    """Render the systemd user service unit."""
    bin_path = _devmemory_bin()
    log_out = LOG_DIR / "daemon.log"
    log_err = LOG_DIR / "daemon-error.log"
    return f"""[Unit]
Description=DevMemoryIndex background daemon
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={Path.home()}
ExecStart={bin_path} daemon start
Restart=on-failure
RestartSec=10
Environment=PYTHONUNBUFFERED=1
StandardOutput=append:{log_out}
StandardError=append:{log_err}

[Install]
WantedBy=default.target
"""


def _run_systemctl(args: list[str]) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["systemctl", "--user", *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "unknown error").strip()
        raise RuntimeError(f"systemctl --user {' '.join(args)} failed: {detail}")
    return result


def install(dry_run: bool = False) -> str:
    """Write and enable the systemd user service. Returns path or unit text for dry-run."""
    unit = service_unit()
    if dry_run:
        return unit

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    SERVICE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SERVICE_PATH.write_text(unit)

    _run_systemctl(["daemon-reload"])
    _run_systemctl(["enable", "--now", SERVICE_NAME])
    return str(SERVICE_PATH)


def uninstall() -> bool:
    """Disable and remove the systemd user service. Returns False if not installed."""
    if not SERVICE_PATH.exists():
        return False

    _run_systemctl(["disable", "--now", SERVICE_NAME])
    SERVICE_PATH.unlink()
    _run_systemctl(["daemon-reload"])
    return True


def status() -> dict:
    """Return install state and whether the systemd user service is active."""
    installed = SERVICE_PATH.exists()
    if not installed:
        return {
            "installed": False,
            "running": False,
            "service": str(SERVICE_PATH),
            "active_state": "not-installed",
        }

    result = subprocess.run(
        ["systemctl", "--user", "is-active", SERVICE_NAME],
        capture_output=True,
        text=True,
    )
    active_state = (result.stdout or result.stderr or "unknown").strip() or "unknown"
    return {
        "installed": True,
        "running": result.returncode == 0 and active_state == "active",
        "service": str(SERVICE_PATH),
        "active_state": active_state,
    }
