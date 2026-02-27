import importlib
from pathlib import Path
import daemon.daemon_log as dlog


def _reload_with_path(tmp_path: Path):
    """Point LOG_PATH at a temp file for test isolation."""
    dlog.LOG_PATH = tmp_path / "daemon.log"
    return dlog


def test_write_creates_file(tmp_path):
    dl = _reload_with_path(tmp_path)
    dl.write("hello world")
    assert dl.LOG_PATH.exists()
    content = dl.LOG_PATH.read_text()
    assert "[INFO] hello world" in content


def test_write_level_error(tmp_path):
    dl = _reload_with_path(tmp_path)
    dl.write("something broke", level="ERROR")
    assert "[ERROR] something broke" in dl.LOG_PATH.read_text()


def test_tail_returns_last_n(tmp_path):
    dl = _reload_with_path(tmp_path)
    for i in range(10):
        dl.write(f"line {i}")
    result = dl.tail(3)
    assert len(result) == 3
    assert "line 9" in result[-1]
    assert "line 7" in result[0]


def test_tail_empty_log(tmp_path):
    dl = _reload_with_path(tmp_path)
    assert dl.tail(10) == []


def test_trim_removes_old_lines(tmp_path):
    dl = _reload_with_path(tmp_path)
    # Write 20 lines, trim to 10
    for i in range(20):
        dl.LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(dl.LOG_PATH, "a") as f:
            f.write(f"line {i}\n")
    removed = dl.trim(max_lines=10)
    assert removed == 10
    lines = dl.LOG_PATH.read_text().splitlines()
    assert len(lines) == 10
    assert lines[0] == "line 10"
    assert lines[-1] == "line 19"


def test_trim_no_op_when_under_limit(tmp_path):
    dl = _reload_with_path(tmp_path)
    for i in range(5):
        dl.write(f"line {i}")
    removed = dl.trim(max_lines=100)
    assert removed == 0


def test_trim_no_op_when_missing(tmp_path):
    dl = _reload_with_path(tmp_path)
    assert dl.trim() == 0
