"""Identidade visual do Legendar: temas claro, escuro e sistema."""

from __future__ import annotations

from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

_PALETTES = {
    "light": {
        "window": "#f4f6fa",
        "surface": "#ffffff",
        "surface_alt": "#f8fafc",
        "text": "#172033",
        "muted": "#68758b",
        "border": "#e1e7f0",
        "accent": "#4659d8",
        "accent_hover": "#3849c4",
        "accent_soft": "#edf0ff",
        "success": "#16845b",
        "success_soft": "#e8f6ef",
        "warning": "#a96712",
        "warning_soft": "#fff4df",
        "danger": "#bf3f50",
        "danger_hover": "#a92f40",
        "danger_soft": "#fff0f1",
        "input": "#ffffff",
        "disabled": "#aab3c2",
        "shadow": "rgba(27, 43, 72, 0.06)",
    },
    "dark": {
        "window": "#111827",
        "surface": "#1b2535",
        "surface_alt": "#202d40",
        "text": "#edf2fa",
        "muted": "#a1aec2",
        "border": "#344258",
        "accent": "#9aa7ff",
        "accent_hover": "#b1baff",
        "accent_soft": "#2e385f",
        "success": "#5bc99a",
        "success_soft": "#203f38",
        "warning": "#e8b76c",
        "warning_soft": "#4b3b26",
        "danger": "#ff8995",
        "danger_hover": "#ffabb3",
        "danger_soft": "#4a2d39",
        "input": "#141e2d",
        "disabled": "#68768c",
        "shadow": "rgba(0, 0, 0, 0.18)",
    },
}


def resolve_theme(theme: str) -> str:
    """Resolve o tema do sistema usando a paleta atual do Qt."""
    if theme in {"light", "dark"}:
        return theme
    palette = QGuiApplication.palette()
    return (
        "dark"
        if palette.color(QPalette.ColorRole.Window).lightness() < 128
        else "light"
    )


def palette_for(theme: str) -> QPalette:
    """Paleta completa do tema, incluindo os estados desabilitados.

    O QSS sozinho não alcança menus, tooltips, popups nativos e o desenho de
    alguns controles: sem paleta, o tema escuro mantém pedaços claros
    justamente nos pontos em que o usuário clica. Por isso a paleta é derivada
    das mesmas cores do QSS.
    """

    colors = _PALETTES[resolve_theme(theme)]
    role = QPalette.ColorRole
    group = QPalette.ColorGroup
    palette = QPalette()
    palette.setColor(role.Window, QColor(colors["window"]))
    palette.setColor(role.WindowText, QColor(colors["text"]))
    palette.setColor(role.Base, QColor(colors["input"]))
    palette.setColor(role.AlternateBase, QColor(colors["surface_alt"]))
    palette.setColor(role.ToolTipBase, QColor(colors["surface"]))
    palette.setColor(role.ToolTipText, QColor(colors["text"]))
    palette.setColor(role.Text, QColor(colors["text"]))
    palette.setColor(role.PlaceholderText, QColor(colors["muted"]))
    palette.setColor(role.Button, QColor(colors["surface_alt"]))
    palette.setColor(role.ButtonText, QColor(colors["text"]))
    palette.setColor(role.BrightText, QColor("#ffffff"))
    palette.setColor(role.Light, QColor(colors["border"]))
    palette.setColor(role.Midlight, QColor(colors["border"]))
    palette.setColor(role.Mid, QColor(colors["border"]))
    palette.setColor(role.Dark, QColor(colors["muted"]))
    palette.setColor(role.Shadow, QColor(0, 0, 0, 60))
    palette.setColor(role.Highlight, QColor(colors["accent"]))
    palette.setColor(role.HighlightedText, QColor("#ffffff"))
    palette.setColor(role.Link, QColor(colors["accent"]))
    palette.setColor(role.LinkVisited, QColor(colors["accent_hover"]))
    for disabled_role in (role.WindowText, role.Text, role.ButtonText):
        palette.setColor(group.Disabled, disabled_role, QColor(colors["disabled"]))
    palette.setColor(group.Disabled, role.Base, QColor(colors["surface_alt"]))
    palette.setColor(group.Disabled, role.Button, QColor(colors["surface_alt"]))
    palette.setColor(group.Disabled, role.Highlight, QColor(colors["border"]))
    return palette


