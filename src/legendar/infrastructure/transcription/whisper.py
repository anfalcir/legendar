"""Adaptador local do OpenAI Whisper para a porta Transcriber.

O módulo não importa Whisper, PyTorch ou NumPy no import-time. O runtime é
carregado somente quando o primeiro job solicita uma transcrição.
"""

from __future__ import annotations

import math
import os
import threading
import time
from collections.abc import Callable, Mapping
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
from legendar.infrastructure.media.waveform import load_pcm_waveform

SUPPORTED_MODELS = frozenset({"tiny", "base", "small", "medium", "large", "turbo"})
SUPPORTED_DEVICES = frozenset({"auto", "cpu", "cuda", "mps"})
DEFAULT_MODEL = "base"

ModelLoader = Callable[[str, str, Path], Any]
DeviceResolver = Callable[[str], str]
AudioLoader = Callable[[AudioAsset], Any]
VersionProvider = Callable[[], str]


def _package_version() -> str:
    try:
        return version("openai-whisper")
    except PackageNotFoundError:
        return "unknown"


def _resolve_device(requested: str) -> str:
    """Resolve CPU/CUDA/MPS somente no momento de carregar o modelo."""
    try:
        import torch
    except ImportError as exc:
        raise ModelError(
            "PyTorch não está instalado no ambiente Whisper. "
            "Reinstale o perfil runtime-cpu ou runtime-cu128."
        ) from exc

    if requested == "auto":
        if torch.cuda.is_available():
            return "cuda"
        mps = getattr(getattr(torch.backends, "mps", None), "is_available", None)
        if callable(mps) and mps():
            return "mps"
        return "cpu"

    if requested == "cuda" and not torch.cuda.is_available():
        raise ModelError(
            "O dispositivo CUDA foi solicitado, mas não há runtime NVIDIA disponível. "
            "Selecione auto/cpu ou valide driver e perfil CUDA."
        )
    if requested == "mps":
        mps = getattr(getattr(torch.backends, "mps", None), "is_available", None)
        if not callable(mps) or not mps():
            raise ModelError(
                "O dispositivo MPS foi solicitado, mas não está disponível."
            )
    return requested


def _load_openai_model(model_name: str, device: str, download_root: Path) -> Any:
    try:
        import whisper
    except ImportError as exc:
        raise ModelError(
            "OpenAI Whisper não está instalado. Instale o perfil de runtime "
            "CPU ou CUDA definido no projeto."
        ) from exc
    return whisper.load_model(
        model_name,
        device=device,
        download_root=str(download_root),
    )


# Compatibilidade com os testes e callers internos existentes.
_load_pcm_wave = load_pcm_waveform


