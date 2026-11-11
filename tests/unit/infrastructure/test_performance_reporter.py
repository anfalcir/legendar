from __future__ import annotations

import json
import os
from pathlib import Path

from legendar.infrastructure.diagnostics import performance as module
from legendar.infrastructure.diagnostics.performance import JsonPerformanceReporter


def test_reporter_writes_private_json_without_media_content(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        module,
        "collect_performance_environment",
        lambda: {"os": "TestOS", "cpu_model": "Test CPU"},
    )
    reporter = JsonPerformanceReporter(tmp_path / "logs")
    report = {
        "schema_version": 1,
        "job_id": "job-123",
        "status": "completed",
        "total_wall_seconds": 12.0,
        "metadata": {"audio_duration_seconds": 60.0},
        "counts": {"recognized_words": 10},
        "stages": [],
        "adapters": {},
    }

    path = reporter.write_report(report)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert path.parent == tmp_path / "logs" / "performance"
    assert payload["environment"]["cpu_model"] == "Test CPU"
    assert payload["metadata"]["audio_duration_seconds"] == 60.0
    assert "audio" not in payload
    assert "transcript" not in payload
    assert "subtitle" not in payload
    assert "source_path" not in payload
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert not list(path.parent.glob("*.partial"))


def test_reporter_uses_safe_filename_for_job_identifier(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(module, "collect_performance_environment", lambda: {})
    reporter = JsonPerformanceReporter(tmp_path / "logs")

    path = reporter.write_report({"job_id": "../../unsafe", "schema_version": 1})

    assert path.name == "job-unsafe.json"
    assert path.parent == tmp_path / "logs" / "performance"
