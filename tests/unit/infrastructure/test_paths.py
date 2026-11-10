from __future__ import annotations

from pathlib import Path

import pytest

from legendar.infrastructure.filesystem.paths import ensure_directory, unique_path


def test_first_candidate_is_used_when_free(tmp_path: Path) -> None:
    assert unique_path(tmp_path, "legenda", ".srt") == tmp_path / "legenda.srt"


def test_existing_files_are_skipped_in_sequence(tmp_path: Path) -> None:
    (tmp_path / "legenda.srt").touch()
    (tmp_path / "legenda_1.srt").touch()

    assert unique_path(tmp_path, "legenda", ".srt") == tmp_path / "legenda_2.srt"


def test_other_suffixes_do_not_conflict(tmp_path: Path) -> None:
    (tmp_path / "legenda.txt").touch()

    assert unique_path(tmp_path, "legenda", ".srt") == tmp_path / "legenda.srt"


def test_does_not_create_directories_or_files(tmp_path: Path) -> None:
    target = tmp_path / "nao-existe"
    result = unique_path(target, "legenda", ".srt")

    assert result == target / "legenda.srt"
    assert not target.exists()


@pytest.mark.parametrize(
    ("stem", "suffix"),
    [("", ".srt"), ("   ", ".srt"), ("a/b", ".srt"), ("legenda", "srt")],
)
def test_rejects_invalid_arguments(tmp_path: Path, stem: str, suffix: str) -> None:
    with pytest.raises(ValueError):
        unique_path(tmp_path, stem, suffix)


def test_ensure_directory_is_idempotent(tmp_path: Path) -> None:
    target = tmp_path / "a" / "b"

    assert ensure_directory(target) == target
    assert target.is_dir()
    assert ensure_directory(target) == target
