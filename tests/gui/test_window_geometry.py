"""Geometria da janela: persistência tipada e reencaixe na tela (achado 2)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QByteArray, QSettings, QSize

from legendar.application.pipeline.serial_pipeline import PipelinePorts, SerialPipeline
from legendar.infrastructure.filesystem.workspace import TempWorkspaceFactory
from legendar.presentation.qt.main_window import MainWindow, UiDependencies
from tests.helpers.fakes import (
    FakeAligner,
    FakeAudioPreparer,
    FakeInspector,
    FakePublisher,
    FakeTranscriber,
    make_media_info,
)

pytestmark = pytest.mark.gui


def _dependencies(tmp_path: Path) -> UiDependencies:
    workspace_root = tmp_path / "jobs"
    workspace_root.mkdir(exist_ok=True)
    ports = PipelinePorts(
        inspector=FakeInspector(info=make_media_info()),
        audio_preparer=FakeAudioPreparer(),
        transcriber=FakeTranscriber(),
        aligner=FakeAligner(),
        publisher=FakePublisher(),
    )
    return UiDependencies(
        output_dir=tmp_path,
        cache_dir=tmp_path / "models",
        workspace_factory=TempWorkspaceFactory(workspace_root),
        pipeline_factory=lambda: SerialPipeline(ports),
        output_path_factory=lambda stem, language: tmp_path / f"{stem}.srt",
        app_version="0.1.0",
    )


def _settings(tmp_path: Path) -> QSettings:
    return QSettings(str(tmp_path / "ui-settings.ini"), QSettings.Format.IniFormat)


def test_saved_geometry_is_a_byte_array_and_restores(qtbot, tmp_path) -> None:
    settings = _settings(tmp_path)
    first = MainWindow(_dependencies(tmp_path), settings=settings)
    qtbot.addWidget(first)
    first.resize(760, 640)
    first._save_settings()

    stored = settings.value("window/geometry")
    assert isinstance(stored, QByteArray)

    second = MainWindow(_dependencies(tmp_path), settings=settings)
    qtbot.addWidget(second)
    available = second._available_geometry()

    assert second.size() == QSize(
        min(760, available.width()), min(640, available.height())
    )


def test_unreadable_legacy_geometry_falls_back_to_the_default(qtbot, tmp_path) -> None:
    settings = _settings(tmp_path)
    settings.setValue("window/geometry", b"\x00\x00\x00\x00")
    settings.sync()

    window = MainWindow(_dependencies(tmp_path), settings=settings)
    qtbot.addWidget(window)
    available = window._available_geometry()

    assert window.width() >= window.minimumWidth()
    assert window.width() <= available.width()
    assert window.height() <= available.height()


def test_maximized_state_is_persisted(qtbot, tmp_path) -> None:
    settings = _settings(tmp_path)
    window = MainWindow(_dependencies(tmp_path), settings=settings)
    qtbot.addWidget(window)
    window.showMaximized()
    window._save_settings()

    assert settings.value("window/maximized", False, type=bool) is True


def test_minimum_size_is_derived_from_the_layout(qtbot, tmp_path) -> None:
    window = MainWindow(_dependencies(tmp_path), settings=_settings(tmp_path))
    qtbot.addWidget(window)

    assert window.minimumWidth() <= 760
    assert window.minimumHeight() <= 640
    assert window.minimumWidth() < window.sizeHint().width()
