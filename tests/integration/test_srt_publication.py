"""Testes de integração do SRT: formato, round-trip, escrita atômica e publicação."""

from __future__ import annotations

from pathlib import Path

import pytest

from legendar.domain.entities.subtitle import SubtitleCue, SubtitleTrack
from legendar.domain.errors.catalog import SrtValidationError
from legendar.domain.value_objects.language import Language
from legendar.domain.value_objects.time import TimeRange
from legendar.infrastructure.filesystem.atomic import atomic_write_text
from legendar.infrastructure.filesystem.publisher import SrtPublisher
from legendar.infrastructure.filesystem.srt import (
    format_srt,
    format_timestamp,
    parse_srt,
    parse_timestamp,
    validate_roundtrip,
)


def _track(*, language: Language = Language.PORTUGUESE) -> SubtitleTrack:
    cues = (
        SubtitleCue(
            index=1,
            text="Olá, mundo!",
            range=TimeRange(0.0, 1.5),
            language=language,
        ),
        SubtitleCue(
            index=2,
            text="Segunda legenda",
            range=TimeRange(2.0, 4.25),
            language=language,
        ),
    )
    return SubtitleTrack(language=language, cues=cues)


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0.0, "00:00:00,000"),
        (1.5, "00:00:01,500"),
        (61.25, "00:01:01,250"),
        (3723.999, "01:02:03,999"),
    ],
)
def test_format_timestamp(seconds: float, expected: str):
    assert format_timestamp(seconds) == expected


def test_timestamp_roundtrip():
    assert parse_timestamp(format_timestamp(83.4)) == pytest.approx(83.4)


def test_negative_timestamp_is_rejected():
    with pytest.raises(SrtValidationError):
        format_timestamp(-1.0)


def test_invalid_timestamp_is_rejected():
    with pytest.raises(SrtValidationError):
        parse_timestamp("00:00:61,000")


def test_format_and_parse_roundtrip():
    track = _track()
    content = format_srt(track)
    parsed = parse_srt(content)

    assert [cue.index for cue in parsed] == [1, 2]
    assert [cue.text for cue in parsed] == ["Olá, mundo!", "Segunda legenda"]
    assert parsed[1].range == TimeRange(2.0, 4.25)


def test_validate_roundtrip_detects_tampering():
    track = _track()
    content = format_srt(track).replace("Segunda legenda", "Alterada")
    with pytest.raises(SrtValidationError):
        validate_roundtrip(track, content)


def test_atomic_write_leaves_no_partial_files(tmp_path: Path):
    destination = tmp_path / "out.srt"
    atomic_write_text(destination, "conteúdo")

    assert destination.read_text(encoding="utf-8") == "conteúdo"
    assert [path.name for path in tmp_path.iterdir()] == ["out.srt"]


def test_atomic_write_overwrites_previous_file(tmp_path: Path):
    destination = tmp_path / "out.srt"
    destination.write_text("antigo", encoding="utf-8")
    atomic_write_text(destination, "novo")
    assert destination.read_text(encoding="utf-8") == "novo"


def test_publisher_writes_valid_srt(tmp_path: Path):
    destination = tmp_path / "saida.srt"
    SrtPublisher().publish(_track(), str(destination))

    content = destination.read_text(encoding="utf-8")
    assert content.startswith("1\n00:00:00,000 --> 00:00:01,500\nOlá, mundo!\n")
    assert parse_srt(content)[1].text == "Segunda legenda"


def test_publisher_never_writes_partial_on_validation_error(tmp_path: Path):
    destination = tmp_path / "saida.srt"
    empty = SubtitleTrack(language=Language.PORTUGUESE, cues=())
    with pytest.raises(SrtValidationError):
        SrtPublisher().publish(empty, str(destination))
    assert not destination.exists()


LONG_TEXT = (
    "A segmentação precisa respeitar o tempo real de fala sem inventar timestamps."
)


def _long_track(text: str = LONG_TEXT) -> SubtitleTrack:
    return SubtitleTrack(
        language=Language.PORTUGUESE,
        cues=(
            SubtitleCue(
                index=1,
                text=text,
                range=TimeRange(0.0, 6.0),
                language=Language.PORTUGUESE,
            ),
        ),
    )


def test_format_wraps_a_long_cue_in_two_lines():
    content = format_srt(_long_track())

    lines = content.strip("\n").split("\n")
    assert lines[0] == "1"
    assert lines[1] == "00:00:00,000 --> 00:00:06,000"
    body = lines[2:]
    assert len(body) == 2
    assert all(len(line) <= 42 for line in body)
    assert " ".join(body) == LONG_TEXT


def test_format_keeps_every_word_when_the_text_overflows_two_lines():
    text = " ".join(["palavra"] * 20)

    content = format_srt(_long_track(text))

    body = content.strip("\n").split("\n")[2:]
    assert len(body) == 2
    assert " ".join(body).split() == text.split()


def test_format_can_be_limited_to_a_single_line():
    content = format_srt(_long_track(), max_lines=1)

    body = content.strip("\n").split("\n")[2:]
    assert len(body) == 1
    assert body[0].split() == LONG_TEXT.split()


def test_wrapped_srt_still_validates_as_a_roundtrip():
    track = _long_track()

    validate_roundtrip(track, format_srt(track))


def test_publisher_writes_two_line_cues_that_read_back_intact(tmp_path: Path):
    destination = tmp_path / "saida.srt"
    track = _long_track()

    SrtPublisher().publish(track, str(destination))

    content = destination.read_text(encoding="utf-8")
    body = content.strip("\n").split("\n")[2:]
    assert len(body) == 2
    parsed = parse_srt(content)
    assert parsed[0].index == 1
    assert " ".join(parsed[0].text.split()) == LONG_TEXT
