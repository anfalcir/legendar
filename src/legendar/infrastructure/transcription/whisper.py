"""Adaptador local do OpenAI Whisper para a porta Transcriber.

O módulo não importa Whisper, PyTorch ou NumPy no import-time. O runtime é
carregado somente quando o primeiro job solicita uma transcrição.
"""

from __future__ import annotations

import os
import threading
import wave
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
            raise ModelError("O dispositivo MPS foi solicitado, mas não está disponível.")
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


def _load_pcm_wave(audio: AudioAsset) -> Any:
    """Lê o WAV PCM s16le mono/16 kHz produzido pela Fase 3."""
    if (
        audio.sample_rate_hz != 16_000
        or audio.channels != 1
        or audio.sample_format.lower() not in {"pcm_s16le", "s16"}
    ):
        raise ModelError(
            "O Whisper recebeu áudio fora do contrato WAV PCM s16le mono/16 kHz."
        )

    try:
        with wave.open(str(audio.path), "rb") as source:
            if (
                source.getnchannels() != 1
                or source.getframerate() != 16_000
                or source.getsampwidth() != 2
                or source.getcomptype() != "NONE"
            ):
                raise ModelError(
                    "O arquivo de áudio não é WAV PCM signed 16-bit mono/16 kHz."
                )
            frame_count = source.getnframes()
            payload = source.readframes(frame_count)
    except (OSError, wave.Error) as exc:
        raise ModelError(f"Não foi possível ler o WAV normalizado: {exc}") from exc

    if frame_count < 1 or len(payload) != frame_count * 2:
        raise ModelError("O WAV normalizado está vazio ou truncado.")

    try:
        import numpy as np
    except ImportError as exc:
        raise ModelError("NumPy não está disponível no runtime Whisper.") from exc

    waveform = np.frombuffer(payload, dtype="<i2").astype(np.float32) / 32768.0
    if (
        waveform.ndim != 1
        or waveform.size != frame_count
        or not np.isfinite(waveform).all()
    ):
        raise ModelError("O WAV produziu uma forma de onda inválida.")
    return waveform


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

    def _get_model(self) -> tuple[Any, str]:
        if self._model is not None and self._device is not None:
            return self._model, self._device

        with self._load_lock:
            if self._model is not None and self._device is not None:
                return self._model, self._device

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

        try:
            waveform = self._audio_loader(audio)
        except ModelError:
            raise
        except Exception as exc:
            raise ModelError(f"Falha ao carregar o áudio normalizado: {exc}") from exc
        if getattr(waveform, "size", None) == 0 or (
            getattr(waveform, "__len__", None) is not None and len(waveform) == 0
        ):
            raise ModelError("O áudio normalizado não contém amostras.")

        language_code = language.value if language is not None else None
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
                    # O início/fim aproximado do decoder não é forced alignment.
                    segments.append(TranscriptSegment(text=normalized_text))

        if not segments:
            full_text = result.get("text")
            if isinstance(full_text, str) and full_text.strip():
                segments.append(TranscriptSegment(text=full_text.strip()))

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
        progress.report(1.0, f"Reconhecimento Whisper {self.model_name} concluído")
        return transcript
