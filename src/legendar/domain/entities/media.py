"""Entidades de mídia: origem declarada, inspeção e áudio normalizado.

Nenhuma entidade aqui toca filesystem, subprocesso ou rede. A validação é
estrutural e determinística; a inspeção real pertence à infraestrutura.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

from legendar.domain.errors.catalog import InvalidInputError, UnsupportedMediaError


class MediaKind(str, Enum):
    """Origem da mídia de entrada."""

    LOCAL_FILE = "local_file"
    YOUTUBE = "youtube"

    @property
    def label_pt(self) -> str:
        return {"local_file": "Arquivo local", "youtube": "YouTube"}[self.value]


class MediaSourceType(str, Enum):
    """Tipo de contêiner identificado na inspeção (não é prova de suporte)."""

    AUDIO = "audio"
    VIDEO = "video"


@dataclass(frozen=True, slots=True)
class MediaSource:
    """Origem declarada pelo usuário, antes de qualquer inspeção real.

    ``location`` é um caminho para arquivo local ou uma URL do YouTube. Não
    valida existência do arquivo: isso exige infraestrutura e pertence ao
    caso de uso ``ValidateInput``.
    """

    kind: MediaKind
    location: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, MediaKind):
            raise InvalidInputError("Tipo de mídia inválido.")
        location = (self.location or "").strip()
        if not location:
            raise InvalidInputError("Informe um arquivo local ou uma URL do YouTube.")
        if self.kind is MediaKind.YOUTUBE and not location.lower().startswith(
            ("http://", "https://")
        ):
            raise InvalidInputError(
                "A URL do YouTube deve começar com http:// ou https://."
            )
        object.__setattr__(self, "location", location)

    @property
    def is_local(self) -> bool:
        return self.kind is MediaKind.LOCAL_FILE


@dataclass(frozen=True, slots=True)
class AudioStreamInfo:
    """Faixa de áudio identificada por ffprobe.

    ``start_time_seconds`` é o offset de apresentação do stream no contêiner;
    deve ser preservado separadamente e nunca somado duas vezes.
    """

    index: int
    codec: str
    channels: int
    sample_rate_hz: int
    start_time_seconds: float = 0.0
    language: str | None = None
    title: str | None = None
    is_default: bool = False
    offset_source: str = "assumed_zero_missing_source_timestamp"

    def __post_init__(self) -> None:
        if not math.isfinite(self.start_time_seconds):
            raise UnsupportedMediaError("Offset da faixa de áudio não é finito.")
        if self.index < 0:
            raise UnsupportedMediaError("Índice da faixa de áudio inválido.")
        if self.channels < 1:
            raise UnsupportedMediaError("Faixa de áudio sem canais válidos.")
        if self.sample_rate_hz < 1:
            raise UnsupportedMediaError(
                "Faixa de áudio com taxa de amostragem inválida."
            )

    @property
    def label_pt(self) -> str:
        parts = [f"Faixa {self.index}", self.codec, f"{self.channels} canais"]
        if self.language:
            parts.append(self.language)
        return " · ".join(parts)


@dataclass(frozen=True, slots=True)
class MediaInfo:
    """Resultado da inspeção de mídia, mapeado para o domínio.

    ``duration_seconds`` é ``None`` quando o contêiner não declara duração
    (casos de stream). Nesse caso a validação temporal não pode afirmar que
    timestamps estão dentro da mídia.
    """

    kind: MediaKind
    source_type: MediaSourceType
    container: str
    duration_seconds: float | None
    audio_streams: tuple[AudioStreamInfo, ...] = field(default_factory=tuple)
    video_streams_count: int = 0

    def __post_init__(self) -> None:
        if self.duration_seconds is not None and (
            not math.isfinite(self.duration_seconds) or self.duration_seconds <= 0
        ):
            raise UnsupportedMediaError("Duração de mídia inválida.")
        for stream in self.audio_streams:
            duration = self.duration_seconds
            if duration is not None and stream.start_time_seconds >= duration:
                raise UnsupportedMediaError(
                    "Offset da faixa de áudio posterior à duração da mídia."
                )

    @property
    def has_audio(self) -> bool:
        return bool(self.audio_streams)

    @property
    def requires_stream_selection(self) -> bool:
        """``True`` quando há mais de uma faixa e o usuário precisa escolher."""
        return len(self.audio_streams) > 1

    def stream_by_index(self, index: int) -> AudioStreamInfo:
        for stream in self.audio_streams:
            if stream.index == index:
                return stream
        raise UnsupportedMediaError(f"Faixa de áudio {index} não existe na mídia.")

    def default_stream(self) -> AudioStreamInfo:
        if not self.audio_streams:
            raise UnsupportedMediaError("A mídia não possui faixa de áudio.")
        return next(
            (stream for stream in self.audio_streams if stream.is_default),
            self.audio_streams[0],
        )


@dataclass(frozen=True, slots=True)
class AudioAsset:
    """Áudio normalizado (WAV PCM mono 16 kHz) e seu início na linha do tempo.

    ``path`` pertence ao diretório temporário do job; o domínio guarda apenas a
    referência e nunca toca no filesystem.
    """

    path: str
    sample_rate_hz: int
    channels: int
    sample_format: str
    duration_seconds: float
    timeline_start_seconds: float = 0.0

    def __post_init__(self) -> None:
        if not self.path:
            raise InvalidInputError("Áudio normalizado sem caminho.")
        if not math.isfinite(self.duration_seconds) or self.duration_seconds <= 0:
            raise InvalidInputError("Áudio normalizado com duração inválida.")
        if not math.isfinite(self.timeline_start_seconds):
            raise InvalidInputError("Offset da linha do tempo não é finito.")
        if self.sample_rate_hz < 1 or self.channels < 1:
            raise InvalidInputError("Formato do áudio normalizado inválido.")
