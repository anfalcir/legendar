"""Testes das entidades de legenda: ordenação, idioma e serialização de texto."""

from __future__ import annotations

import pytest

from legendar.domain.entities.subtitle import SubtitleCue, SubtitleTrack
from legendar.domain.errors.catalog import InvalidInputError, SrtValidationError
from legendar.domain.value_objects.language import Language
from legendar.domain.value_objects.time import TimeRange


def _cue(
    index: int, start: float, language: Language = Language.PORTUGUESE
) -> SubtitleCue:
    return SubtitleCue(
        index=index,
        text=f"texto {index}",
        range=TimeRange(start, start + 1.0),
        language=language,
    )


def test_cue_normalizes_whitespace_and_newlines():
    cue = SubtitleCue(
        index=1,
        text="  uma   linha\nquebrada  ",
        range=TimeRange(0.0, 1.0),
        language=Language.PORTUGUESE,
    )
    assert cue.normalized_text == "uma linha quebrada"


@pytest.mark.parametrize("index", [0, -1])
def test_cue_index_starts_at_one(index: int):
    with pytest.raises(InvalidInputError):
        _cue(index, 0.0)


def test_cue_rejects_blank_text():
    with pytest.raises(InvalidInputError):
        SubtitleCue(
            index=1,
            text="   ",
            range=TimeRange(0.0, 1.0),
            language=Language.PORTUGUESE,
        )


def test_track_requires_sequential_indexes():
    with pytest.raises(SrtValidationError):
        SubtitleTrack(language=Language.PORTUGUESE, cues=(_cue(2, 0.0),))


def test_track_rejects_overlapping_cues():
    first = _cue(1, 0.0)
    overlapping = SubtitleCue(
        index=2,
        text="sobreposta",
        range=TimeRange(0.5, 1.5),
        language=Language.PORTUGUESE,
    )
    with pytest.raises(SrtValidationError):
        SubtitleTrack(language=Language.PORTUGUESE, cues=(first, overlapping))


def test_track_rejects_mixed_languages():
    with pytest.raises(SrtValidationError):
        SubtitleTrack(
            language=Language.PORTUGUESE,
            cues=(_cue(1, 0.0), _cue(2, 1.0, language=Language.ENGLISH)),
        )


def test_empty_track_is_allowed_but_reported():
    track = SubtitleTrack(language=Language.PORTUGUESE, cues=())
    assert track.is_empty
    assert track.duration_covered == 0.0
