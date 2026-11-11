"""Adaptador faster-whisper/CTranslate2 para reconhecimento local.

A implementação mantém a porta Transcriber e o contrato temporal do Legendar.
Os timestamps devolvidos pelo decoder são somente janelas locais de busca para
o WhisperX; nunca são promovidos a timestamps finais de palavra.
"""

from __future__ import annotations

import math
import os
import threading
import time
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from legendar.application.ports.protocols import CancellationToken, ProgressSink
from legendar.domain.entities.media import AudioAsset
from legendar.domain.entities.transcript import Transcript, TranscriptSegment
from legendar.domain.errors.catalog import (
    JobCancelledError,
    ModelError,
    UnsupportedLanguageError,
)
from legendar.domain.value_objects.language import Language
from legendar.domain.value_objects.time import TemporalError, TimeRange
from legendar.infrastructure.diagnostics.performance import (
    collect_torch_thread_settings,
)
from legendar.infrastructure.media.waveform import load_pcm_waveform

SUPPORTED_MODELS = frozenset(
    {"tiny", "base", "small", "medium", "large", "large-v3", "turbo"}
)
SUPPORTED_DEVICES = frozenset({"auto", "cpu", "cuda"})
SUPPORTED_COMPUTE_TYPES = frozenset(
    {"default", "auto", "int8", "int8_float16", "int8_float32", "float16", "float32"}
)

ModelLoader = Callable[[str, str, str, int, Path], Any]
AudioLoader = Callable[[AudioAsset], Any]


def _package_version() -> str:
    try:
        return version("faster-whisper")
    except PackageNotFoundError:
        return "unknown"


def _resolve_device(requested: str) -> str:
    try:
        import ctranslate2
    except ImportError as exc:
        raise ModelError(
            "faster-whisper/CTranslate2 não está instalado. "
            "Sincronize o perfil runtime-cpu ou runtime-cu128."
        ) from exc

    if requested == "auto":
        return "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
    if requested == "cuda" and ctranslate2.get_cuda_device_count() < 1:
        raise ModelError(
            "CUDA foi solicitada para faster-whisper, mas não há dispositivo "
            "NVIDIA disponível. Selecione cpu/auto ou valide o runtime CUDA."
        )
    return requested


def _load_model(
    model_name: str,
    device: str,
    compute_type: str,
    cpu_threads: int,
    download_root: Path,
) -> Any:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise ModelError(
            "faster-whisper não está instalado. Sincronize o perfil runtime-cpu "
            "ou runtime-cu128."
        ) from exc
    return WhisperModel(
        model_name,
        device=device,
        compute_type=compute_type,
        cpu_threads=cpu_threads,
        num_workers=1,
        download_root=str(download_root),
    )


