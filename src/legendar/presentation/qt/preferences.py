"""Preferências de apresentação persistidas sem armazenar dados privados da mídia."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QByteArray, QSettings

from legendar.domain.value_objects.language import Language

_VALID_THEMES = {"system", "light", "dark"}


@dataclass(frozen=True, slots=True)
class UiPreferences:
    """Preferências visuais e operacionais não sensíveis da janela."""

    theme: str = "system"
    output_dir: Path = Path.home()
    target_language: Language = Language.PORTUGUESE
    log_expanded: bool = False

    def __post_init__(self) -> None:
        if self.theme not in _VALID_THEMES:
            raise ValueError(f"Tema inválido: {self.theme!r}")


def load_preferences(settings: QSettings, default_output_dir: Path) -> UiPreferences:
    """Lê preferências com defaults e validação defensiva."""

    theme = str(settings.value("ui/theme", "system"))
    if theme not in _VALID_THEMES:
        theme = "system"

    language_value = str(
        settings.value("ui/target_language", Language.PORTUGUESE.value)
    )
    try:
        language = Language(language_value)
    except ValueError:
        language = Language.PORTUGUESE

    output_value = str(settings.value("paths/output_dir", str(default_output_dir)))
    output_dir = Path(output_value).expanduser()
    if not output_value.strip():
        output_dir = default_output_dir

    return UiPreferences(
        theme=theme,
        output_dir=output_dir,
        target_language=language,
        log_expanded=settings.value("ui/log_expanded", False, type=bool),
    )


def save_preferences(
    settings: QSettings,
    preferences: UiPreferences,
    *,
    geometry: QByteArray | bytes | None = None,
    maximized: bool | None = None,
) -> None:
    """Persiste somente tema, destino, idioma, log e geometria da janela.

    Caminho de mídia, conteúdo de transcrição, tokens e credenciais não fazem
    parte do contrato persistido. ``geometry`` deve ser o ``QByteArray`` de
    ``QMainWindow.saveGeometry()``; ``bytes`` continua aceito por
    compatibilidade com instalações que gravaram a forma antiga.
    """

    settings.setValue("ui/theme", preferences.theme)
    settings.setValue("ui/target_language", preferences.target_language.value)
    settings.setValue("paths/output_dir", str(preferences.output_dir))
    settings.setValue("ui/log_expanded", preferences.log_expanded)
    if geometry is not None:
        settings.setValue("window/geometry", geometry)
    if maximized is not None:
        settings.setValue("window/maximized", bool(maximized))
    settings.sync()
