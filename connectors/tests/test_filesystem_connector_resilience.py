"""Performance and resilience tests for FilesystemConnector."""

from pathlib import Path

from connectors.filesystem_connector import FilesystemConnector
from connectors import filesystem_connector as fs


class FakeStore:
    def __init__(self):
        self.ids_by_source = {}
        self.added = []
        self.deleted = []
        self.exists_calls = []

    def get_ids_by_source(self, source, type_filter=None):
        return set(self.ids_by_source.get(source, set()))

    def exists(self, memory_id):
        self.exists_calls.append(memory_id)
        return False

    def add(self, memory, vector):
        self.added.append(memory)
        self.ids_by_source.setdefault(memory.source, set()).add(memory.id)
        return True

    def delete(self, memory_id):
        self.deleted.append(memory_id)


def _write_py(path: Path, n_lines: int = 20) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(f"x = {i}" for i in range(n_lines)))
    return path


def _connector(tmp_path, roots, *, max_files=None, repo=None, progress=None):
    c = FilesystemConnector(
        dirs=[str(root) for root in roots],
        state_path=tmp_path / "state.json",
        max_files=max_files,
        repo=repo,
        progress_callback=progress,
    )
    c.store = FakeStore()
    return c


def test_second_collect_skips_unchanged_files_before_embedding(tmp_path, monkeypatch):
    root = tmp_path / "project"
    _write_py(root / "app.py")
    calls = []
    monkeypatch.setattr(fs, "embed", lambda text: calls.append(text) or [0.0] * 384)

    c = _connector(tmp_path, [root])
    assert c.collect() >= 1
    first_call_count = len(calls)

    assert c.collect() == 0

    assert len(calls) == first_call_count
    assert c.last_stats["skipped"]["unchanged"] == 1


def test_max_files_limits_scan_and_reports_progress(tmp_path, monkeypatch):
    root = tmp_path / "project"
    for i in range(3):
        _write_py(root / f"file_{i}.py")
    progress_events = []
    monkeypatch.setattr(fs, "embed", lambda text: [0.0] * 384)

    c = _connector(tmp_path, [root], max_files=2, progress=progress_events.append)
    c.collect()

    assert c.last_stats["inspected"] == 2
    assert c.last_stats["skipped"]["max_files"] == 1
    assert any(event["event"] == "file" and event["inspected"] == 2 for event in progress_events)
    assert progress_events[-1]["event"] == "summary"


def test_repo_filter_only_scans_matching_repo_directory(tmp_path, monkeypatch):
    wanted = tmp_path / "wanted"
    other = tmp_path / "other"
    _write_py(wanted / "app.py")
    _write_py(other / "app.py")
    monkeypatch.setattr(fs, "embed", lambda text: [0.0] * 384)

    c = _connector(tmp_path, [wanted, other], repo="wanted")
    c.collect()

    assert c.last_stats["roots_scanned"] == [str(wanted.resolve())]
    assert all("wanted" in memory.source for memory in c.store.added)


def test_collect_persists_fingerprints_after_each_file_for_resumability(tmp_path, monkeypatch):
    root = tmp_path / "project"
    first = _write_py(root / "first.py")
    second = _write_py(root / "second.py")
    calls = {"n": 0}

    def flaky_embed(text):
        calls["n"] += 1
        if calls["n"] > 1:
            raise RuntimeError("simulated interruption")
        return [0.0] * 384

    monkeypatch.setattr(fs, "embed", flaky_embed)
    c = _connector(tmp_path, [root])

    try:
        c.collect()
    except RuntimeError:
        pass

    state = fs.FilesystemIndexState(tmp_path / "state.json")
    assert str(first.resolve()) in state.data["files"]
    assert str(second.resolve()) not in state.data["files"]
