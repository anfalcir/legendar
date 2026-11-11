from __future__ import annotations

from pathlib import Path

import pytest

from legendar.application.job.context import CancellationTokenImpl
from legendar.domain.entities.media import AudioAsset
from legendar.domain.entities.transcript import Transcript, TranscriptSegment
from legendar.domain.errors.catalog import JobCancelledError, ModelError
from legendar.domain.value_objects.language import Language
from legendar.domain.value_objects.time import TimeRange
from legendar.infrastructure.alignment.whisperx import WhisperXAligner

DEFAULT_ALIGNMENT_WINDOW = TimeRange(0.0, 2.0)


class FakeWaveform:
    def __init__(self, sample_count: int = 48_000) -> None:
        self.size = sample_count


class ProgressRecorder:
    def __init__(self) -> None:
        self.reports: list[tuple[float, str]] = []

    def report(self, fraction: float, message: str = "") -> None:
        self.reports.append((fraction, message))


def make_audio(
    *,
    duration: float = 3.0,
    timeline_offset: float = 5.25,
) -> AudioAsset:
    return AudioAsset(
        path="/tmp/normalized.wav",
        sample_rate_hz=16_000,
        channels=1,
        sample_format="pcm_s16le",
        duration_seconds=duration,
        timeline_start_seconds=timeline_offset,
        timeline_offset_source="stream.start_time",
    )


def make_transcript(
    *,
    language: Language = Language.PORTUGUESE,
    text: str = "Olá mundo",
    window: TimeRange | None = DEFAULT_ALIGNMENT_WINDOW,
) -> Transcript:
    return Transcript(
        segments=(
            TranscriptSegment(
                text=text,
                alignment_window=window,
            ),
        ),
        language=language,
        model_name="base",
        model_revision="20250625",
    )


def make_aligner(
    tmp_path: Path,
    *,
    result: dict | None = None,
    calls: list | None = None,
    loader_calls: list | None = None,
    model_error: Exception | None = None,
    waveform: FakeWaveform | None = None,
    **kwargs,
) -> WhisperXAligner:
    model_calls = loader_calls if loader_calls is not None else []
    align_calls = calls if calls is not None else []
    fake_model = object()
    fake_metadata = {"language": "pt", "dictionary": {}}

    def loader(language: str, device: str, root: Path):
        model_calls.append((language, device, root))
        if model_error is not None:
            raise model_error
        return fake_model, fake_metadata

    def align_function(
        segments, model, metadata, audio, device, *, progress_callback=None
    ):
        align_calls.append((segments, model, metadata, audio, device))
        if progress_callback is not None:
            progress_callback(50.0)
        return result or {
            "word_segments": [
                {"word": "Olá", "start": 0.1, "end": 0.4, "score": 0.95},
                {"word": "mundo", "start": 0.55, "end": 0.8, "score": 0.9},
            ]
        }

    return WhisperXAligner(
        tmp_path / "models",
        device="cpu",
        model_loader=loader,
        align_function=align_function,
        device_resolver=lambda requested: requested,
        audio_loader=lambda _audio: waveform or FakeWaveform(),
        version_provider=lambda: "3.8.6",
        punkt_preparer=lambda _language, _path: None,
        **kwargs,
    )


def test_aligns_words_and_applies_source_offset_exactly_once(tmp_path: Path) -> None:
    calls: list = []
    aligner = make_aligner(tmp_path, calls=calls)
    progress = ProgressRecorder()

    result = aligner.align(
        make_audio(),
        make_transcript(),
        progress=progress,
    )

    words = result.transcript.segments[0].words
    assert [word.text for word in words] == ["Olá", "mundo"]
    assert [word.range for word in words] == [
        TimeRange(5.35, 5.65),
        TimeRange(5.80, 6.05),
    ]
    assert result.transcript.segments[0].range == TimeRange(5.35, 6.05)
    assert result.transcript.segments[0].alignment_window == TimeRange(0.0, 2.0)
    assert result.diagnostics.aligned_words == 2
    assert result.diagnostics.unmatched_words == ()
    assert result.diagnostics.issues == ()
    assert result.diagnostics.alignment_ratio == pytest.approx(1.0)
    assert result.is_complete
    assert result.model_name == (
        "WhisperX 3.8.6 / jonatasgrosman/wav2vec2-large-xlsr-53-portuguese"
    )
    assert len(calls) == 1
    assert calls[0][0][0] == {"start": 0.0, "end": 2.0, "text": "Olá mundo"}
    assert progress.reports[-1] == (1.0, "Forced alignment WhisperX concluído")


