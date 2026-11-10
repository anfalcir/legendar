from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QSettings

from legendar.domain.value_objects.language import Language
from legendar.presentation.qt.preferences import (
    UiPreferences,
    load_preferences,
    save_preferences,
)


def test_preferences_load_with_safe_defaults(tmp_path: Path) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)

    preferences = load_preferences(settings, tmp_path / "output")

    assert preferences.theme == "system"
    assert preferences.output_dir == tmp_path / "output"
    assert preferences.target_language is Language.PORTUGUESE
    assert preferences.log_expanded is True


def test_preferences_round_trip_without_persisting_media_paths(
    tmp_path: Path,
) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    expected = UiPreferences(
        theme="dark",
        output_dir=tmp_path / "legendas",
        target_language=Language.ENGLISH,
        log_expanded=False,
    )

    save_preferences(settings, expected, geometry=b"geometry-fixture")
    loaded = load_preferences(settings, tmp_path)

    assert loaded == expected
    assert bytes(settings.value("window/geometry")) == b"geometry-fixture"
    assert not settings.contains("media/source_path")
    assert not settings.contains("media/transcript")
    assert not settings.contains("credentials/api_key")


def test_invalid_persisted_values_fall_back_to_safe_defaults(
    tmp_path: Path,
) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.setValue("ui/theme", "neon")
    settings.setValue("ui/target_language", "xx")
    settings.setValue("paths/output_dir", "")
    settings.sync()

    preferences = load_preferences(settings, tmp_path / "safe-output")

    assert preferences.theme == "system"
    assert preferences.target_language is Language.PORTUGUESE
    assert preferences.output_dir == tmp_path / "safe-output"


def test_preferences_reject_unknown_theme(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Tema inválido"):
        UiPreferences(theme="neon", output_dir=tmp_path)
