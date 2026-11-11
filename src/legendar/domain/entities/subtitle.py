"""Entidade de legenda final e validação estrutural da lista de cues.

O domínio garante ordem, numeração e limites; a serialização SRT fica no
infraestrutura e é verificada por um validador determinístico.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from legendar.domain.errors.catalog import InvalidInputError, SrtValidationError
from legendar.domain.value_objects.language import Language
from legendar.domain.value_objects.text_layout import (
    DEFAULT_MAX_CHARS_PER_LINE,
    DEFAULT_MAX_LINES,
    wrap_lines,
)
from legendar.domain.value_objects.time import TimeRange


@dataclass(frozen=True, slots=True)
class SubtitleCue:
    """Unidade de legenda final, ligada à fala de origem.

    ``source_segments`` referencia índices da transcrição original para que a
    tradução nunca perca o vínculo temporal.
    """

    index: int
    text: str
    range: TimeRange
    language: Language
    source_segments: tuple[int, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.index < 1:
            raise InvalidInputError("Numeração de legenda inicia em 1.")
        if not (self.text or "").strip():
            raise InvalidInputError("Legenda sem texto.")
        if not isinstance(self.range, TimeRange):
            raise InvalidInputError("Legenda sem intervalo temporal válido.")
        if not isinstance(self.language, Language):
            raise InvalidInputError("Legenda sem idioma final válido.")
        if any(ref < 0 for ref in self.source_segments):
            raise InvalidInputError("Referência de segmento de origem inválida.")

    @property
    def normalized_text(self) -> str:
        """Texto em uma linha única, sem espaços redundantes."""
        return " ".join(self.text.split())

    def lines(
        self,
        *,
        max_chars_per_line: int = DEFAULT_MAX_CHARS_PER_LINE,
        max_lines: int = DEFAULT_MAX_LINES,
    ) -> tuple[str, ...]:
        """Texto dividido nas linhas exibidas no arquivo final (até duas)."""
        return wrap_lines(
            self.normalized_text,
            max_chars_per_line=max_chars_per_line,
            max_lines=max_lines,
        )


@dataclass(frozen=True, slots=True)
class SubtitleTrack:
    """Lista ordenada de cues de um único idioma final."""

    language: Language
    cues: tuple[SubtitleCue, ...]

    def __post_init__(self) -> None:
        if self.cues:
            self._validate_order()

    @property
    def is_empty(self) -> bool:
        return not self.cues

    @property
    def duration_covered(self) -> float:
        return sum(cue.range.duration for cue in self.cues)

    def _validate_order(self) -> None:
        expected = 1
        previous_end = -1.0
        for cue in self.cues:
            if cue.index != expected:
                raise SrtValidationError(
                    f"Numeração de legendas fora de sequência: esperado {expected}, "
                    f"recebido {cue.index}."
                )
            if cue.range.start < previous_end:
                raise SrtValidationError(
                    f"Sobreposição de legendas na cue {cue.index}."
                )
            if cue.language is not self.language:
                raise SrtValidationError(
                    f"Cue {cue.index} com idioma diferente do trilho."
                )
            previous_end = cue.range.end
            expected += 1

    def overlapping_pairs(self) -> tuple[tuple[int, int], ...]:
        """Pares de cues que se sobrepõem, para diagnóstico (não usado na validação)."""
        pairs: list[tuple[int, int]] = []
        for previous, current in zip(self.cues, self.cues[1:], strict=False):
            if previous.range.overlaps(current.range):
                pairs.append((previous.index, current.index))
        return tuple(pairs)
