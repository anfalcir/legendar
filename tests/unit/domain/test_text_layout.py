"""Testes da quebra de linha editorial: duas linhas, sem perder palavras."""

from __future__ import annotations

import pytest

from legendar.domain.entities.subtitle import SubtitleCue
from legendar.domain.errors.catalog import InvalidInputError
from legendar.domain.value_objects.language import Language
from legendar.domain.value_objects.text_layout import (
    DEFAULT_MAX_CHARS_PER_LINE,
    DEFAULT_MAX_LINES,
    wrap_lines,
)
from legendar.domain.value_objects.time import TimeRange

LONG_TEXT = (
    "A segmentação precisa respeitar o tempo real de fala sem inventar timestamps."
)
NUMBERS = [
    "um",
    "dois",
    "tres",
    "quatro",
    "cinco",
    "seis",
    "sete",
    "oito",
    "nove",
    "dez",
    "onze",
    "doze",
]


def test_defaults_match_the_two_line_editorial_target() -> None:
    assert DEFAULT_MAX_CHARS_PER_LINE == 42
    assert DEFAULT_MAX_LINES == 2


def test_empty_text_has_no_lines() -> None:
    assert wrap_lines("   ") == ()


def test_short_text_stays_in_a_single_line() -> None:
    assert wrap_lines("Olá, mundo!") == ("Olá, mundo!",)


def test_long_text_is_split_in_two_balanced_lines() -> None:
    lines = wrap_lines(LONG_TEXT)

    assert len(lines) == 2
    assert all(len(line) <= DEFAULT_MAX_CHARS_PER_LINE for line in lines)
    joined = " ".join(lines)
    assert joined == " ".join(LONG_TEXT.split())


def test_lines_are_balanced_instead_of_greedy() -> None:
    lines = wrap_lines(
        "um dois tres quatro cinco seis sete oito nove dez onze doze",
        max_chars_per_line=30,
        max_lines=3,
    )

    lengths = [len(line) for line in lines]
    assert max(lengths) - min(lengths) <= 12
    assert " ".join(lines).split() == NUMBERS


def test_overflow_keeps_every_word_in_the_last_line() -> None:
    text = " ".join(["palavra"] * 40)
    lines = wrap_lines(text, max_chars_per_line=20, max_lines=2)

    assert len(lines) == 2
    assert " ".join(lines).split() == text.split()


def test_word_wider_than_the_line_occupies_a_line_alone() -> None:
    lines = wrap_lines("incompreensivelmente curto", max_chars_per_line=10)

    assert lines == ("incompreensivelmente", "curto")


def test_single_line_mode_never_returns_more_than_one_line() -> None:
    lines = wrap_lines(LONG_TEXT, max_lines=1)

    assert len(lines) == 1
    assert lines[0].split() == LONG_TEXT.split()


def test_invalid_layout_parameters_are_rejected() -> None:
    with pytest.raises(InvalidInputError):
        wrap_lines("texto", max_chars_per_line=0)
    with pytest.raises(InvalidInputError):
        wrap_lines("texto", max_lines=0)


def test_cue_lines_uses_the_default_policy() -> None:
    cue = SubtitleCue(
        index=1,
        text=LONG_TEXT,
        range=TimeRange(0.0, 6.0),
        language=Language.PORTUGUESE,
    )

    lines = cue.lines()

    assert len(lines) <= DEFAULT_MAX_LINES
    assert [word for line in lines for word in line.split()] == LONG_TEXT.split()


def test_cue_lines_can_be_overridden_per_call() -> None:
    cue = SubtitleCue(
        index=1,
        text="uma frase um pouco maior que a largura curta",
        range=TimeRange(0.0, 3.0),
        language=Language.PORTUGUESE,
    )

    lines = cue.lines(max_chars_per_line=20, max_lines=3)

    assert len(lines) == 3
    assert all(len(line) <= 20 for line in lines)
