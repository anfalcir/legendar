"""Diálogos de confirmação e preferências da interface profissional."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from legendar.domain.value_objects.language import Language
from legendar.presentation.qt.preferences import UiPreferences


class JobConfirmationDialog(QDialog):
    """Resumo explícito da operação antes de iniciar qualquer worker."""

    def __init__(
        self,
        *,
        source_label: str,
        source_language: str,
        target_language: str,
        output_path: Path,
        output_exists: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("appDialog")
        self.setWindowTitle("Confirmar geração de legenda")
        self.setModal(True)
        self.setMinimumWidth(480)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(14)

        eyebrow = QLabel("REVISÃO DO TRABALHO")
        eyebrow.setObjectName("eyebrow")
        title = QLabel("Tudo pronto para começar?")
        title.setObjectName("sectionTitle")
        title.setStyleSheet("font-size: 16pt;")
        subtitle = QLabel(
            "Confira a mídia e o destino antes de iniciar o processamento."
        )
        subtitle.setObjectName("mutedText")
        subtitle.setWordWrap(True)
        root.addWidget(eyebrow)
        root.addWidget(title)
        root.addWidget(subtitle)

        details = QFrame(self)
        details.setObjectName("panel")
        form = QFormLayout(details)
        form.setContentsMargins(14, 14, 14, 14)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)

        self.source_value = QLabel(source_label)
        self.source_value.setObjectName("statusText")
        self.source_value.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.source_language_value = QLabel(source_language)
        self.target_language_value = QLabel(target_language)
        self.output_value = QLabel(str(output_path))
        self.output_value.setWordWrap(True)
        self.output_value.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        for widget in (
            self.source_language_value,
            self.target_language_value,
            self.output_value,
        ):
            widget.setObjectName("mutedText")

        form.addRow("Mídia", self.source_value)
        form.addRow("Idioma falado", self.source_language_value)
        form.addRow("Idioma da legenda", self.target_language_value)
        form.addRow("Arquivo de saída", self.output_value)
        root.addWidget(details)

        if output_exists:
            warning = QLabel(
                "Já existe um arquivo neste destino. A substituição exigirá "
                "uma segunda confirmação."
            )
            warning.setObjectName("dialogWarning")
            warning.setWordWrap(True)
            root.addWidget(warning)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok,
            parent=self,
        )
        self.back_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        self.confirm_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.back_button.setText("Voltar")
        self.confirm_button.setText("Iniciar processamento")
        self.confirm_button.setProperty("variant", "primary")
        self.back_button.setDefault(True)
        self.confirm_button.setAutoDefault(False)
        self.back_button.clicked.connect(self.reject)
        self.confirm_button.clicked.connect(self.accept)
        root.addWidget(buttons)


class PreferencesDialog(QDialog):
    """Preferências simples; valores sensíveis não são aceitos pelo diálogo."""

    def __init__(
        self, preferences: UiPreferences, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("appDialog")
        self.setWindowTitle("Preferências do Legendar")
        self.setModal(True)
        self.setMinimumWidth(500)
        self._initial = preferences

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(14)

        eyebrow = QLabel("PERSONALIZAÇÃO")
        eyebrow.setObjectName("eyebrow")
        title = QLabel("Preferências")
        title.setObjectName("sectionTitle")
        title.setStyleSheet("font-size: 16pt;")
        subtitle = QLabel(
            "Ajustes locais da interface. Seus caminhos de mídia e conteúdos "
            "não são armazenados."
        )
        subtitle.setObjectName("mutedText")
        subtitle.setWordWrap(True)
        root.addWidget(eyebrow)
        root.addWidget(title)
        root.addWidget(subtitle)

        form = QFormLayout()
        form.setVerticalSpacing(14)
        form.setHorizontalSpacing(18)

        self.theme_combo = QComboBox(self)
        self.theme_combo.setObjectName("themeCombo")
        self.theme_combo.addItem("Seguir o sistema", "system")
        self.theme_combo.addItem("Claro", "light")
        self.theme_combo.addItem("Escuro", "dark")
        self.theme_combo.setCurrentIndex(
            max(0, self.theme_combo.findData(preferences.theme))
        )

        self.language_combo = QComboBox(self)
        self.language_combo.setObjectName("defaultLanguageCombo")
        for language in Language:
            self.language_combo.addItem(language.label_pt, language.value)
        self.language_combo.setCurrentIndex(
            max(
                0,
                self.language_combo.findData(preferences.target_language.value),
            )
        )

        output_row = QHBoxLayout()
        self.output_dir_edit = QLineEdit(str(preferences.output_dir), self)
        self.output_dir_edit.setObjectName("defaultOutputDirectory")
        self.output_dir_edit.setPlaceholderText("Pasta padrão de saída")
        self.output_browse_button = QPushButton("Escolher…", self)
        self.output_browse_button.setObjectName("preferencesBrowseButton")
        output_row.addWidget(self.output_dir_edit, stretch=1)
        output_row.addWidget(self.output_browse_button)
        output_container = QWidget(self)
        output_container.setLayout(output_row)

        self.log_expanded_check = QCheckBox("Manter painel de detalhes expandido", self)
        self.log_expanded_check.setObjectName("logExpandedPreference")
        self.log_expanded_check.setChecked(preferences.log_expanded)

        form.addRow("Aparência", self.theme_combo)
        form.addRow("Idioma final padrão", self.language_combo)
        form.addRow("Pasta padrão de saída", output_container)
        root.addLayout(form)
        root.addWidget(self.log_expanded_check)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Save,
            parent=self,
        )
        self.cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        self.save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        self.cancel_button.setText("Cancelar")
        self.save_button.setText("Salvar preferências")
        self.save_button.setProperty("variant", "primary")
        self.cancel_button.setDefault(True)
        self.save_button.setAutoDefault(False)
        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self.accept)
        root.addWidget(buttons)

        self.output_browse_button.clicked.connect(self._choose_output_directory)

    @property
    def preferences(self) -> UiPreferences:
        """Retorna os valores validados após o usuário salvar."""
        output_text = self.output_dir_edit.text().strip()
        output_dir = (
            Path(output_text).expanduser() if output_text else self._initial.output_dir
        )
        return UiPreferences(
            theme=str(self.theme_combo.currentData()),
            output_dir=output_dir,
            target_language=Language(str(self.language_combo.currentData())),
            log_expanded=self.log_expanded_check.isChecked(),
        )

    def _choose_output_directory(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Escolher pasta padrão de saída",
            self.output_dir_edit.text() or str(Path.home()),
        )
        if selected:
            self.output_dir_edit.setText(selected)
