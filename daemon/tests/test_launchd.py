from daemon import launchd


class RunRecorder:
    def __init__(self):
        self.calls = []

    def __call__(self, args, **kwargs):
        self.calls.append((args, kwargs))


def test_launchd_install_dry_run_returns_plist_without_writing_or_loading(tmp_path, monkeypatch):
    plist_path = tmp_path / "com.devmemory.daemon.plist"
    monkeypatch.setattr(launchd, "PLIST_PATH", plist_path)
    monkeypatch.setattr(launchd, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(launchd, "_devmemory_bin", lambda: "/usr/local/bin/devmemory")
    run = RunRecorder()
    monkeypatch.setattr(launchd.subprocess, "run", run)

    plist = launchd.install(dry_run=True)

    assert "<string>com.devmemory.daemon</string>" in plist
    assert "<string>/usr/local/bin/devmemory</string>" in plist
    assert "<string>daemon</string>" in plist
    assert "<string>start</string>" in plist
    assert not plist_path.exists()
    assert run.calls == []
