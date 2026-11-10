"""Testes de integração da janela com Qt offscreen e pipeline dublê."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from PySide6.QtCore import Qt

from legendar.application.pipeline.serial_pipeline import PipelinePorts, SerialPipeline
from legendar.domain.errors.catalog import MediaToolError
from legendar.domain.state.machine import JobState
from legendar.domain.value_objects.language import Language
from legendar.infrastructure.filesystem.workspace import TempWorkspaceFactory
from legendar.presentation.qt.main_window import MainWindow, UiDependencies
from tests.helpers.fakes import (
    FakeAligner,
    FakeAudioPreparer,
    FakeInspector,
    FakePublisher,
    FakeTranscriber,
    make_media_info,
    make_transcript,
)

pytestmark = pytest.mark.gui


def _ports(**overrides) -> PipelinePorts:
    values = {
        "inspector": FakeInspector(info=make_media_info()),
        "audio_preparer": FakeAudioPreparer(),
        "transcriber": FakeTranscriber(),
        "aligner": FakeAligner(),
        "publisher": FakePublisher(),
    }
    values.update(overrides)
    return PipelinePorts(**values)


def _dependencies(
    tmp_path: Path, pipeline: SerialPipeline | None = None
) -> UiDependencies:
    workspace_root = tmp_path / "jobs"
    workspace_root.mkdir()
    return UiDependencies(
        output_dir=tmp_path,
        cache_dir=tmp_path / "models",
        workspace_factory=TempWorkspaceFactory(workspace_root),
        pipeline_factory=lambda: pipeline or SerialPipeline(_ports()),
        output_path_factory=lambda stem, language: (
            tmp_path / f"{stem}.{language.value}.srt"
        ),
        translate_available=False,
        readiness_ok=True,
        readiness_details=("ffmpeg e ffprobe encontrados.",),
        app_version="0.1.0",
    )


@pytest.fixture
def media(tmp_path: Path) -> Path:
    path = tmp_path / "aula.mp4"
    path.write_bytes(b"\x00")
    return path


def _window(qtbot, dependencies: UiDependencies) -> MainWindow:
    window = MainWindow(dependencies)
    qtbot.addWidget(window)
    window.show()
    return window


def test_generate_runs_off_the_ui_thread_and_completes(qtbot, tmp_path, media) -> None:
    window = _window(qtbot, _dependencies(tmp_path))
    window.file_edit.setText(str(media))
    window.output_edit.setText(str(tmp_path / "saida.srt"))

    qtbot.mouseClick(window.generate_button, Qt.MouseButton.LeftButton)

    assert window.is_running
    qtbot.waitUntil(lambda: not window.is_running, timeout=5000)
    snapshot = window.view_model.snapshot
    assert snapshot.state is JobState.COMPLETED
    assert window.progress_bar.value() == 100
    assert snapshot.output_path.endswith("saida.srt")
    assert window.generate_button.isEnabled()
    assert not window.cancel_button.isEnabled()


def test_missing_file_is_reported_without_starting(qtbot, tmp_path) -> None:
    window = _window(qtbot, _dependencies(tmp_path))
    window.file_edit.setText(str(tmp_path / "nao-existe.mp4"))

    qtbot.mouseClick(window.generate_button, Qt.MouseButton.LeftButton)

    assert not window.is_running
    assert "não encontrado" in window.view_model.snapshot.error_message


def test_output_without_srt_suffix_is_normalized(qtbot, tmp_path, media) -> None:
    window = _window(qtbot, _dependencies(tmp_path))
    window.file_edit.setText(str(media))
    window.output_edit.setText(str(tmp_path / "legenda-final"))

    qtbot.mouseClick(window.generate_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not window.is_running, timeout=5000)

    assert window.view_model.snapshot.output_path == str(tmp_path / "legenda-final.srt")


def test_source_language_syncs_target_when_not_translating(
    qtbot, tmp_path, media
) -> None:
    window = _window(qtbot, _dependencies(tmp_path))

    window.source_combo.setCurrentIndex(window.source_combo.findData("en"))

    assert window.target_combo.currentData() == "en"
    assert not window.target_combo.isEnabled()


def test_translation_checkbox_is_disabled_without_translator(qtbot, tmp_path) -> None:
    window = _window(qtbot, _dependencies(tmp_path))

    assert not window.translate_check.isEnabled()


def test_pipeline_failure_is_shown_and_allows_retry(qtbot, tmp_path, media) -> None:
    class BrokenInspector:
        def inspect(self, source):
            raise MediaToolError("ffprobe falhou ao inspecionar a mídia.")

    window = _window(
        qtbot,
        _dependencies(tmp_path, SerialPipeline(_ports(inspector=BrokenInspector()))),
    )
    window.file_edit.setText(str(media))
    window.output_edit.setText(str(tmp_path / "saida.srt"))

    qtbot.mouseClick(window.generate_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not window.is_running, timeout=5000)

    snapshot = window.view_model.snapshot
    assert snapshot.state is JobState.FAILED
    assert "ffprobe" in snapshot.error_message
    assert window.generate_button.isEnabled()


def test_cancel_stops_a_cooperative_pipeline(qtbot, tmp_path, media) -> None:
    class SlowTranscriber:
        def __init__(self) -> None:
            self.started = threading.Event()
            self.release = threading.Event()

        def transcribe(self, audio, *, language=None, progress=None):
            self.started.set()
            self.release.wait(timeout=5)
            return make_transcript(language=Language.PORTUGUESE)

    slow = SlowTranscriber()
    window = _window(
        qtbot, _dependencies(tmp_path, SerialPipeline(_ports(transcriber=slow)))
    )
    window.file_edit.setText(str(media))
    window.output_edit.setText(str(tmp_path / "saida.srt"))
    qtbot.mouseClick(window.generate_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(slow.started.is_set, timeout=5000)

    qtbot.mouseClick(window.cancel_button, Qt.MouseButton.LeftButton)
    slow.release.set()
    qtbot.waitUntil(lambda: not window.is_running, timeout=5000)

    assert window.view_model.snapshot.state is JobState.CANCELLED
