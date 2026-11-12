"""Contrato de tradução sobre as cues finais da legenda.

A tradução acontece **depois** da segmentação: cada cue já tem tempo e texto
definidos, então o tradutor recebe exatamente as unidades que serão publicadas
e devolve exatamente um texto por unidade. Assim o vínculo temporal nunca
depende de o segmento do Whisper coincidir com a cue final — que pode ser um
fragmento dele.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from legendar.domain.entities.subtitle import SubtitleCue, SubtitleTrack
from legendar.domain.errors.catalog import InvalidInputError, TranslationError
from legendar.domain.value_objects.language import Language
from legendar.domain.value_objects.time import TimeRange


@dataclass(frozen=True, slots=True)
class TranslationContext:
    """Contexto textual explícito que acompanha uma unidade de tradução."""

    before: tuple[str, ...] = ()
    after: tuple[str, ...] = ()
    protected_terms: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TranslationUnit:
    """Unidade contextualizada com rastreabilidade temporal explícita."""

    index: int
    text: str
    source_cue_ids: tuple[int, ...] = ()
    source_range: TimeRange | None = None
    context: TranslationContext = field(default_factory=TranslationContext)

    def __post_init__(self) -> None:
        if self.index < 1:
            raise TranslationError("Unidade de tradução sem índice válido.")
        if not (self.text or "").strip():
            raise TranslationError(f"Unidade de tradução {self.index} sem texto.")
        if any(cue_id < 1 for cue_id in self.source_cue_ids):
            raise TranslationError(
                f"Unidade de tradução {self.index} contém ID de origem inválido."
            )
        if (
            self.source_range is not None
            and self.source_range.end <= self.source_range.start
        ):
            raise TranslationError(
                f"Unidade de tradução {self.index} possui intervalo temporal inválido."
            )


@dataclass(frozen=True, slots=True)
class TranslationResult:
    """Resultado com IDs explícitos das unidades que foram traduzidas."""

    language: Language
    texts: tuple[str, ...]
    unit_indexes: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class TranslationApplication:
    """Trilho traduzido e o que precisa ser reportado ao usuário."""

    track: SubtitleTrack
    warnings: tuple[str, ...] = field(default_factory=tuple)
    unchanged_cues: tuple[int, ...] = ()


def build_translation_units(track: SubtitleTrack) -> tuple[TranslationUnit, ...]:
    """Extrai uma unidade por cue, preservando índices e ordem."""
    if track.is_empty:
        raise InvalidInputError("Nenhuma legenda segmentada para traduzir.")
    units: list[TranslationUnit] = []
    for position, cue in enumerate(track.cues):
        before = tuple(
            item.normalized_text
            for item in track.cues[max(0, position - 2) : position]
        )
        after = tuple(
            item.normalized_text for item in track.cues[position + 1 : position + 3]
        )
        units.append(
            TranslationUnit(
                index=cue.index,
                text=cue.normalized_text,
                source_cue_ids=(cue.index,),
                source_range=cue.range,
                context=TranslationContext(before=before, after=after),
            )
        )
    return tuple(units)


def apply_translation(
    track: SubtitleTrack,
    result: TranslationResult,
) -> TranslationApplication:
    """Reaplica os textos traduzidos mantendo exatamente os tempos originais.

    Falhas explícitas: contagem divergente, texto vazio ou tradução que não
    alterou nenhuma cue. Cues idênticas ao original são permitidas (nomes,
    siglas, interjeições), mas contabilizadas como aviso.
    """
    if not isinstance(result, TranslationResult):
        raise TranslationError("Resultado de tradução inválido.")
    if not isinstance(result.language, Language):
        raise TranslationError("Idioma da tradução inválido.")
    if track.is_empty:
        raise InvalidInputError("Nenhuma legenda segmentada para traduzir.")
    expected_indexes = tuple(cue.index for cue in track.cues)
    if result.unit_indexes != expected_indexes:
        raise TranslationError(
            "A tradução não manteve a correspondência por ID com as legendas "
            f"(esperado {expected_indexes}, recebido {result.unit_indexes})."
        )
    if len(result.texts) != len(track.cues):
        raise TranslationError(
            "A tradução não manteve a cardinalidade das unidades "
            f"({len(result.texts)} textos para {len(track.cues)} cues)."
        )

    cues: list[SubtitleCue] = []
    unchanged: list[int] = []
    for cue, raw in zip(track.cues, result.texts, strict=True):
        text = " ".join((raw or "").split())
        if not text:
            raise TranslationError(f"Tradução vazia na legenda {cue.index}.")
        if text == cue.normalized_text:
            unchanged.append(cue.index)
        cues.append(
            SubtitleCue(
                index=cue.index,
                text=text,
                range=cue.range,
                language=result.language,
                source_segments=cue.source_segments,
            )
        )

    if len(unchanged) == len(cues):
        raise TranslationError(
            "A tradução não alterou nenhum texto; verifique os idiomas de origem e "
            "destino e o modelo configurado."
        )

    warnings: tuple[str, ...] = ()
    if unchanged:
        warnings = (
            f"{len(unchanged)} legenda(s) idêntica(s) ao texto original: "
            f"{_cue_list(unchanged)}.",
        )
    return TranslationApplication(
        track=SubtitleTrack(language=result.language, cues=tuple(cues)),
        warnings=warnings,
        unchanged_cues=tuple(unchanged),
    )


def _cue_list(indexes: list[int], *, limit: int = 8) -> str:
    shown = ", ".join(str(index) for index in indexes[:limit])
    if len(indexes) > limit:
        shown += ", …"
    return shown