def apply_theme(theme: str) -> str:
    """Aplica estilo, paleta e QSS na aplicação inteira e devolve o tema usado.

    A aplicação é feita no ``QApplication`` — e não na janela — para que menus,
    tooltips, caixas de mensagem e popups de combo recebam o mesmo tema. O
    estilo Fusion é necessário porque os estilos nativos ignoram parte da
    paleta e deixam controles claros sobre o QSS escuro.
    """

    resolved = resolve_theme(theme)
    app = QApplication.instance()
    if isinstance(app, QApplication):
        if app.style().objectName().lower() != "fusion":
            app.setStyle("Fusion")
        app.setPalette(palette_for(resolved))
        app.setStyleSheet(stylesheet_for(resolved))
    return resolved


def stylesheet_for(theme: str) -> str:
    """Retorna o QSS completo para o tema solicitado."""
    colors = _PALETTES[resolve_theme(theme)]
    return f"""
QMainWindow#mainWindow, QDialog#appDialog {{
    background: {colors["window"]};
    color: {colors["text"]};
    font-family: "Inter", "Segoe UI", "Noto Sans", sans-serif;
    font-size: 10pt;
}}
QWidget {{
    color: {colors["text"]};
    font-family: "Inter", "Segoe UI", "Noto Sans", sans-serif;
    font-size: 10pt;
}}
QFrame#headerCard, QFrame#panel {{
    background: {colors["surface"]};
    border: 1px solid {colors["border"]};
    border-radius: 16px;
}}
QFrame#brandMark {{
    background: {colors["accent"]};
    border: 0;
    border-radius: 12px;
}}
QLabel#brandLetter {{
    color: #ffffff;
    font-size: 19pt;
    font-weight: 800;
}}
QLabel#eyebrow {{
    color: {colors["accent"]};
    font-size: 8pt;
    font-weight: 800;
    letter-spacing: 1.4px;
}}
QLabel#pageTitle {{
    color: {colors["text"]};
    font-size: 20pt;
    font-weight: 800;
}}
QLabel#pageSubtitle, QLabel#mutedText, QLabel#readinessDetail {{
    color: {colors["muted"]};
}}
QLabel#sectionTitle {{
    color: {colors["text"]};
    font-size: 12pt;
    font-weight: 750;
}}
QLabel#dialogTitle {{
    color: {colors["text"]};
    font-size: 16pt;
    font-weight: 800;
}}
QLabel#sectionSubtitle {{
    color: {colors["muted"]};
    font-size: 9pt;
}}
QLabel#fieldLabel {{
    color: {colors["muted"]};
    font-size: 8pt;
    font-weight: 750;
    letter-spacing: 0.6px;
}}
QLabel#statusPill {{
    background: {colors["success_soft"]};
    color: {colors["success"]};
    border: 1px solid {colors["border"]};
    border-radius: 10px;
    padding: 7px 11px;
    font-size: 8pt;
    font-weight: 750;
}}
QLabel#statusPill[state="warning"] {{
    background: {colors["warning_soft"]};
    color: {colors["warning"]};
}}
QLabel#statusPill[state="running"] {{
    background: {colors["accent_soft"]};
    color: {colors["accent"]};
}}
QLabel#statusPill[state="error"] {{
    background: {colors["danger_soft"]};
    color: {colors["danger"]};
}}
QLabel#statusText {{
    color: {colors["text"]};
    font-size: 10pt;
    font-weight: 650;
}}
QLabel#progressMeta {{
    color: {colors["muted"]};
    font-size: 8pt;
    font-weight: 650;
}}
QLineEdit, QComboBox {{
    background: {colors["input"]};
    color: {colors["text"]};
    border: 1px solid {colors["border"]};
    border-radius: 9px;
    padding: 10px 12px;
    min-height: 20px;
    selection-background-color: {colors["accent"]};
}}
QLineEdit:hover, QComboBox:hover {{
    border-color: {colors["accent"]};
}}
QLineEdit:focus, QComboBox:focus {{
    border: 2px solid {colors["accent"]};
    padding: 9px 11px;
}}
QLineEdit:disabled, QComboBox:disabled {{
    background: {colors["surface_alt"]};
    color: {colors["disabled"]};
    border-color: {colors["border"]};
}}
QComboBox::drop-down {{
    border: 0;
    width: 28px;
}}
QComboBox QAbstractItemView {{
    background: {colors["surface"]};
    color: {colors["text"]};
    border: 1px solid {colors["border"]};
    border-radius: 8px;
    padding: 4px;
    selection-background-color: {colors["accent_soft"]};
    selection-color: {colors["text"]};
    outline: 0;
}}
QComboBox QAbstractItemView::item {{
    min-height: 26px;
    padding: 5px 10px;
    border-radius: 6px;
}}
QComboBox QAbstractItemView::item:selected {{
    background: {colors["accent_soft"]};
    color: {colors["text"]};
}}
QPushButton {{
    background: {colors["surface_alt"]};
    color: {colors["text"]};
    border: 1px solid {colors["border"]};
    border-radius: 9px;
    padding: 10px 16px;
    min-height: 20px;
    font-weight: 700;
}}
QPushButton:hover {{
    border-color: {colors["accent"]};
    background: {colors["accent_soft"]};
}}
QPushButton:pressed {{
    padding-top: 11px;
    padding-bottom: 9px;
}}
QPushButton:disabled {{
    background: {colors["surface_alt"]};
    color: {colors["disabled"]};
    border-color: {colors["border"]};
}}
QPushButton:focus, QToolButton:focus, QCheckBox:focus {{
    border: 2px solid {colors["accent"]};
}}
QPushButton[variant="primary"] {{
    background: {colors["accent"]};
    color: #ffffff;
    border: 1px solid {colors["accent"]};
    padding: 12px 22px;
    font-size: 10pt;
}}
QPushButton[variant="primary"]:hover {{
    background: {colors["accent_hover"]};
    border-color: {colors["accent_hover"]};
}}
QPushButton[variant="primary"]:disabled {{
    background: {colors["disabled"]};
    color: {colors["surface"]};
    border-color: {colors["disabled"]};
}}
QPushButton[variant="danger"] {{
    background: {colors["danger_soft"]};
    color: {colors["danger"]};
    border: 1px solid {colors["danger"]};
}}
QPushButton[variant="danger"]:hover {{
    background: {colors["danger"]};
    color: #ffffff;
}}
QPushButton[variant="ghost"] {{
    background: transparent;
    border-color: transparent;
    color: {colors["muted"]};
}}
QPushButton[variant="ghost"]:hover {{
    background: {colors["surface_alt"]};
    color: {colors["text"]};
    border-color: {colors["border"]};
}}
QCheckBox {{
    color: {colors["text"]};
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 17px;
    height: 17px;
    border: 1px solid {colors["border"]};
    border-radius: 5px;
    background: {colors["input"]};
}}
QCheckBox::indicator:checked {{
    background: {colors["accent"]};
    border-color: {colors["accent"]};
}}
QCheckBox:disabled {{
    color: {colors["disabled"]};
}}
QProgressBar {{
    background: {colors["surface_alt"]};
    color: {colors["text"]};
    border: 1px solid {colors["border"]};
    border-radius: 7px;
    min-height: 12px;
    max-height: 12px;
    text-align: center;
}}
QProgressBar::chunk {{
    background: {colors["accent"]};
    border-radius: 6px;
}}
QPlainTextEdit {{
    background: {colors["surface_alt"]};
    color: {colors["text"]};
    border: 1px solid {colors["border"]};
    border-radius: 9px;
    padding: 10px;
    selection-background-color: {colors["accent"]};
    font-family: "JetBrains Mono", "Cascadia Mono", monospace;
    font-size: 8pt;
}}
QToolButton {{
    background: transparent;
    color: {colors["accent"]};
    border: 0;
    padding: 4px 2px;
    font-weight: 750;
}}
QToolButton:hover {{
    color: {colors["accent_hover"]};
}}
QScrollArea {{
    background: transparent;
    border: 0;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {colors["border"]};
    border-radius: 5px;
    min-height: 28px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QStatusBar {{
    background: {colors["surface"]};
    color: {colors["muted"]};
    border-top: 1px solid {colors["border"]};
}}
QDialogButtonBox QPushButton {{
    min-width: 110px;
}}
QMessageBox {{
    background: {colors["surface"]};
}}
QLabel#dialogWarning {{
    color: {colors["warning"]};
    background: {colors["warning_soft"]};
    border-radius: 8px;
    padding: 10px;
}}
QLabel#fieldHint {{
    color: {colors["muted"]};
    font-size: 8pt;
}}
QLabel#alertBanner {{
    background: {colors["danger_soft"]};
    color: {colors["danger"]};
    border: 1px solid {colors["danger"]};
    border-radius: 10px;
    padding: 11px 14px;
    font-weight: 650;
}}
QLabel#alertBanner[level="warning"] {{
    background: {colors["warning_soft"]};
    color: {colors["warning"]};
    border-color: {colors["warning"]};
}}
QLabel#alertBanner[level="info"] {{
    background: {colors["accent_soft"]};
    color: {colors["accent"]};
    border-color: {colors["accent"]};
}}
QLabel#readinessIcon {{
    font-size: 12pt;
}}
QLabel#readinessIcon[state="ok"] {{
    color: {colors["success"]};
}}
QLabel#readinessIcon[state="warning"] {{
    color: {colors["warning"]};
}}
QLabel#readinessIcon[state="error"] {{
    color: {colors["danger"]};
}}
QPushButton[variant="danger"]:disabled {{
    background: {colors["surface_alt"]};
    color: {colors["disabled"]};
    border-color: {colors["border"]};
}}
QPushButton[variant="ghost"]:disabled {{
    background: transparent;
    color: {colors["disabled"]};
    border-color: transparent;
}}
QPushButton[variant="primary"]:focus, QPushButton[variant="danger"]:focus {{
    border: 2px solid {colors["text"]};
}}
QCheckBox::indicator:checked:disabled {{
    background: {colors["disabled"]};
    border-color: {colors["disabled"]};
}}
QMenu {{
    background: {colors["surface"]};
    color: {colors["text"]};
    border: 1px solid {colors["border"]};
    border-radius: 8px;
    padding: 6px;
}}
QMenu::item {{
    padding: 6px 18px 6px 12px;
    border-radius: 6px;
}}
QMenu::item:selected {{
    background: {colors["accent_soft"]};
    color: {colors["text"]};
}}
QMenu::item:disabled {{
    color: {colors["disabled"]};
}}
QMenu::separator {{
    height: 1px;
    background: {colors["border"]};
    margin: 5px 8px;
}}
QToolTip {{
    background: {colors["surface"]};
    color: {colors["text"]};
    border: 1px solid {colors["border"]};
    border-radius: 6px;
    padding: 6px 8px;
    opacity: 240;
}}
QComboBox QAbstractItemView::item:disabled {{
    color: {colors["disabled"]};
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {colors["border"]};
    border-radius: 5px;
    min-width: 28px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}
QScrollArea > QWidget > QWidget {{
    background: {colors["window"]};
}}
QPlainTextEdit QWidget {{
    background: {colors["surface_alt"]};
}}
QStatusBar::item {{
    border: 0;
}}
QMessageBox QLabel {{
    color: {colors["text"]};
}}
"""
