"""Testes da tradução por cue: unidades 1:1, tempos preservados e falhas claras."""

from __future__ import annotations

import pytest

from legendar.application.pipeline.translation import (
    TranslationContext,
    TranslationResult,
    TranslationUnit,
    apply_translation,
    build_translation_units,
)
from legendar.domain.entities.subtitle import SubtitleCue, SubtitleTrack
from legendar.domain.errors.catalog import InvalidInputError, TranslationError
from legendar.domain.value_objects.language import Language
from legendar.domain.value_objects.time import TimeRange


def _track(*texts: str, language: Language = Language.PORTUGUESE) -> SubtitleTrack:
    cues = tuple(
        SubtitleCue(
            index=position,
            text=text,
            range=TimeRange(start=position - 1.0, end=position - 0.2),
            language=language,
            source_segments=(position - 1,),
        )
        for position, text in enumerate(texts, start=1)
    )
    return SubtitleTrack(language=language, cues=cues)


def test_build_units_preserves_index_order_and_normalized_text() -> None:
    track = _track("  bom   dia ", "tudo bem?")

    units = build_translation_units(track)

    assert [unit.index for unit in units] == [1, 2]
    assert [unit.text for unit in units] == ["bom dia", "tudo bem?"]


def test_build_units_carries_context_and_temporal_source_mapping() -> None:
    track = _track("primeira", "segunda", "terceira", "quarta")

    units = build_translation_units(track)

    assert units[0].source_cue_ids == (1,)
    assert units[0].source_range == track.cues[0].range
    assert units[0].context.before == ()
    assert units[0].context.after == ("segunda", "terceira")
    assert units[2].context.before == ("primeira", "segunda")
    assert units[2].context.after == ("quarta",)
    assert units[2].context.protected_terms == ()


def test_build_units_rejects_empty_track() -> None:
    with pytest.raises(InvalidInputError):
        build_translation_units(SubtitleTrack(language=Language.PORTUGUESE, cues=()))


def test_unit_requires_valid_index_and_text() -> None:
    with pytest.raises(TranslationError):
        TranslationUnit(index=0, text="texto")
    with pytest.raises(TranslationError):
        TranslationUnit(index=1, text="   ")


def test_apply_translation_keeps_ranges_and_switches_language() -> None:
    track = _track("bom dia", "até logo")
    result = TranslationResult(
        language=Language.ENGLISH,
        texts=("good morning", "see you soon"),
        unit_indexes=(1, 2),
    )

    application = apply_translation(track, result)

    assert [cue.text for cue in application.track.cues] == [
        "good morning",
        "see you soon",
    ]
    assert [cue.range for cue in application.track.cues] == [
        cue.range for cue in track.cues
    ]
    assert application.track.language is Language.ENGLISH
    assert all(cue.language is Language.ENGLISH for cue in application.track.cues)
    assert application.track.cues[0].source_segments == (0,)
    assert application.warnings == ()
    assert application.unchanged_cues == ()


def test_apply_translation_normalizes_whitespace_of_model_output() -> None:
    track = _track("bom dia")
    result = TranslationResult(
        language=Language.ENGLISH,
        texts=("  good \n morning ",),
        unit_indexes=(1,),
    )

    application = apply_translation(track, result)

    assert application.track.cues[0].text == "good morning"


def test_apply_translation_rejects_divergent_count() -> None:
    track = _track("um", "dois")
    result = TranslationResult(
        language=Language.ENGLISH, texts=("one",), unit_indexes=(1,)
    )

    with pytest.raises(TranslationError, match="cardinalidade|1:1"):
        apply_translation(track, result)


def test_apply_translation_rejects_mismatched_unit_ids() -> None:
    track = _track("um", "dois")
    result = TranslationResult(
        language=Language.ENGLISH,
        texts=("one", "two"),
        unit_indexes=(2, 1),
    )

    with pytest.raises(TranslationError, match="correspondência por ID"):
        apply_translation(track, result)


def test_apply_translation_rejects_empty_text() -> None:
    track = _track("um")
    result = TranslationResult(
        language=Language.ENGLISH, texts=("   ",), unit_indexes=(1,)
    )

    with pytest.raises(TranslationError, match="vazia"):
        apply_translation(track, result)


def test_apply_translation_rejects_a_fully_unchanged_track() -> None:
    track = _track("bom dia", "até logo")
    result = TranslationResult(
        language=Language.ENGLISH,
        texts=("bom dia", "até logo"),
        unit_indexes=(1, 2),
    )

    with pytest.raises(TranslationError, match="não alterou nenhum texto"):
        apply_translation(track, result)


def test_partially_unchanged_cues_become_a_warning() -> None:
    track = _track("bom dia", "OpenAI", "até logo")
    result = TranslationResult(
        language=Language.ENGLISH,
        texts=("good morning", "OpenAI", "see you soon"),
        unit_indexes=(1, 2, 3),
    )

    application = apply_translation(track, result)

    assert application.unchanged_cues == (2,)
    assert application.warnings == ("1 legenda(s) idêntica(s) ao texto original: 2.",)
    assert application.track.cues[1].text == "OpenAI"


def test_apply_translation_rejects_invalid_result_objects() -> None:
    track = _track("bom dia")

    with pytest.raises(TranslationError, match="Resultado de tradução inválido"):
        apply_translation(track, {"language": Language.ENGLISH, "texts": ("hi",)})
    with pytest.raises(TranslationError, match="Idioma da tradução inválido"):
        apply_translation(
            track,
            TranslationResult(language="en", texts=("hi",), unit_indexes=(1,)),
        )


def test_apply_translation_rejects_empty_track() -> None:
    empty = SubtitleTrack(language=Language.PORTUGUESE, cues=())
    result = TranslationResult(language=Language.ENGLISH, texts=(), unit_indexes=())
    with pytest.raises(InvalidInputError):
        apply_translation(empty, result)