class FasterWhisperTranscriber:
    """Transcriber CTranslate2 com carga tardia e consumo integral do generator."""

    def __init__(
        self,
        models_dir: Path,
        *,
        model_name: str = "base",
        device: str = "auto",
        compute_type: str | None = None,
        cpu_threads: int = 4,
        beam_size: int = 5,
        vad_filter: bool = False,
        model_loader: ModelLoader = _load_model,
        device_resolver: Callable[[str], str] = _resolve_device,
        audio_loader: AudioLoader = load_pcm_waveform,
        version_provider: Callable[[], str] = _package_version,
    ) -> None:
        normalized_model = (model_name or "").strip().lower()
        normalized_device = (device or "").strip().lower()
        normalized_compute = (compute_type or "").strip().lower() or None
        if normalized_model not in SUPPORTED_MODELS:
            raise ValueError(
                f"Modelo faster-whisper inválido: {model_name!r}. "
                f"Opções: {', '.join(sorted(SUPPORTED_MODELS))}."
            )
        if normalized_device not in SUPPORTED_DEVICES:
            raise ValueError(
                f"Dispositivo faster-whisper inválido: {device!r}. "
                "Opções: auto, cpu, cuda."
            )
        if (
            normalized_compute is not None
            and normalized_compute not in SUPPORTED_COMPUTE_TYPES
        ):
            raise ValueError(
                f"compute_type inválido: {compute_type!r}. "
                f"Opções: {', '.join(sorted(SUPPORTED_COMPUTE_TYPES))}."
            )
        if (
            isinstance(cpu_threads, bool)
            or not isinstance(cpu_threads, int)
            or cpu_threads < 1
        ):
            raise ValueError("cpu_threads deve ser inteiro positivo.")
        if (
            isinstance(beam_size, bool)
            or not isinstance(beam_size, int)
            or not 1 <= beam_size <= 10
        ):
            raise ValueError("beam_size deve ficar entre 1 e 10.")
        if not isinstance(vad_filter, bool):
            raise ValueError("vad_filter deve ser booleano.")

        self.model_name = normalized_model
        self.requested_device = normalized_device
        self.requested_compute_type = normalized_compute
        self.cpu_threads = cpu_threads
        self.beam_size = beam_size
        self.vad_filter = vad_filter
        self.download_root = Path(models_dir).expanduser() / "faster-whisper"
        self._model_loader = model_loader
        self._device_resolver = device_resolver
        self._audio_loader = audio_loader
        self._version_provider = version_provider
        self._model: Any | None = None
        self._device: str | None = None
        self._compute_type: str | None = None
        self._revision: str | None = None
        self._load_lock = threading.Lock()
        self._inference_lock = threading.Lock()
        self._metrics_lock = threading.Lock()
        self._metrics: dict[str, int | float] = {
            "model_load_attempts": 0,
            "model_load_successes": 0,
            "model_load_seconds": 0.0,
            "audio_load_seconds": 0.0,
            "inference_calls": 0,
            "inference_seconds": 0.0,
            "transcribed_segments": 0,
            "recognized_words": 0,
        }

    @classmethod
    def from_environment(cls, models_dir: Path) -> FasterWhisperTranscriber:
        model = os.environ.get("LEGENDAR_WHISPER_MODEL", "base")
        device = os.environ.get("LEGENDAR_WHISPER_DEVICE", "auto")
        compute_type = os.environ.get("LEGENDAR_FASTER_WHISPER_COMPUTE_TYPE")
        raw_threads = os.environ.get("LEGENDAR_FASTER_WHISPER_CPU_THREADS", "4")
        raw_beam = os.environ.get("LEGENDAR_FASTER_WHISPER_BEAM_SIZE", "5")
        raw_vad = os.environ.get("LEGENDAR_FASTER_WHISPER_VAD_FILTER", "false")
        try:
            cpu_threads = int(raw_threads)
            beam_size = int(raw_beam)
        except ValueError as exc:
            raise ValueError(
                "LEGENDAR_FASTER_WHISPER_CPU_THREADS e BEAM_SIZE devem ser inteiros."
            ) from exc
        normalized_vad = raw_vad.strip().casefold()
        if normalized_vad not in {"true", "false", "1", "0", "yes", "no"}:
            raise ValueError("LEGENDAR_FASTER_WHISPER_VAD_FILTER deve ser booleano.")
        return cls(
            models_dir,
            model_name=model,
            device=device,
            compute_type=compute_type,
            cpu_threads=cpu_threads,
            beam_size=beam_size,
            vad_filter=normalized_vad in {"true", "1", "yes"},
        )

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    @property
    def loaded_device(self) -> str | None:
        return self._device

    @property
    def revision(self) -> str | None:
        return self._revision

    def performance_snapshot(self) -> dict[str, Any]:
        with self._metrics_lock:
            counters = dict(self._metrics)
        return {
            "loaded": self.is_loaded,
            "configuration": {
                "adapter": "faster-whisper",
                "model": self.model_name,
                "package_version": self._revision or self._version_provider(),
                "requested_device": self.requested_device,
                "loaded_device": self._device,
                "compute_type": self._compute_type or self.requested_compute_type,
                "cpu_threads": self.cpu_threads,
                "beam_size": self.beam_size,
                "vad_filter": self.vad_filter,
                "word_timestamps": False,
                **collect_torch_thread_settings(),
            },
            "counters": counters,
        }

    def _record_metric(self, name: str, value: int | float) -> None:
        with self._metrics_lock:
            self._metrics[name] = self._metrics.get(name, 0) + value

    def _get_model(self) -> tuple[Any, str, str]:
        if self._model is not None and self._device and self._compute_type:
            return self._model, self._device, self._compute_type
        with self._load_lock:
            if self._model is not None and self._device and self._compute_type:
                return self._model, self._device, self._compute_type

            started = time.perf_counter()
            self._record_metric("model_load_attempts", 1)
            try:
                device = self._device_resolver(self.requested_device)
                compute_type = self.requested_compute_type or (
                    "float16" if device == "cuda" else "int8"
                )
                self.download_root.mkdir(parents=True, exist_ok=True)
                model = self._model_loader(
                    self.model_name,
                    device,
                    compute_type,
                    self.cpu_threads,
                    self.download_root,
                )
                revision = self._version_provider()
            except ModelError:
                raise
            except Exception as exc:
                raise ModelError(
                    f"Não foi possível carregar faster-whisper {self.model_name!r}: {exc}"
                ) from exc
            finally:
                self._record_metric("model_load_seconds", time.perf_counter() - started)
            self._record_metric("model_load_successes", 1)
            self._model = model
            self._device = device
            self._compute_type = compute_type
            self._revision = revision
            return model, device, compute_type

    def transcribe(
        self,
        audio: AudioAsset,
        *,
        language: Language | None,
        progress: ProgressSink,
        token: CancellationToken | None = None,
    ) -> Transcript:
        if token is not None:
            token.raise_if_cancelled()
        model, _device, _compute_type = self._get_model()
        if token is not None:
            token.raise_if_cancelled()

        audio_started = time.perf_counter()
        try:
            waveform = self._audio_loader(audio)
        except ModelError:
            raise
        except Exception as exc:
            raise ModelError(f"Falha ao carregar o áudio normalizado: {exc}") from exc
        finally:
            self._record_metric(
                "audio_load_seconds", time.perf_counter() - audio_started
            )

        waveform_size = getattr(waveform, "size", None)
        if waveform_size is None:
            try:
                waveform_size = len(waveform)
            except TypeError as exc:
                raise ModelError("Waveform inválido para faster-whisper.") from exc
        if waveform_size < 1:
            raise ModelError("O áudio normalizado não contém amostras.")

        requested_language = language.value if language is not None else None
        inference_started = time.perf_counter()
        self._record_metric("inference_calls", 1)
        try:
            with self._inference_lock:
                if token is not None:
                    token.raise_if_cancelled()
                segment_generator, info = model.transcribe(
                    waveform,
                    task="transcribe",
                    language=requested_language,
                    beam_size=self.beam_size,
                    best_of=5,
                    temperature=(0.0, 0.2, 0.4, 0.6, 0.8, 1.0),
                    compression_ratio_threshold=2.4,
                    log_prob_threshold=-1.0,
                    no_speech_threshold=0.6,
                    condition_on_previous_text=True,
                    word_timestamps=False,
                    vad_filter=self.vad_filter,
                )
                # faster-whisper executa a inferência ao consumir o generator.
                # Consumimos integralmente para não perder segmentos nem medir
                # somente o custo de criação do iterador.
                raw_segments = []
                for raw_segment in segment_generator:
                    if token is not None:
                        token.raise_if_cancelled()
                    raw_segments.append(raw_segment)
                if token is not None:
                    token.raise_if_cancelled()
        except JobCancelledError:
            raise
        except Exception as exc:
            if token is not None:
                token.raise_if_cancelled()
            raise ModelError(
                f"Falha durante o reconhecimento com faster-whisper {self.model_name}: {exc}"
            ) from exc
        finally:
            self._record_metric(
                "inference_seconds", time.perf_counter() - inference_started
            )

        detected = getattr(info, "language", None)
        if not isinstance(detected, str) or not detected.strip():
            detected = requested_language
        try:
            transcript_language = Language.parse(detected)
        except Exception as exc:
            raise UnsupportedLanguageError(
                f"faster-whisper detectou idioma não suportado: {detected!r}."
            ) from exc
        if transcript_language is None:
            raise ModelError("faster-whisper não conseguiu identificar o idioma.")

        segments: list[TranscriptSegment] = []
        for index, raw_segment in enumerate(raw_segments):
            text = getattr(raw_segment, "text", None)
            if not isinstance(text, str):
                raise ModelError(
                    f"faster-whisper retornou texto inválido no segmento {index}."
                )
            normalized = text.strip()
            if not normalized:
                continue
            raw_start = getattr(raw_segment, "start", None)
            raw_end = getattr(raw_segment, "end", None)
            window = None
            if (
                isinstance(raw_start, (int, float))
                and not isinstance(raw_start, bool)
                and isinstance(raw_end, (int, float))
                and not isinstance(raw_end, bool)
                and math.isfinite(float(raw_start))
                and math.isfinite(float(raw_end))
                and 0.0 <= float(raw_start) < float(raw_end) <= audio.duration_seconds
            ):
                try:
                    window = TimeRange(start=float(raw_start), end=float(raw_end))
                except TemporalError:
                    window = None
            segments.append(
                TranscriptSegment(text=normalized, alignment_window=window)
            )

        if not segments:
            raise ModelError(
                "faster-whisper não reconheceu fala nesta mídia. "
                "Verifique o áudio, idioma e perfil do modelo."
            )

        transcript = Transcript(
            segments=tuple(segments),
            language=transcript_language,
            model_name=self.model_name,
            model_revision=self._revision,
            language_probability=getattr(info, "language_probability", None),
        )
        if token is not None:
            token.raise_if_cancelled()
        self._record_metric("transcribed_segments", len(segments))
        self._record_metric(
            "recognized_words", sum(len(segment.text.split()) for segment in segments)
        )
        progress.report(1.0, f"Reconhecimento faster-whisper {self.model_name} concluído")
        return transcript
