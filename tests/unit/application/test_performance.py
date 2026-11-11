from __future__ import annotations

from legendar.application.pipeline.performance import PipelinePerformanceSession


def test_session_records_wall_cpu_resources_and_adapter_deltas() -> None:
    snapshots = iter(
        [
            {"process_rss_bytes": 100, "system_memory_available_bytes": 900},
            {"process_rss_bytes": 150, "system_memory_available_bytes": 850},
        ]
    )
    before = {
        "transcription": {
            "loaded": False,
            "configuration": {"adapter": "fake-whisper"},
            "counters": {"model_load_seconds": 0.0, "inference_seconds": 0.0},
        }
    }
    after = {
        "transcription": {
            "loaded": True,
            "configuration": {"adapter": "fake-whisper"},
            "counters": {"model_load_seconds": 2.5, "inference_seconds": 8.0},
        }
    }
    session = PipelinePerformanceSession(
        "job-test",
        resource_provider=lambda: next(snapshots),
        adapter_metrics_before=before,
    )
    session.set_metadata(audio_duration_seconds=120.0, translation_requested=False)
    session.set_count("recognized_words", 24)

    with session.measure("transcription"):
        pass

    report = session.build_report(
        status="completed",
        adapter_metrics_after=after,
    )

    assert report["schema_version"] == 1
    assert report["status"] == "completed"
    assert report["metadata"]["audio_duration_seconds"] == 120.0
    assert report["counts"]["recognized_words"] == 24
    assert len(report["stages"]) == 1
    stage = report["stages"][0]
    assert stage["name"] == "transcription"
    assert stage["wall_seconds"] >= 0
    assert stage["process_cpu_seconds"] >= 0
    assert stage["resources_before"]["process_rss_bytes"] == 100
    assert stage["resources_after"]["process_rss_bytes"] == 150
    adapter = report["adapters"]["transcription"]
    assert adapter["loaded_before_job"] is False
    assert adapter["loaded_after_job"] is True
    assert adapter["counter_delta"]["model_load_seconds"] == 2.5
    assert adapter["counter_delta"]["inference_seconds"] == 8.0


def test_session_keeps_failure_type_without_exception_text() -> None:
    session = PipelinePerformanceSession("job-failed")
    report = session.build_report(status="failed", error_type="ModelError")

    assert report["status"] == "failed"
    assert report["error_type"] == "ModelError"
    assert "traceback" not in report
    assert "exception_message" not in report
