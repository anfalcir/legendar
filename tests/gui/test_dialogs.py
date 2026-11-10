from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QDialog

from legendar.domain.value_objects.language import Language
from legendar.presentation.qt.dialogs import (
    JobConfirmationDialog,
    PreferencesDialog,
)
from legendar.presentation.qt.preferences import UiPreferences

pytestmark = __import__("pytest").mark.gui


def test_job_confirmation_shows_all_critical_details(qtbot, tmp_path: Path) -> None:
    output_path = tmp_path / "aula.srt"
    dialog = JobConfirmationDialog(
        source_label="aula.mp4",
        source_language="Detectar automaticamente",
        target_language="Português brasileiro",
        output_path=output_path,
        output_exists=True,
    )
    qtbot.addWidget(dialog)

    assert dialog.source_value.text() == "aula.mp4"
    assert dialog.source_language_value.text() == "Detectar automaticamente"
    assert dialog.target_language_value.text() == "Português brasileiro"
    assert dialog.output_value.text() == str(output_path)
    assert "segunda confirmação" in " ".join(
        label.text() for label in dialog.findChildren(__import__("PySide6").QtWidgets.QLabel)
    )
    assert dialog.back_button.isDefault()
    assert dialog.confirm_button.text() == "Iniciar processamento"


def test_job_confirmation_back_button_rejects_by_default(qtbot) -> None:
    dialog = JobConfirmationDialog(
        source_label="aula.mp4",
        source_language="Português brasileiro",
        target_language="Português brasileiro",
        output_path=Path("/tmp/aula.srt"),
        output_exists=False,
    )
    qtbot.addWidget(dialog)
    dialog.show()

    qtbot.mouseClick(dialog.back_button, __import__("PySide6").QtCore.Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Rejected


def test_job_confirmation_requires_explicit_start(qtbot) -> None:
    dialog = JobConfirmationDialog(
        source_label="aula.mp4",
        source_language="Português brasileiro",
        target_language="Inglês",
        output_path=Path("/tmp/aula.srt"),
        output_exists=False,
    )
    qtbot.addWidget(dialog)
    dialog.show()

    qtbot.mouseClick(dialog.confirm_button, __import__("PySide6").QtCore.Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted


def test_preferences_dialog_returns_edited_values(qtbot, tmp_path: Path) -> None:
    dialog = PreferencesDialog(UiPreferences(output_dir=tmp_path))
    qtbot.addWidget(dialog)

    dialog.theme_combo.setCurrentIndex(dialog.theme_combo.findData("dark"))
    dialog.language_combo.setCurrentIndex(
        dialog.language_combo.findData(Language.ENGLISH.value)
    )
    dialog.output_dir_edit.setText(str(tmp_path / "new-output"))
    dialog.log_expanded_check.setChecked(False)

    preferences = dialog.preferences

    assert preferences.theme == "dark"
    assert preferences.target_language is Language.ENGLISH
    assert preferences.output_dir == tmp_path / "new-output"
    assert preferences.log_expanded is False
