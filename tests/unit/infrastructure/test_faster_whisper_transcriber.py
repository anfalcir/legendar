from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from legendar.application.job.context import CancellationTokenImpl
from legendar.domain.entities.media import AudioAsset
from legendar.domain.errors.catalog import JobCancelledError, ModelError
from legendar.domain.value_objects.language import Language
from legendar.domain.value_objects.time import TimeRange
from legendar.infrastructure.transcription.faster_whisper import (
    FasterWhisperTranscriber,
)


class ProgressRecorder:
    def __init__(self) -> None:
        self.reports: list[tuple[float, str]] = []

    def report(self, fraction: float, message: str = "") -> None:
        self.reports.append((fraction, message))


class FakeModel:
    def __init__(self, segments=None, *, error: Exception | None = None) -> None:
        self.segments = segments if segments is not None else [
            SimpleNamespace(start=0.0, end=0.4, text=" Olá,"),
            SimpleNamespace(start=0.5, end=1.0, text=" mundo! "),
        ]
        self.error = error
        self.calls: list[dict] = []
        self.generator_consumed = False

    def transcribe(self, waveform, **kwargs):
        self.calls.append({"waveform": waveform, **kwargs})

        def generate():
            if self.error is not None:
                raise self.error
            for segment in self.segments:
                yield segment
            self.generator_consumed = True

        return generate(), SimpleNamespace(
            language="pt", language_probability=0.99
        )


def make_audio(tmp_path: Path) -> AudioAsset:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "audio.wav"
    path.write_bytes(b"test fixture; the audio loader is injected")
    return AudioAsset(
        path=str(path),
        sample_rate_hz=16_000,
        channels=1,
        sample_format="pcm_s16le",
        duration_seconds=2.0,
        timeline_start_seconds=3.5,
        timeline_offset_source="stream.start_time",
    )


def make_transcriber(
    tmp_path: Path,
    model: FakeModel | None = None,
    *,
    loader_calls: list | None = None,
    **kwargs,
) -> FasterWhisperTranscriber:
    model = model or FakeModel()
    calls = loader_calls if loader_calls is not None else []

    def loader(name: str, device: str, compute_type: str, threads: int, root: Path):
        calls.append((name, device, compute_type, threads, root))
        return model

    return FasterWhisperTranscriber(
        tmp_path / "models",
        model_name="base",
        device="cpu",
        model_loader=loader,
        device_resolver=lambda requested: requested,
        audio_loader=lambda _asset: [0.0, 0.1, -0.1],
        version_provider=lambda: "1.2.1",
        **kwargs,
    )


def test_transcribes_and_consumes_the_complete_generator(tmp_path: Path) -> None:
    model = FakeModel()
    transcriber = make_transcriber(tmp_path, model)
    progress = ProgressRecorder()

    transcript = transcriber.transcribe(
        make_audio(tmp_path),
        language=Language.PORTUGUESE,
        progress=progress,
    )

    assert transcript.language is Language.PORTUGUESE
    assert transcript.text == "Olá, mundo!"
    assert transcript.model_name == "base"
    assert transcript.model_revision == "1.2.1"
    assert transcript.language_probability == 0.99
    assert [segment.text for segment in transcript.segments] == ["Olá,", "mundo!"]
    assert [segment.alignment_window for segment in transcript.segments] == [
        TimeRange(0.0, 0.4),
        TimeRange(0.5, 1.0),
    ]
    assert model.generator_consumed
    assert model.calls[0]["task"] == "transcribe"
    assert model.calls[0]["language"] == "pt"
    assert model.calls[0]["beam_size"] == 5
    assert model.calls[0]["word_timestamps"] is False
    assert model.calls[0]["vad_filter"] is False
    assert progress.reports == [
        (1.0, "Reconhecimento faster-whisper base concluído")
    ]


