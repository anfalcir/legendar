"""Testes da segmentação: agrupamento por pausa, perdas explícitas e não sobreposição."""

from __future__ import annotations

import pytest

from legendar.application.pipeline.segmentation import (
    SegmentationPolicy,
    segment_alignment,
)
from legendar.domain.entities.transcript import (
    AlignmentDiagnostics,
    AlignmentResult,
    Transcript,
    TranscriptSegment,
    TranscriptWord,
)
from legendar.domain.value_objects.language import Language
from legendar.domain.value_objects.time import TimeRange


def _word(text: str, start: float, end: float) -> TranscriptWord:
    return TranscriptWord(text=text, range=TimeRange(start, end))


def _alignment(*segments: TranscriptSegment) -> AlignmentResult:
    transcript = Transcript(
        segments=segments, language=Language.PORTUGUESE, model_name="tiny"
    )
    aligned = sum(len(segment.words) for segment in segments)
    return AlignmentResult(
        transcript=transcript, diagnostics=AlignmentDiagnostics(aligned_words=aligned)
    )


def _segment(*words: TranscriptWord) -> TranscriptSegment:
    text = " ".join(word.text for word in words)
    start = words[0].range.start
    end = words[-1].range.end
    return TranscriptSegment(text=text, range=TimeRange(start, end), words=words)


def test_pause_larger_than_gap_splits_cues():
    segment = _segment(
        _word("bom", 0.0, 0.4), _word("dia", 0.5, 0.9), _word("tudo", 2.0, 2.4)
    )
    result = segment_alignment(_alignment(segment))

    assert result.cue_count == 2
    assert [cue.text for cue in result.track.cues] == ["bom dia", "tudo"]


def test_continuous_speech_stays_in_one_cue():
    segment = _segment(_word("olá", 0.0, 0.4), _word("mundo", 0.45, 0.9))
    result = segment_alignment(_alignment(segment))

    assert result.cue_count == 1
    assert result.is_lossless


def test_segment_without_words_uses_its_own_range():
    segment = TranscriptSegment(text="texto sem palavras", range=TimeRange(0.0, 2.0))
    result = segment_alignment(_alignment(segment))

    assert result.cue_count == 1
    assert result.track.cues[0].range == TimeRange(0.0, 2.0)
    assert result.dropped_segments == ()
    assert result.is_lossless


def test_unmatched_words_are_explicit_and_make_result_lossy():
    aligned = _segment(_word("olá", 0.0, 0.4))
    unmatched = TranscriptWord(text="mundo")
    transcript = Transcript(
        segments=(
            TranscriptSegment(
                text="olá mundo",
                range=TimeRange(0.0, 1.0),
                words=(aligned.words[0], unmatched),
            ),
        ),
        language=Language.PORTUGUESE,
        model_name="tiny",
    )
    alignment = AlignmentResult(
        transcript=transcript,
        diagnostics=AlignmentDiagnostics(
            aligned_words=1,
            unmatched_words=(unmatched,),
            issues=("unmatched_word",),
        ),
    )

    result = segment_alignment(alignment)

    assert result.has_unmatched_words
    assert result.unmatched_words == (unmatched,)
    assert not result.is_lossless
    assert "unmatched_word" in result.diagnostics


def test_segment_without_words_or_range_is_dropped():
    segment = TranscriptSegment(text="sem tempo")
    result = segment_alignment(_alignment(segment))

    assert result.track.is_empty
    assert result.dropped_segments == (0,)
    assert "dropped_segment" in result.diagnostics
    assert result.coverage_ratio == pytest.approx(0.0)


def test_overlapping_segments_are_clipped_not_duplicated():
    first = TranscriptSegment(text="primeiro", range=TimeRange(0.0, 2.0))
    second = TranscriptSegment(text="segundo", range=TimeRange(1.0, 3.0))
    result = segment_alignment(_alignment(first, second))

    starts = [cue.range.start for cue in result.track.cues]
    ends = [cue.range.end for cue in result.track.cues]
    assert starts == sorted(starts)
    assert all(end <= start for end, start in zip(ends, starts[1:], strict=False))


def test_short_cue_is_reported():
    segment = _segment(_word("oi", 0.0, 0.2))
    result = segment_alignment(_alignment(segment))

    assert result.short_cues == (1,)
    assert "short_cue" in result.diagnostics


def test_reading_speed_overflow_is_reported():
    segment = _segment(_word("a" * 80, 0.0, 1.0))
    result = segment_alignment(_alignment(segment))

    assert result.overflow_cues == (1,)
    assert "reading_speed_overflow" in result.diagnostics


