"""Sink de progresso com garantia de monotonicidade.

O alinhador e o transcritor reportam progresso local por etapa; o pipeline
compõe frações ponderadas para exibir um valor global. Este sink impede que a
barra ande para trás por causa de arredondamento ou de uma etapa que reporta
``0`` ao iniciar.
"""

from __future__ import annotations

from collections.abc import Callable

from legendar.domain.errors.catalog import InvalidInputError


class MonotonicProgress:
    """Progresso em ``[0, 1]`` que nunca retrocede."""

    __slots__ = ("_last", "_callback")

    def __init__(self, callback: Callable[[float, str], None] | None = None) -> None:
        self._last = 0.0
        self._callback = callback

    @property
    def value(self) -> float:
        return self._last

    def report(self, fraction: float, message: str = "") -> None:
        if not 0.0 <= fraction <= 1.0:
            raise InvalidInputError(f"Progresso fora de [0, 1]: {fraction!r}")
        if fraction < self._last:
            return
        self._last = fraction
        if self._callback is not None:
            self._callback(fraction, message)

    def reset(self) -> None:
        self._last = 0.0


class ScaledProgress:
    """Mapeia progresso local de uma etapa para uma faixa ponderada global.

    ``start``/``end`` delimitam a contribuição da etapa no progresso total.
    Um novo objeto é criado por etapa; isso evita que uma etapa "volte" o
    progresso de outra.
    """

    __slots__ = ("_sink", "_start", "_end")

    def __init__(self, sink: MonotonicProgress, start: float, end: float) -> None:
        if not 0.0 <= start <= end <= 1.0:
            raise InvalidInputError("Faixa de progresso inválida.")
        self._sink = sink
        self._start = start
        self._end = end

    def report(self, fraction: float, message: str = "") -> None:
        if not 0.0 <= fraction <= 1.0:
            raise InvalidInputError(f"Progresso fora de [0, 1]: {fraction!r}")
        span = self._end - self._start
        self._sink.report(self._start + span * fraction, message)