def test_model_is_loaded_once_and_reused_between_jobs(tmp_path: Path) -> None:
    calls: list = []
    transcriber = make_transcriber(tmp_path, loader_calls=calls)

    for _ in range(2):
        transcriber.transcribe(
            make_audio(tmp_path),
            language=Language.PORTUGUESE,
            progress=ProgressRecorder(),
        )

    assert len(calls) == 1
    assert calls[0][0:4] == ("base", "cpu", "int8", 4)
    assert calls[0][4] == tmp_path / "models" / "faster-whisper"


def test_automatic_compute_type_is_int8_on_cpu(tmp_path: Path) -> None:
    transcriber = make_transcriber(tmp_path)

    transcriber.transcribe(
        make_audio(tmp_path),
        language=Language.PORTUGUESE,
        progress=ProgressRecorder(),
    )

    assert transcriber.performance_snapshot()["configuration"]["compute_type"] == "int8"


def test_invalid_configuration_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="compute_type"):
        FasterWhisperTranscriber(tmp_path, compute_type="unsupported")
    with pytest.raises(ValueError, match="cpu_threads"):
        FasterWhisperTranscriber(tmp_path, cpu_threads=0)
    with pytest.raises(ValueError, match="beam_size"):
        FasterWhisperTranscriber(tmp_path, beam_size=0)
    with pytest.raises(ValueError, match="Dispositivo"):
        FasterWhisperTranscriber(tmp_path, device="mps")


def test_missing_model_timestamps_are_not_fabricated(tmp_path: Path) -> None:
    model = FakeModel(
        [SimpleNamespace(start=-1.0, end=3.0, text="Texto sem janela válida")]
    )
    transcriber = make_transcriber(tmp_path, model)

    transcript = transcriber.transcribe(
        make_audio(tmp_path),
        language=Language.PORTUGUESE,
        progress=ProgressRecorder(),
    )

    assert transcript.segments[0].alignment_window is None


def test_empty_generator_is_reported_as_model_error(tmp_path: Path) -> None:
    transcriber = make_transcriber(tmp_path, FakeModel([]))

    with pytest.raises(ModelError, match="não reconheceu fala"):
        transcriber.transcribe(
            make_audio(tmp_path),
            language=Language.PORTUGUESE,
            progress=ProgressRecorder(),
        )


def test_backend_errors_are_wrapped_without_hiding_cancellation(tmp_path: Path) -> None:
    transcriber = make_transcriber(
        tmp_path, FakeModel(error=RuntimeError("backend failure"))
    )

    with pytest.raises(ModelError, match="Falha durante o reconhecimento"):
        transcriber.transcribe(
            make_audio(tmp_path),
            language=Language.PORTUGUESE,
            progress=ProgressRecorder(),
        )

    token = CancellationTokenImpl()
    model = FakeModel()
    transcriber = make_transcriber(tmp_path / "cancelled", model)

    def cancel_after_first_segment():
        yield model.segments[0]
        token.cancel("cancelado pelo teste")
        yield model.segments[1]

    model.transcribe = lambda *_args, **_kwargs: (
        cancel_after_first_segment(),
        SimpleNamespace(language="pt", language_probability=1.0),
    )

    with pytest.raises(JobCancelledError):
        transcriber.transcribe(
            make_audio(tmp_path),
            language=Language.PORTUGUESE,
            progress=ProgressRecorder(),
            token=token,
        )


def test_environment_configuration_is_validated(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LEGENDAR_FASTER_WHISPER_CPU_THREADS", "not-an-int")
    with pytest.raises(ValueError, match="devem ser inteiros"):
        FasterWhisperTranscriber.from_environment(tmp_path)

    monkeypatch.setenv("LEGENDAR_FASTER_WHISPER_CPU_THREADS", "4")
    monkeypatch.setenv("LEGENDAR_FASTER_WHISPER_VAD_FILTER", "maybe")
    with pytest.raises(ValueError, match="deve ser booleano"):
        FasterWhisperTranscriber.from_environment(tmp_path)
