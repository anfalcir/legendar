"""Testes de objetos de valor: tempo, idioma e mapeamento de linha do tempo."""

from __future__ import annotations

import math

import pytest

from legendar.domain.value_objects.language import (
    Language,
    LanguageError,
    OutputLanguage,
)
from legendar.domain.value_objects.time import TemporalError, TimeRange


def test_time_range_duration_and_overlap():
    first = TimeRange(0.0, 1.0)
    second = TimeRange(0.9, 2.0)
    assert first.duration == pytest.approx(1.0)
    assert first.overlaps(second)


def test_adjacent_ranges_do_not_overlap():
    first = TimeRange(0.0, 1.0)
    second = TimeRange(1.0, 2.0)
    assert not first.overlaps(second)


@pytest.mark.parametrize(
    ("start", "end"),
    [(-0.1, 1.0), (1.0, 1.0), (2.0, 1.0), (math.inf, 2.0), (0.0, math.nan)],
)
def test_invalid_time_ranges_are_rejected(start: float, end: float):
    with pytest.raises(TemporalError):
        TimeRange(start, end)


def test_clamp_preserves_positive_duration():
    clamped = TimeRange(0.5, 3.0).clamp(lower=0.0, upper=2.0)
    assert clamped == TimeRange(0.5, 2.0)


def test_clamp_cannot_collapse_range():
    with pytest.raises(TemporalError):
        TimeRange(0.5, 1.0).clamp(lower=1.0, upper=2.0)


def test_language_parse_normalizes_aliases():
    assert Language.parse("PT-BR") is Language.PORTUGUESE
    assert Language.parse("inglês") is Language.ENGLISH
    assert Language.parse("auto") is None
    assert Language.parse(None) is None


def test_language_parse_rejects_unknown_labels():
    with pytest.raises(LanguageError):
        Language.parse("klingon")


def test_output_language_requires_concrete_language():
    with pytest.raises(LanguageError):
        OutputLanguage(value="pt")  # type: ignore[arg-type]
    assert str(OutputLanguage(Language.PORTUGUESE)) == "pt"



def test_negative_source_offset_maps_positive_local_time_without_negative_global_range():
    from legendar.domain.value_objects.time import TimelineMapping

    mapping = TimelineMapping(source_offset=-0.5)

    assert mapping.range_to_global(TimeRange(0.75, 1.25)) == TimeRange(0.25, 0.75)
    with pytest.raises(TemporalError):
        mapping.range_to_global(TimeRange(0.1, 0.4))
