"""Validação do trilho final antes da publicação do SRT.

Duas camadas, ambas determinísticas e sem I/O:

- **falhas estruturais** interrompem o job (``SrtValidationError``): trilho
  vazio, cue sem texto, cue que termina depois da mídia;
- **riscos de legibilidade** viram avisos explícitos no resultado: cue curta
  demais, longa demais, acima do tempo de leitura ou acima da capacidade de
  duas linhas.

Nada é corrigido silenciosamente: o usuário vê exatamente o que ficou fora do
alvo editorial.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from legendar.application.pipeline.segmentation import SegmentationPolicy
from legendar.domain.entities.subtitle import SubtitleTrack
from legendar.domain.errors.catalog import SrtValidationError

#: Tolerância para arredondamento de timestamp (ms) e offsets de contêiner.
MEDIA_DURATION_TOLERANCE_SECONDS = 0.5
#: Quantos índices de cue aparecem em cada aviso antes de abreviar.
_LIST_LIMIT = 8


@dataclass(frozen=True, slots=True)
class TrackValidationReport:
    """Diagnóstico do trilho final; ``warnings`` alimenta o resultado do job."""

    warnings: tuple[str, ...] = field(default_factory=tuple)
    short_cues: tuple[int, ...] = ()
    long_cues: tuple[int, ...] = ()
    overflow_cues: tuple[int, ...] = ()
    wide_cues: tuple[int, ...] = ()

    @property
    def is_clean(self) -> bool:
        return not (
            self.short_cues or self.long_cues or self.overflow_cues or self.wide_cues
        )


def validate_track(
    track: SubtitleTrack,
    *,
    policy: SegmentationPolicy | None = None,
    media_duration: float | None = None,
) -> TrackValidationReport:
    """Valida estrutura e legibilidade do trilho que será publicado."""
    policy = policy or SegmentationPolicy()
    if track.is_empty:
        raise SrtValidationError("Trilho de legendas vazio.")

    short: list[int] = []
    long: list[int] = []
    overflow: list[int] = []
    wide: list[int] = []

    for cue in track.cues:
        text = cue.normalized_text
        if not text:
            raise SrtValidationError(f"Cue {cue.index} sem texto.")
        if (
            media_duration is not None
            and cue.range.end > media_duration + MEDIA_DURATION_TOLERANCE_SECONDS
        ):
            raise SrtValidationError(
                f"Cue {cue.index} termina em {_seconds(cue.range.end)} s, depois do "
                f"fim da mídia ({_seconds(media_duration)} s)."
            )
        if cue.range.duration < policy.min_cue_duration:
            short.append(cue.index)
        if cue.range.duration > policy.max_cue_duration:
            long.append(cue.index)
        if cue.range.duration < policy.reading_time(text):
            overflow.append(cue.index)
        if len(text) > policy.max_chars_per_cue:
            wide.append(cue.index)

    warnings: list[str] = []
    if short:
        warnings.append(
            f"{len(short)} {_noun(len(short))} abaixo da duração mínima de "
            f"{_seconds(policy.min_cue_duration)} s: {_cue_list(short)}."
        )
    if long:
        warnings.append(
            f"{len(long)} {_noun(len(long))} acima da duração máxima de "
            f"{_seconds(policy.max_cue_duration)} s: {_cue_list(long)}."
        )
    if overflow:
        warnings.append(
            f"{len(overflow)} {_noun(len(overflow))} acima da velocidade de leitura "
            f"alvo de {policy.chars_per_second:g} caracteres por segundo: "
            f"{_cue_list(overflow)}."
        )
    if wide:
        warnings.append(
            f"{len(wide)} {_noun(len(wide))} acima de {policy.max_chars_per_cue} "
            f"caracteres por cue: {_cue_list(wide)}."
        )

    return TrackValidationReport(
        warnings=tuple(warnings),
        short_cues=tuple(short),
        long_cues=tuple(long),
        overflow_cues=tuple(overflow),
        wide_cues=tuple(wide),
    )


def _noun(count: int) -> str:
    return "legenda" if count == 1 else "legendas"


def _seconds(value: float) -> str:
    return f"{value:.1f}".replace(".", ",")


def _cue_list(indexes: list[int]) -> str:
    shown = ", ".join(str(index) for index in indexes[:_LIST_LIMIT])
    if len(indexes) > _LIST_LIMIT:
        shown += ", …"
    return shown
