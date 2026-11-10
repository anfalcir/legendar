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
