"""Testes de integração da janela com Qt offscreen e pipeline dublê."""

from __future__ import annotations

import threading
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QMessageBox, QScrollArea

from legendar.application.pipeline.serial_pipeline import PipelinePorts, SerialPipeline
from legendar.domain.entities.media import MediaKind
from legendar.domain.errors.catalog import InvalidInputError, MediaToolError
from legendar.domain.events.job_events import (
    JobFailed,
    LogRecorded,
    ProgressReported,
    StateChanged,
)
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
        media_inspector=FakeInspector(info=make_media_info()),
        youtube_available=True,
        youtube_readiness_details=("yt-dlp instalado", "Runtime EJS disponível"),
    )


@pytest.fixture
def media(tmp_path: Path) -> Path:
    path = tmp_path / "aula.mp4"
    path.write_bytes(b"\x00")
    return path


def _window(qtbot, dependencies: UiDependencies, tmp_path: Path) -> MainWindow:
    settings = QSettings(str(tmp_path / "ui-settings.ini"), QSettings.Format.IniFormat)
    window = MainWindow(dependencies, settings=settings)
    # Os testes de fluxo exercitam o job; diálogos modais têm testes próprios.
    window._confirm_start = lambda *_args: True
    window._confirm_cancel = lambda **_kwargs: True
    qtbot.addWidget(window)
    window.show()
    return window


def test_generate_runs_off_the_ui_thread_and_completes(qtbot, tmp_path, media) -> None:
    window = _window(qtbot, _dependencies(tmp_path), tmp_path)
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


def test_start_declined_does_not_create_workspace(qtbot, tmp_path, media) -> None:
    window = _window(qtbot, _dependencies(tmp_path), tmp_path)
    window.file_edit.setText(str(media))
    window.output_edit.setText(str(tmp_path / "saida.srt"))
    window._confirm_start = lambda *_args: False

    window._start_job()

    assert not window.is_running
    assert list((tmp_path / "jobs").iterdir()) == []
    assert window.generate_button.isEnabled()


def test_reentrant_start_confirmation_cannot_create_duplicate_jobs(
    qtbot, tmp_path, media
) -> None:
    calls = 0

    def pipeline_factory():
        nonlocal calls
        calls += 1
        return SerialPipeline(_ports())

    dependencies = _dependencies(tmp_path)
    dependencies = replace(dependencies, pipeline_factory=pipeline_factory)
    window = _window(qtbot, dependencies, tmp_path)
    window.file_edit.setText(str(media))
    window.output_edit.setText(str(tmp_path / "saida.srt"))

    def reentrant_confirmation(*_args):
        window._start_job()
        return True

    window._confirm_start = reentrant_confirmation
    window._start_job()

    assert window.is_running
    assert calls == 1
    assert not window.generate_button.isEnabled()
    qtbot.waitUntil(lambda: not window.is_running, timeout=5000)
    assert calls == 1


def test_existing_output_requires_a_second_explicit_confirmation(
    qtbot, tmp_path, media
) -> None:
    destination = tmp_path / "saida.srt"
    destination.write_text("legenda anterior", encoding="utf-8")
    window = _window(qtbot, _dependencies(tmp_path), tmp_path)
    window.file_edit.setText(str(media))
    window.output_edit.setText(str(destination))
    window._confirm_overwrite = lambda _path: False

    window._start_job()

    assert not window.is_running
    assert destination.read_text(encoding="utf-8") == "legenda anterior"
    assert list((tmp_path / "jobs").iterdir()) == []


