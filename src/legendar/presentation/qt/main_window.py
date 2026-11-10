"""Janela profissional do Legendar, isolada do processamento de mídia."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSettings, QThread, Qt, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from legendar.application.job.context import JobContext
from legendar.application.pipeline.serial_pipeline import JobRequest, SerialPipeline
from legendar.application.ports.protocols import WorkspaceFactory
from legendar.domain.entities.media import MediaKind, MediaSource
from legendar.domain.errors.base import DomainError
from legendar.domain.errors.catalog import InvalidInputError
from legendar.domain.events.job_events import JobCompleted, JobEvent, JobFailed
from legendar.domain.value_objects.language import Language
from legendar.domain.state.machine import JobState
from legendar.presentation.qt.dialogs import (
    JobConfirmationDialog,
    PreferencesDialog,
)
from legendar.presentation.qt.preferences import (
    UiPreferences,
    load_preferences,
    save_preferences,
)
from legendar.presentation.qt.theme import stylesheet_for
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
    """Dependências da janela, já compostas pelo bootstrap."""

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
    """Interface única com confirmações, preferências e estados visuais explícitos."""

    def __init__(
        self,
        dependencies: UiDependencies,
        parent: QWidget | None = None,
        *,
        settings: QSettings | None = None,
    ) -> None:
        super().__init__(parent)
        self._deps = dependencies
        self._settings = settings or QSettings("Legendar", "Legendar")
        self._preferences = load_preferences(self._settings, dependencies.output_dir)
        self._view_model = JobViewModel()
        self._thread = None
        self._worker: JobWorker | None = None
        self._context: JobContext | None = None
        self._output_touched = False
        self._starting = False
        self._cancel_pending = False
        self._cancel_dialog_open = False

        self.setObjectName("mainWindow")
        self.setWindowTitle("Legendar")
        self.setMinimumSize(680, 620)
        self.resize(900, 780)
        self.setStyleSheet(stylesheet_for(self._preferences.theme))
        self._build_ui()
        self._wire_signals()
        self._sync_translation_controls()
        self._apply_preferences()
        self._restore_geometry()
        self._render(self._view_model.snapshot)

    @property
    def is_running(self) -> bool:
        """True durante confirmação, inicialização ou execução de um job."""
        return self._starting or self._thread is not None

    @property
    def view_model(self) -> JobViewModel:
        return self._view_model

    # -- composição visual -------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget(self)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea(central)
        scroll.setObjectName("mainScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget(scroll)
        root = QVBoxLayout(content)
        root.setContentsMargins(30, 24, 30, 24)
        root.setSpacing(16)

        root.addWidget(self._build_header())
        root.addWidget(self._build_input_panel())
        root.addWidget(self._build_language_panel())
        root.addWidget(self._build_output_panel())
        root.addWidget(self._build_actions_panel())
        root.addWidget(self._build_progress_panel())
        root.addWidget(self._build_log_panel())
        root.addWidget(self._build_readiness_panel())
        root.addStretch(1)

        scroll.setWidget(content)
        outer.addWidget(scroll)
        self.setCentralWidget(central)
        self.statusBar().showMessage(f"Legendar {self._deps.app_version}".strip())

    def _panel(self, name: str) -> tuple[QFrame, QVBoxLayout]:
        panel = QFrame(self)
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 17, 20, 18)
        layout.setSpacing(12)
        title = QLabel(name, panel)
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        return panel, layout

    def _field_label(self, text: str, parent: QWidget) -> QLabel:
        label = QLabel(text.upper(), parent)
        label.setObjectName("fieldLabel")
        return label

    def _build_header(self) -> QFrame:
        card = QFrame(self)
        card.setObjectName("headerCard")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(20, 17, 20, 17)
        layout.setSpacing(14)

        mark = QFrame(card)
        mark.setObjectName("brandMark")
        mark.setFixedSize(48, 48)
        mark_layout = QVBoxLayout(mark)
        mark_layout.setContentsMargins(0, 0, 0, 0)
        letter = QLabel("L", mark)
        letter.setObjectName("brandLetter")
        letter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark_layout.addWidget(letter)

        title_column = QVBoxLayout()
        eyebrow = QLabel("LEGENDAR", card)
        eyebrow.setObjectName("eyebrow")
        title = QLabel("Legendas com clareza.", card)
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            "Prepare sua mídia e acompanhe cada etapa do trabalho.",
            card,
        )
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)
        title_column.addWidget(eyebrow)
        title_column.addWidget(title)
        title_column.addWidget(subtitle)

        self.status_pill = QLabel(card)
        self.status_pill.setObjectName("statusPill")
        self.status_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_pill.setMinimumWidth(112)

        self.preferences_button = QPushButton("Preferências", card)
        self.preferences_button.setObjectName("preferencesButton")
        self.preferences_button.setProperty("variant", "ghost")
        self.preferences_button.setAccessibleName("Abrir preferências")

        layout.addWidget(mark, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addLayout(title_column, stretch=1)
        layout.addWidget(self.status_pill, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.preferences_button, alignment=Qt.AlignmentFlag.AlignTop)
        return card

    def _build_input_panel(self) -> QFrame:
        panel, layout = self._panel("Origem da mídia")
        description = QLabel(
            "Selecione um arquivo local de áudio ou vídeo para preparar o trabalho.",
            panel,
        )
        description.setObjectName("sectionSubtitle")
        description.setWordWrap(True)
        layout.addWidget(description)

        self.file_edit = QLineEdit(panel)
        self.file_edit.setObjectName("fileEdit")
        self.file_edit.setPlaceholderText("Nenhum arquivo selecionado")
        self.file_edit.setClearButtonEnabled(True)
        self.file_edit.setAccessibleName("Arquivo de mídia")
        self.browse_button = QPushButton("Selecionar arquivo…", panel)
        self.browse_button.setObjectName("browseButton")
        self.browse_button.setAccessibleName("Selecionar arquivo de mídia")

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(self.file_edit, stretch=1)
        row.addWidget(self.browse_button)
        layout.addLayout(row)
        return panel

    def _build_language_panel(self) -> QFrame:
        panel, layout = self._panel("Idioma da legenda")
        description = QLabel(
            "O idioma falado pode ser detectado automaticamente ou informado.",
            panel,
        )
        description.setObjectName("sectionSubtitle")
        description.setWordWrap(True)
        layout.addWidget(description)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(7)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        self.source_combo = QComboBox(panel)
        self.source_combo.setObjectName("sourceLanguageCombo")
        self.source_combo.addItem("Detectar automaticamente", None)
        for language in Language:
            self.source_combo.addItem(language.label_pt, language.value)
        self.source_combo.setAccessibleName("Idioma falado na mídia")

        self.target_combo = QComboBox(panel)
        self.target_combo.setObjectName("targetLanguageCombo")
        for language in Language:
            self.target_combo.addItem(language.label_pt, language.value)
        self.target_combo.setCurrentIndex(
            max(0, self.target_combo.findData(self._preferences.target_language.value))
        )
        self.target_combo.setAccessibleName("Idioma final da legenda")

        grid.addWidget(self._field_label("Idioma falado", panel), 0, 0)
        grid.addWidget(self._field_label("Idioma final", panel), 0, 1)
        grid.addWidget(self.source_combo, 1, 0)
        grid.addWidget(self.target_combo, 1, 1)
        layout.addLayout(grid)

        self.translate_check = QCheckBox(
            "Traduzir a fala para o idioma final", panel
        )
        self.translate_check.setObjectName("translateCheck")
        self.translate_check.setEnabled(self._deps.translate_available)
        if not self._deps.translate_available:
            self.translate_check.setToolTip(
                "A integração com tradução será habilitada em uma fase posterior."
            )
        layout.addWidget(self.translate_check)
        return panel

    def _build_output_panel(self) -> QFrame:
        panel, layout = self._panel("Destino do arquivo")
        description = QLabel(
            "O arquivo será salvo como SRT UTF-8 na pasta escolhida.",
            panel,
        )
        description.setObjectName("sectionSubtitle")
        description.setWordWrap(True)
        layout.addWidget(description)

        self.output_edit = QLineEdit(panel)
        self.output_edit.setObjectName("outputEdit")
        self.output_edit.setPlaceholderText("Escolha onde salvar a legenda")
        self.output_edit.setAccessibleName("Caminho do arquivo SRT")
        self.output_browse_button = QPushButton("Salvar como…", panel)
        self.output_browse_button.setObjectName("outputBrowseButton")
        self.output_browse_button.setAccessibleName("Escolher destino do SRT")

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(self.output_edit, stretch=1)
        row.addWidget(self.output_browse_button)
        layout.addLayout(row)
        self.output_edit.setText(str(self._default_output_path("legenda")))
        return panel

    def _build_actions_panel(self) -> QFrame:
        panel = QFrame(self)
        panel.setObjectName("actionsPanel")
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.addStretch(1)

        self.cancel_button = QPushButton("Cancelar trabalho", panel)
        self.cancel_button.setObjectName("cancelButton")
        self.cancel_button.setProperty("variant", "danger")
        self.cancel_button.setEnabled(False)
        self.cancel_button.setAccessibleName("Cancelar o trabalho em andamento")

        self.generate_button = QPushButton("Gerar legenda  →", panel)
        self.generate_button.setObjectName("generateButton")
        self.generate_button.setProperty("variant", "primary")
        self.generate_button.setDefault(True)
        self.generate_button.setAccessibleName("Confirmar e iniciar geração da legenda")

        layout.addWidget(self.cancel_button)
        layout.addWidget(self.generate_button)
        return panel

    def _build_progress_panel(self) -> QFrame:
        panel, layout = self._panel("Andamento do trabalho")
        top = QHBoxLayout()
        self.status_label = QLabel("Aguardando um arquivo de mídia.", panel)
        self.status_label.setObjectName("statusText")
        self.status_label.setWordWrap(True)
        self.progress_meta = QLabel("Pronto para iniciar", panel)
        self.progress_meta.setObjectName("progressMeta")
        top.addWidget(self.status_label, stretch=1)
        top.addWidget(
            self.progress_meta,
            alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )

        self.progress_bar = QProgressBar(panel)
        self.progress_bar.setObjectName("progressBar")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setAccessibleName("Progresso do processamento")

        layout.addLayout(top)
        layout.addWidget(self.progress_bar)
        return panel

    def _build_log_panel(self) -> QFrame:
        panel, layout = self._panel("Atividade")
        header = QHBoxLayout()
        note = QLabel("Etapas, avisos e mensagens do trabalho.", panel)
        note.setObjectName("sectionSubtitle")
        self.log_toggle = QToolButton(panel)
        self.log_toggle.setObjectName("logToggle")
        self.log_toggle.setCheckable(True)
        self.log_toggle.setText("Ocultar detalhes  ▾")
        self.log_toggle.setAccessibleName("Expandir ou recolher detalhes")
        header.addWidget(note, stretch=1)
        header.addWidget(self.log_toggle)
        layout.addLayout(header)

        self.log_view = QPlainTextEdit(panel)
        self.log_view.setObjectName("logView")
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(500)
        self.log_view.setMinimumHeight(132)
        self.log_view.setPlaceholderText(
            "Quando o trabalho começar, as etapas e mensagens aparecerão aqui."
        )
        layout.addWidget(self.log_view)
        return panel

    def _build_readiness_panel(self) -> QFrame:
        panel = QFrame(self)
        panel.setObjectName("readinessPanel")
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(4, 2, 4, 2)
        self.readiness_icon = QLabel("●", panel)
        self.readiness_label = QLabel(panel)
        self.readiness_label.setObjectName("readinessDetail")
        self.readiness_label.setWordWrap(True)
        layout.addWidget(self.readiness_icon)
        layout.addWidget(self.readiness_label, stretch=1)
        return panel

    def _wire_signals(self) -> None:
        self.browse_button.clicked.connect(self._choose_file)
        self.output_browse_button.clicked.connect(self._choose_output)
        self.preferences_button.clicked.connect(self._open_preferences)
        self.output_edit.textEdited.connect(self._on_output_edited)
        self.file_edit.textEdited.connect(self._on_file_edited)
        self.source_combo.currentIndexChanged.connect(self._on_language_changed)
        self.target_combo.currentIndexChanged.connect(self._on_language_changed)
        self.translate_check.toggled.connect(self._on_translate_toggled)
        self.log_toggle.toggled.connect(self._on_log_toggled)
        self.generate_button.clicked.connect(self._start_job)
        self.cancel_button.clicked.connect(self._cancel_job)

    # -- entradas e preferências ------------------------------------------

    def _default_output_path(self, stem: str) -> Path:
        base = self._preferences.output_dir / f"{stem or 'legenda'}.srt"
        if not base.exists():
            return base
        counter = 1
        while True:
            candidate = base.with_name(f"{base.stem}_{counter}{base.suffix}")
            if not candidate.exists():
                return candidate
            counter += 1

    def _choose_file(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self, "Selecionar mídia", str(Path.home()), _MEDIA_FILTER
        )
        if selected:
            self.file_edit.setText(selected)
            self._suggest_output(Path(selected))

    def _choose_output(self) -> None:
        current = self.output_edit.text() or str(self._preferences.output_dir)
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
        self.output_edit.setText(str(self._default_output_path(source_path.stem)))

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
            self.target_combo.setEnabled(not self.is_running)
            return
        if source is not None:
            index = self.target_combo.findData(source.value)
            if index >= 0:
                self.target_combo.setCurrentIndex(index)
            self.target_combo.setEnabled(False)
        else:
            self.target_combo.setEnabled(not self.is_running)

    def _source_language(self) -> Language | None:
        value = self.source_combo.currentData()
        return Language(value) if value is not None else None

    def _target_language(self) -> Language:
        value = self.target_combo.currentData()
        return Language(value) if value is not None else self._preferences.target_language

    def _open_preferences(self) -> None:
        if self.is_running:
            return
        dialog = PreferencesDialog(self._preferences, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._preferences = dialog.preferences
        self._settings.setValue("ui/theme", self._preferences.theme)
        self._settings.setValue(
            "ui/target_language", self._preferences.target_language.value
        )
        self._settings.setValue("paths/output_dir", str(self._preferences.output_dir))
        self._settings.setValue("ui/log_expanded", self._preferences.log_expanded)
        self._settings.sync()
        self._apply_preferences()
        if not self._output_touched:
            self.output_edit.setText(str(self._default_output_path("legenda")))
        index = self.target_combo.findData(self._preferences.target_language.value)
        if index >= 0:
            self.target_combo.setCurrentIndex(index)
        self._sync_translation_controls()

    def _apply_preferences(self) -> None:
        self.setStyleSheet(stylesheet_for(self._preferences.theme))
        self.log_toggle.setChecked(self._preferences.log_expanded)
        self._set_log_expanded(self._preferences.log_expanded)

    def _on_log_toggled(self, expanded: bool) -> None:
        self._set_log_expanded(expanded)
        self._preferences = UiPreferences(
            theme=self._preferences.theme,
            output_dir=self._preferences.output_dir,
            target_language=self._preferences.target_language,
            log_expanded=expanded,
        )

    def _set_log_expanded(self, expanded: bool) -> None:
        self.log_view.setVisible(expanded)
        self.log_toggle.setText(
            "Ocultar detalhes  ▾" if expanded else "Mostrar detalhes  ▸"
        )

    # -- confirmação e montagem do trabalho -------------------------------

    def _build_job(self) -> tuple[JobRequest, Path, Path]:
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

        resolved_output = output_path.resolve()
        if resolved_output == media_path.resolve():
            raise InvalidInputError(
                "O destino da legenda não pode sobrescrever o arquivo de mídia."
            )
        models_root = self._deps.cache_dir.resolve()
        if resolved_output == models_root or models_root in resolved_output.parents:
            raise InvalidInputError(
                "O destino da legenda não pode ficar dentro do cache de modelos."
            )

        source_language, target_language, translate = self._resolved_languages()
        request = JobRequest(
            source=MediaSource(kind=MediaKind.LOCAL_FILE, location=str(media_path)),
            output_language=target_language,
            source_language=source_language,
            translate=translate,
        )
        return request, media_path, output_path

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

    def _confirm_start(
        self, request: JobRequest, media_path: Path, output_path: Path
    ) -> bool:
        source_language = (
            self._source_language().label_pt
            if self._source_language() is not None
            else "Detectar automaticamente"
        )
        dialog = JobConfirmationDialog(
            source_label=media_path.name,
            source_language=source_language,
            target_language=request.output_language.label_pt,
            output_path=output_path,
            output_exists=output_path.exists(),
            parent=self,
        )
        return dialog.exec() == QDialog.DialogCode.Accepted

    def _confirm_overwrite(self, output_path: Path) -> bool:
        response = QMessageBox.warning(
            self,
            "Substituir arquivo existente?",
            (
                f"O arquivo {output_path.name} já existe. "
                "Deseja substituí-lo pela nova legenda?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return response == QMessageBox.StandardButton.Yes

    def _confirm_cancel(self, *, closing: bool = False) -> bool:
        title = "Cancelar trabalho?" if not closing else "Fechar durante o trabalho?"
        message = (
            "O processamento será interrompido em um ponto seguro. "
            "Deseja realmente cancelar?"
            if not closing
            else "Fechar a janela solicitará o cancelamento do trabalho atual. "
            "Deseja continuar?"
        )
        response = QMessageBox.question(
            self,
            title,
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return response == QMessageBox.StandardButton.Yes

    def _start_job(self) -> None:
        if self._starting or self._thread is not None:
            return
        self._starting = True
        self._render(self._view_model.snapshot)
        try:
            request, media_path, output_path = self._build_job()
        except (DomainError, ValueError) as exc:
            self._starting = False
            message = exc.message if isinstance(exc, DomainError) else str(exc)
            self._render(self._view_model.report_error(message))
            return

        if not self._confirm_start(request, media_path, output_path):
            self._starting = False
            self._render(self._view_model.snapshot)
            return
        if output_path.exists() and not self._confirm_overwrite(output_path):
            self._starting = False
            self._render(self._view_model.snapshot)
            return

        context: JobContext | None = None
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            context = self._deps.workspace_factory.create(
                job_id=uuid.uuid4().hex[:12],
                source_label=media_path.name,
                output_path=output_path,
                cache_dir=self._deps.cache_dir,
            )
            self._view_model.reset()
            worker = JobWorker(self._deps.pipeline_factory(), request, context)
        except (DomainError, OSError, ValueError, RuntimeError) as exc:
            self._starting = False
            if context is not None:
                self._discard_workspace(context)
            message = exc.message if isinstance(exc, DomainError) else str(exc)
            self._render(
                self._view_model.report_error(
                    f"Não foi possível preparar o trabalho: {message}"
                )
            )
            return
        except Exception as exc:  # noqa: BLE001 - fronteira da apresentação
            self._starting = False
            if context is not None:
                self._discard_workspace(context)
            self._render(
                self._view_model.report_error(
                    f"Não foi possível preparar o trabalho: {exc}"
                )
            )
            return

        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.event_received.connect(
            self._on_domain_event, Qt.ConnectionType.QueuedConnection
        )
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
        self._starting = False
        self._cancel_pending = False
        self._render(self._view_model.snapshot)
        try:
            thread.start()
        except RuntimeError as exc:
            self._thread = None
            self._worker = None
            self._context = None
            self._starting = False
            self._discard_workspace(context)
            self._render(self._view_model.report_error(str(exc)))

    @Slot(object)
    def _on_domain_event(self, event: JobEvent) -> None:
        snapshot = self._view_model.apply(event)
        self._render(snapshot)
        if isinstance(event, JobFailed):
            self.statusBar().showMessage("O trabalho terminou com erro.", 8000)
        elif isinstance(event, JobCompleted):
            self.statusBar().showMessage(
                f"Legenda salva em {event.output_path}", 10000
            )

    @Slot()
    def _on_job_finished(self) -> None:
        context, self._context = self._context, None
        if context is not None:
            self._discard_workspace(context)

    @Slot()
    def _on_thread_finished(self) -> None:
        self._thread = None
        self._worker = None
        self._cancel_pending = False
        self._render(self._view_model.snapshot)

    def _cancel_job(self) -> None:
        if (
            self._worker is None
            or self._cancel_pending
            or self._cancel_dialog_open
            or not self._view_model.snapshot.can_cancel
        ):
            return
        self._cancel_dialog_open = True
        try:
            confirmed = self._confirm_cancel()
        finally:
            self._cancel_dialog_open = False
        if not confirmed:
            return
        self._cancel_pending = True
        self.cancel_button.setEnabled(False)
        self.cancel_button.setText("Cancelando…")
        self._worker.request_cancel()

    def _discard_workspace(self, context: JobContext) -> None:
        try:
            self._deps.workspace_factory.cleanup(context)
        except Exception as exc:  # noqa: BLE001 - limpeza não pode derrubar a UI
            self._render(
                self._view_model.report_warning(
                    f"não foi possível limpar o diretório temporário: {exc}"
                )
            )

    # -- renderização de estados ------------------------------------------

    def _render(self, snapshot: JobViewSnapshot) -> None:
        busy = self.is_running
        worker_running = self._thread is not None
        self.status_label.setText(
            "Aguardando sua confirmação para iniciar."
            if self._starting and not worker_running
            else snapshot.status_text
        )

        if worker_running and not snapshot.progress_known and not snapshot.is_finished:
            self.progress_bar.setRange(0, 0)
            self.progress_meta.setText("Etapa em andamento · sem percentual medido")
        else:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(snapshot.progress_percent)
            if snapshot.progress_known:
                self.progress_meta.setText(
                    f"{snapshot.progress_percent}% concluído"
                )
            elif snapshot.is_finished:
                self.progress_meta.setText("Trabalho encerrado")
            else:
                self.progress_meta.setText("Pronto para iniciar")

        scrollbar = self.log_view.verticalScrollBar()
        follow_log = scrollbar.value() >= scrollbar.maximum() - 2
        self.log_view.setPlainText("\n".join(snapshot.log_lines))
        if follow_log:
            scrollbar.setValue(scrollbar.maximum())

        if not busy:
            self.generate_button.setEnabled(self._deps.readiness_ok)
            self.cancel_button.setEnabled(False)
            self.cancel_button.setText("Cancelar trabalho")
            self.preferences_button.setEnabled(True)
            self._set_inputs_enabled(True)
        else:
            self.generate_button.setEnabled(False)
            self.cancel_button.setEnabled(
                worker_running and snapshot.can_cancel and not self._cancel_pending
            )
            self.preferences_button.setEnabled(False)
            self._set_inputs_enabled(False)

        self._update_status_pill(snapshot, busy)

    def _update_status_pill(self, snapshot: JobViewSnapshot, busy: bool) -> None:
        if snapshot.state is JobState.FAILED:
            label, state = "Atenção necessária", "error"
        elif snapshot.state is JobState.COMPLETED:
            label, state = "Concluído", "success"
        elif snapshot.state is JobState.CANCELLED:
            label, state = "Cancelado", "warning"
        elif busy:
            label, state = "Em andamento", "running"
        elif self._deps.readiness_ok:
            label, state = "Ambiente pronto", "success"
        else:
            label, state = "Verifique o ambiente", "warning"
        self.status_pill.setText(label)
        self.status_pill.setProperty("state", state)
        self.status_pill.style().unpolish(self.status_pill)
        self.status_pill.style().polish(self.status_pill)

        if self._deps.readiness_ok:
            self.readiness_icon.setStyleSheet("color: #16845b;")
            self.readiness_label.setText(
                "Ferramentas externas verificadas. " +
                " ".join(self._deps.readiness_details)
            )
        else:
            self.readiness_icon.setStyleSheet("color: #a96712;")
            self.readiness_label.setText(
                "O ambiente precisa de ajustes. " +
                " ".join(self._deps.readiness_details)
            )

    def _set_inputs_enabled(self, enabled: bool) -> None:
        self.file_edit.setEnabled(enabled)
        self.browse_button.setEnabled(enabled)
        self.output_edit.setEnabled(enabled)
        self.output_browse_button.setEnabled(enabled)
        self.source_combo.setEnabled(enabled)
        self.translate_check.setEnabled(enabled and self._deps.translate_available)
        if enabled:
            self._sync_translation_controls()
        else:
            self.target_combo.setEnabled(False)

    # -- geometria e encerramento -----------------------------------------

    def _restore_geometry(self) -> None:
        geometry = self._settings.value("window/geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def _save_settings(self) -> None:
        save_preferences(
            self._settings,
            self._preferences,
            geometry=bytes(self.saveGeometry()),
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._starting and self._thread is None:
            event.ignore()
            return
        if self._thread is None:
            self._save_settings()
            super().closeEvent(event)
            return

        current_state = self._view_model.snapshot.state
        if not self._cancel_pending and current_state is JobState.PUBLISHING:
            QMessageBox.information(
                self,
                "Trabalho em etapa final",
                "A publicação está em andamento e não pode ser interrompida. "
                "Aguarde a conclusão para fechar a janela.",
            )
            event.ignore()
            return

        if not self._cancel_pending and not current_state.is_terminal:
            # IDLE também é cancelável aqui: a thread pode ter iniciado antes
            # de o primeiro evento chegar à thread visual.
            if current_state is not JobState.IDLE and not current_state.is_cancellable:
                QMessageBox.information(
                    self,
                    "Trabalho em andamento",
                    "Aguarde a confirmação do estado atual antes de fechar.",
                )
                event.ignore()
                return
            if not self._confirm_cancel(closing=True):
                event.ignore()
                return
            if self._worker is not None:
                self._cancel_pending = True
                self._worker.request_cancel()

        if self._thread.wait(_CLOSE_WAIT_MS):
            context, self._context = self._context, None
            if context is not None:
                self._discard_workspace(context)
            self._save_settings()
            super().closeEvent(event)
        else:
            self.status_label.setText(
                "Cancelando… aguarde a etapa atual terminar para fechar."
            )
            event.ignore()
