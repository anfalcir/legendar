from __future__ import annotations

from pathlib import Path

import pytest

from legendar.domain.errors.catalog import SrtValidationError
from legendar.domain.value_objects.language import Language
from legendar.infrastructure.filesystem.srt import read_srt_file


def _srt(*, first_index: int = 7, second_index: int = 19) -> str:
    return (
        f"{first_index}\n"
        "00:00:01,000 --> 00:00:02,500\n"
        "Hello, world!\n\n"
        f"{second_index}\n"
        "00:00:03,000 --> 00:00:04,000\n"
        "We are safe.\n"
    )


def test_read_srt_file_preserves_cue_order_text_and_timestamps(tmp_path: Path) -> None:
    path = tmp_path / "baseline.srt"
    path.write_text(_srt(), encoding="utf-8")

    track, encoding = read_srt_file(path, language=Language.ENGLISH)

    assert encoding == "utf-8"
    assert track.language is Language.ENGLISH
    assert [cue.index for cue in track.cues] == [1, 2]
    assert [cue.text for cue in track.cues] == ["Hello, world!", "We are safe."]
    assert [cue.range.start for cue in track.cues] == [1.0, 3.0]
    assert [cue.range.end for cue in track.cues] == [2.5, 4.0]
    assert all(cue.language is Language.ENGLISH for cue in track.cues)


@pytest.mark.parametrize(
    ("encoding", "expected_encoding"),
    [
        ("utf-8-sig", "utf-8"),
        ("utf-16", "utf-16"),
        ("cp1252", "cp1252"),
    ],
)
def test_read_srt_file_supports_common_subtitle_encodings(
    tmp_path: Path,
    encoding: str,
    expected_encoding: str,
) -> None:
    path = tmp_path / "encoded.srt"
    content = _srt().replace("Hello, world!", "Olá, ação!")
    path.write_bytes(content.encode(encoding))

    track, detected_encoding = read_srt_file(
        path,
        language=Language.PORTUGUESE,
    )

    assert detected_encoding == expected_encoding
    assert track.cues[0].text == "Olá, ação!"


def test_read_srt_file_rejects_missing_and_empty_files(tmp_path: Path) -> None:
    with pytest.raises(SrtValidationError, match="não encontrado"):
        read_srt_file(
            tmp_path / "missing.srt",
            language=Language.ENGLISH,
        )

    empty = tmp_path / "empty.srt"
    empty.write_bytes(b"")
    with pytest.raises(SrtValidationError, match="vazio"):
        read_srt_file(empty, language=Language.ENGLISH)


def test_read_srt_file_rejects_invalid_encoding_without_replacement(tmp_path: Path) -> None:
    path = tmp_path / "invalid.srt"
    path.write_bytes(b"1\n00:00:01,000 --> 00:00:02,000\n\x81\n")

    with pytest.raises(SrtValidationError, match="codificação"):
        read_srt_file(path, language=Language.ENGLISH)


def test_read_srt_file_rejects_overlapping_cues_without_changing_times(
    tmp_path: Path,
) -> None:
    path = tmp_path / "overlap.srt"
    path.write_text(
        "1\n00:00:01,000 --> 00:00:03,000\nFirst.\n\n"
        "2\n00:00:02,000 --> 00:00:04,000\nSecond.\n",
        encoding="utf-8",
    )

    with pytest.raises(SrtValidationError, match="Sobreposição"):
        read_srt_file(path, language=Language.ENGLISH)


def test_read_srt_file_requires_a_declared_language(tmp_path: Path) -> None:
    path = tmp_path / "baseline.srt"
    path.write_text(_srt(), encoding="utf-8")

    with pytest.raises(SrtValidationError, match="idioma conhecido"):
        read_srt_file(path, language="en")
