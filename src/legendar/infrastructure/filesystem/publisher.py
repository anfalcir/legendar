"""Adaptador de publicação de SRT com validação e troca atômica."""

from __future__ import annotations

from pathlib import Path

from legendar.domain.entities.subtitle import SubtitleTrack
from legendar.infrastructure.filesystem.atomic import atomic_write_text
from legendar.infrastructure.filesystem.srt import format_srt, validate_roundtrip


class SrtPublisher:
    """Serializa, valida por round-trip e publica atomicamente.

    A validação acontece **antes** de qualquer escrita no destino: se o SRT
    gerado não reabrir idêntico, nada é publicado.
    """

    def publish(self, track: SubtitleTrack, destination_path: str) -> str:
        content = format_srt(track)
        validate_roundtrip(track, content)
        written = atomic_write_text(Path(destination_path), content)
        return str(written)
