from __future__ import annotations

from pathlib import Path

import pytest

from legendar.application.job.context import CancellationTokenImpl
from legendar.domain.entities.media import AudioAsset
from legendar.domain.errors.catalog import (
    JobCancelledError,
    ModelError,
    UnsupportedLanguageError,
)
from legendar.domain.value_objects.language import Language
from legendar.domain.value_objects.time import TimeRange
from legendar.infrastructure.transcription.whisper import WhisperTranscriber


class ProgressRecorder:
    def __init__(self) -> None:
        self.reports: list[tuple[float, str]] = []

    def report(self, fraction: float, message: str = "") -> None:
        self.reports.append((fraction, message))


class FakeModel:
    def __init__(self, result=None, *, error: Exception | None = None, token=None):
        self.result = result or {
            "language": "pt",
            "text": " Olá, mundo! ",
            "segments": [
                {"start": 0.0, "end": 0.4, "text": " Olá,"},
                {"start": 0.5, "end": 1.0, "text": " mundo! "},
            ],
        }
        self.error = error
        self.token = token
        self.calls: list[dict] = []

    def transcribe(self, waveform, **kwargs):
        self.calls.append({"waveform": waveform, **kwargs})
        if self.token is not None:
            self.token.cancel("cancelado durante a inferência")
        if self.error is not None:
            raise self.error
        return self.result


def make_audio(tmp_path: Path) -> AudioAsset:
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
) -> WhisperTranscriber:
    model = model or FakeModel()
    calls = loader_calls if loader_calls is not None else []

    def loader(name: str, device: str, root: Path):
        calls.append((name, device, root))
        return model

    return WhisperTranscriber(
        tmp_path / "models",
        model_name="base",
        device="cpu",
        model_loader=loader,
        device_resolver=lambda requested: requested,
        audio_loader=lambda _asset: [0.0, 0.1, -0.1],
        version_provider=lambda: "20250625",
        **kwargs,
    )


def test_transcribes_original_language_and_preserves_recognized_segments(
    tmp_path: Path,
) -> None:
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
    assert transcript.model_revision == "20250625"
    assert [segment.text for segment in transcript.segments] == ["Olá,", "mundo!"]
    assert all(segment.range is None for segment in transcript.segments)
    assert [segment.alignment_window for segment in transcript.segments] == [
        TimeRange(0.0, 0.4),
        TimeRange(0.5, 1.0),
    ]
    assert all(not segment.words for segment in transcript.segments)
    assert model.calls[0]["task"] == "transcribe"
    assert model.calls[0]["language"] == "pt"
    assert model.calls[0]["word_timestamps"] is False
    assert model.calls[0]["fp16"] is False
    assert progress.reports == [(1.0, "Reconhecimento Whisper base concluído")]


def test_detects_language_when_not_declared(tmp_path: Path) -> None:
    model = FakeModel({"language": "en", "text": "Hello there", "segments": []})
    transcriber = make_transcriber(tmp_path, model)

    transcript = transcriber.transcribe(
        make_audio(tmp_path),
        language=None,
        progress=ProgressRecorder(),
    )

    assert transcript.language is Language.ENGLISH
    assert transcript.text == "Hello there"
    assert model.calls[0]["language"] is None


def test_model_is_loaded_once_and_reused_between_jobs(tmp_path: Path) -> None:
    calls: list = []
    model = FakeModel()
    transcriber = make_transcriber(tmp_path, model, loader_calls=calls)

    for _ in range(2):
        transcriber.transcribe(
            make_audio(tmp_path),
            language=Language.PORTUGUESE,
            progress=ProgressRecorder(),
        )

    assert len(calls) == 1
    assert transcriber.is_loaded
    assert transcriber.loaded_device == "cpu"
    assert calls[0][2] == tmp_path / "models" / "whisper"


def test_rejects_languages_outside_product_scope(tmp_path: Path) -> None:
    model = FakeModel({"language": "es", "text": "Hola", "segments": []})
    transcriber = make_transcriber(tmp_path, model)

    with pytest.raises(UnsupportedLanguageError, match="idioma não suportado"):
        transcriber.transcribe(
            make_audio(tmp_path),
            language=None,
            progress=ProgressRecorder(),
        )


def test_empty_recognition_is_reported_as_model_error(tmp_path: Path) -> None:
    model = FakeModel({"language": "pt", "text": " ", "segments": []})
    transcriber = make_transcriber(tmp_path, model)

    with pytest.raises(ModelError, match="não reconheceu fala"):
        transcriber.transcribe(
            make_audio(tmp_path),
            language=Language.PORTUGUESE,
            progress=ProgressRecorder(),
        )


def test_unexpected_result_shape_is_rejected(tmp_path: Path) -> None:
    model = FakeModel({"language": "pt", "text": "x", "segments": [None]})
    transcriber = make_transcriber(tmp_path, model)

    with pytest.raises(ModelError, match="segmento 0"):
        transcriber.transcribe(
            make_audio(tmp_path),
            language=Language.PORTUGUESE,
            progress=ProgressRecorder(),
        )


