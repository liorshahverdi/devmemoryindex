from pathlib import Path
from types import SimpleNamespace

import pytest

from daemon import systemd


class RunRecorder:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.calls = []
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    def __call__(self, args, **kwargs):
        self.calls.append((args, kwargs))
        return SimpleNamespace(
            returncode=self.returncode,
            stdout=self.stdout,
            stderr=self.stderr,
        )


def test_service_unit_uses_resolved_devmemory_executable_and_log_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(systemd, "SERVICE_PATH", tmp_path / "devmemory.service")
    monkeypatch.setattr(systemd, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(systemd, "_devmemory_bin", lambda: "/opt/devmemory/bin/devmemory")

    unit = systemd.service_unit()

    assert "Description=DevMemoryIndex background daemon" in unit
    assert "After=network-online.target" in unit
    assert "Wants=network-online.target" in unit
    assert f"WorkingDirectory={Path.home()}" in unit
    assert "ExecStart=/opt/devmemory/bin/devmemory daemon start" in unit
    assert "Restart=on-failure" in unit
    assert "RestartSec=10" in unit
    assert "Environment=PYTHONUNBUFFERED=1" in unit
    assert f"StandardOutput=append:{tmp_path / 'logs' / 'daemon.log'}" in unit
    assert f"StandardError=append:{tmp_path / 'logs' / 'daemon-error.log'}" in unit
    assert "WantedBy=default.target" in unit


def test_install_writes_service_and_enables_it(tmp_path, monkeypatch):
    service_path = tmp_path / "systemd" / "user" / "devmemory.service"
    monkeypatch.setattr(systemd, "SERVICE_PATH", service_path)
    monkeypatch.setattr(systemd, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(systemd, "_devmemory_bin", lambda: "/usr/local/bin/devmemory")
    run = RunRecorder()
    monkeypatch.setattr(systemd.subprocess, "run", run)

    installed = systemd.install()

    assert installed == str(service_path)
    assert service_path.exists()
    assert "ExecStart=/usr/local/bin/devmemory daemon start" in service_path.read_text()
    assert run.calls == [
        (["systemctl", "--user", "daemon-reload"], {"capture_output": True, "text": True}),
        (["systemctl", "--user", "enable", "--now", "devmemory.service"], {"capture_output": True, "text": True}),
    ]


def test_install_dry_run_returns_unit_without_writing_or_running_commands(tmp_path, monkeypatch):
    service_path = tmp_path / "devmemory.service"
    monkeypatch.setattr(systemd, "SERVICE_PATH", service_path)
    monkeypatch.setattr(systemd, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(systemd, "_devmemory_bin", lambda: "/usr/bin/devmemory")
    run = RunRecorder()
    monkeypatch.setattr(systemd.subprocess, "run", run)

    unit = systemd.install(dry_run=True)

    assert "ExecStart=/usr/bin/devmemory daemon start" in unit
    assert not service_path.exists()
    assert run.calls == []


def test_install_raises_when_systemctl_fails(tmp_path, monkeypatch):
    service_path = tmp_path / "devmemory.service"
    monkeypatch.setattr(systemd, "SERVICE_PATH", service_path)
    monkeypatch.setattr(systemd, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(systemd, "_devmemory_bin", lambda: "/usr/bin/devmemory")
    run = RunRecorder(returncode=1, stderr="no user bus")
    monkeypatch.setattr(systemd.subprocess, "run", run)

    with pytest.raises(RuntimeError, match="systemctl --user daemon-reload failed: no user bus"):
        systemd.install()


def test_uninstall_disables_and_removes_existing_service(tmp_path, monkeypatch):
    service_path = tmp_path / "devmemory.service"
    service_path.write_text("unit")
    monkeypatch.setattr(systemd, "SERVICE_PATH", service_path)
    run = RunRecorder()
    monkeypatch.setattr(systemd.subprocess, "run", run)

    assert systemd.uninstall() is True

    assert not service_path.exists()
    assert run.calls == [
        (["systemctl", "--user", "disable", "--now", "devmemory.service"], {"capture_output": True, "text": True}),
        (["systemctl", "--user", "daemon-reload"], {"capture_output": True, "text": True}),
    ]


def test_uninstall_returns_false_when_not_installed(tmp_path, monkeypatch):
    monkeypatch.setattr(systemd, "SERVICE_PATH", tmp_path / "missing.service")
    run = RunRecorder()
    monkeypatch.setattr(systemd.subprocess, "run", run)

    assert systemd.uninstall() is False
    assert run.calls == []


def test_status_reports_installed_running_and_active_state(tmp_path, monkeypatch):
    service_path = tmp_path / "devmemory.service"
    service_path.write_text("unit")
    monkeypatch.setattr(systemd, "SERVICE_PATH", service_path)
    run = RunRecorder(returncode=0, stdout="active\n")
    monkeypatch.setattr(systemd.subprocess, "run", run)

    status = systemd.status()

    assert status == {
        "installed": True,
        "running": True,
        "service": str(service_path),
        "active_state": "active",
    }
    assert run.calls == [
        (["systemctl", "--user", "is-active", "devmemory.service"], {"capture_output": True, "text": True})
    ]


def test_status_reports_not_installed_without_systemctl(tmp_path, monkeypatch):
    monkeypatch.setattr(systemd, "SERVICE_PATH", tmp_path / "missing.service")
    run = RunRecorder(returncode=0, stdout="active\n")
    monkeypatch.setattr(systemd.subprocess, "run", run)

    assert systemd.status() == {
        "installed": False,
        "running": False,
        "service": str(tmp_path / "missing.service"),
        "active_state": "not-installed",
    }
    assert run.calls == []
