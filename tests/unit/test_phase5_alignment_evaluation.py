from __future__ import annotations

import json
import wave
from pathlib import Path

import pytest

from legendar.domain.value_objects.language import LanguageError
from scripts.phase5_alignment_evaluation import (
    _error_summary,
    _percentile,
    _read_manifest,
)


def _make_wave(path: Path) -> None:
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(16_000)
        target.writeframes(b"\0\0" * 32_000)


def test_percentile_uses_nearest_rank_for_p95() -> None:
    assert _percentile([0.1, 0.2, 0.3, 0.4], 95.0) == pytest.approx(0.4)
    assert _percentile([], 95.0) is None


def test_error_summary_reports_start_end_and_provisional_targets() -> None:
    result = _error_summary([0.02, 0.04], [0.03, 0.05])

    assert result["median_start_error_ms"] == pytest.approx(30.0)
    assert result["p95_start_error_ms"] == pytest.approx(40.0)
    assert result["median_end_error_ms"] == pytest.approx(40.0)
    assert result["p95_end_error_ms"] == pytest.approx(50.0)
    assert result["median_boundary_error_ms"] == pytest.approx(35.0)
    assert result["p95_boundary_error_ms"] == pytest.approx(50.0)
    assert result["provisional_targets"]["both_met"]


def test_error_summary_marks_missing_data_without_claiming_success() -> None:
    result = _error_summary([], [])

    assert result["median_boundary_error_ms"] is None
    assert result["p95_boundary_error_ms"] is None
    assert not result["provisional_targets"]["both_met"]


def test_reads_annotated_manifest_with_relative_audio_and_global_word_times(
    tmp_path: Path,
) -> None:
    audio = tmp_path / "sample.wav"
    _make_wave(audio)
    manifest = tmp_path / "references.jsonl"
    record = {
        "sample_id": "sample-01",
        "audio": "sample.wav",
        "language": "pt-BR",
        "timeline_offset_seconds": 4.5,
        "segments": [
            {
                "text": "bom dia",
                "window_start_seconds": 0.0,
                "window_end_seconds": 1.5,
                "words": [
                    {"word": "bom", "start": 4.6, "end": 4.9},
                    {"word": "dia", "start": 5.0, "end": 5.3},
                ],
            }
        ],
    }
    manifest.write_text(
        json.dumps(record, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    rows = _read_manifest(manifest)

    assert len(rows) == 1
    assert rows[0]["sample_id"] == "sample-01"
    assert rows[0]["audio_path"] == audio.resolve()
    assert rows[0]["language"].value == "pt"
    assert rows[0]["timeline_offset_seconds"] == pytest.approx(4.5)
    assert rows[0]["segments"][0]["window"].start == pytest.approx(0.0)
    assert rows[0]["segments"][0]["words"][0]["start"] == pytest.approx(4.6)


def test_manifest_rejects_reference_word_count_that_differs_from_text(
    tmp_path: Path,
) -> None:
    audio = tmp_path / "sample.wav"
    _make_wave(audio)
    manifest = tmp_path / "references.jsonl"
    manifest.write_text(
        json.dumps(
            {
                "sample_id": "bad-01",
                "audio": "sample.wav",
                "language": "pt",
                "segments": [
                    {
                        "text": "bom dia",
                        "window_start_seconds": 0.0,
                        "window_end_seconds": 1.0,
                        "words": [{"word": "bom", "start": 0.1, "end": 0.3}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="uma palavra de referência"):
        _read_manifest(manifest)


def test_manifest_rejects_non_finite_reference_timestamp(tmp_path: Path) -> None:
    audio = tmp_path / "sample.wav"
    _make_wave(audio)
    manifest = tmp_path / "references.jsonl"
    record = {
        "sample_id": "bad-02",
        "audio": "sample.wav",
        "language": "en",
        "segments": [
            {
                "text": "hello",
                "window_start_seconds": 0.0,
                "window_end_seconds": 1.0,
                "words": [{"word": "hello", "start": float("nan"), "end": 0.5}],
            }
        ],
    }
    manifest.write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(ValueError, match="deve ser finito"):
        _read_manifest(manifest)


def test_manifest_rejects_unknown_language(tmp_path: Path) -> None:
    manifest = tmp_path / "references.jsonl"
    manifest.write_text(
        json.dumps(
            {
                "sample_id": "bad-03",
                "audio": "missing.wav",
                "language": "es",
                "segments": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(LanguageError, match="[Ii]dioma"):
        _read_manifest(manifest)


def test_manifest_rejects_missing_audio_for_supported_language(tmp_path: Path) -> None:
    manifest = tmp_path / "references.jsonl"
    manifest.write_text(
        json.dumps(
            {
                "sample_id": "bad-04",
                "audio": "missing.wav",
                "language": "pt",
                "segments": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(FileNotFoundError, match="arquivo de áudio"):
        _read_manifest(manifest)