def test_model_load_error_has_actionable_domain_error(tmp_path: Path) -> None:
    def fail_loader(_name: str, _device: str, _root: Path):
        raise OSError("download unavailable")

    transcriber = WhisperTranscriber(
        tmp_path,
        model_name="tiny",
        device="cpu",
        model_loader=fail_loader,
        device_resolver=lambda _requested: "cpu",
        audio_loader=lambda _audio: [0.0],
    )

    with pytest.raises(ModelError, match="Não foi possível carregar"):
        transcriber.transcribe(
            make_audio(tmp_path),
            language=Language.PORTUGUESE,
            progress=ProgressRecorder(),
        )


def test_cancelled_job_does_not_load_or_run_model(tmp_path: Path) -> None:
    calls: list = []
    transcriber = make_transcriber(tmp_path, loader_calls=calls)
    token = CancellationTokenImpl()
    token.cancel("cancelado antes do carregamento")

    with pytest.raises(JobCancelledError, match="antes do carregamento"):
        transcriber.transcribe(
            make_audio(tmp_path),
            language=Language.PORTUGUESE,
            progress=ProgressRecorder(),
            token=token,
        )

    assert calls == []


def test_cancel_requested_during_inference_is_reported_after_safe_return(
    tmp_path: Path,
) -> None:
    token = CancellationTokenImpl()
    model = FakeModel(token=token)
    transcriber = make_transcriber(tmp_path, model)

    with pytest.raises(JobCancelledError, match="durante a inferência"):
        transcriber.transcribe(
            make_audio(tmp_path),
            language=Language.PORTUGUESE,
            progress=ProgressRecorder(),
            token=token,
        )


@pytest.mark.parametrize("model_name", ["", "base.en", "unknown"])
def test_rejects_invalid_or_english_only_model_profiles(
    tmp_path: Path, model_name: str
) -> None:
    with pytest.raises(ValueError, match="Modelo Whisper inválido"):
        WhisperTranscriber(tmp_path, model_name=model_name)


def test_rejects_unknown_device_profile(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Dispositivo Whisper inválido"):
        WhisperTranscriber(tmp_path, device="rocm")


def test_default_pcm_loader_reads_signed_16_bit_samples(tmp_path: Path) -> None:
    import struct
    import wave

    from legendar.infrastructure.transcription.whisper import _load_pcm_wave

    path = tmp_path / "pcm.wav"
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(16_000)
        target.writeframes(struct.pack("<hhh", -32768, 0, 16384))

    asset = AudioAsset(
        path=str(path),
        sample_rate_hz=16_000,
        channels=1,
        sample_format="pcm_s16le",
        duration_seconds=3 / 16_000,
    )
    np = pytest.importorskip("numpy")
    waveform = _load_pcm_wave(asset)

    assert waveform.dtype == np.float32
    assert waveform.tolist() == pytest.approx([-1.0, 0.0, 0.5])


def test_default_pcm_loader_rejects_truncated_or_non_wav_input(
    tmp_path: Path,
) -> None:
    from legendar.infrastructure.transcription.whisper import _load_pcm_wave

    with pytest.raises(ModelError, match="Não foi possível ler o WAV"):
        _load_pcm_wave(make_audio(tmp_path))


def test_audio_loader_failure_is_wrapped_as_domain_error(tmp_path: Path) -> None:
    transcriber = WhisperTranscriber(
        tmp_path / "models",
        model_name="tiny",
        device="cpu",
        model_loader=lambda _name, _device, _root: FakeModel(),
        device_resolver=lambda _requested: "cpu",
        audio_loader=lambda _audio: (_ for _ in ()).throw(OSError("read failed")),
    )

    with pytest.raises(ModelError, match="Falha ao carregar o áudio"):
        transcriber.transcribe(
            make_audio(tmp_path),
            language=Language.PORTUGUESE,
            progress=ProgressRecorder(),
        )


def test_performance_snapshot_separates_model_load_audio_load_and_inference(
    tmp_path: Path,
) -> None:
    transcriber = make_transcriber(tmp_path)
    transcriber.transcribe(
        make_audio(tmp_path),
        language=Language.PORTUGUESE,
        progress=ProgressRecorder(),
    )

    snapshot = transcriber.performance_snapshot()

    assert snapshot["loaded"] is True
    assert snapshot["configuration"]["adapter"] == "openai-whisper"
    assert snapshot["configuration"]["model"] == "base"
    assert snapshot["counters"]["model_load_attempts"] == 1
    assert snapshot["counters"]["model_load_successes"] == 1
    assert snapshot["counters"]["inference_calls"] == 1
    assert snapshot["counters"]["transcribed_segments"] == 2
    assert snapshot["counters"]["recognized_words"] == 2
    assert snapshot["counters"]["model_load_seconds"] >= 0
    assert snapshot["counters"]["inference_seconds"] >= 0
