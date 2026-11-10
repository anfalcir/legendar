"""Parser puro da saída JSON do ``ffprobe`` para entidades de domínio.

Este módulo não executa processos nem toca no filesystem: recebe o documento
já decodificado e devolve ``MediaInfo`` ou um erro de domínio. A separação
permite testar todos os casos de borda sem FFmpeg instalado.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from legendar.domain.entities.media import (
    AudioStreamInfo,
    MediaInfo,
    MediaKind,
    MediaSourceType,
)
from legendar.domain.errors.catalog import MediaToolError, UnsupportedMediaError

_MISSING_VALUES = {"", "n/a", "none", "null"}


def _as_mapping(value: Any, *, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise UnsupportedMediaError(f"ffprobe não retornou {field} válido.")
    return value


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip().lower() in _MISSING_VALUES:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed


def _seconds(value: Any) -> float:
    parsed = _optional_float(value)
    return parsed if parsed is not None else 0.0


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _container_name(format_info: Mapping[str, Any]) -> str:
    raw = _text(format_info.get("format_name"))
    if raw is None:
        return "desconhecido"
    # ffprobe devolve nomes alternativos separados por vírgula
    # (ex.: "mov,mp4,m4a,3gp,3g2,mj2"); o primeiro é o rótulo estável.
    return raw.split(",")[0].strip() or "desconhecido"


def _audio_stream(stream: Mapping[str, Any], position: int) -> AudioStreamInfo:
    index = stream.get("index", position)
    if not isinstance(index, int):
        raise UnsupportedMediaError("ffprobe retornou índice de faixa inválido.")
    tags = stream.get("tags")
    tags = tags if isinstance(tags, Mapping) else {}
    channels = stream.get("channels")
    sample_rate = stream.get("sample_rate")
    try:
        channels_value = int(channels)
        sample_rate_value = int(sample_rate)
    except (TypeError, ValueError) as exc:
        raise UnsupportedMediaError(
            "A faixa de áudio não declara canais ou taxa de amostragem."
        ) from exc
    return AudioStreamInfo(
        index=index,
        codec=_text(stream.get("codec_name")) or "desconhecido",
        channels=channels_value,
        sample_rate_hz=sample_rate_value,
        start_time_seconds=_seconds(stream.get("start_time")),
        language=_text(tags.get("language")),
        title=_text(tags.get("title")),
    )


def parse_ffprobe_payload(
    payload: Mapping[str, Any], *, kind: MediaKind = MediaKind.LOCAL_FILE
) -> MediaInfo:
    """Converte o documento JSON do ffprobe em ``MediaInfo``.

    A duração é opcional: contêineres de stream podem não declará-la. Nesse
    caso a validação temporal não pode afirmar que offsets estão dentro da
    mídia e o pipeline deve tratar isso explicitamente.
    """
    document = _as_mapping(payload, field="documento")
    raw_streams = document.get("streams")
    if not isinstance(raw_streams, Sequence) or isinstance(raw_streams, (str, bytes)):
        raise UnsupportedMediaError("ffprobe não retornou a lista de faixas.")
    streams = [_as_mapping(stream, field="faixa") for stream in raw_streams]
    if not streams:
        raise UnsupportedMediaError("A mídia não possui faixas reconhecíveis.")

    audio_streams = tuple(
        _audio_stream(stream, position)
        for position, stream in enumerate(streams)
        if stream.get("codec_type") == "audio"
    )
    video_count = sum(1 for stream in streams if stream.get("codec_type") == "video")

    format_info = document.get("format")
    if format_info is not None:
        format_info = _as_mapping(format_info, field="formato")
    else:
        format_info = {}
    duration = _optional_float(format_info.get("duration"))
    if duration is not None and duration <= 0:
        duration = None

    return MediaInfo(
        kind=kind,
        source_type=(MediaSourceType.VIDEO if video_count else MediaSourceType.AUDIO),
        container=_container_name(format_info),
        duration_seconds=duration,
        audio_streams=audio_streams,
        video_streams_count=video_count,
    )


def parse_ffprobe_document(
    text: str, *, kind: MediaKind = MediaKind.LOCAL_FILE
) -> MediaInfo:
    """Decodifica o JSON bruto do ffprobe e delega ao parser de payload."""
    try:
        payload = json.loads(text)
    except (TypeError, json.JSONDecodeError) as exc:
        raise MediaToolError(
            "O ffprobe retornou uma saída inválida.",
            technical_detail=f"{type(exc).__name__}: {exc}",
        ) from exc
    return parse_ffprobe_payload(payload, kind=kind)
