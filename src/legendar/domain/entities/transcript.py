"""Entidades de transcrição e alinhamento.

Palavras sem alinhamento permanecem explícitas: o domínio nunca fabrica
timestamps nem descarta palavras para "fechar" o resultado.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from legendar.domain.errors.catalog import InvalidInputError
from legendar.domain.value_objects.language import Language
from legendar.domain.value_objects.time import TimeRange


@dataclass(frozen=True, slots=True)
class TranscriptWord:
    """Palavra reconhecida/alinhada; ``range`` é ``None`` se não alinhada."""

    text: str
    range: TimeRange | None = None
    confidence: float | None = None

    def __post_init__(self) -> None:
        if not (self.text or "").strip():
            raise InvalidInputError("Palavra de transcrição vazia.")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise InvalidInputError("Confiança de palavra fora de [0, 1].")

    @property
    def is_aligned(self) -> bool:
        return self.range is not None


@dataclass(frozen=True, slots=True)
class TranscriptSegment:
    """Trecho contínuo reconhecido pelo Whisper, no idioma de origem."""

    text: str
    range: TimeRange | None = None
    words: tuple[TranscriptWord, ...] = field(default_factory=tuple)
    confidence: float | None = None

    def __post_init__(self) -> None:
        if not (self.text or "").strip():
            raise InvalidInputError("Segmento de transcrição vazio.")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise InvalidInputError("Confiança de segmento fora de [0, 1].")

    @property
    def is_aligned(self) -> bool:
        return self.range is not None

    @property
    def aligned_words(self) -> tuple[TranscriptWord, ...]:
        return tuple(word for word in self.words if word.is_aligned)


@dataclass(frozen=True, slots=True)
class Transcript:
    """Transcrição completa no idioma de origem, com metadados do modelo."""

    segments: tuple[TranscriptSegment, ...]
    language: Language
    model_name: str
    model_revision: str | None = None
    language_probability: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.language, Language):
            raise InvalidInputError("Transcrição sem idioma de origem válido.")
        if not self.model_name:
            raise InvalidInputError("Transcrição sem identificação do modelo.")
        if self.language_probability is not None and not (
            0.0 <= self.language_probability <= 1.0
        ):
            raise InvalidInputError("Probabilidade de idioma fora de [0, 1].")

    @property
    def text(self) -> str:
        return " ".join(segment.text.strip() for segment in self.segments).strip()

    @property
    def word_count(self) -> int:
        return sum(len(segment.words) for segment in self.segments)

    @property
    def is_empty(self) -> bool:
        return not self.text


@dataclass(frozen=True, slots=True)
class AlignmentDiagnostics:
    """Diagnóstico de qualidade do alinhamento.

    ``issues`` carrega rótulos estáveis (ex.: ``unmatched_word``,
    ``overlap``, ``out_of_bounds``) consumidos pela validação e pela GUI.
    """

    aligned_words: int = 0
    unmatched_words: tuple[TranscriptWord, ...] = field(default_factory=tuple)
    issues: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.aligned_words < 0:
            raise InvalidInputError(
                "Contagem de palavras alinhadas não pode ser negativa."
            )

    @property
    def total_words(self) -> int:
        return self.aligned_words + len(self.unmatched_words)

    @property
    def alignment_ratio(self) -> float:
        """Percentual de palavras alinhadas; ``0.0`` quando não há palavras."""
        total = self.total_words
        return (self.aligned_words / total) if total else 0.0

    @property
    def has_unmatched(self) -> bool:
        return bool(self.unmatched_words)

    def with_issue(self, issue: str) -> AlignmentDiagnostics:
        if issue in self.issues:
            return self
        return AlignmentDiagnostics(
            aligned_words=self.aligned_words,
            unmatched_words=self.unmatched_words,
            issues=(*self.issues, issue),
        )


@dataclass(frozen=True, slots=True)
class AlignmentResult:
    """Transcrição com palavras alinhadas à linha do tempo da mídia original.

    ``is_complete`` é ``False`` quando houve falha parcial; uma falha parcial
    jamais deve ser promovida a sucesso integral pelo pipeline.
    """

    transcript: Transcript
    diagnostics: AlignmentDiagnostics
    model_name: str | None = None

    @property
    def is_complete(self) -> bool:
        return not self.diagnostics.has_unmatched and not self.diagnostics.issues

    @property
    def requires_review(self) -> bool:
        return not self.is_complete