def test_policy_rejects_incoherent_durations():
    from legendar.domain.errors.catalog import SrtValidationError

    with pytest.raises(SrtValidationError):
        SegmentationPolicy(min_cue_duration=5.0, max_cue_duration=1.0)


def test_default_policy_targets_two_lines_and_reading_speed():
    policy = SegmentationPolicy()

    assert policy.max_chars_per_line == 42
    assert policy.max_lines == 2
    assert policy.max_chars_per_cue == 84
    assert policy.min_cue_duration == 1.0
    assert policy.max_cue_duration == 7.0
    assert policy.chars_per_second == 17.0
    assert policy.reading_time("a" * 34) == pytest.approx(2.0)


def test_policy_rejects_invalid_editorial_parameters():
    from legendar.domain.errors.catalog import SrtValidationError

    with pytest.raises(SrtValidationError, match="Largura de linha"):
        SegmentationPolicy(max_chars_per_line=10)
    with pytest.raises(SrtValidationError, match="ao menos uma linha"):
        SegmentationPolicy(max_lines=0)
    with pytest.raises(SrtValidationError, match="caracteres por cue muito baixo"):
        SegmentationPolicy(max_chars_per_cue=10)
    with pytest.raises(SrtValidationError, match="excede a capacidade"):
        SegmentationPolicy(max_chars_per_line=42, max_lines=2, max_chars_per_cue=100)
    with pytest.raises(SrtValidationError, match="Velocidade de leitura"):
        SegmentationPolicy(chars_per_second=0)
    with pytest.raises(SrtValidationError, match="Proporção de quebra"):
        SegmentationPolicy(sentence_break_ratio=1.5)
    with pytest.raises(SrtValidationError, match="ao menos uma palavra"):
        SegmentationPolicy(min_words_per_split_part=0)


def _fast_speech_segment(count: int = 8) -> TranscriptSegment:
    """Fala rápida: ~3,3 palavras/s com palavras de 7 caracteres."""
    words = tuple(
        _word("palavra", index * 0.3, index * 0.3 + 0.25) for index in range(count)
    )
    return _segment(*words)


def test_fast_speech_is_split_into_shorter_cues():
    segment = _fast_speech_segment()
    result = segment_alignment(_alignment(segment))

    assert result.cue_count > 1
    assert "reading_speed_split" in result.diagnostics
    assert " ".join(cue.text for cue in result.track.cues) == segment.text


def test_split_cues_reuse_word_timestamps_only():
    segment = _fast_speech_segment()
    boundaries = {
        boundary
        for word in segment.words
        for boundary in (word.range.start, word.range.end)
    }

    result = segment_alignment(_alignment(segment))

    for cue in result.track.cues:
        assert cue.range.start in boundaries
        assert cue.range.end in boundaries
        assert segment.range.start <= cue.range.start < cue.range.end
        assert cue.range.end <= segment.range.end


def test_split_cues_do_not_overlap_or_leave_gaps_between_words():
    segment = _fast_speech_segment()
    result = segment_alignment(_alignment(segment))

    cues = result.track.cues
    for previous, current in zip(cues, cues[1:], strict=False):
        assert current.range.start >= previous.range.end


def test_slow_speech_keeps_a_single_cue_without_split_diagnostic():
    segment = _segment(
        _word("bom", 0.0, 0.5), _word("dia", 0.9, 1.4), _word("a", 1.8, 2.0)
    )
    result = segment_alignment(_alignment(segment))

    assert result.cue_count == 1
    assert "reading_speed_split" not in result.diagnostics


def test_single_line_policy_produces_shorter_cues():
    words = tuple(
        _word("palavra", index * 0.8, index * 0.8 + 0.5) for index in range(10)
    )
    segment = _segment(*words)
    policy = SegmentationPolicy(max_lines=1, max_chars_per_cue=42)

    result = segment_alignment(_alignment(segment), policy=policy)

    assert result.cue_count > 1
    assert all(len(cue.text) <= 42 for cue in result.track.cues)


def test_cues_never_exceed_the_character_limit_per_cue():
    words = tuple(
        _word("palavra", index * 0.9, index * 0.9 + 0.6) for index in range(20)
    )
    segment = _segment(*words)

    result = segment_alignment(_alignment(segment))

    assert all(len(cue.text) <= 84 for cue in result.track.cues)


def test_continuous_speech_merges_across_asr_segment_boundaries():
    first = _segment(_word("esta", 0.0, 0.3), _word("é", 0.31, 0.45))
    second = _segment(_word("uma", 0.46, 0.7), _word("frase.", 0.71, 1.1))

    result = segment_alignment(_alignment(first, second))

    assert result.cue_count == 1
    cue = result.track.cues[0]
    assert cue.text == "esta é uma frase."
    assert cue.source_segments == (0, 1)
    assert "cross_segment_merge" in result.diagnostics


