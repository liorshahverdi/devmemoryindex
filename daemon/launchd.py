"""
macOS launchd integration for DevMemoryIndex daemon.

Installs/uninstalls a LaunchAgent plist so the daemon starts automatically
at login and restarts if it crashes.

Plist path: ~/Library/LaunchAgents/com.devmemory.daemon.plist
Log path:   ~/.local/share/devmemory/daemon.log
"""

import shutil
import subprocess
import sys
from pathlib import Path

PLIST_LABEL = "com.devmemory.daemon"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{PLIST_LABEL}.plist"
LOG_DIR = Path.home() / ".local" / "share" / "devmemory"


def _devmemory_bin() -> str:
    """Resolve the absolute path to the devmemory executable."""
    found = shutil.which("devmemory")
    if found:
        return found
    # Fall back to same bin dir as the running Python (covers venv usage)
    candidate = Path(sys.executable).parent / "devmemory"
    if candidate.exists():
        return str(candidate)
    raise RuntimeError(
        "Cannot locate 'devmemory' executable. "
        "Make sure the package is installed: uv pip install -e ."
    )


def _plist_xml() -> str:
    bin_path = _devmemory_bin()
    log_out = LOG_DIR / "daemon.log"
    log_err = LOG_DIR / "daemon-error.log"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{PLIST_LABEL}</string>

    <key>ProgramArguments</key>
    <array>
        <string>{bin_path}</string>
        <string>daemon</string>
        <string>start</string>
    </array>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>{log_out}</string>

    <key>StandardErrorPath</key>
    <string>{log_err}</string>

    <key>WorkingDirectory</key>
    <string>{Path.home()}</string>
</dict>
</plist>
"""


def install() -> str:
    """Write the plist and load it. Returns the plist path."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.write_text(_plist_xml())

    # Unload first in case an older version is already loaded
    subprocess.run(
        ["launchctl", "unload", str(PLIST_PATH)],
        capture_output=True,
    )
    result = subprocess.run(
        ["launchctl", "load", str(PLIST_PATH)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"launchctl load failed: {result.stderr.strip()}")
    return str(PLIST_PATH)


def uninstall() -> bool:
    """Unload and remove the plist. Returns False if it wasn't installed."""
    if not PLIST_PATH.exists():
        return False
    subprocess.run(
        ["launchctl", "unload", str(PLIST_PATH)],
        capture_output=True,
    )
    PLIST_PATH.unlink()
    return True


def status() -> dict:
    """Return install state and whether the job is currently running."""
    installed = PLIST_PATH.exists()
    running = False
    pid = None
    if installed:
        result = subprocess.run(
            ["launchctl", "list", PLIST_LABEL],
            capture_output=True,
            text=True,
        )
        running = result.returncode == 0
        # Parse PID from output like: "12345\t0\tcom.devmemory.daemon"
        if running and result.stdout:
            parts = result.stdout.strip().split("\t")
            if parts[0].lstrip("-").isdigit() and parts[0] != "-":
                pid = int(parts[0])
    return {"installed": installed, "running": running, "pid": pid, "plist": str(PLIST_PATH)}
