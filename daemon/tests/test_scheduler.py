from datetime import date

import daemon.scheduler as scheduler


MONDAY = date(2026, 6, 22)
TUESDAY = date(2026, 6, 23)


def _quiet_daily_jobs(monkeypatch):
    monkeypatch.setattr(scheduler, "prune_memories", lambda: 0)
    monkeypatch.setattr(scheduler, "dedup_memories", lambda: 0)
    monkeypatch.setattr(scheduler.dlog, "trim", lambda: 0)


def test_periodic_jobs_run_edge_inference_once_each_monday(monkeypatch):
    _quiet_daily_jobs(monkeypatch)
    calls = []
    logs = []
    monkeypatch.setattr(
        scheduler,
        "run_edge_inference",
        lambda: calls.append("edge") or {"edges_added": 2, "pairs_scanned": 9},
    )
    monkeypatch.setattr(scheduler, "_log", lambda message, level="INFO": logs.append((level, message)))
    state = {}

    scheduler._run_periodic_jobs(MONDAY, state)
    scheduler._run_periodic_jobs(MONDAY, state)

    assert calls == ["edge"]
    assert state["last_edge_inference_date"] == MONDAY
    assert any("Auto-linked 2 memory graph edges" in message for _level, message in logs)


def test_periodic_jobs_skip_edge_inference_on_non_monday(monkeypatch):
    _quiet_daily_jobs(monkeypatch)
    calls = []
    monkeypatch.setattr(
        scheduler,
        "run_edge_inference",
        lambda: calls.append("edge") or {"edges_added": 1, "pairs_scanned": 1},
    )
    state = {}

    scheduler._run_periodic_jobs(TUESDAY, state)

    assert calls == []
    assert "last_edge_inference_date" not in state


def test_periodic_jobs_log_edge_inference_errors_without_crashing(monkeypatch):
    _quiet_daily_jobs(monkeypatch)
    logs = []

    def fail_edge_inference():
        raise RuntimeError("edge store unavailable")

    monkeypatch.setattr(scheduler, "run_edge_inference", fail_edge_inference)
    monkeypatch.setattr(scheduler, "_log", lambda message, level="INFO": logs.append((level, message)))
    state = {}

    scheduler._run_periodic_jobs(MONDAY, state)

    assert state["last_edge_inference_date"] == MONDAY
    assert ("WARN", "Edge inference failed: edge store unavailable") in logs