def test_unaligned_word_is_not_interpolated_or_given_a_timestamp(
    tmp_path: Path,
) -> None:
    aligner = make_aligner(
        tmp_path,
        result={
            "word_segments": [
                {"word": "Olá", "start": 0.1, "end": 0.4, "score": 0.9},
                {"word": "mundo"},
            ]
        },
    )

    result = aligner.align(
        make_audio(),
        make_transcript(),
        progress=ProgressRecorder(),
    )

    words = result.transcript.segments[0].words
    assert words[0].is_aligned
    assert not words[1].is_aligned
    assert words[1].range is None
    assert [word.text for word in result.diagnostics.unmatched_words] == ["mundo"]
    assert result.diagnostics.aligned_words == 1
    assert result.diagnostics.alignment_ratio == pytest.approx(0.5)
    assert "unmatched_word" in result.diagnostics.issues
    assert not result.is_complete


def test_missing_search_window_does_not_load_or_call_alignment_model(
    tmp_path: Path,
) -> None:
    calls: list = []
    loads: list = []
    aligner = make_aligner(
        tmp_path,
        calls=calls,
        loader_calls=loads,
    )

    result = aligner.align(
        make_audio(),
        make_transcript(window=None),
        progress=ProgressRecorder(),
    )

    assert loads == []
    assert calls == []
    assert result.diagnostics.aligned_words == 0
    assert [word.text for word in result.diagnostics.unmatched_words] == [
        "Olá",
        "mundo",
    ]
    assert "missing_alignment_window" in result.diagnostics.issues


def test_out_of_bounds_search_window_is_rejected_without_loading_model(
    tmp_path: Path,
) -> None:
    loads: list = []
    aligner = make_aligner(tmp_path, loader_calls=loads)

    result = aligner.align(
        make_audio(),
        make_transcript(window=TimeRange(2.0, 4.0)),
        progress=ProgressRecorder(),
    )

    assert loads == []
    assert result.diagnostics.aligned_words == 0
    assert "out_of_bounds" in result.diagnostics.issues
    assert len(result.diagnostics.unmatched_words) == 2


def test_alignment_window_longer_than_configured_limit_is_not_processed(
    tmp_path: Path,
) -> None:
    loads: list = []
    aligner = make_aligner(
        tmp_path,
        loader_calls=loads,
        max_window_seconds=1.0,
    )

    result = aligner.align(
        make_audio(duration=3.0, timeline_offset=0.0),
        make_transcript(window=TimeRange(0.0, 2.0)),
        progress=ProgressRecorder(),
    )

    assert loads == []
    assert result.diagnostics.aligned_words == 0
    assert "window_too_long" in result.diagnostics.issues


def test_reuses_loaded_alignment_model_for_the_same_language(tmp_path: Path) -> None:
    loads: list = []
    calls: list = []
    aligner = make_aligner(
        tmp_path,
        calls=calls,
        loader_calls=loads,
    )

    for _ in range(2):
        aligner.align(
            make_audio(),
            make_transcript(),
            progress=ProgressRecorder(),
        )

    assert len(loads) == 1
    assert len(calls) == 2
    assert loads[0][0] == "pt"
    assert loads[0][1] == "cpu"
    assert loads[0][2] == tmp_path / "models" / "whisperx-align"
    assert aligner.loaded_languages == ("pt",)
    assert aligner.loaded_device == "cpu"
    assert aligner.revision == "3.8.6"


def test_english_uses_english_alignment_model(tmp_path: Path) -> None:
    loads: list = []
    aligner = make_aligner(tmp_path, loader_calls=loads)

    aligner.align(
        make_audio(timeline_offset=0.0),
        make_transcript(
            language=Language.ENGLISH,
            text="Hello world",
        ),
        progress=ProgressRecorder(),
    )

    assert loads[0][0] == "en"