class WhisperTranscriber:
    """Transcriber local com carga tardia, cache persistente e uso serial.

    Os timestamps segment-level aproximados devolvidos pelo Whisper não são
    promovidos a âncoras temporais do domínio. A Fase 5 é responsável pelo
    forced alignment e pela linha do tempo global.
    """

    def __init__(
        self,
        models_dir: Path,
        *,
        model_name: str = DEFAULT_MODEL,
        device: str = "auto",
        model_loader: ModelLoader = _load_openai_model,
        device_resolver: DeviceResolver = _resolve_device,
        audio_loader: AudioLoader = _load_pcm_wave,
        version_provider: VersionProvider = _package_version,
    ) -> None:
        normalized_model = (model_name or "").strip().lower()
        normalized_device = (device or "").strip().lower()
        if normalized_model not in SUPPORTED_MODELS:
            raise ValueError(
                f"Modelo Whisper inválido: {model_name!r}. "
                f"Opções: {', '.join(sorted(SUPPORTED_MODELS))}."
            )
        if normalized_device not in SUPPORTED_DEVICES:
            raise ValueError(
                f"Dispositivo Whisper inválido: {device!r}. "
                f"Opções: {', '.join(sorted(SUPPORTED_DEVICES))}."
            )

        self.model_name = normalized_model
        self.requested_device = normalized_device
        self.download_root = Path(models_dir).expanduser() / "whisper"
        self._model_loader = model_loader
        self._device_resolver = device_resolver
        self._audio_loader = audio_loader
        self._version_provider = version_provider
        self._model: Any | None = None
        self._device: str | None = None
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
    def from_environment(cls, models_dir: Path) -> WhisperTranscriber:
        """Lê apenas os dois ajustes operacionais documentados do runtime."""
        return cls(
            models_dir=models_dir,
            model_name=os.environ.get("LEGENDAR_WHISPER_MODEL", DEFAULT_MODEL),
            device=os.environ.get("LEGENDAR_WHISPER_DEVICE", "auto"),
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
        """Snapshot acumulado de tempos/contagens; não contém áudio nem transcrição."""
        with self._metrics_lock:
            counters = dict(self._metrics)
        return {
            "loaded": self.is_loaded,
            "configuration": {
                "adapter": "openai-whisper",
                "model": self.model_name,
                "package_version": self._revision or self._version_provider(),
                "requested_device": self.requested_device,
                "loaded_device": self._device,
                "fp16": self._device not in (None, "cpu"),
                "word_timestamps": False,
            },
            "counters": counters,
        }

    def _record_metric(self, name: str, value: int | float) -> None:
        with self._metrics_lock:
            self._metrics[name] = self._metrics.get(name, 0) + value

    def _get_model(self) -> tuple[Any, str]:
        if self._model is not None and self._device is not None:
            return self._model, self._device

        with self._load_lock:
            if self._model is not None and self._device is not None:
                return self._model, self._device

            load_started = time.perf_counter()
            self._record_metric("model_load_attempts", 1)
            try:
                device = self._device_resolver(self.requested_device)
                self.download_root.mkdir(parents=True, exist_ok=True)
                model = self._model_loader(
                    self.model_name,
                    device,
                    self.download_root,
                )
                revision = self._version_provider()
            except ModelError:
                raise
            except Exception as exc:
                raise ModelError(
                    f"Não foi possível carregar o modelo Whisper "
                    f"{self.model_name!r}: {exc}"
                ) from exc
            finally:
                self._record_metric(
                    "model_load_seconds", time.perf_counter() - load_started
                )

            self._record_metric("model_load_successes", 1)
            self._model = model
            self._device = device
            self._revision = revision
            return model, device

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

        model, device = self._get_model()
        if token is not None:
            token.raise_if_cancelled()

        audio_load_started = time.perf_counter()
        try:
            waveform = self._audio_loader(audio)
        except ModelError:
            raise
        except Exception as exc:
            raise ModelError(f"Falha ao carregar o áudio normalizado: {exc}") from exc
        finally:
            self._record_metric(
                "audio_load_seconds", time.perf_counter() - audio_load_started
            )
        if getattr(waveform, "size", None) == 0 or (
            getattr(waveform, "__len__", None) is not None and len(waveform) == 0
        ):
            raise ModelError("O áudio normalizado não contém amostras.")

        language_code = language.value if language is not None else None
        inference_started = time.perf_counter()
        self._record_metric("inference_calls", 1)
        try:
            # Um único modelo é reutilizado e a inferência é serializada. A UI
            # executa esta chamada na QThread do job, nunca na thread principal.
            with self._inference_lock:
                if token is not None:
                    token.raise_if_cancelled()
                result = model.transcribe(
                    waveform,
                    task="transcribe",
                    language=language_code,
                    fp16=device != "cpu",
                    verbose=None,
                    word_timestamps=False,
                )
                if token is not None:
                    token.raise_if_cancelled()
        except JobCancelledError:
            raise
        except Exception as exc:
            if token is not None:
                token.raise_if_cancelled()
            raise ModelError(
                f"Falha durante o reconhecimento com Whisper {self.model_name}: {exc}"
            ) from exc
        finally:
            self._record_metric(
                "inference_seconds", time.perf_counter() - inference_started
            )

        if not isinstance(result, Mapping):
            raise ModelError("Whisper retornou uma resposta em formato inesperado.")

        detected = result.get("language")
        if not isinstance(detected, str) or not detected.strip():
            detected = language_code
        try:
            transcript_language = Language.parse(detected)
        except Exception as exc:
            raise UnsupportedLanguageError(
                f"O Whisper detectou um idioma não suportado pelo Legendar: {detected!r}."
            ) from exc
        if transcript_language is None:
            raise ModelError("Whisper não conseguiu identificar o idioma da fala.")

        raw_segments = result.get("segments")
        segments: list[TranscriptSegment] = []
        if isinstance(raw_segments, (list, tuple)):
            for index, raw_segment in enumerate(raw_segments):
                if not isinstance(raw_segment, Mapping):
                    raise ModelError(
                        f"Whisper retornou o segmento {index} em formato inválido."
                    )
                text = raw_segment.get("text")
                if text is None:
                    continue
                if not isinstance(text, str):
                    raise ModelError(
                        f"Whisper retornou texto inválido no segmento {index}."
                    )
                normalized_text = text.strip()
                if normalized_text:
                    # A janela do decoder limita a busca, mas não é tempo final.
                    raw_start = raw_segment.get("start")
                    raw_end = raw_segment.get("end")
                    alignment_window = None
                    if (
                        isinstance(raw_start, (int, float))
                        and not isinstance(raw_start, bool)
                        and isinstance(raw_end, (int, float))
                        and not isinstance(raw_end, bool)
                        and math.isfinite(float(raw_start))
                        and math.isfinite(float(raw_end))
                        and 0.0
                        <= float(raw_start)
                        < float(raw_end)
                        <= audio.duration_seconds
                    ):
                        try:
                            alignment_window = TimeRange(
                                start=float(raw_start),
                                end=float(raw_end),
                            )
                        except TemporalError:
                            alignment_window = None
                    segments.append(
                        TranscriptSegment(
                            text=normalized_text,
                            alignment_window=alignment_window,
                        )
                    )

        if not segments:
            full_text = result.get("text")
            if isinstance(full_text, str) and full_text.strip():
                # Sem limites por segmento, a mídia inteira é somente janela
                # de busca; o alinhador ainda aplica seu limite de segurança.
                segments.append(
                    TranscriptSegment(
                        text=full_text.strip(),
                        alignment_window=TimeRange(
                            start=0.0,
                            end=audio.duration_seconds,
                        ),
                    )
                )

        if not segments:
            raise ModelError(
                "Whisper não reconheceu fala nesta mídia. Verifique o áudio, "
                "o idioma e o perfil do modelo."
            )

        transcript = Transcript(
            segments=tuple(segments),
            language=transcript_language,
            model_name=self.model_name,
            model_revision=self._revision,
        )
        if token is not None:
            token.raise_if_cancelled()
        self._record_metric("transcribed_segments", len(segments))
        self._record_metric(
            "recognized_words",
            sum(len(segment.text.split()) for segment in segments),
        )
        progress.report(1.0, f"Reconhecimento Whisper {self.model_name} concluído")
        return transcript
