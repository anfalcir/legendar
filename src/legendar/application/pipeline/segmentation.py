"""Segmentação de palavras alinhadas em cues de legenda.

Regras puras e determinísticas, sem Qt e sem I/O. O ponto central: **nenhum
timestamp é fabricado**. Se uma cue ficaria curta demais para leitura, ela é
mantida com o intervalo real e reportada em ``short_cues``; se um segmento não
tem palavras alinhadas nem intervalo, ele é registrado em ``dropped_segments``.

A partir da Fase 6 o alvo editorial é o de duas linhas de 42 caracteres, com
quebra preferencial em fim de frase ou de oração e velocidade de leitura de
~17 caracteres por segundo. Quando um grupo de palavras não cabe no tempo
disponível, ele é subdividido em partes contíguas (nunca em timestamps
inventados) antes de ser reportado como ``overflow_cues``.
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

#: Limites editoriais de legibilidade (duas linhas, ~17 cps, 1–7 s por cue).
MAX_CHARS_PER_LINE = 42
MAX_LINES = 2
MAX_CHARS_PER_CUE = MAX_LINES * MAX_CHARS_PER_LINE
MAX_CUE_DURATION_SECONDS = 7.0
MIN_CUE_DURATION_SECONDS = 1.0
MAX_GAP_SECONDS = 0.6
CHARS_PER_SECOND = 17.0
SENTENCE_BREAK_RATIO = 0.5
MIN_WORDS_PER_SPLIT_PART = 2
MAX_SPLIT_DEPTH = 6
DISPLAY_SAFETY_MARGIN_SECONDS = 0.08
_MIN_WINDOW_SECONDS = 1e-3
_SENTENCE_ENDINGS = (".", "!", "?", "…")
_CLAUSE_ENDINGS = (*_SENTENCE_ENDINGS, ",", ";", ":", "—", "-")


@dataclass(frozen=True, slots=True)
class SegmentationPolicy:
    """Parâmetros de segmentação; imutáveis para reprodutibilidade."""

    max_chars_per_line: int = MAX_CHARS_PER_LINE
    max_lines: int = MAX_LINES
    max_chars_per_cue: int = MAX_CHARS_PER_CUE
    max_cue_duration: float = MAX_CUE_DURATION_SECONDS
    min_cue_duration: float = MIN_CUE_DURATION_SECONDS
    max_gap: float = MAX_GAP_SECONDS
    chars_per_second: float = CHARS_PER_SECOND
    sentence_break_ratio: float = SENTENCE_BREAK_RATIO
    min_words_per_split_part: int = MIN_WORDS_PER_SPLIT_PART

    def __post_init__(self) -> None:
        if self.max_chars_per_line < 20:
            raise SrtValidationError("Largura de linha da legenda muito baixa.")
        if self.max_lines < 1:
            raise SrtValidationError("A legenda precisa de ao menos uma linha.")
        if self.max_chars_per_cue < 20:
            raise SrtValidationError("Limite de caracteres por cue muito baixo.")
        if self.max_chars_per_cue > self.max_chars_per_line * self.max_lines:
            raise SrtValidationError(
                "Limite de caracteres por cue excede a capacidade das linhas."
            )
        if not 0 < self.min_cue_duration < self.max_cue_duration:
            raise SrtValidationError("Durações de cue inconsistentes.")
        if self.chars_per_second <= 0:
            raise SrtValidationError("Velocidade de leitura deve ser positiva.")
        if not 0 <= self.sentence_break_ratio <= 1:
            raise SrtValidationError("Proporção de quebra por frase fora de faixa.")
        if self.min_words_per_split_part < 1:
            raise SrtValidationError("Partes de cue precisam de ao menos uma palavra.")

    def reading_time(self, text: str) -> float:
        """Tempo mínimo de leitura do texto, em segundos."""
        return len(text) / self.chars_per_second


@dataclass(frozen=True, slots=True)
class SegmentationResult:
    """Trilho gerado e diagnóstico explícito de perdas e riscos."""

    track: SubtitleTrack
    dropped_segments: tuple[int, ...] = ()
    short_cues: tuple[int, ...] = ()
    overflow_cues: tuple[int, ...] = ()
    source_segment_count: int = 0
    unmatched_words: tuple[TranscriptWord, ...] = ()
    diagnostics: tuple[str, ...] = field(default_factory=tuple)

    @property
    def cue_count(self) -> int:
        return len(self.track.cues)

    @property
    def has_dropped_segments(self) -> bool:
        return bool(self.dropped_segments)

    @property
    def is_lossless(self) -> bool:
        return (
            not self.dropped_segments
            and not self.overflow_cues
            and not self.unmatched_words
        )

    @property
    def has_unmatched_words(self) -> bool:
        """Indica conteúdo reconhecido que ainda não possui âncora temporal."""
        return bool(self.unmatched_words)

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
    """Segmenta um fluxo global de palavras, inclusive entre limites do ASR.

    A origem de cada palavra é mantida para que cada cue continue rastreável.
    Segmentos sem word timestamps continuam usando apenas seu próprio range.
    """
    policy = policy or SegmentationPolicy()
    events: list[tuple[TimeRange, str, tuple[int, ...]]] = []
    dropped: list[int] = []
    short: list[int] = []
    overflow: list[int] = []
    words: list[tuple[TranscriptWord, TimeRange, int]] = []

    for position, segment in enumerate(alignment.transcript.segments):
        aligned = [
            (word, word.range, position)
            for word in segment.words
            if word.range is not None
        ]
        if aligned:
            words.extend(aligned)
            continue
        text = " ".join(segment.text.split())
        if segment.range is None or not text:
            dropped.append(position)
            continue
        events.append((segment.range, text, (position,)))

    # A sequência global deve respeitar a cronologia. Ordenar silenciosamente
    # poderia alterar a ordem falada; portanto, inconsistência é erro explícito.
    for previous, current in zip(words, words[1:], strict=False):
        if current[1].start < previous[1].start:
            raise SrtValidationError(
                "Palavras alinhadas fora da ordem cronológica da transcrição."
            )

    plain_words = [(word, time_range) for word, time_range, _ in words]
    groups = _split_words(plain_words, policy) if plain_words else []
    refined = _refine_for_reading_speed(groups, policy)
    split_applied = len(refined) > len(groups)
    source_by_identity = {id(word): source for word, _, source in words}

    for group in refined:
        window = TimeRange(start=group[0][1].start, end=group[-1][1].end)
        text = _text_of(group)
        sources = tuple(
            sorted({source_by_identity[id(word)] for word, _ in group})
        )
        events.append((window, text, sources))

    # Eventos de segmentos sem timestamps por palavra coexistem com as cues
    # globais, mas a publicação permanece cronológica e sem sobreposição.
    events.sort(key=lambda item: (item[0].start, item[0].end))
    cues: list[SubtitleCue] = []
    last_end = 0.0
    for event_index, (window, text, sources) in enumerate(events):
        clipped = _clip_to_previous(window, last_end)
        if clipped is None:
            dropped.extend(sources)
            continue
        next_start = (
            events[event_index + 1][0].start
            if event_index + 1 < len(events)
            else None
        )
        clipped = _extend_into_safe_silence(
            clipped,
            next_start=next_start,
            policy=policy,
        )
        last_end = clipped.end
        cue = SubtitleCue(
            index=len(cues) + 1,
            text=text,
            range=clipped,
            language=alignment.transcript.language,
            source_segments=sources,
        )
        cues.append(cue)
        if clipped.duration < policy.min_cue_duration:
            short.append(cue.index)
        if clipped.duration < policy.reading_time(text):
            overflow.append(cue.index)

    diagnostics: list[str] = []
    unmatched_words = alignment.diagnostics.unmatched_words
    if unmatched_words:
        diagnostics.append("unmatched_word")
    if dropped:
        diagnostics.append("dropped_segment")
    if short:
        diagnostics.append("short_cue")
    if overflow:
        diagnostics.append("reading_speed_overflow")
    if split_applied:
        diagnostics.append("reading_speed_split")
    if any(len(cue.source_segments) > 1 for cue in cues):
        diagnostics.append("cross_segment_merge")

    return SegmentationResult(
        track=SubtitleTrack(language=alignment.transcript.language, cues=tuple(cues)),
        dropped_segments=tuple(dict.fromkeys(dropped)),
        short_cues=tuple(short),
        overflow_cues=tuple(overflow),
        source_segment_count=len(alignment.transcript.segments),
        unmatched_words=tuple(unmatched_words),
        diagnostics=tuple(dict.fromkeys(diagnostics)),
    )


def _extend_into_safe_silence(
    window: TimeRange,
    *,
    next_start: float | None,
    policy: SegmentationPolicy,
) -> TimeRange:
    """Estende cue curta somente no silêncio antes da próxima fala/cue.

    A margem de segurança impede que a exibição invada a próxima palavra.
    A última cue não é estendida porque a segmentação não conhece o fim real
    da mídia nem dispõe de evidência de silêncio após a última palavra.
    """
    if next_start is None or window.duration >= policy.min_cue_duration:
        return window
    safe_end = min(
        next_start - DISPLAY_SAFETY_MARGIN_SECONDS,
        window.start + policy.max_cue_duration,
    )
    target_end = min(
        safe_end,
        window.start + policy.min_cue_duration,
    )
    if target_end <= window.end:
        return window
    return TimeRange(start=window.start, end=target_end)


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
            or _prefers_break_after(current, policy)
        ):
            groups.append(current)
            current = [item]
        else:
            current.append(item)
    if current:
        groups.append(current)
    return groups


def _prefers_break_after(
    group: list[tuple[TranscriptWord, TimeRange]],
    policy: SegmentationPolicy,
) -> bool:
    """Prefere encerrar a cue em fim de frase quando ela já tem massa de texto."""
    text = _text_of(group)
    if len(text) < policy.sentence_break_ratio * policy.max_chars_per_cue:
        return False
    return text.endswith(_SENTENCE_ENDINGS)


def _refine_for_reading_speed(
    groups: list[list[tuple[TranscriptWord, TimeRange]]],
    policy: SegmentationPolicy,
) -> list[list[tuple[TranscriptWord, TimeRange]]]:
    """Subdivide grupos que não cabem no tempo real de fala disponível.

    O corte reaproveita os timestamps das próprias palavras: nenhuma parte
    recebe tempo que a fala não ocupou.
    """
    refined: list[list[tuple[TranscriptWord, TimeRange]]] = []
    for group in groups:
        refined.extend(_split_group_by_reading_speed(group, policy, depth=0))
    return refined


def _split_group_by_reading_speed(
    group: list[tuple[TranscriptWord, TimeRange]],
    policy: SegmentationPolicy,
    *,
    depth: int,
) -> list[list[tuple[TranscriptWord, TimeRange]]]:
    if depth >= MAX_SPLIT_DEPTH or len(group) < 2 * policy.min_words_per_split_part:
        return [group]
    window = TimeRange(start=group[0][1].start, end=group[-1][1].end)
    if window.duration >= policy.reading_time(_text_of(group)):
        return [group]
    index = _split_index(group, policy)
    if index is None:
        return [group]
    return [
        *_split_group_by_reading_speed(group[:index], policy, depth=depth + 1),
        *_split_group_by_reading_speed(group[index:], policy, depth=depth + 1),
    ]


def _split_index(
    group: list[tuple[TranscriptWord, TimeRange]],
    policy: SegmentationPolicy,
) -> int | None:
    """Melhor ponto de corte: elimina overflow e prefere pausa sintática."""
    best_key: tuple[int, int, float, int] | None = None
    best_index: int | None = None
    first = policy.min_words_per_split_part
    last = len(group) - policy.min_words_per_split_part + 1
    for index in range(first, last):
        left, right = group[:index], group[index:]
        left_text, right_text = _text_of(left), _text_of(right)
        if (
            len(left_text) > policy.max_chars_per_cue
            or len(right_text) > policy.max_chars_per_cue
        ):
            continue
        worst = max(
            _reading_ratio(left, left_text, policy),
            _reading_ratio(right, right_text, policy),
        )
        key = (
            0 if worst <= 1.0 else 1,
            0 if left_text.endswith(_CLAUSE_ENDINGS) else 1,
            round(worst, 4),
            abs(len(left_text) - len(right_text)),
        )
        if best_key is None or key < best_key:
            best_key = key
            best_index = index
    return best_index


def _reading_ratio(
    part: list[tuple[TranscriptWord, TimeRange]],
    text: str,
    policy: SegmentationPolicy,
) -> float:
    window = TimeRange(start=part[0][1].start, end=part[-1][1].end)
    return policy.reading_time(text) / window.duration


def _text_of(words: list[tuple[TranscriptWord, TimeRange]]) -> str:
    return " ".join(word.text.strip() for word, _ in words).strip()