def test_overlapping_words_are_reported_as_an_alignment_issue(tmp_path: Path) -> None:
    aligner = make_aligner(
        tmp_path,
        result={
            "word_segments": [
                {"word": "Olá", "start": 0.1, "end": 0.6, "score": 0.9},
                {"word": "mundo", "start": 0.5, "end": 0.8, "score": 0.9},
            ]
        },
    )

    result = aligner.align(
        make_audio(timeline_offset=0.0),
        make_transcript(),
        progress=ProgressRecorder(),
    )

    assert result.diagnostics.aligned_words == 2
    assert "overlap" in result.diagnostics.issues
    assert not result.is_complete


def test_invalid_alignment_confidence_does_not_create_valid_word(
    tmp_path: Path,
) -> None:
    aligner = make_aligner(
        tmp_path,
        result={
            "word_segments": [
                {"word": "Olá", "start": 0.1, "end": 0.4, "score": 1.2},
                {"word": "mundo", "start": 0.5, "end": 0.8, "score": 0.9},
            ]
        },
    )

    result = aligner.align(
        make_audio(timeline_offset=0.0),
        make_transcript(),
        progress=ProgressRecorder(),
    )

    assert result.diagnostics.aligned_words == 1
    assert result.diagnostics.unmatched_words[0].text == "Olá"
    assert "invalid_word_score" in result.diagnostics.issues


def test_cancelled_job_does_not_load_model(tmp_path: Path) -> None:
    loads: list = []
    aligner = make_aligner(tmp_path, loader_calls=loads)
    token = CancellationTokenImpl()
    token.cancel("cancelado antes do alinhamento")

    with pytest.raises(JobCancelledError, match="antes do alinhamento"):
        aligner.align(
            make_audio(),
            make_transcript(),
            progress=ProgressRecorder(),
            token=token,
        )

    assert loads == []


def test_model_loading_failure_becomes_domain_error(tmp_path: Path) -> None:
    aligner = make_aligner(
        tmp_path,
        model_error=OSError("download unavailable"),
    )

    with pytest.raises(ModelError, match="Não foi possível carregar o modelo WhisperX"):
        aligner.align(
            make_audio(),
            make_transcript(),
            progress=ProgressRecorder(),
        )


def test_audio_duration_mismatch_is_rejected_before_model_loading(
    tmp_path: Path,
) -> None:
    loads: list = []
    aligner = make_aligner(
        tmp_path,
        loader_calls=loads,
        waveform=FakeWaveform(sample_count=32_000),
    )

    with pytest.raises(ModelError, match="diverge da duração"):
        aligner.align(
            make_audio(duration=3.0),
            make_transcript(),
            progress=ProgressRecorder(),
        )

    assert loads == []


def test_invalid_device_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Dispositivo WhisperX inválido"):
        WhisperXAligner(tmp_path, device="mps")



def test_missing_word_does_not_shift_following_alignment_to_wrong_token(
    tmp_path: Path,
) -> None:
    aligner = make_aligner(
        tmp_path,
        result={
            "word_segments": [
                {"word": "mundo", "start": 0.55, "end": 0.8, "score": 0.9},
            ]
        },
    )

    result = aligner.align(
        make_audio(),
        make_transcript(),
        progress=ProgressRecorder(),
    )

    words = result.transcript.segments[0].words
    assert words[0].text == "Olá"
    assert words[0].range is None
    assert words[1].text == "mundo"
    assert words[1].range == TimeRange(5.80, 6.05)
    assert [word.text for word in result.diagnostics.unmatched_words] == ["Olá"]
    assert result.diagnostics.aligned_words == 1


def test_negative_stream_start_maps_valid_later_word_times(tmp_path: Path) -> None:
    aligner = make_aligner(
        tmp_path,
        result={
            "word_segments": [
                {"word": "Olá", "start": 1.1, "end": 1.4, "score": 0.9},
                {"word": "mundo", "start": 1.55, "end": 1.8, "score": 0.9},
            ]
        },
    )

    result = aligner.align(
        make_audio(timeline_offset=-0.5),
        make_transcript(window=TimeRange(1.0, 2.0)),
        progress=ProgressRecorder(),
    )

    ranges = [word.range for word in result.transcript.segments[0].words]
    assert ranges[0].start == pytest.approx(0.6)
    assert ranges[0].end == pytest.approx(0.9)
    assert ranges[1].start == pytest.approx(1.05)
    assert ranges[1].end == pytest.approx(1.3)