def test_cancel_declined_keeps_the_job_running(qtbot, tmp_path, media) -> None:
    class SlowTranscriber:
        def __init__(self) -> None:
            self.started = threading.Event()
            self.release = threading.Event()

        def transcribe(self, audio, *, language=None, progress=None, token=None):
            self.started.set()
            self.release.wait(timeout=5)
            return make_transcript(language=Language.PORTUGUESE)

    slow = SlowTranscriber()
    window = _window(
        qtbot,
        _dependencies(tmp_path, SerialPipeline(_ports(transcriber=slow))),
        tmp_path,
    )
    window.file_edit.setText(str(media))
    window.output_edit.setText(str(tmp_path / "saida.srt"))
    window._confirm_cancel = lambda **_kwargs: False
    qtbot.mouseClick(window.generate_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(slow.started.is_set, timeout=5000)

    window._cancel_job()

    assert window.is_running
    assert window.cancel_button.isEnabled()
    assert not window.file_edit.isEnabled()
    assert not window.output_edit.isEnabled()
    assert not window.source_combo.isEnabled()
    assert not window.preferences_button.isEnabled()
    slow.release.set()
    qtbot.waitUntil(lambda: not window.is_running, timeout=5000)
    assert window.view_model.snapshot.state is JobState.COMPLETED
    assert window.file_edit.isEnabled()
    assert window.output_edit.isEnabled()
    assert window.preferences_button.isEnabled()


def test_cancel_rejection_is_reported_when_pipeline_has_entered_publication(
    qtbot, tmp_path
) -> None:
    window = _window(qtbot, _dependencies(tmp_path), tmp_path)
    window._thread = object()
    window._view_model.apply(
        StateChanged("job-1", 1, previous=JobState.IDLE, current=JobState.TRANSCRIBING)
    )

    class PublishingWorker:
        def request_cancel(self) -> bool:
            return False

    window._worker = PublishingWorker()
    window._confirm_cancel = lambda **_kwargs: True

    window._cancel_job()

    assert window._cancel_pending
    assert not window.cancel_button.isEnabled()
    assert window.cancel_button.text() == "Etapa finalizando…"
    assert "não pode ser cancelada" in window.status_label.text()

    window._worker = None
    window._thread = None
    window._cancel_pending = False


def test_repeated_cancel_requests_are_ignored_after_first_acceptance(
    qtbot, tmp_path, media
) -> None:
    class SlowTranscriber:
        def __init__(self) -> None:
            self.started = threading.Event()
            self.release = threading.Event()

        def transcribe(self, audio, *, language=None, progress=None, token=None):
            self.started.set()
            self.release.wait(timeout=5)
            return make_transcript(language=Language.PORTUGUESE)

    slow = SlowTranscriber()
    window = _window(
        qtbot,
        _dependencies(tmp_path, SerialPipeline(_ports(transcriber=slow))),
        tmp_path,
    )
    window.file_edit.setText(str(media))
    window.output_edit.setText(str(tmp_path / "saida.srt"))
    confirmations = []
    window._confirm_cancel = lambda **_kwargs: confirmations.append(True) or True

    qtbot.mouseClick(window.generate_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(slow.started.is_set, timeout=5000)
    window._cancel_job()
    window._cancel_job()

    assert len(confirmations) == 1
    assert not window.cancel_button.isEnabled()
    slow.release.set()
    qtbot.waitUntil(lambda: not window.is_running, timeout=5000)
    assert window.view_model.snapshot.state is JobState.CANCELLED


def test_progress_is_indeterminate_until_pipeline_reports_a_measurement(
    qtbot, tmp_path
) -> None:
    window = _window(qtbot, _dependencies(tmp_path), tmp_path)
    window._thread = object()
    snapshot = window.view_model.apply(
        StateChanged(
            "job-1", 1, previous=JobState.IDLE, current=JobState.VALIDATING_INPUT
        )
    )
    window._render(snapshot)

    assert window.progress_bar.minimum() == 0
    assert window.progress_bar.maximum() == 0

    snapshot = window.view_model.apply(
        ProgressReported("job-1", 2, fraction=0.4, message="Preparando áudio")
    )
    window._render(snapshot)

    assert window.progress_bar.maximum() == 100
    assert window.progress_bar.value() == 40
    assert window.progress_meta.text() == "40% concluído"
    window._thread = None


def test_keyboard_tab_order_and_accessible_names_are_explicit(qtbot, tmp_path) -> None:
    window = _window(qtbot, _dependencies(tmp_path), tmp_path)

    assert window.file_edit.accessibleName() == "Arquivo ou URL da mídia"
    assert window.generate_button.accessibleName()
    assert window.cancel_button.accessibleName()
    assert window.log_view.accessibleName() == "Registro de atividade do trabalho"
    assert window.readiness_label.accessibleName() == (
        "Estado das ferramentas externas"
    )

    window.file_edit.setFocus()
    qtbot.waitUntil(window.file_edit.hasFocus)
    qtbot.keyClick(window.file_edit, Qt.Key.Key_Tab)
    qtbot.waitUntil(window.browse_button.hasFocus)


def test_destructive_prompts_use_no_as_the_default_choice(
    qtbot, tmp_path, monkeypatch
) -> None:
    window = _window(qtbot, _dependencies(tmp_path), tmp_path)
    del window._confirm_cancel
    calls = {}

    def warning(*args):
        calls["overwrite"] = args
        return QMessageBox.StandardButton.No

    def question(*args):
        calls["cancel"] = args
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "warning", warning)
    monkeypatch.setattr(QMessageBox, "question", question)

    assert not window._confirm_overwrite(tmp_path / "saida.srt")
    assert not window._confirm_cancel()

    assert calls["overwrite"][-1] == QMessageBox.StandardButton.No
    assert calls["cancel"][-1] == QMessageBox.StandardButton.No


def test_activity_panel_can_be_collapsed_and_expanded(qtbot, tmp_path) -> None:
    window = _window(qtbot, _dependencies(tmp_path), tmp_path)

    assert window.log_view.isVisible()
    qtbot.mouseClick(window.log_toggle, Qt.MouseButton.LeftButton)
    assert not window.log_view.isVisible()
    assert window._preferences.log_expanded is False

    qtbot.mouseClick(window.log_toggle, Qt.MouseButton.LeftButton)
    assert window.log_view.isVisible()
    assert window._preferences.log_expanded is True


def test_log_scroll_follows_only_when_the_user_is_at_the_bottom(
    qtbot, tmp_path
) -> None:
    window = _window(qtbot, _dependencies(tmp_path), tmp_path)
    for sequence in range(1, 45):
        window.view_model.apply(
            LogRecorded("job-1", sequence, message=f"atividade {sequence}")
        )
    window._render(window.view_model.snapshot)

    scrollbar = window.log_view.verticalScrollBar()
    assert scrollbar.maximum() > 0

    scrollbar.setValue(0)
    snapshot = window.view_model.apply(
        LogRecorded("job-1", 45, message="nova atividade enquanto lê o histórico")
    )
    window._render(snapshot)
    assert scrollbar.value() == 0

    scrollbar.setValue(scrollbar.maximum())
    snapshot = window.view_model.apply(
        LogRecorded("job-1", 46, message="atividade mais recente")
    )
    window._render(snapshot)
    assert scrollbar.value() == scrollbar.maximum()


def test_narrow_window_keeps_content_in_a_vertical_scroll_area(qtbot, tmp_path) -> None:
    window = _window(qtbot, _dependencies(tmp_path), tmp_path)
    window.resize(680, 620)
    qtbot.wait(20)

    scroll = window.findChild(QScrollArea, "mainScrollArea")
    assert scroll is not None
    assert scroll.widgetResizable()
    assert scroll.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert scroll.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded
    assert window.width() >= window.minimumWidth()


def test_missing_file_is_reported_without_starting(qtbot, tmp_path) -> None:
    window = _window(qtbot, _dependencies(tmp_path), tmp_path)
    window.file_edit.setText(str(tmp_path / "nao-existe.mp4"))

    qtbot.mouseClick(window.generate_button, Qt.MouseButton.LeftButton)

    assert not window.is_running
    assert "não encontrado" in window.view_model.snapshot.error_message


def test_output_without_srt_suffix_is_normalized(qtbot, tmp_path, media) -> None:
    window = _window(qtbot, _dependencies(tmp_path), tmp_path)
    window.file_edit.setText(str(media))
    window.output_edit.setText(str(tmp_path / "legenda-final"))

    qtbot.mouseClick(window.generate_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not window.is_running, timeout=5000)

    assert window.view_model.snapshot.output_path == str(tmp_path / "legenda-final.srt")


def test_output_cannot_overwrite_the_selected_media_file(qtbot, tmp_path) -> None:
    source = tmp_path / "origem.srt"
    source.write_text("conteúdo original", encoding="utf-8")
    window = _window(qtbot, _dependencies(tmp_path), tmp_path)
    window.file_edit.setText(str(source))
    window.output_edit.setText(str(source))

    qtbot.mouseClick(window.generate_button, Qt.MouseButton.LeftButton)

    assert not window.is_running
    assert source.read_text(encoding="utf-8") == "conteúdo original"
    assert "não pode sobrescrever" in window.view_model.snapshot.error_message


def test_output_cannot_be_placed_inside_model_cache(qtbot, tmp_path, media) -> None:
    dependencies = _dependencies(tmp_path)
    dependencies.cache_dir.mkdir()
    window = _window(qtbot, dependencies, tmp_path)
    window.file_edit.setText(str(media))
    destination = dependencies.cache_dir / "saida.srt"
    window.output_edit.setText(str(destination))

    qtbot.mouseClick(window.generate_button, Qt.MouseButton.LeftButton)

    assert not window.is_running
    assert not destination.exists()
    assert "cache de modelos" in window.view_model.snapshot.error_message


def test_progress_indicator_stops_animating_after_terminal_failure(
    qtbot, tmp_path
) -> None:
    window = _window(qtbot, _dependencies(tmp_path), tmp_path)
    window._thread = object()
    snapshot = window.view_model.apply(
        StateChanged(
            "job-1", 1, previous=JobState.IDLE, current=JobState.VALIDATING_INPUT
        )
    )
    window._render(snapshot)
    assert window.progress_bar.maximum() == 0

    snapshot = window.view_model.apply(
        JobFailed("job-1", 2, message="falha de referência")
    )
    window._render(snapshot)

    assert window.progress_bar.maximum() == 100
    assert window.progress_bar.value() == 0
    window._thread = None


def test_source_language_syncs_target_when_not_translating(
    qtbot, tmp_path, media
) -> None:
    window = _window(qtbot, _dependencies(tmp_path), tmp_path)

    window.source_combo.setCurrentIndex(window.source_combo.findData("en"))

    assert window.target_combo.currentData() == "en"
    assert not window.target_combo.isEnabled()


def test_translation_checkbox_is_disabled_without_translator(qtbot, tmp_path) -> None:
    window = _window(qtbot, _dependencies(tmp_path), tmp_path)

    assert not window.translate_check.isEnabled()


def test_pipeline_failure_is_shown_and_allows_retry(qtbot, tmp_path, media) -> None:
    class BrokenInspector:
        def inspect(self, source, *, token=None):
            raise MediaToolError("ffprobe falhou ao inspecionar a mídia.")

    window = _window(
        qtbot,
        _dependencies(tmp_path, SerialPipeline(_ports(inspector=BrokenInspector()))),
        tmp_path,
    )
    window.file_edit.setText(str(media))
    window.output_edit.setText(str(tmp_path / "saida.srt"))

    qtbot.mouseClick(window.generate_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not window.is_running, timeout=5000)

    snapshot = window.view_model.snapshot
    assert snapshot.state is JobState.FAILED
    assert "ffprobe" in snapshot.error_message
    assert window.generate_button.isEnabled()


def test_source_selector_switches_between_local_and_youtube(qtbot, tmp_path) -> None:
    window = _window(qtbot, _dependencies(tmp_path), tmp_path)

    assert window.media_kind_combo.currentData() == "local_file"
    assert window.browse_button.isVisible()
    assert window.inspect_button.isVisible()

    window.media_kind_combo.setCurrentIndex(window.media_kind_combo.findData("youtube"))

    assert not window.browse_button.isVisible()
    assert not window.inspect_button.isVisible()
    assert "youtube.com" in window.file_edit.placeholderText()
    assert not window.stream_combo.isEnabled()

    window.media_kind_combo.setCurrentIndex(
        window.media_kind_combo.findData("local_file")
    )

    assert window.browse_button.isVisible()
    assert window.inspect_button.isVisible()


def test_youtube_job_request_uses_remote_source_and_safe_label(qtbot, tmp_path) -> None:
    window = _window(qtbot, _dependencies(tmp_path), tmp_path)
    window.media_kind_combo.setCurrentIndex(window.media_kind_combo.findData("youtube"))
    window.file_edit.setText("https://www.youtube.com/watch?v=video123")
    window.output_edit.setText(str(tmp_path / "youtube.srt"))

    request, source_label, output_path = window._build_job()

    assert request.source.kind is MediaKind.YOUTUBE
    assert request.source.location.endswith("video123")
    assert request.stream_index is None
    assert source_label == "vídeo do YouTube"
    assert output_path == tmp_path / "youtube.srt"


def test_youtube_job_is_blocked_when_runtime_or_ejs_is_missing(qtbot, tmp_path) -> None:
    dependencies = replace(
        _dependencies(tmp_path),
        youtube_available=False,
        youtube_readiness_details=("yt-dlp não instalado",),
    )
    window = _window(qtbot, dependencies, tmp_path)
    window.media_kind_combo.setCurrentIndex(window.media_kind_combo.findData("youtube"))
    window.file_edit.setText("https://youtu.be/video123")

    with pytest.raises(InvalidInputError, match="suporte ao YouTube"):
        window._build_job()


def test_media_inspection_runs_in_worker_and_exposes_stream_selection(
    qtbot, tmp_path, media
) -> None:
    from legendar.domain.entities.media import AudioStreamInfo

    inspected_threads = []
    original_info = make_media_info()
    default_stream = replace(original_info.audio_streams[0], is_default=True)
    alternate_stream = AudioStreamInfo(
        index=4,
        codec="opus",
        channels=1,
        sample_rate_hz=48_000,
        language="eng",
        title="Comentários",
    )
    info = replace(
        original_info,
        audio_streams=(default_stream, alternate_stream),
    )

    class RecordingInspector:
        def inspect(self, source, *, token=None):
            inspected_threads.append(threading.current_thread())
            if token is not None:
                token.raise_if_cancelled()
            return info

    dependencies = replace(
        _dependencies(tmp_path),
        media_inspector=RecordingInspector(),
    )
    window = _window(qtbot, dependencies, tmp_path)
    window.file_edit.setText(str(media))
    window.output_edit.setText(str(tmp_path / "saida.srt"))

    window._start_media_inspection()

    assert window.is_running
    qtbot.waitUntil(
        lambda: window._inspection_thread is None and window._media_info is not None,
        timeout=5000,
    )

    assert inspected_threads
    assert inspected_threads[0] is not threading.current_thread()
    assert window.stream_combo.count() == 3
    assert window.stream_combo.currentData() == 0
    assert "Comentários" in window.stream_combo.itemText(
        window.stream_combo.findData(4)
    )

    window.stream_combo.setCurrentIndex(window.stream_combo.findData(4))
    request, _label, _output = window._build_job()
    assert request.stream_index == 4


def test_media_inspection_can_be_cancelled_without_blocking_the_window(
    qtbot, tmp_path, media
) -> None:
    class BlockingInspector:
        def __init__(self) -> None:
            self.started = threading.Event()

        def inspect(self, source, *, token=None):
            self.started.set()
            while token is not None and not token.is_cancelled:
                token.raise_if_cancelled()
                threading.Event().wait(0.01)
            token.raise_if_cancelled()
            raise AssertionError("o cancelamento deveria encerrar a inspeção")

    inspector = BlockingInspector()
    dependencies = replace(
        _dependencies(tmp_path),
        media_inspector=inspector,
    )
    window = _window(qtbot, dependencies, tmp_path)
    window.file_edit.setText(str(media))
    window._confirm_cancel = lambda **_kwargs: True

    window._start_media_inspection()
    qtbot.waitUntil(inspector.started.is_set, timeout=5000)
    window._cancel_media_inspection()
    qtbot.waitUntil(lambda: window._inspection_thread is None, timeout=5000)

    assert not window.is_running
    assert window.media_info_label.text() == "Inspeção de mídia cancelada."
    assert window.file_edit.isEnabled()


def test_close_after_thread_wait_cleans_workspace_before_window_exit(
    qtbot, tmp_path, monkeypatch
) -> None:
    from PySide6.QtGui import QCloseEvent

    window = _window(qtbot, _dependencies(tmp_path), tmp_path)
    context = window._deps.workspace_factory.create(
        job_id="close-test",
        source_label="aula.mp4",
        output_path=tmp_path / "aula.srt",
        cache_dir=window._deps.cache_dir,
    )

    class FinishedThread:
        def wait(self, _timeout: int) -> bool:
            return True

    class FakeWorker:
        cancelled = False

        def request_cancel(self) -> None:
            self.cancelled = True

    worker = FakeWorker()
    cleaned = []
    window._thread = FinishedThread()
    window._worker = worker
    window._context = context
    monkeypatch.setattr(window, "_discard_workspace", cleaned.append)

    event = QCloseEvent()
    window.closeEvent(event)

    assert worker.cancelled
    assert cleaned == [context]
    assert window._context is None
    assert event.isAccepted()


def test_cancel_stops_a_cooperative_pipeline(qtbot, tmp_path, media) -> None:
    class SlowTranscriber:
        def __init__(self) -> None:
            self.started = threading.Event()
            self.release = threading.Event()

        def transcribe(self, audio, *, language=None, progress=None, token=None):
            self.started.set()
            self.release.wait(timeout=5)
            return make_transcript(language=Language.PORTUGUESE)

    slow = SlowTranscriber()
    window = _window(
        qtbot,
        _dependencies(tmp_path, SerialPipeline(_ports(transcriber=slow))),
        tmp_path,
    )
    window.file_edit.setText(str(media))
    window.output_edit.setText(str(tmp_path / "saida.srt"))
    qtbot.mouseClick(window.generate_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(slow.started.is_set, timeout=5000)

    qtbot.mouseClick(window.cancel_button, Qt.MouseButton.LeftButton)
    slow.release.set()
    qtbot.waitUntil(lambda: not window.is_running, timeout=5000)

    assert window.view_model.snapshot.state is JobState.CANCELLED


def test_youtube_readiness_also_requires_ffmpeg_and_ffprobe(qtbot, tmp_path) -> None:
    dependencies = replace(
        _dependencies(tmp_path),
        readiness_ok=False,
        readiness_details=("ffmpeg: não encontrado", "ffprobe: não encontrado"),
        youtube_available=True,
    )
    window = _window(qtbot, dependencies, tmp_path)
    window.media_kind_combo.setCurrentIndex(window.media_kind_combo.findData("youtube"))
    window._render(window.view_model.snapshot)

    assert window.status_pill.text() == "Verifique o ambiente"
    assert "YouTube indisponível" in window.readiness_label.text()
    assert "FFmpeg e ffprobe precisam estar instalados" in window.readiness_label.text()



def test_final_generation_stays_disabled_until_srt_publisher_is_available(
    qtbot, tmp_path, media
) -> None:
    dependencies = replace(
        _dependencies(tmp_path),
        publishing_available=False,
        publishing_readiness_details=(
            "O publicador SRT será conectado nas Fases 6/7.",
        ),
    )
    window = _window(qtbot, dependencies, tmp_path)
    window.file_edit.setText(str(media))
    window.output_edit.setText(str(tmp_path / "saida.srt"))

    assert not window.generate_button.isEnabled()
    assert "publicação SRT ainda não foi implementada" in window.readiness_label.text()
    with pytest.raises(InvalidInputError, match="publicação final"):
        window._build_job()
