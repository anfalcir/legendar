"""Janela principal da Fase 1: escolher mídia, acompanhar e cancelar o job.

A janela não conhece ffmpeg, WhisperX, PyTorch nem o cache de modelos. Ela
recebe fábricas já compostas pelo ``bootstrap`` e conversa com o núcleo apenas
por ``JobRequest``, ``JobController``, eventos de domínio e um ``WorkspaceFactory``.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from legendar.application.job.context import JobContext
from legendar.application.pipeline.serial_pipeline import JobRequest, SerialPipeline
from legendar.application.ports.protocols import WorkspaceFactory
from legendar.domain.entities.media import MediaKind, MediaSource
from legendar.domain.errors.base import DomainError
from legendar.domain.errors.catalog import InvalidInputError
from legendar.domain.events.job_events import JobEvent
from legendar.domain.value_objects.language import Language
from legendar.presentation.qt.view_model.job_view_model import (
    JobViewModel,
    JobViewSnapshot,
)
from legendar.presentation.qt.workers.job_worker import JobWorker

PipelineFactory = Callable[[], SerialPipeline]
OutputPathFactory = Callable[[str, Language], Path]

_MEDIA_FILTER = (
    "Mídia (*.mp4 *.mkv *.mov *.webm *.m4a *.mp3 *.wav *.flac *.ogg *.opus *.aac);;"
    "Todos os arquivos (*)"
)
_SRT_FILTER = "Legenda SRT (*.srt)"
_CLOSE_WAIT_MS = 5000


@dataclass(frozen=True, slots=True)
class UiDependencies:
    """Tudo o que a janela precisa, já montado pelo bootstrap.

    Nenhum valor aqui importa ``infrastructure``: o que é concreto fica
    escondido atrás de ``WorkspaceFactory`` e das fábricas.
    """

    output_dir: Path
    cache_dir: Path
    workspace_factory: WorkspaceFactory
    pipeline_factory: PipelineFactory
    output_path_factory: OutputPathFactory
    translate_available: bool = False
    readiness_ok: bool = True
    readiness_details: tuple[str, ...] = ()
    app_version: str = ""


class MainWindow(QMainWindow):
    """Tela única da Fase 1, sem lógica de pipeline e sem I/O de mídia."""

    def __init__(
        self, dependencies: UiDependencies, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._deps = dependencies
        self._view_model = JobViewModel()
        self._thread: QThread | None = None
        self._worker: JobWorker | None = None
        self._context: JobContext | None = None
        self._output_touched = False

        self.setWindowTitle("Legendar")
        self.resize(780, 640)
        self._build_ui()
        self._wire_signals()
        self._sync_translation_controls()
        self._render(self._view_model.snapshot)

    # -- API de leitura para testes e bootstrap ---------------------------

    @property
    def is_running(self) -> bool:
        return self._thread is not None

    @property
    def view_model(self) -> JobViewModel:
        return self._view_model

    # -- construção da UI -------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget(self)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)
        root.addWidget(self._build_input_group())
        root.addWidget(self._build_language_group())
        root.addLayout(self._build_actions())
        root.addWidget(self._build_progress_group())
        root.addWidget(self._build_log_group(), stretch=1)
        root.addWidget(self._build_readiness_label())
        self.setCentralWidget(central)
        self.statusBar().showMessage(f"Legendar {self._deps.app_version}".strip())

    def _build_input_group(self) -> QGroupBox:
        group = QGroupBox("Entrada e saída", self)
        grid = QGridLayout(group)
        grid.setColumnStretch(1, 1)

        self.file_edit = QLineEdit(group)
        self.file_edit.setObjectName("fileEdit")
        self.file_edit.setPlaceholderText("Selecione um arquivo de vídeo ou áudio")
        self.browse_button = QPushButton("Escolher mídia…", group)
        self.browse_button.setObjectName("browseButton")

        self.output_edit = QLineEdit(group)
        self.output_edit.setObjectName("outputEdit")
        self.output_edit.setPlaceholderText("Onde salvar o arquivo .srt")
        self.output_browse_button = QPushButton("Salvar como…", group)
        self.output_browse_button.setObjectName("outputBrowseButton")
        self.output_edit.setText(
            str(self._deps.output_path_factory("legenda", Language.PORTUGUESE))
        )

        grid.addWidget(QLabel("Arquivo de mídia:", group), 0, 0)
        grid.addWidget(self.file_edit, 0, 1)
        grid.addWidget(self.browse_button, 0, 2)
        grid.addWidget(QLabel("Salvar legenda em:", group), 1, 0)
        grid.addWidget(self.output_edit, 1, 1)
        grid.addWidget(self.output_browse_button, 1, 2)
        return group

    def _build_language_group(self) -> QGroupBox:
        group = QGroupBox("Idiomas", self)
        layout = QHBoxLayout(group)

        self.source_combo = QComboBox(group)
        self.source_combo.setObjectName("sourceLanguageCombo")
        self.source_combo.addItem("Detectar automaticamente", None)
        for language in Language:
            self.source_combo.addItem(language.label_pt, language.value)

        self.target_combo = QComboBox(group)
        self.target_combo.setObjectName("targetLanguageCombo")
        for language in Language:
            self.target_combo.addItem(language.label_pt, language.value)
        self.target_combo.setCurrentIndex(
            self.target_combo.findData(Language.PORTUGUESE.value)
        )

        self.translate_check = QCheckBox(
            "Traduzir a fala para o idioma da legenda", group
        )
        self.translate_check.setObjectName("translateCheck")
        self.translate_check.setEnabled(self._deps.translate_available)
        if not self._deps.translate_available:
            self.translate_check.setToolTip(
                "A tradução será habilitada em uma fase posterior."
            )

        layout.addWidget(QLabel("Fala em:", group))
        layout.addWidget(self.source_combo)
        layout.addWidget(QLabel("Legenda em:", group))
        layout.addWidget(self.target_combo)
        layout.addWidget(self.translate_check, stretch=1)
        return group

    def _build_actions(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        self.generate_button = QPushButton("Gerar legenda", self)
        self.generate_button.setObjectName("generateButton")
        self.generate_button.setDefault(True)
        self.cancel_button = QPushButton("Cancelar", self)
        self.cancel_button.setObjectName("cancelButton")
        self.cancel_button.setEnabled(False)
        layout.addStretch(1)
        layout.addWidget(self.cancel_button)
        layout.addWidget(self.generate_button)
        return layout

    def _build_progress_group(self) -> QGroupBox:
        group = QGroupBox("Andamento", self)
        layout = QVBoxLayout(group)
        self.progress_bar = QProgressBar(group)
        self.progress_bar.setObjectName("progressBar")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.status_label = QLabel(group)
        self.status_label.setObjectName("statusLabel")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.status_label)
        return group

    def _build_log_group(self) -> QGroupBox:
        group = QGroupBox("Detalhes", self)
        layout = QVBoxLayout(group)
        self.log_view = QPlainTextEdit(group)
        self.log_view.setObjectName("logView")
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(500)
        self.log_view.setPlaceholderText("Os detalhes do processamento aparecem aqui.")
        layout.addWidget(self.log_view)
        return group

    def _build_readiness_label(self) -> QLabel:
        self.readiness_label = QLabel(self)
        self.readiness_label.setObjectName("readinessLabel")
        self.readiness_label.setWordWrap(True)
        if self._deps.readiness_ok:
            prefix = "Pronto para uso."
        else:
            prefix = "Atenção: o ambiente precisa de ajustes."
        details = " ".join(self._deps.readiness_details)
        self.readiness_label.setText(f"{prefix} {details}".strip())
        return self.readiness_label

    def _wire_signals(self) -> None:
        self.browse_button.clicked.connect(self._choose_file)
        self.output_browse_button.clicked.connect(self._choose_output)
        self.output_edit.textEdited.connect(self._on_output_edited)
        self.file_edit.textEdited.connect(self._on_file_edited)
        self.source_combo.currentIndexChanged.connect(self._on_language_changed)
        self.target_combo.currentIndexChanged.connect(self._on_language_changed)
        self.translate_check.toggled.connect(self._on_translate_toggled)
        self.generate_button.clicked.connect(self._start_job)
        self.cancel_button.clicked.connect(self._cancel_job)

    # -- ações de entrada -------------------------------------------------

    def _choose_file(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self, "Selecionar mídia", str(Path.home()), _MEDIA_FILTER
        )
        if selected:
            self.file_edit.setText(selected)
            self._suggest_output(Path(selected))

    def _choose_output(self) -> None:
        current = self.output_edit.text() or str(self._deps.output_dir)
        selected, _ = QFileDialog.getSaveFileName(
            self, "Salvar legenda", current, _SRT_FILTER
        )
        if selected:
            self.output_edit.setText(selected)
            self._output_touched = True

    def _on_file_edited(self, text: str) -> None:
        if text.strip():
            self._suggest_output(Path(text.strip()))

    def _suggest_output(self, source_path: Path) -> None:
        if self._output_touched:
            return
        try:
            suggestion = self._deps.output_path_factory(
                source_path.stem, self._target_language()
            )
        except (OSError, ValueError):
            return
        self.output_edit.setText(str(suggestion))

    def _on_output_edited(self, _text: str) -> None:
        self._output_touched = True

    def _on_language_changed(self, _index: int) -> None:
        self._sync_translation_controls()

    def _on_translate_toggled(self, _checked: bool) -> None:
        self._sync_translation_controls()

    def _sync_translation_controls(self) -> None:
        translating = (
            self.translate_check.isChecked() and self._deps.translate_available
        )
        source = self._source_language()
        if translating:
            self.target_combo.setEnabled(True)
            return
        if source is not None:
            index = self.target_combo.findData(source.value)
            if index >= 0:
                self.target_combo.setCurrentIndex(index)
            self.target_combo.setEnabled(False)
        else:
            self.target_combo.setEnabled(True)

    def _source_language(self) -> Language | None:
        value = self.source_combo.currentData()
        return Language(value) if value is not None else None

    def _target_language(self) -> Language:
        value = self.target_combo.currentData()
        return Language(value) if value is not None else Language.PORTUGUESE

    # -- início, eventos e cancelamento -----------------------------------

    def _build_job(self) -> tuple[JobRequest, JobContext]:
        media_text = self.file_edit.text().strip()
        if not media_text:
            raise InvalidInputError("Selecione um arquivo de mídia.")
        media_path = Path(media_text).expanduser()
        if not media_path.is_file():
            raise InvalidInputError(f"Arquivo de mídia não encontrado: {media_path}")

        output_text = self.output_edit.text().strip()
        if not output_text:
            raise InvalidInputError("Defina onde salvar a legenda.")
        output_path = Path(output_text).expanduser()
        if output_path.suffix.lower() != ".srt":
            output_path = output_path.with_suffix(".srt")
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise InvalidInputError(
                f"Não foi possível criar a pasta de destino: {exc}"
            ) from exc

        source_language, target_language, translate = self._resolved_languages()
        request = JobRequest(
            source=MediaSource(kind=MediaKind.LOCAL_FILE, location=str(media_path)),
            output_language=target_language,
            source_language=source_language,
            translate=translate,
        )
        context = self._deps.workspace_factory.create(
            job_id=uuid.uuid4().hex[:12],
            source_label=media_path.name,
            output_path=output_path,
            cache_dir=self._deps.cache_dir,
        )
        return request, context

    def _resolved_languages(self) -> tuple[Language | None, Language, bool]:
        source = self._source_language()
        target = self._target_language()
        translate = self.translate_check.isChecked() and self._deps.translate_available
        if translate and source is None:
            raise InvalidInputError(
                "Para traduzir, informe também o idioma falado na mídia."
            )
        if translate and source is target:
            raise InvalidInputError(
                "Origem e destino são o mesmo idioma; desmarque a tradução."
            )
        if not translate and source is not None and target is not source:
            raise InvalidInputError(
                "Sem tradução, o idioma da legenda deve ser o mesmo da fala."
            )
        return source, target, translate

    def _start_job(self) -> None:
        if self.is_running:
            return
        try:
            request, context = self._build_job()
        except (DomainError, ValueError) as exc:
            message = exc.message if isinstance(exc, DomainError) else str(exc)
            self._render(self._view_model.report_error(message))
            return

        self._view_model.reset()
        try:
            worker = JobWorker(self._deps.pipeline_factory(), request, context)
        except Exception as exc:  # noqa: BLE001 - fronteira da UI
            self._discard_workspace(context)
            self._render(
                self._view_model.report_error(
                    f"Não foi possível preparar o processamento: {exc}"
                )
            )
            return

        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.event_received.connect(
            self._on_domain_event, Qt.ConnectionType.QueuedConnection
        )
        # ``quit`` precisa acontecer mesmo se a thread da UI estiver bloqueada
        # em ``closeEvent``; chamar direto da thread de trabalho é seguro.
        worker.completed.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        worker.completed.connect(
            self._on_job_finished, Qt.ConnectionType.QueuedConnection
        )
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._on_thread_finished)
        thread.finished.connect(thread.deleteLater)

        self._worker = worker
        self._context = context
        self._thread = thread
        self._render(self._view_model.snapshot)
        thread.start()

    @Slot(object)
    def _on_domain_event(self, event: JobEvent) -> None:
        self._render(self._view_model.apply(event))

    @Slot()
    def _on_job_finished(self) -> None:
        context, self._context = self._context, None
        if context is not None:
            self._discard_workspace(context)
        self._set_inputs_enabled(True)

    @Slot()
    def _on_thread_finished(self) -> None:
        self._thread = None
        self._worker = None
        self._render(self._view_model.snapshot)

    def _cancel_job(self) -> None:
        if self._worker is not None:
            self._worker.request_cancel()
            self.cancel_button.setEnabled(False)
            self.status_label.setText("Cancelando…")

    def _discard_workspace(self, context: JobContext) -> None:
        try:
            self._deps.workspace_factory.cleanup(context)
        except Exception as exc:  # noqa: BLE001 - limpeza não pode derrubar a UI
            self.log_view.appendPlainText(
                f"Aviso: não foi possível limpar o diretório temporário: {exc}"
            )

    # -- desenho ----------------------------------------------------------

    def _render(self, snapshot: JobViewSnapshot) -> None:
        running = snapshot.is_running or self.is_running
        self.progress_bar.setValue(snapshot.progress_percent)
        self.status_label.setText(snapshot.status_text)
        self.log_view.setPlainText("\n".join(snapshot.log_lines))
        scrollbar = self.log_view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        self.generate_button.setEnabled(not running and self._deps.readiness_ok)
        self.cancel_button.setEnabled(snapshot.can_cancel)
        self._set_inputs_enabled(not running)

    def _set_inputs_enabled(self, enabled: bool) -> None:
        self.file_edit.setEnabled(enabled)
        self.browse_button.setEnabled(enabled)
        self.output_edit.setEnabled(enabled)
        self.output_browse_button.setEnabled(enabled)
        self.source_combo.setEnabled(enabled)
        if enabled:
            self._sync_translation_controls()
        else:
            self.target_combo.setEnabled(False)
        self.translate_check.setEnabled(enabled and self._deps.translate_available)

    # -- encerramento -----------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._thread is None:
            super().closeEvent(event)
            return
        if self._worker is not None:
            self._worker.request_cancel()
        if self._thread.wait(_CLOSE_WAIT_MS):
            # A UI thread blocked in wait() cannot process the queued
            # ``completed`` slot; clean the workspace here before closing.
            context, self._context = self._context, None
            if context is not None:
                self._discard_workspace(context)
            super().closeEvent(event)
        else:
            self.status_label.setText(
                "Cancelando… aguarde a etapa atual terminar para fechar."
            )
            event.ignore()
