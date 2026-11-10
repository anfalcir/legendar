"""Objetos de valor temporais independentes de framework.

Todos os instantes internos usam segundos em ponto flutuante finito, sempre
mapeados à linha do tempo da mídia original. A conversão de tempo local do
alinhador para tempo global segue a regra da Fase 0:

    timestamp_global = source_stream_offset + chunk_offset + timestamp_local
"""

from __future__ import annotations

import math
from dataclasses import dataclass

_EPSILON = 1e-9


class TemporalError(ValueError):
    """Erro de invariante temporal (valores não finitos, intervalos inválidos)."""


def _require_finite(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TemporalError(f"{name} deve ser numérico, recebido {type(value)!r}")
    number = float(value)
    if not math.isfinite(number):
        raise TemporalError(f"{name} deve ser finito, recebido {value!r}")
    return number


@dataclass(frozen=True, slots=True)
class TimeRange:
    """Intervalo temporal fechado-aberto ``[start, end)`` em segundos.

    Invariantes:
    - ``start`` e ``end`` finitos e não negativos;
    - ``start < end`` (duração estritamente positiva).
    """

    start: float
    end: float

    def __post_init__(self) -> None:
        start = _require_finite("start", self.start)
        end = _require_finite("end", self.end)
        if start < 0:
            raise TemporalError(f"start não pode ser negativo: {start!r}")
        if not end > start + _EPSILON:
            raise TemporalError(f"end ({end!r}) deve ser maior que start ({start!r})")
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)

    @property
    def duration(self) -> float:
        return self.end - self.start

    def overlaps(self, other: TimeRange) -> bool:
        """``True`` quando os intervalos compartilham um instante positivo."""
        return min(self.end, other.end) > max(self.start, other.start) + _EPSILON

    def clamp(self, *, lower: float = 0.0, upper: float | None = None) -> TimeRange:
        """Ajusta os limites ao intervalo permitido, preservando duração positiva.

        Usado para tolerar pequenos desvios nas bordas da mídia, nunca para
        redistribuir fala ou fabricar timestamps.
        """
        new_start = max(self.start, lower)
        new_end = self.end if upper is None else min(self.end, upper)
        return TimeRange(start=new_start, end=new_end)

    def contains(self, instant: float, *, tolerance: float = _EPSILON) -> bool:
        return self.start - tolerance <= instant <= self.end + tolerance

    def __str__(self) -> str:
        return f"[{self.start:.3f}, {self.end:.3f})"


@dataclass(frozen=True, slots=True)
class TimelineMapping:
    """Mapeamento aditivo de tempo local para a linha do tempo da mídia.

    ``source_offset`` é o ``start_time`` do stream de áudio selecionado no
    contêiner original; ``chunk_offset`` é o deslocamento global do chunk
    dentro do stream normalizado. Não somar offsets mais de uma vez.
    """

    source_offset: float = 0.0
    chunk_offset: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "source_offset", _require_finite("source_offset", self.source_offset)
        )
        object.__setattr__(
            self, "chunk_offset", _require_finite("chunk_offset", self.chunk_offset)
        )
        if self.source_offset + self.chunk_offset < 0:
            raise TemporalError("offset global não pode ser negativo")

    @property
    def global_offset(self) -> float:
        return self.source_offset + self.chunk_offset

    def to_global(self, local_seconds: float) -> float:
        return self.global_offset + _require_finite("local_seconds", local_seconds)

    def range_to_global(self, local_range: TimeRange) -> TimeRange:
        return TimeRange(
            start=self.to_global(local_range.start),
            end=self.to_global(local_range.end),
        )

    def without_chunk(self) -> TimelineMapping:
        """Retorna o mapeamento apenas com o offset da origem (descartando chunk)."""
        return TimelineMapping(source_offset=self.source_offset, chunk_offset=0.0)
