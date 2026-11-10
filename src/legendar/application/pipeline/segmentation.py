"""Segmentação de palavras alinhadas em cues de legenda.

Regras puras e determinísticas, sem Qt e sem I/O. O ponto central: **nenhum
timestamp é fabricado**. Se uma cue ficaria curta demais para leitura, ela é
mantida com o intervalo real e reportada em ``short_cues``; se um segmento não
tem palavras alinhadas nem intervalo, ele é registrado em ``dropped_segments``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from legendar.domain.entities.subtitle import SubtitleCue, SubtitleTrack
from legendar.domain.entities.transcript import (
    AlignmentResult,
    TranscriptSegment,
    TranscriptWord,
)
from legendar.domain.errors.catalog import SrtValidationError
from legendar.domain.value_objects.time import TimeRange

#: Limites conservadores de legibilidade (revisáveis na Fase 2).
MAX_CHARS_PER_CUE = 84
MAX_CUE_DURATION_SECONDS = 7.0
MIN_CUE_DURATION_SECONDS = 0.8
MAX_GAP_SECONDS = 0.6
CHARS_PER_SECOND = 22.0
_MIN_WINDOW_SECONDS = 1e-3


@dataclass(frozen=True, slots=True)
class SegmentationPolicy:
    """Parâmetros de segmentação; imutáveis para reprodutibilidade."""

    max_chars_per_cue: int = MAX_CHARS_PER_CUE
    max_cue_duration: float = MAX_CUE_DURATION_SECONDS
    min_cue_duration: float = MIN_CUE_DURATION_SECONDS
    max_gap: float = MAX_GAP_SECONDS
    chars_per_second: float = CHARS_PER_SECOND

    def __post_init__(self) -> None:
        if self.max_chars_per_cue < 20:
            raise SrtValidationError("Limite de caracteres por cue muito baixo.")
        if not 0 < self.min_cue_duration < self.max_cue_duration:
            raise SrtValidationError("Durações de cue inconsistentes.")
        if self.chars_per_second <= 0:
            raise SrtValidationError("Velocidade de leitura deve ser positiva.")

    def reading_time(self, text: str) -> float:
        return len(text) / self.chars_per_second


@dataclass(frozen=True, slots=True)
class SegmentationResult:
    """Trilho gerado e diagnóstico explícito de perdas e riscos."""

    track: SubtitleTrack
    dropped_segments: tuple[int, ...] = ()
    short_cues: tuple[int, ...] = ()
    overflow_cues: tuple[int, ...] = ()
    source_segment_count: int = 0
    diagnostics: tuple[str, ...] = field(default_factory=tuple)

    @property
    def cue_count(self) -> int:
        return len(self.track.cues)

    @property
    def has_dropped_segments(self) -> bool:
        return bool(self.dropped_segments)

    @property
    def is_lossless(self) -> bool:
        return not self.dropped_segments and not self.overflow_cues

    @property
    def coverage_ratio(self) -> float:
        """Fração de segmentos que geraram ao menos uma cue."""
        if not self.source_segment_count:
            return 0.0
        covered = self.source_segment_count - len(self.dropped_segments)
        return covered / self.source_segment_count


def segment_alignment(
    alignment: AlignmentResult,
    *,
    policy: SegmentationPolicy | None = None,
) -> SegmentationResult:
    """Converte um ``AlignmentResult`` em ``SubtitleTrack`` ordenado."""
    policy = policy or SegmentationPolicy()
    cues: list[SubtitleCue] = []
    dropped: list[int] = []
    short: list[int] = []
    overflow: list[int] = []

    last_end = 0.0
    for position, segment in enumerate(alignment.transcript.segments):
        for window, text in _groups_for_segment(segment, policy, dropped, position):
            window = _clip_to_previous(window, last_end)
            if window is None:
                dropped.append(position)
                continue
            last_end = window.end
            cue = SubtitleCue(
                index=len(cues) + 1,
                text=text,
                range=window,
                language=alignment.transcript.language,
                source_segments=(position,),
            )
            cues.append(cue)
            if window.duration < policy.min_cue_duration:
                short.append(cue.index)
            # Overflows: texto que não cabe no tempo de leitura da janela.
            if window.duration < policy.reading_time(text):
                overflow.append(cue.index)

    diagnostics: list[str] = []
    if dropped:
        diagnostics.append("dropped_segment")
    if short:
        diagnostics.append("short_cue")
    if overflow:
        diagnostics.append("reading_speed_overflow")

    return SegmentationResult(
        track=SubtitleTrack(language=alignment.transcript.language, cues=tuple(cues)),
        dropped_segments=tuple(dict.fromkeys(dropped)),
        short_cues=tuple(short),
        overflow_cues=tuple(overflow),
        source_segment_count=len(alignment.transcript.segments),
        diagnostics=tuple(diagnostics),
    )


def _clip_to_previous(window: TimeRange, last_end: float) -> TimeRange | None:
    """Remove sobreposição com a cue anterior sem inventar tempo novo.

    Se a janela inteira já está coberta pela cue anterior, ela é descartada
    (o chamador registra a perda); caso contrário, apenas o início é aparado.
    """
    if window.end <= last_end + _MIN_WINDOW_SECONDS:
        return None
    if window.start < last_end:
        return TimeRange(start=last_end, end=window.end)
    return window


def _groups_for_segment(
    segment: TranscriptSegment,
    policy: SegmentationPolicy,
    dropped: list[int],
    position: int,
) -> list[tuple[TimeRange, str]]:
    """Agrupa o segmento em janelas temporais com texto final.

    Cada item retornado é ``(janela, texto)``; a janela vem sempre de dados
    temporais reais (palavras alinhadas ou intervalo do segmento).
    """
    aligned: list[tuple[TranscriptWord, TimeRange]] = [
        (word, word.range) for word in segment.words if word.range is not None
    ]
    if aligned:
        return [
            (TimeRange(start=group[0][1].start, end=group[-1][1].end), _text_of(group))
            for group in _split_words(aligned, policy)
        ]

    if segment.range is None:
        dropped.append(position)
        return []

    text = " ".join(segment.text.split())
    if not text:
        dropped.append(position)
        return []

    # Sem palavras alinhadas: usa o intervalo do próprio segmento, preservando
    # o texto original. Nenhum tempo novo é inventado.
    return [(segment.range, text)]


def _split_words(
    words: list[tuple[TranscriptWord, TimeRange]],
    policy: SegmentationPolicy,
) -> list[list[tuple[TranscriptWord, TimeRange]]]:
    """Divide palavras alinhadas em grupos que respeitam texto, tempo e pausa."""
    groups: list[list[tuple[TranscriptWord, TimeRange]]] = []
    current: list[tuple[TranscriptWord, TimeRange]] = []
    for item in words:
        if not current:
            current = [item]
            continue
        candidate_text = _text_of([*current, item])
        gap = item[1].start - current[-1][1].end
        duration = item[1].end - current[0][1].start
        if (
            len(candidate_text) > policy.max_chars_per_cue
            or duration > policy.max_cue_duration
            or gap > policy.max_gap
        ):
            groups.append(current)
            current = [item]
        else:
            current.append(item)
    if current:
        groups.append(current)
    return groups


def _text_of(words: list[tuple[TranscriptWord, TimeRange]]) -> str:
    return " ".join(word.text.strip() for word, _ in words).strip()
