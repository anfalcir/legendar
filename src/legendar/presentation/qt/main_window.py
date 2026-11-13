"""Janela profissional do Legendar, isolada do processamento de mídia."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from PySide6.QtCore import (
    QByteArray,
    QRect,
    QSettings,
    QSize,
    Qt,
    QThread,
    QTimer,
    QUrl,
    Slot,
)
from PySide6.QtGui import (
    QCloseEvent,
    QDesktopServices,
    QGuiApplication,
    QResizeEvent,
)
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
from legendar.application.ports.protocols import MediaInspector, WorkspaceFactory
from legendar.domain.entities.media import MediaInfo, MediaKind, MediaSource
from legendar.domain.errors.base import DomainError
from legendar.domain.errors.catalog import InvalidInputError, JobCancelledError
from legendar.domain.events.job_events import JobCompleted, JobEvent, JobFailed
from legendar.domain.state.machine import JobState
from legendar.domain.value_objects.language import Language
from legendar.infrastructure.config.credentials import (
    delete_gemini_api_key,
    load_gemini_api_key,
    save_gemini_api_key,
)
from legendar.presentation.qt.branding import app_icon
from legendar.presentation.qt.dialogs import (
    JobConfirmationDialog,
    PreferencesDialog,
)
from legendar.presentation.qt.preferences import (
    UiPreferences,
    load_preferences,
    save_preferences,
)
from legendar.presentation.qt.theme import apply_theme
from legendar.presentation.qt.view_model.job_view_model import (
    JobViewModel,
    JobViewSnapshot,
)
from legendar.presentation.qt.widgets import prepare_combo
from legendar.presentation.qt.workers.job_worker import JobWorker
from legendar.presentation.qt.workers.media_inspection_worker import (
    MediaInspectionWorker,
)

PipelineFactory = Callable[[], SerialPipeline]
OutputPathFactory = Callable[[str, Language], Path]

_MEDIA_FILTER = (
    "Mídia (*.mp4 *.mkv *.mov *.webm *.m4a *.mp3 *.wav *.flac *.ogg *.opus *.aac);;"
    "Todos os arquivos (*)"
)
_SRT_FILTER = "Legenda SRT (*.srt)"
_SRT_SOURCE_KIND = "srt_file"
_CLOSE_WAIT_MS = 5000


def _as_byte_array(value: object) -> QByteArray | None:
    """Normaliza o que o ``QSettings`` devolve para ``window/geometry``.

    Versões anteriores gravavam ``bytes(self.saveGeometry())``. O Qt só aceita
    ``QByteArray`` em ``restoreGeometry``; com ``bytes`` a restauração falhava
    silenciosamente. A conversão mantém compatibilidade com instalações antigas.
    """

    if isinstance(value, QByteArray):
        return value
    if isinstance(value, (bytes, bytearray)):
        return QByteArray(bytes(value))
    return None


def _format_elapsed(seconds: float) -> str:
    total = max(0, int(seconds))
    minutes, remaining = divmod(total, 60)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"{hours} h {minutes:02d} min"
    if minutes:
        return f"{minutes} min {remaining:02d} s"
    return f"{remaining} s"


@dataclass(frozen=True, slots=True)
class UiDependencies:
    """Dependências da janela, já compostas pelo bootstrap."""

    output_dir: Path
    cache_dir: Path
    workspace_factory: WorkspaceFactory
    pipeline_factory: PipelineFactory
    output_path_factory: OutputPathFactory
    translate_available: bool = False
    translate_readiness_details: tuple[str, ...] = ()
    readiness_ok: bool = True
    readiness_details: tuple[str, ...] = ()
    app_version: str = ""
    media_inspector: MediaInspector | None = None
    youtube_available: bool = False
    youtube_readiness_details: tuple[str, ...] = ()
    transcription_available: bool = True
    transcription_readiness_details: tuple[str, ...] = ()
    alignment_available: bool = True
    alignment_readiness_details: tuple[str, ...] = ()
    publishing_available: bool = True
    publishing_readiness_details: tuple[str, ...] = ()
    translation_backend: str = "nllb"
    translation_reconfigure: (
        Callable[[str, str | None], tuple[bool, tuple[str, ...]]] | None
    ) = None
    runtime_shutdown: Callable[[], None] | None = None
    runtime_authorization_required: Callable[[], bool] | None = None
    runtime_authorize: Callable[[], None] | None = None
    translation_authorization_required: Callable[[], bool] | None = None
    translation_authorize: Callable[[], None] | None = None


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
        self._inspection_thread = None
        self._inspection_worker: MediaInspectionWorker | None = None
        self._media_info: MediaInfo | None = None
        self._inspection_cancel_pending = False
        self._context: JobContext | None = None
        self._output_touched = False
        self._starting = False
        self._cancel_pending = False
        self._cancel_dialog_open = False
        self._form_side_by_side: bool | None = None
        self._last_state: JobState | None = None
        self._state_started_at = time.monotonic()
        self._heartbeat = QTimer(self)
        self._heartbeat.setInterval(1000)
        self._heartbeat.timeout.connect(self._refresh_elapsed_label)

        self.setObjectName("mainWindow")
        self.setWindowTitle("Legendar")
        self.setWindowIcon(app_icon())
        self._build_ui()
        self._apply_minimum_size()
        self._wire_signals()
        self._apply_preferences()
        self._restore_geometry()
        self._render(self._view_model.snapshot)

    @property
    def is_running(self) -> bool:
        """True durante confirmação, inicialização ou execução de um job."""
        return (
            self._starting
            or self._thread is not None
            or self._inspection_thread is not None
        )

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
        scroll.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        content = QWidget(scroll)
        content.setObjectName("contentColumn")
        # Em telas largas (4K) o formulário não deve esticar além do confortável.
        content.setMaximumWidth(1180)
        self.content_column = content
        root = QVBoxLayout(content)
        root.setContentsMargins(24, 18, 24, 18)
        root.setSpacing(10)

        self.alert_banner = QLabel(content)
        self.alert_banner.setObjectName("alertBanner")
        self.alert_banner.setWordWrap(True)
        self.alert_banner.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.alert_banner.setVisible(False)
        root.addWidget(self.alert_banner)

        root.addWidget(self._build_header())
        root.addWidget(self._build_input_panel())

        # Idioma e destino dividem a linha; em janela estreita voltam a empilhar.
        self.language_panel = self._build_language_panel()
        self.output_panel = self._build_output_panel()
        self.form_grid = QGridLayout()
        self.form_grid.setContentsMargins(0, 0, 0, 0)
        self.form_grid.setHorizontalSpacing(12)
        self.form_grid.setVerticalSpacing(12)
        self.form_grid.addWidget(self.language_panel, 0, 0)
        self.form_grid.addWidget(self.output_panel, 0, 1)
        self.form_grid.setColumnStretch(0, 1)
        self.form_grid.setColumnStretch(1, 1)
        self._form_side_by_side = True
        root.addLayout(self.form_grid)

        root.addWidget(self._build_actions_panel())
        root.addWidget(self._build_progress_panel())
        root.addWidget(self._build_log_panel())
        root.addWidget(self._build_readiness_panel())
        root.addStretch(1)

        scroll.setWidget(content)
        outer.addWidget(scroll)
        self.setCentralWidget(central)
        self.statusBar().showMessage(f"Legendar {self._deps.app_version}".strip())

    def _apply_minimum_size(self) -> None:
        """Piso da janela derivado do layout, não um par fixo de números.

        O valor antigo (680×620) era maior que o necessário em telas pequenas e
        independente do conteúdo: com o piso artificial, compactar a janela
        espremia os cartões em vez de rolar, e o gerenciador de janelas não
        conseguia maximizar corretamente em monitores pequenos.
        """

        hint = self.centralWidget().minimumSizeHint()
        self.setMinimumSize(
            QSize(max(520, min(hint.width(), 760)), max(420, min(hint.height(), 640)))
        )

    def _reflow_language(self, stacked: bool) -> None:
        """Empilha falado/final quando a coluna fica estreita, sem cortar texto."""

        if not hasattr(self, "language_grid"):
            return
        if stacked == self._language_stacked:
            return
        self._language_stacked = stacked
        widgets = (
            self.source_label,
            self.source_combo,
            self.target_label,
            self.target_combo,
        )
        for widget in widgets:
            self.language_grid.removeWidget(widget)
        positions = (
            ((0, 0), (1, 0), (2, 0), (3, 0))
            if stacked
            else ((0, 0), (1, 0), (0, 1), (1, 1))
        )
        for widget, (row, column) in zip(widgets, positions, strict=True):
            self.language_grid.addWidget(widget, row, column)
        self.language_grid.setColumnStretch(0, 1)
        self.language_grid.setColumnStretch(1, 0 if stacked else 1)

    def _reflow_form(self, width: int) -> None:
        """Alterna uma/duas colunas sem recriar widgets (idempotente)."""

        if not hasattr(self, "form_grid"):
            return
        side_by_side = width >= 940
        self._reflow_language(not side_by_side)
        if side_by_side == self._form_side_by_side:
            return
        self._form_side_by_side = side_by_side
        self.form_grid.removeWidget(self.output_panel)
        if side_by_side:
            self.form_grid.addWidget(self.output_panel, 0, 1)
            self.form_grid.setColumnStretch(0, 1)
            self.form_grid.setColumnStretch(1, 1)
            return
        self.form_grid.addWidget(self.output_panel, 1, 0, 1, 2)
        self.form_grid.setColumnStretch(0, 1)
        self.form_grid.setColumnStretch(1, 0)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt
        super().resizeEvent(event)
        self._reflow_form(event.size().width())

    def _panel(self, name: str) -> tuple[QFrame, QVBoxLayout]:
        panel = QFrame(self)
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(8)
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
        layout.setContentsMargins(18, 13, 18, 13)
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
        title_column.addWidget(eyebrow)
        title_column.addWidget(title)

        self.status_pill = QLabel(card)
        self.status_pill.setObjectName("statusPill")
        self.status_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_pill.setMinimumWidth(112)
        self.status_pill.setAccessibleName("Estado geral do Legendar")

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
        panel, layout = self._panel("Origem da mídia ou legenda")

        self.media_kind_combo = prepare_combo(QComboBox(panel))
        self.media_kind_combo.setObjectName("mediaKindCombo")
        self.media_kind_combo.addItem("Arquivo de mídia", MediaKind.LOCAL_FILE.value)
        self.media_kind_combo.addItem("Arquivo SRT", _SRT_SOURCE_KIND)
        self.media_kind_combo.addItem("YouTube", MediaKind.YOUTUBE.value)
        self.media_kind_combo.setAccessibleName("Tipo de origem da legenda ou mídia")

        self.file_edit = QLineEdit(panel)
        self.file_edit.setObjectName("fileEdit")
        self.file_edit.setPlaceholderText("Caminho do arquivo de áudio ou vídeo")
        self.file_edit.setClearButtonEnabled(True)
        self.file_edit.setAccessibleName("Arquivo SRT, arquivo de mídia ou URL")
        self.browse_button = QPushButton("Selecionar arquivo…", panel)
        self.browse_button.setObjectName("browseButton")
        self.browse_button.setAccessibleName("Selecionar arquivo de mídia")

        source_row = QHBoxLayout()
        source_row.setSpacing(10)
        source_row.addWidget(self.media_kind_combo)
        source_row.addWidget(self.file_edit, stretch=1)
        source_row.addWidget(self.browse_button)
        layout.addLayout(source_row)

        inspection_row = QHBoxLayout()
        self.inspect_button = QPushButton("Inspecionar faixas", panel)
        self.inspect_button.setObjectName("inspectMediaButton")
        self.inspect_button.setAccessibleName("Inspecionar faixas de áudio")
        self.inspect_cancel_button = QPushButton("Cancelar inspeção", panel)
        self.inspect_cancel_button.setObjectName("cancelInspectionButton")
        self.inspect_cancel_button.setProperty("variant", "danger")
        self.inspect_cancel_button.setVisible(False)
        self.inspect_cancel_button.setEnabled(False)

        self.stream_combo = prepare_combo(QComboBox(panel))
        self.stream_combo.setObjectName("audioStreamCombo")
        self.stream_combo.addItem("Usar faixa padrão da mídia", None)
        self.stream_combo.setAccessibleName("Faixa de áudio selecionada")
        self.stream_combo.setEnabled(False)

        inspection_row.addWidget(self.inspect_button)
        inspection_row.addWidget(self.stream_combo, stretch=1)
        inspection_row.addWidget(self.inspect_cancel_button)
        layout.addLayout(inspection_row)

        self.media_info_label = QLabel(panel)
        self.media_info_label.setObjectName("sectionSubtitle")
        self.media_info_label.setWordWrap(True)
        # O texto padrão ("a faixa padrão será usada…") era ruído cinza fixo:
        # fica no tooltip e só aparece quando há informação real de faixa/erro.
        self.media_info_label.setVisible(False)
        layout.addWidget(self.media_info_label)
        self.stream_combo.setToolTip(
            "A faixa padrão da mídia é usada automaticamente. "
            "Inspecione para escolher outra."
        )
        self._sync_source_controls()
        return panel

    def _build_language_panel(self) -> QFrame:
        panel, layout = self._panel("Idioma da legenda")

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(7)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        self.source_combo = prepare_combo(QComboBox(panel))
        self.source_combo.setObjectName("sourceLanguageCombo")
        self.source_combo.addItem("Detectar automaticamente", None)
        for language in Language:
            self.source_combo.addItem(language.label_pt, language.value)
        self.source_combo.setAccessibleName("Idioma falado na mídia")

        self.target_combo = prepare_combo(QComboBox(panel))
        self.target_combo.setObjectName("targetLanguageCombo")
        for language in Language:
            self.target_combo.addItem(language.label_pt, language.value)
        self.target_combo.setCurrentIndex(
            max(0, self.target_combo.findData(self._preferences.target_language.value))
        )
        self.target_combo.setAccessibleName("Idioma final da legenda")

        self.source_label = self._field_label("Idioma falado", panel)
        self.target_label = self._field_label("Idioma final", panel)
        grid.addWidget(self.source_label, 0, 0)
        grid.addWidget(self.target_label, 0, 1)
        grid.addWidget(self.source_combo, 1, 0)
        grid.addWidget(self.target_combo, 1, 1)
        layout.addLayout(grid)
        self.language_grid = grid
        self._language_stacked = False

        self.translate_check = QCheckBox("Traduzir a fala para o idioma final", panel)
        self.translate_check.setObjectName("translateCheck")
        self.translate_check.setEnabled(self._deps.translate_available)
        if not self._deps.translate_available:
            details = " ".join(self._deps.translate_readiness_details)
            backend_label = (
                "Gemini"
                if self._deps.translation_backend == "gemini"
                else "TranslateGemma 4B"
                if self._deps.translation_backend == "translategemma"
                else "NLLB-200"
            )
            self.translate_check.setToolTip(
                f"A tradução {backend_label} não está pronta neste ambiente. " + details
            )
        else:
            backend_label = (
                "Gemini (API)"
                if self._deps.translation_backend == "gemini"
                else "TranslateGemma 4B (local)"
                if self._deps.translation_backend == "translategemma"
                else "NLLB-200 (local)"
            )
            self.translate_check.setToolTip(
                f"Traduz PT-BR ↔ EN com {backend_label}, preservando os tempos. "
                "Com a opção desmarcada, a legenda sai no idioma falado."
            )
        layout.addWidget(self.translate_check)

        self.language_hint = QLabel(panel)
        self.language_hint.setObjectName("fieldHint")
        self.language_hint.setWordWrap(True)
        layout.addWidget(self.language_hint)
        return panel

    def _build_output_panel(self) -> QFrame:
        panel, layout = self._panel("Destino do arquivo")

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
        layout.addStretch(1)
        self.output_edit.setText(str(self._default_output_path("legenda")))
        return panel

    def _build_actions_panel(self) -> QFrame:
        panel = QFrame(self)
        panel.setObjectName("actionsPanel")
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.addStretch(1)

        self.open_folder_button = QPushButton("Abrir pasta", panel)
        self.open_folder_button.setObjectName("openFolderButton")
        self.open_folder_button.setProperty("variant", "ghost")
        self.open_folder_button.setEnabled(False)
        self.open_folder_button.setToolTip(
            "Disponível depois que o SRT for publicado nesta sessão."
        )
        self.open_folder_button.setAccessibleName(
            "Abrir a pasta do arquivo SRT publicado"
        )

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

        layout.addWidget(self.open_folder_button)
        layout.addWidget(self.cancel_button)
        layout.addWidget(self.generate_button)
        return panel

    def _build_progress_panel(self) -> QFrame:
        panel, layout = self._panel("Andamento do trabalho")
        top = QHBoxLayout()
        self.status_label = QLabel("Aguardando um arquivo de mídia.", panel)
        self.status_label.setObjectName("statusText")
        self.status_label.setAccessibleName("Estado do processamento")
        self.status_label.setWordWrap(True)
        self.progress_meta = QLabel("Pronto para iniciar", panel)
        self.progress_meta.setObjectName("progressMeta")
        self.progress_meta.setAccessibleName("Percentual de progresso")
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
        self.log_view.setAccessibleName("Registro de atividade do trabalho")
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
        self.readiness_icon.setObjectName("readinessIcon")
        self.readiness_icon.setProperty("state", "ok")
        self.readiness_label = QLabel(panel)
        self.readiness_label.setObjectName("readinessDetail")
        self.readiness_label.setAccessibleName("Estado das ferramentas externas")
        self.readiness_label.setWordWrap(True)
        layout.addWidget(self.readiness_icon)
        layout.addWidget(self.readiness_label, stretch=1)
        return panel

    def _wire_signals(self) -> None:
        self.browse_button.clicked.connect(self._choose_file)
        self.output_browse_button.clicked.connect(self._choose_output)
        self.preferences_button.clicked.connect(self._open_preferences)
        self.inspect_button.clicked.connect(self._start_media_inspection)
        self.inspect_cancel_button.clicked.connect(self._cancel_media_inspection)
        self.media_kind_combo.currentIndexChanged.connect(self._on_media_kind_changed)
        self.output_edit.textEdited.connect(self._on_output_edited)
        self.file_edit.textEdited.connect(self._on_file_edited)
        self.stream_combo.currentIndexChanged.connect(self._on_stream_selection_changed)
        self.source_combo.currentIndexChanged.connect(self._on_language_changed)
        self.target_combo.currentIndexChanged.connect(self._on_language_changed)
        self.translate_check.toggled.connect(self._on_translate_toggled)
        self.log_toggle.toggled.connect(self._on_log_toggled)
        self.generate_button.clicked.connect(self._start_job)
        self.cancel_button.clicked.connect(self._cancel_job)
        self.open_folder_button.clicked.connect(self._open_output_folder)

        # Ordem explícita e previsível para navegação sem mouse.
        self.setTabOrder(self.preferences_button, self.media_kind_combo)
        self.setTabOrder(self.media_kind_combo, self.file_edit)
        self.setTabOrder(self.file_edit, self.browse_button)
        self.setTabOrder(self.browse_button, self.inspect_button)
        self.setTabOrder(self.inspect_button, self.stream_combo)
        self.setTabOrder(self.stream_combo, self.source_combo)
        self.setTabOrder(self.source_combo, self.target_combo)
        self.setTabOrder(self.target_combo, self.translate_check)
        self.setTabOrder(self.translate_check, self.output_edit)
        self.setTabOrder(self.output_edit, self.output_browse_button)
        self.setTabOrder(self.output_browse_button, self.open_folder_button)
        self.setTabOrder(self.open_folder_button, self.cancel_button)
        self.setTabOrder(self.cancel_button, self.generate_button)
        self.setTabOrder(self.generate_button, self.log_toggle)

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

    def _source_kind(self) -> str:
        return str(self.media_kind_combo.currentData())

    def _sync_source_controls(self) -> None:
        source_kind = self._source_kind()
        local = source_kind == MediaKind.LOCAL_FILE.value
        srt_source = source_kind == _SRT_SOURCE_KIND
        youtube = source_kind == MediaKind.YOUTUBE.value
        self.browse_button.setVisible(local or srt_source)
        self.browse_button.setEnabled((local or srt_source) and not self.is_running)
        self.browse_button.setText(
            "Selecionar SRT…" if srt_source else "Selecionar arquivo…"
        )
        self.browse_button.setAccessibleName(
            "Selecionar arquivo SRT" if srt_source else "Selecionar arquivo de mídia"
        )
        self.file_edit.setPlaceholderText(
            "Caminho do arquivo SRT de origem"
            if srt_source
            else "Caminho do arquivo de áudio ou vídeo"
            if local
            else "https://www.youtube.com/watch?v=..."
        )
        self.inspect_button.setVisible(local)
        self.inspect_button.setEnabled(
            local
            and self._deps.media_inspector is not None
            and not self.is_running
            and self._inspection_thread is None
        )
        self.inspect_cancel_button.setVisible(self._inspection_thread is not None)
        self.inspect_cancel_button.setEnabled(
            self._inspection_thread is not None and not self._inspection_cancel_pending
        )
        self.stream_combo.setVisible(not srt_source)
        self.stream_combo.setEnabled(
            local and self._stream_choice_available() and not self.is_running
        )
        if srt_source:
            self._show_media_info(
                "O texto e os timestamps serão lidos diretamente do SRT. "
                "Whisper, WhisperX e FFmpeg não serão executados."
            )
            self._set_stream_placeholder("Não se aplica a arquivos SRT")
        elif youtube:
            self._show_media_info(
                "O áudio do vídeo será obtido automaticamente. "
                "A seleção manual de faixa local não se aplica ao download."
            )
            self._set_stream_placeholder("Faixa de áudio selecionada automaticamente")

    def _set_stream_placeholder(self, label: str) -> None:
        """Atualiza o placeholder da faixa somente quando necessário."""
        if self.stream_combo.count() == 1 and self.stream_combo.itemText(0) == label:
            return
        self.stream_combo.blockSignals(True)
        self.stream_combo.clear()
        self.stream_combo.addItem(label, None)
        self.stream_combo.blockSignals(False)

    def _show_media_info(self, text: str) -> None:
        """Mostra o estado real da mídia; texto vazio recolhe o rótulo."""

        self.media_info_label.setText(text)
        self.media_info_label.setVisible(bool(text))

    def _stream_choice_available(self) -> bool:
        """True só quando existe mais de uma faixa de áudio para escolher."""

        info = self._media_info
        return info is not None and len(info.audio_streams) > 1

    def _invalidate_media_inspection(self) -> None:
        self._media_info = None
        self._set_stream_placeholder("Usar faixa padrão da mídia")
        self.stream_combo.setEnabled(False)
        self._show_media_info("")
        self._sync_source_controls()

    def _on_media_kind_changed(self, _index: int) -> None:
        self._invalidate_media_inspection()
        source_kind = self._source_kind()
        if source_kind == MediaKind.YOUTUBE.value:
            self._output_touched = False
            self._suggest_output(Path("youtube-media"))
        elif source_kind in {MediaKind.LOCAL_FILE.value, _SRT_SOURCE_KIND} and self.file_edit.text().strip():
            self._suggest_output(Path(self.file_edit.text().strip()))
        self._sync_translation_controls()

    def _choose_file(self) -> None:
        srt_source = self._source_kind() == _SRT_SOURCE_KIND
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Selecionar SRT de origem" if srt_source else "Selecionar mídia",
            str(Path.home()),
            _SRT_FILTER if srt_source else _MEDIA_FILTER,
        )
        if selected:
            self.file_edit.setText(selected)
            self._invalidate_media_inspection()
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
        self._invalidate_media_inspection()
        source_kind = self._source_kind()
        if source_kind in {MediaKind.LOCAL_FILE.value, _SRT_SOURCE_KIND} and text.strip():
            self._suggest_output(Path(text.strip()))
        elif source_kind == MediaKind.YOUTUBE.value and text.strip():
            self._suggest_output(Path("youtube-media"))

    def _suggest_output(self, source_path: Path) -> None:
        if self._output_touched:
            return
        self.output_edit.setText(str(self._default_output_path(source_path.stem)))

    def _start_media_inspection(self) -> None:
        if (
            self._inspection_thread is not None
            or self._thread is not None
            or self._deps.media_inspector is None
        ):
            return
        source_text = self.file_edit.text().strip()
        if not source_text:
            self._render(
                self._view_model.report_error(
                    "Selecione um arquivo antes de inspecionar."
                )
            )
            return
        source_path = Path(source_text).expanduser()
        try:
            source = MediaSource(
                kind=MediaKind.LOCAL_FILE,
                location=str(source_path),
            )
        except DomainError as exc:
            self._render(self._view_model.report_error(exc.message))
            return
        if not source_path.is_file():
            self._render(
                self._view_model.report_error(
                    f"Arquivo de mídia não encontrado: {source_path}"
                )
            )
            return

        self._inspection_cancel_pending = False
        self._invalidate_media_inspection()
        thread = MediaInspectionWorker(self._deps.media_inspector, source, self)
        thread.completed.connect(
            self._on_media_inspected, Qt.ConnectionType.QueuedConnection
        )
        thread.failed.connect(
            self._on_media_inspection_failed, Qt.ConnectionType.QueuedConnection
        )
        thread.finished.connect(
            self._on_media_inspection_thread_finished,
            Qt.ConnectionType.QueuedConnection,
        )
        thread.finished.connect(thread.deleteLater)

        # A inspeção é uma QThread dedicada: o objeto da thread pertence à GUI,
        # mas run() e o subprocesso executam fora dela. A finalização volta por
        # conexão enfileirada, sem destruir QObject worker em thread diferente.
        self._inspection_worker = thread
        self._inspection_thread = thread
        self._sync_source_controls()
        self._render(self._view_model.snapshot)
        try:
            thread.start()
        except RuntimeError as exc:
            self._inspection_worker = None
            self._inspection_thread = None
            thread.deleteLater()
            self._sync_source_controls()
            self._render(self._view_model.report_error(str(exc)))

    @Slot(object)
    def _on_media_inspected(self, info: MediaInfo) -> None:
        self._media_info = info
        self.stream_combo.clear()
        self.stream_combo.addItem("Usar faixa padrão da mídia", None)
        for stream in info.audio_streams:
            suffix = " · padrão" if stream.is_default else ""
            self.stream_combo.addItem(f"{stream.label_pt}{suffix}", stream.index)
        if len(info.audio_streams) > 1:
            default = info.default_stream()
            default_index = self.stream_combo.findData(default.index)
            if default_index >= 0:
                self.stream_combo.setCurrentIndex(default_index)
            self.stream_combo.setToolTip("Escolha a faixa de áudio do trabalho.")
            self._on_stream_selection_changed(self.stream_combo.currentIndex())
        elif info.audio_streams:
            # Faixa única: não há escolha a fazer, então o campo não é editável.
            self.stream_combo.setCurrentIndex(0)
            self.stream_combo.setToolTip(
                "A mídia tem apenas uma faixa de áudio; ela será usada."
            )
            self._on_stream_selection_changed(self.stream_combo.currentIndex())
        else:
            duration = (
                f"{info.duration_seconds:.2f} s"
                if info.duration_seconds is not None
                else "duração não informada"
            )
            self._show_media_info(
                f"{info.container} · {duration} · mídia sem faixa de áudio."
            )
        self._sync_source_controls()

    @Slot(int)
    def _on_stream_selection_changed(self, _index: int) -> None:
        if self._media_info is None or not self._media_info.audio_streams:
            return
        selected = self.stream_combo.currentData()
        stream = (
            self._media_info.default_stream()
            if selected is None
            else self._media_info.stream_by_index(int(selected))
        )
        duration = (
            f"{self._media_info.duration_seconds:.2f} s"
            if self._media_info.duration_seconds is not None
            else "duração não informada"
        )
        selection = "Faixa padrão" if selected is None else "Faixa escolhida"
        title = f" · {stream.title}" if stream.title else ""
        self._show_media_info(
            f"{self._media_info.container} · {duration} · {selection}: "
            f"faixa {stream.index}{title} ({stream.codec}, "
            f"{stream.channels} canais, {stream.sample_rate_hz} Hz; "
            f"offset {stream.start_time_seconds:.3f} s via {stream.offset_source})."
        )

    @Slot(object)
    def _on_media_inspection_failed(self, error: Exception) -> None:
        if isinstance(error, JobCancelledError):
            self._show_media_info("Inspeção de mídia cancelada.")
            return
        message = (
            error.message
            if isinstance(error, DomainError)
            else f"Não foi possível inspecionar a mídia: {error}"
        )
        self._show_media_info(message)
        self.statusBar().showMessage(message, 10000)

    @Slot()
    def _on_media_inspection_thread_finished(self) -> None:
        self._inspection_thread = None
        self._inspection_worker = None
        self._inspection_cancel_pending = False
        self._sync_source_controls()
        self._render(self._view_model.snapshot)

    def _cancel_media_inspection(self) -> None:
        if self._inspection_worker is None or self._inspection_cancel_pending:
            return
        if not self._confirm_cancel():
            return
        self._inspection_cancel_pending = True
        self.inspect_cancel_button.setEnabled(False)
        self.inspect_button.setEnabled(False)
        self._inspection_worker.request_cancel()
        self._show_media_info("Cancelando a inspeção de mídia…")

    def _on_output_edited(self, _text: str) -> None:
        self._output_touched = True

    def _on_language_changed(self, _index: int) -> None:
        self._sync_translation_controls()
        self._preferences = UiPreferences(
            theme=self._preferences.theme,
            output_dir=self._preferences.output_dir,
            target_language=self._target_language(),
            log_expanded=self._preferences.log_expanded,
        )

    def _on_translate_toggled(self, _checked: bool) -> None:
        self._sync_translation_controls()

    def _sync_translation_controls(self) -> None:
        """Mantém falado e final independentes e explica o efeito na legenda.

        Antes, escolher o idioma falado reescrevia e travava o idioma final: o
        campo parecia quebrado porque o usuário não conseguia mais mudá-lo. Os
        dois campos agora conservam a própria escolha e a consequência aparece
        em uma frase curta abaixo da caixa de tradução.
        """

        if not hasattr(self, "language_hint"):
            return
        srt_source = self._source_kind() == _SRT_SOURCE_KIND
        self.translate_check.setText(
            "Traduzir o SRT de origem para o idioma final"
            if srt_source
            else "Traduzir a fala para o idioma final"
        )
        self.source_label.setText("IDIOMA DO SRT" if srt_source else "IDIOMA FALADO")
        self.source_combo.setAccessibleName(
            "Idioma atual do SRT de origem"
            if srt_source
            else "Idioma falado na mídia"
        )
        # A disponibilidade pode mudar depois das confirmações nas Preferências.
        # Atualizar o controle aqui evita deixá-lo desabilitado até um novo render.
        self.translate_check.setEnabled(
            self._deps.translate_available and not self.is_running
        )
        backend_label = (
            "Gemini (API)"
            if self._deps.translation_backend == "gemini"
            else "TranslateGemma 4B (local)"
            if self._deps.translation_backend == "translategemma"
            else "NLLB-200 (local)"
        )
        if self._deps.translate_available:
            self.translate_check.setToolTip(
                (
                    f"Traduz o texto das cues do SRT com {backend_label}, "
                    "preservando exatamente os timestamps."
                    if srt_source
                    else f"Traduz PT-BR ↔ EN com {backend_label}, preservando os tempos. "
                    "Com a opção desmarcada, a legenda sai no idioma falado."
                )
            )
        else:
            details = " ".join(self._deps.translate_readiness_details)
            self.translate_check.setToolTip(
                f"A tradução {backend_label} não está pronta neste ambiente. {details}"
            )
        translating = (
            self.translate_check.isChecked() and self._deps.translate_available
        )
        source = self._source_language()
        target = self._target_language()
        self.target_combo.setEnabled(not self.is_running)
        self.target_combo.setToolTip(
            "Idioma final do arquivo. O texto só muda quando a tradução está marcada."
        )
        if srt_source and source is None:
            hint = (
                "Informe o idioma atual do SRT. Não há detecção automática confiável "
                "de idioma em arquivos de legenda."
            )
        elif translating and source is None:
            hint = (
                "Tradução marcada: o idioma falado será detectado e depois "
                f"traduzido para {target.label_pt}."
            )
        elif translating and source is target:
            hint = (
                f"Origem e destino são {target.label_pt}: não há o que traduzir. "
                + (
                    "O SRT será republicado sem alterar os timestamps."
                    if srt_source
                    else "A legenda sai no idioma falado."
                )
            )
        elif translating:
            backend_label = (
                "Gemini (API)"
                if self._deps.translation_backend == "gemini"
                else "TranslateGemma 4B"
                if self._deps.translation_backend == "translategemma"
                else "NLLB-200"
            )
            hint = (
                f"Tradução {source.label_pt} → {target.label_pt} com {backend_label}, "
                + (
                    "mantendo exatamente os timestamps do SRT."
                    if srt_source
                    else "preservando os tempos originais."
                )
            )
        elif source is None:
            hint = (
                "Sem tradução: informe o idioma atual do SRT."
                if srt_source
                else "Sem tradução: a legenda sai no idioma detectado na fala."
            )
        else:
            hint = (
                f"Sem tradução: o SRT será mantido em {source.label_pt}. "
                "Marque a tradução para publicar em outro idioma."
                if srt_source
                else f"Sem tradução: a legenda sai em {source.label_pt}. "
                "Marque a tradução para publicar em outro idioma."
            )
        self.language_hint.setText(hint)

    def _source_language(self) -> Language | None:
        value = self.source_combo.currentData()
        return Language(value) if value is not None else None

    def _target_language(self) -> Language:
        value = self.target_combo.currentData()
        return (
            Language(value) if value is not None else self._preferences.target_language
        )

    def _open_preferences(self) -> None:
        if self.is_running:
            return
        dialog = PreferencesDialog(self._preferences, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        new_preferences = dialog.preferences
        if (
            new_preferences.translation_backend == "translategemma"
            and self._deps.runtime_authorization_required is not None
            and self._deps.runtime_authorization_required()
        ):
            answer = QMessageBox.question(
                self,
                "Instalar llama.cpp",
                "O Legendar precisa do runtime CPU llama.cpp para executar o TranslateGemma localmente. "
                "O pacote oficial fixado ocupa cerca de 22 MB e será instalado somente no cache privado "
                "do aplicativo, sem sudo e sem alterar o sistema. Autoriza a instalação automática?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes:
                if self._deps.runtime_authorize is not None:
                    self._deps.runtime_authorize()
            else:
                new_preferences = replace(
                    new_preferences,
                    translation_backend=self._preferences.translation_backend,
                )
        if (
            new_preferences.translation_backend == "translategemma"
            and self._deps.translation_authorization_required is not None
            and self._deps.translation_authorization_required()
        ):
            answer = QMessageBox.question(
                self,
                "Preparar TranslateGemma",
                "O modelo TranslateGemma 4B Q4_K_M ocupa aproximadamente 2,49 GB. "
                "Autoriza o Legendar a baixá-lo automaticamente na primeira tradução? "
                "O download será retomável e validado por SHA-256. "
                "É necessário aceitar previamente os termos Gemma no Hugging Face; "
                "a autenticação local existente será reutilizada, sem copiar o token.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes:
                if self._deps.translation_authorize is not None:
                    self._deps.translation_authorize()
            else:
                new_preferences = replace(
                    new_preferences,
                    translation_backend=self._preferences.translation_backend,
                )
        api_key_input = dialog.gemini_api_key_input
        try:
            if api_key_input:
                save_gemini_api_key(api_key_input)
            elif dialog.gemini_key_cleared:
                delete_gemini_api_key()
        except (OSError, RuntimeError, ValueError) as exc:
            QMessageBox.critical(
                self,
                "Não foi possível salvar a chave Gemini",
                f"A chave não foi alterada. Verifique as permissões do perfil do usuário.\n\n{exc}",
            )
            return

        self._preferences = new_preferences
        self._settings.setValue("ui/theme", self._preferences.theme)
        self._settings.setValue(
            "ui/target_language", self._preferences.target_language.value
        )
        self._settings.setValue("paths/output_dir", str(self._preferences.output_dir))
        self._settings.setValue("ui/log_expanded", self._preferences.log_expanded)
        self._settings.setValue(
            "translation/backend", self._preferences.translation_backend
        )
        self._settings.sync()

        api_key = load_gemini_api_key()
        if self._deps.translation_reconfigure is not None:
            available, details = self._deps.translation_reconfigure(
                self._preferences.translation_backend,
                api_key,
            )
            self._deps = replace(
                self._deps,
                translate_available=available,
                translate_readiness_details=details,
                translation_backend=self._preferences.translation_backend,
            )
            if (
                self._preferences.translation_backend == "translategemma"
                and not available
            ):
                if any("llama.cpp não encontrado" in item for item in details):
                    QMessageBox.information(
                        self,
                        "TranslateGemma ainda não está pronto",
                        "O runtime llama.cpp ainda não está disponível. Autorize sua instalação "
                        "nas Preferências e tente novamente.",
                    )
                elif any("aguarda autorização explícita" in item for item in details):
                    QMessageBox.information(
                        self,
                        "Download do TranslateGemma não autorizado",
                        "A tradução local permanece desabilitada até que você autorize "
                        "o download do modelo nas Preferências.",
                    )
        self._apply_preferences()
        if not self._output_touched:
            self.output_edit.setText(str(self._default_output_path("legenda")))
        index = self.target_combo.findData(self._preferences.target_language.value)
        if index >= 0:
            self.target_combo.setCurrentIndex(index)
        self._sync_translation_controls()

    def _apply_preferences(self) -> None:
        apply_theme(self._preferences.theme)
        self.setWindowIcon(app_icon())
        self.log_toggle.setChecked(self._preferences.log_expanded)
        self._set_log_expanded(self._preferences.log_expanded)

    def _on_log_toggled(self, expanded: bool) -> None:
        self._set_log_expanded(expanded)
        self._preferences = UiPreferences(
            theme=self._preferences.theme,
            output_dir=self._preferences.output_dir,
            target_language=self._preferences.target_language,
            log_expanded=expanded,
            translation_backend=self._preferences.translation_backend,
        )

    def _set_log_expanded(self, expanded: bool) -> None:
        self.log_view.setVisible(expanded)
        self.log_toggle.setText(
            "Ocultar detalhes  ▾" if expanded else "Mostrar detalhes  ▸"
        )

    # -- confirmação e montagem do trabalho -------------------------------

    def _build_job(self) -> tuple[JobRequest, str, Path]:
        if not self._deps.publishing_available:
            details = " ".join(self._deps.publishing_readiness_details)
            raise InvalidInputError(
                "A publicação final de legendas ainda não está disponível. " + details
            )

        source_text = self.file_edit.text().strip()
        if not source_text:
            raise InvalidInputError("Selecione um arquivo ou informe uma URL.")
        source_kind = self._source_kind()
        is_srt_source = source_kind == _SRT_SOURCE_KIND
        source_language, target_language, translate = self._resolved_languages(
            require_source=is_srt_source,
        )

        stream_index = None
        media_path: Path | None = None
        subtitle_path: Path | None = None
        source: MediaSource | None = None

        if is_srt_source:
            subtitle_path = Path(source_text).expanduser()
            if subtitle_path.suffix.lower() != ".srt":
                raise InvalidInputError("Selecione um arquivo com extensão .srt.")
            if not subtitle_path.is_file():
                raise InvalidInputError(
                    f"Arquivo SRT não encontrado: {subtitle_path}"
                )
            if (
                source_language is not target_language
                and not self._deps.translate_available
            ):
                details = " ".join(self._deps.translate_readiness_details)
                raise InvalidInputError(
                    "O tradutor não está pronto para converter este SRT. " + details
                )
            source_label = f"SRT · {subtitle_path.name}"
            media_path = subtitle_path
        elif source_kind == MediaKind.LOCAL_FILE.value:
            if not self._deps.transcription_available:
                details = " ".join(self._deps.transcription_readiness_details)
                raise InvalidInputError(
                    "O reconhecimento Whisper não está pronto neste ambiente. " + details
                )
            if not self._deps.alignment_available:
                details = " ".join(self._deps.alignment_readiness_details)
                raise InvalidInputError(
                    "O alinhamento WhisperX não está pronto neste ambiente. " + details
                )
            media_path = Path(source_text).expanduser()
            if not media_path.is_file():
                raise InvalidInputError(
                    f"Arquivo de mídia não encontrado: {media_path}"
                )
            source = MediaSource(
                kind=MediaKind.LOCAL_FILE,
                location=str(media_path),
            )
            source_label = media_path.name
            selected_stream = self.stream_combo.currentData()
            if selected_stream is not None:
                if self._media_info is None:
                    raise InvalidInputError(
                        "Inspecione novamente a mídia antes de escolher uma faixa."
                    )
                stream_index = int(selected_stream)
                self._media_info.stream_by_index(stream_index)
        elif source_kind == MediaKind.YOUTUBE.value:
            if not self._deps.transcription_available:
                details = " ".join(self._deps.transcription_readiness_details)
                raise InvalidInputError(
                    "O reconhecimento Whisper não está pronto neste ambiente. " + details
                )
            if not self._deps.alignment_available:
                details = " ".join(self._deps.alignment_readiness_details)
                raise InvalidInputError(
                    "O alinhamento WhisperX não está pronto neste ambiente. " + details
                )
            if not self._deps.youtube_available:
                details = " ".join(self._deps.youtube_readiness_details)
                raise InvalidInputError(
                    "O suporte ao YouTube não está pronto neste ambiente. " + details
                )
            source = MediaSource(
                kind=MediaKind.YOUTUBE,
                location=source_text,
            )
            source_label = "vídeo do YouTube"
        else:
            raise InvalidInputError("Tipo de origem desconhecido.")

        output_text = self.output_edit.text().strip()
        if not output_text:
            raise InvalidInputError("Defina onde salvar a legenda.")
        output_path = Path(output_text).expanduser()
        if output_path.suffix.lower() != ".srt":
            output_path = output_path.with_suffix(".srt")

        resolved_output = output_path.resolve()
        if media_path is not None and resolved_output == media_path.resolve():
            raise InvalidInputError(
                "O destino da legenda não pode sobrescrever o arquivo de origem."
            )
        models_root = self._deps.cache_dir.resolve()
        if resolved_output == models_root or models_root in resolved_output.parents:
            raise InvalidInputError(
                "O destino da legenda não pode ficar dentro do cache de modelos."
            )

        request = JobRequest(
            source=source,
            subtitle_path=subtitle_path,
            output_language=target_language,
            source_language=source_language,
            translate=translate,
            stream_index=stream_index,
        )
        return request, source_label, output_path

    def _resolved_languages(
        self,
        *,
        require_source: bool = False,
    ) -> tuple[Language | None, Language, bool]:
        """Resolve o par de idiomas antes de qualquer trabalho começar.

        SRT não carrega metadados de idioma confiáveis: nesse modo a origem deve
        ser declarada pelo usuário, enquanto a mídia pode usar detecção automática.
        """
        source = self._source_language()
        target = self._target_language()
        if require_source and source is None:
            raise InvalidInputError(
                "Informe o idioma atual do SRT antes de iniciar a tradução."
            )
        translate = self.translate_check.isChecked() and self._deps.translate_available
        if translate and source is None:
            raise InvalidInputError(
                "Para traduzir, informe também o idioma falado na mídia."
            )
        if translate and source is target:
            return source, target, False
        if not translate and source is not None and target is not source:
            if self.translate_check.isChecked() and not self._deps.translate_available:
                details = " ".join(self._deps.translate_readiness_details)
                raise InvalidInputError(
                    "O tradutor não está pronto para o idioma final selecionado. "
                    + details
                )
            raise InvalidInputError(
                f"Sem tradução, o idioma final precisa ser {source.label_pt}. "
                "Marque a opção de tradução para converter o texto."
            )
        return source, target, translate

    def _confirm_start(
        self, request: JobRequest, source_label: str, output_path: Path
    ) -> bool:
        source_language = (
            self._source_language().label_pt
            if self._source_language() is not None
            else "Detectar automaticamente"
        )
        dialog = JobConfirmationDialog(
            source_label=source_label,
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
        if (
            self._starting
            or self._thread is not None
            or self._inspection_thread is not None
        ):
            return
        self._starting = True
        self._render(self._view_model.snapshot)
        try:
            request, source_label, output_path = self._build_job()
        except (DomainError, ValueError) as exc:
            self._starting = False
            message = exc.message if isinstance(exc, DomainError) else str(exc)
            self._render(self._view_model.report_error(message))
            return

        if not self._confirm_start(request, source_label, output_path):
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
                source_label=source_label,
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
            self.statusBar().showMessage(f"Legenda salva em {event.output_path}", 10000)

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
        if self._inspection_thread is not None:
            self._cancel_media_inspection()
            return
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
        accepted = self._worker.request_cancel()
        if accepted:
            self.cancel_button.setText("Cancelando…")
            self.status_label.setText("Cancelando em um ponto seguro…")
        else:
            self.cancel_button.setText("Etapa finalizando…")
            self.status_label.setText(
                "O trabalho avançou para uma etapa que não pode ser cancelada. "
                "Aguarde a publicação terminar."
            )
            self.statusBar().showMessage(
                "O cancelamento não foi aceito porque a publicação já começou.",
                8000,
            )

    def _discard_workspace(self, context: JobContext) -> None:
        try:
            self._deps.workspace_factory.cleanup(context)
        except Exception as exc:  # noqa: BLE001 - limpeza não pode derrubar a UI
            self._render(
                self._view_model.report_warning(
                    f"não foi possível limpar o diretório temporário: {exc}"
                )
            )

    # -- resultado publicado ----------------------------------------------

    def _published_folder(self, snapshot: JobViewSnapshot | None = None) -> Path | None:
        """Pasta do SRT publicado nesta sessão, quando ela ainda existe."""
        snapshot = snapshot or self._view_model.snapshot
        output = snapshot.output_path
        if not output:
            return None
        folder = Path(output).expanduser().parent
        return folder if folder.is_dir() else None

    @Slot()
    def _open_output_folder(self) -> None:
        """Abre a pasta do SRT publicado, sem bloquear a thread da interface."""
        folder = self._published_folder()
        if folder is None:
            self.statusBar().showMessage(
                "Nenhum SRT foi publicado nesta sessão ainda.", 8000
            )
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
            self.statusBar().showMessage(
                f"Não foi possível abrir a pasta: {folder}", 8000
            )

    # -- renderização de estados ------------------------------------------

    def _render(self, snapshot: JobViewSnapshot) -> None:
        busy = self.is_running
        worker_running = self._thread is not None
        inspection_running = self._inspection_thread is not None
        if snapshot.state is not self._last_state:
            self._last_state = snapshot.state
            self._state_started_at = time.monotonic()
        self._update_alert_banner(snapshot)
        self.open_folder_button.setEnabled(
            not busy and self._published_folder(snapshot) is not None
        )
        if inspection_running:
            self._heartbeat.stop()
            self.status_label.setText("Inspecionando mídia com ffprobe…")
            self.progress_meta.setText("Lendo contêineres e faixas")
            self.progress_bar.setRange(0, 0)
        else:
            self.status_label.setText(
                "Aguardando sua confirmação para iniciar."
                if self._starting and not worker_running
                else snapshot.status_text
            )
            if (
                worker_running
                and not snapshot.progress_known
                and not snapshot.is_finished
            ):
                self.progress_bar.setRange(0, 0)
                self._heartbeat.start()
                self._refresh_elapsed_label()
            else:
                self._heartbeat.stop()
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
            self.generate_button.setEnabled(self._source_ready())
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
        self._sync_source_controls()
        self._update_status_pill(snapshot, busy)

    def _source_ready(self) -> bool:
        """Prontidão mínima correspondente ao tipo de entrada selecionado."""
        source_kind = self._source_kind()
        if source_kind == _SRT_SOURCE_KIND:
            if not self._deps.publishing_available:
                return False
            source = self._source_language()
            if source is None:
                return False
            target = self._target_language()
            requires_translation = source is not target
            return (
                not requires_translation
                or (
                    self.translate_check.isChecked()
                    and self._deps.translate_available
                )
            )
        return (
            self._deps.readiness_ok
            and self._deps.transcription_available
            and self._deps.alignment_available
            and self._deps.publishing_available
            and (
                source_kind == MediaKind.LOCAL_FILE.value
                or (
                    source_kind == MediaKind.YOUTUBE.value
                    and self._deps.youtube_available
                )
            )
        )

    def _update_status_pill(self, snapshot: JobViewSnapshot, busy: bool) -> None:
        source_kind = self._source_kind()
        is_srt_source = source_kind == _SRT_SOURCE_KIND
        local_source = source_kind == MediaKind.LOCAL_FILE.value
        source_ready = self._source_ready()
        if snapshot.state is JobState.FAILED:
            label, state = "Atenção necessária", "error"
        elif snapshot.state is JobState.COMPLETED:
            label, state = "Concluído", "success"
        elif snapshot.state is JobState.CANCELLED:
            label, state = "Cancelado", "warning"
        elif busy:
            label, state = "Em andamento", "running"
        elif source_ready:
            label, state = "Ambiente pronto", "success"
        else:
            label, state = "Verifique o ambiente", "warning"
        self.status_pill.setText(label)
        self.status_pill.setProperty("state", state)
        self.status_pill.style().unpolish(self.status_pill)
        self.status_pill.style().polish(self.status_pill)

        media_requirement = (
            "FFmpeg e ffprobe precisam estar instalados. "
            if not self._deps.readiness_ok
            else ""
        )
        whisper_requirement = (
            "O runtime openai-whisper precisa ser instalado. "
            if not self._deps.transcription_available
            else ""
        )
        alignment_requirement = (
            "O runtime WhisperX precisa ser instalado/configurado. "
            if not self._deps.alignment_available
            else ""
        )
        publishing_requirement = (
            "O publicador SRT não está disponível neste ambiente. "
            if not self._deps.publishing_available
            else ""
        )
        youtube_requirement = (
            ""
            if self._deps.youtube_available
            else "yt-dlp e um runtime EJS compatível são necessários. "
        )

        details = [*self._deps.publishing_readiness_details]
        if is_srt_source:
            details.extend(self._deps.translate_readiness_details)
            if source_ready:
                summary = (
                    "Pronto para ler e traduzir SRT diretamente, sem executar "
                    "transcrição ou alinhamento."
                )
            else:
                summary = (
                    "Tradução de SRT indisponível. "
                    f"{publishing_requirement}"
                    + " ".join(self._deps.translate_readiness_details)
                )
        else:
            details.extend(self._deps.readiness_details)
            details.extend(self._deps.transcription_readiness_details)
            details.extend(self._deps.alignment_readiness_details)
            if local_source:
                if source_ready:
                    summary = "Ambiente pronto para gerar legendas neste computador."
                else:
                    summary = (
                        "Geração local indisponível. "
                        f"{media_requirement}{whisper_requirement}"
                        f"{alignment_requirement}{publishing_requirement}"
                    )
            else:
                details.extend(self._deps.youtube_readiness_details)
                if source_ready:
                    summary = "Ambiente pronto para gerar legendas do YouTube."
                else:
                    summary = (
                        "YouTube indisponível. "
                        f"{media_requirement}{whisper_requirement}"
                        f"{alignment_requirement}{publishing_requirement}"
                        f"{youtube_requirement}"
                    )
        self._update_readiness_footer(summary, details, ok=source_ready)
        self.status_pill.setToolTip(" ".join(part for part in details if part))

    def _update_readiness_footer(
        self, summary: str, details: list[str], *, ok: bool
    ) -> None:
        state = "ok" if ok else "warning"
        if state != self.readiness_icon.property("state"):
            self.readiness_icon.setProperty("state", state)
            self.readiness_icon.style().unpolish(self.readiness_icon)
            self.readiness_icon.style().polish(self.readiness_icon)
        self.readiness_label.setText(summary)
        tooltip = " ".join(part for part in details if part).strip()
        self.readiness_label.setToolTip(tooltip or summary)

    def _refresh_elapsed_label(self) -> None:
        """Diz há quanto tempo a etapa sem percentual está rodando.

        Transcrição e alinhamento não expõem progresso medido. Sem um relógio
        visível, quinze minutos de trabalho parecem travamento; com ele, o
        usuário vê que o processo continua avançando.
        """

        snapshot = self._view_model.snapshot
        if self._thread is None or snapshot.progress_known or snapshot.is_finished:
            self._heartbeat.stop()
            return
        stage = (
            snapshot.state.label_pt
            if snapshot.state is not JobState.IDLE
            else "Preparando"
        )
        elapsed = _format_elapsed(time.monotonic() - self._state_started_at)
        self.progress_meta.setText(f"{stage} · {elapsed} · sem percentual medido")

    def _update_alert_banner(self, snapshot: JobViewSnapshot) -> None:
        """Destaca falhas e avisos no topo, em vez de só empurrá-los ao log."""

        message = snapshot.notice_message
        if not message:
            self.alert_banner.setVisible(False)
            return
        level = snapshot.notice_level or "error"
        if self.alert_banner.property("level") != level:
            self.alert_banner.setProperty("level", level)
            self.alert_banner.style().unpolish(self.alert_banner)
            self.alert_banner.style().polish(self.alert_banner)
        self.alert_banner.setText(message)
        self.alert_banner.setToolTip(
            "Detalhes técnicos em ~/.cache/legendar/logs/legendar.log"
        )
        self.alert_banner.setVisible(True)

    def _set_inputs_enabled(self, enabled: bool) -> None:
        self.media_kind_combo.setEnabled(enabled)
        self.file_edit.setEnabled(enabled)
        source_kind = self._source_kind()
        local = source_kind == MediaKind.LOCAL_FILE.value
        self.browse_button.setEnabled(
            enabled and (local or source_kind == _SRT_SOURCE_KIND)
        )
        self.inspect_button.setEnabled(
            enabled and local and self._deps.media_inspector is not None
        )
        self.stream_combo.setEnabled(
            enabled and local and self._stream_choice_available()
        )
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
        """Restaura geometria tipada e devolve a janela para dentro da tela.

        O valor era salvo como ``bytes``, mas ``restoreGeometry`` só aceita
        ``QByteArray``: a chamada devolvia ``False`` e a janela voltava sempre
        no tamanho padrão. O estado salvo agora é convertido, validado contra a
        tela atual e reencaixado quando o monitor mudou de tamanho.
        """

        available = self._available_geometry()
        default = QSize(
            min(1120, max(720, available.width() - 120)),
            min(820, max(560, available.height() - 120)),
        )
        geometry = _as_byte_array(self._settings.value("window/geometry"))
        restored = (
            geometry is not None
            and not geometry.isEmpty()
            and self.restoreGeometry(geometry)
        )
        if restored:
            self._clamp_to_available(available)
        else:
            self.resize(default)
        if self._settings.value("window/maximized", False, type=bool):
            self.setWindowState(self.windowState() | Qt.WindowState.WindowMaximized)

    def _available_geometry(self) -> QRect:
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return QRect(0, 0, 1280, 800)
        return screen.availableGeometry()

    def _clamp_to_available(self, available: QRect) -> None:
        width = min(max(self.width(), self.minimumWidth()), available.width())
        height = min(max(self.height(), self.minimumHeight()), available.height())
        if (width, height) != (self.width(), self.height()):
            self.resize(width, height)
        frame = self.frameGeometry()
        x = min(
            max(frame.left(), available.left()),
            available.right() - frame.width() + 1,
        )
        y = min(
            max(frame.top(), available.top()),
            available.bottom() - frame.height() + 1,
        )
        if (x, y) != (frame.left(), frame.top()):
            self.move(x, y)

    def _save_settings(self) -> None:
        save_preferences(
            self._settings,
            self._preferences,
            geometry=self.saveGeometry(),
            maximized=bool(self.windowState() & Qt.WindowState.WindowMaximized),
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._starting and self._thread is None and self._inspection_thread is None:
            event.ignore()
            return
        if self._inspection_thread is not None:
            if not self._inspection_cancel_pending:
                if not self._confirm_cancel(closing=True):
                    event.ignore()
                    return
                if self._inspection_worker is not None:
                    self._inspection_cancel_pending = True
                    self._inspection_worker.request_cancel()
            if self._inspection_thread.wait(_CLOSE_WAIT_MS):
                self._inspection_thread = None
                self._inspection_worker = None
                self._save_settings()
                super().closeEvent(event)
            else:
                self._show_media_info(
                    "A inspeção ainda está encerrando; aguarde para fechar."
                )
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
                self._cancel_pending = self._worker.request_cancel()

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
