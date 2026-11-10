"""Testes do progresso: monotonicidade e composição por etapas."""

from __future__ import annotations

import pytest

from legendar.application.progress.sink import MonotonicProgress, ScaledProgress
from legendar.domain.errors.catalog import InvalidInputError


def test_progress_never_regresses():
    seen: list[tuple[float, str]] = []
    sink = MonotonicProgress(lambda fraction, message: seen.append((fraction, message)))
    for fraction in (0.2, 0.5, 0.4, 0.9):
        sink.report(fraction, "etapa")
    assert [fraction for fraction, _ in seen] == [0.2, 0.5, 0.9]
    assert sink.value == pytest.approx(0.9)


@pytest.mark.parametrize("fraction", [-0.01, 1.01])
def test_progress_out_of_range_is_rejected(fraction: float):
    with pytest.raises(InvalidInputError):
        MonotonicProgress().report(fraction)


def test_scaled_progress_maps_subrange():
    seen: list[float] = []
    sink = MonotonicProgress(lambda fraction, _message: seen.append(fraction))
    stage = ScaledProgress(sink, 0.2, 0.4)
    stage.report(0.0)
    stage.report(0.5)
    stage.report(1.0)
    assert seen == pytest.approx([0.2, 0.3, 0.4])


def test_scaled_progress_rejects_inverted_range():
    with pytest.raises(InvalidInputError):
        ScaledProgress(MonotonicProgress(), 0.6, 0.2)