def test_global_stream_keeps_pause_as_boundary_across_segments():
    first = _segment(_word("primeira", 0.0, 0.4), _word("parte.", 0.41, 0.8))
    second = _segment(_word("segunda", 2.0, 2.4), _word("parte.", 2.41, 2.8))

    result = segment_alignment(_alignment(first, second))

    assert [cue.text for cue in result.track.cues] == [
        "primeira parte.",
        "segunda parte.",
    ]
    assert [cue.source_segments for cue in result.track.cues] == [(0,), (1,)]


def test_global_stream_preserves_all_source_segments_when_split():
    first = _segment(_word("palavra", 0.0, 0.25), _word("palavra", 0.3, 0.55))
    second = _segment(_word("palavra", 0.6, 0.85), _word("palavra", 0.9, 1.15))

    result = segment_alignment(_alignment(first, second))

    assert " ".join(cue.text for cue in result.track.cues) == (
        "palavra palavra palavra palavra"
    )
    source_segments = {
        source for cue in result.track.cues for source in cue.source_segments
    }
    assert source_segments == {0, 1}


def test_global_stream_rejects_non_chronological_aligned_words():
    first = _segment(_word("primeiro", 1.0, 1.3))
    second = _segment(_word("segundo", 0.5, 0.8))

    from legendar.domain.errors.catalog import SrtValidationError

    with pytest.raises(SrtValidationError, match="ordem cronológica"):
        segment_alignment(_alignment(first, second))


def test_short_cue_extends_only_into_silence_before_next_cue():
    first = _segment(_word("oi", 0.0, 0.2))
    second = _segment(_word("tudo", 2.0, 2.4))

    result = segment_alignment(_alignment(first, second))

    first_cue, second_cue = result.track.cues
    assert first_cue.range.start == pytest.approx(0.0)
    assert first_cue.range.end == pytest.approx(1.0)
    assert second_cue.range.start == pytest.approx(2.0)
    assert first_cue.range.end < second_cue.range.start


def test_short_final_cue_is_not_extended_without_silence_evidence():
    segment = _segment(_word("oi", 0.0, 0.2))

    result = segment_alignment(_alignment(segment))

    assert result.track.cues[0].range == TimeRange(0.0, 0.2)
    assert result.short_cues == (1,)


def test_short_cue_uses_available_silence_to_reach_reading_time():
    first = _segment(_word("texto", 0.0, 0.2), _word("mais", 0.21, 0.4))
    second = _segment(_word("próxima", 2.0, 2.4))

    result = segment_alignment(_alignment(first, second))

    first_cue = result.track.cues[0]
    assert first_cue.range.duration >= len(first_cue.text) / 17.0
    assert first_cue.range.end <= second.range.start - 0.08


def test_meaningful_short_sentence_boundary_is_not_merged_with_next_sentence():
    first = _segment(
        _word("Isso", 0.0, 0.25),
        _word("é", 0.3, 0.45),
        _word("muito", 0.5, 0.8),
        _word("bom.", 0.85, 1.2),
    )
    second = _segment(
        _word("Agora", 1.3, 1.65),
        _word("vamos", 1.7, 2.0),
        _word("seguir.", 2.05, 2.4),
    )

    result = segment_alignment(_alignment(first, second))

    assert [cue.text for cue in result.track.cues] == [
        "Isso é muito bom.",
        "Agora vamos seguir.",
    ]


def test_global_stream_rejects_out_of_order_fallback_segment_ranges():
    aligned = _segment(_word("primeiro", 2.0, 2.3))
    fallback = TranscriptSegment(text="segundo", range=TimeRange(1.0, 1.5))

    from legendar.domain.errors.catalog import SrtValidationError

    with pytest.raises(SrtValidationError, match="Segmentos.*ordem cronológica"):
        segment_alignment(_alignment(aligned, fallback))


def test_fallback_segment_is_preserved_and_blocks_cross_segment_grouping():
    first = _segment(_word("antes", 0.0, 0.3))
    fallback = TranscriptSegment(text="intermediário", range=TimeRange(0.5, 0.8))
    last = _segment(_word("depois", 1.0, 1.3))

    result = segment_alignment(_alignment(first, fallback, last))

    assert [cue.text for cue in result.track.cues] == [
        "antes",
        "intermediário",
        "depois",
    ]
    assert [cue.source_segments for cue in result.track.cues] == [
        (0,),
        (1,),
        (2,),
    ]
    assert result.dropped_segments == ()
