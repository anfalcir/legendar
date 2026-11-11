from PySide6.QtGui import QPalette

from legendar.presentation.qt.theme import palette_for, stylesheet_for


def test_light_and_dark_stylesheets_define_the_visual_system() -> None:
    light = stylesheet_for("light")
    dark = stylesheet_for("dark")

    assert "QFrame#headerCard" in light
    assert 'QPushButton[variant="primary"]' in light
    assert "QLineEdit:focus" in light
    assert "QProgressBar::chunk" in light
    assert "#f4f6fa" in light
    assert "#111827" in dark
    assert "#9aa7ff" in dark


def test_dark_stylesheet_covers_the_surfaces_that_were_left_light() -> None:
    """Achado 1: menus, tooltips, popups e barras horizontais seguem o tema."""

    dark = stylesheet_for("dark")
    light = stylesheet_for("light")

    for stylesheet in (dark, light):
        for selector in (
            "QMenu",
            "QMenu::item:selected",
            "QToolTip",
            "QComboBox QAbstractItemView::item",
            "QScrollBar:horizontal",
            "QScrollBar::handle:horizontal",
            "QDialog#appDialog",
        ):
            assert selector in stylesheet
    assert 'QPushButton[variant="danger"]:disabled' in dark
    assert 'QPushButton[variant="ghost"]:disabled' in dark


def test_palette_is_derived_from_the_same_colors_as_the_stylesheet() -> None:
    """Achado 1: sem paleta, os controles nativos ficavam claros no escuro."""

    palette = palette_for("dark")

    assert palette.color(QPalette.ColorRole.Window).name() == "#111827"
    assert palette.color(QPalette.ColorRole.WindowText).name() == "#edf2fa"
    assert palette.color(QPalette.ColorRole.Base).name() == "#141e2d"
    assert palette.color(QPalette.ColorRole.ToolTipBase).name() == "#1b2535"
    disabled = palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text)
    assert disabled.name() == "#68768c"


def test_light_palette_matches_the_light_stylesheet() -> None:
    palette = palette_for("light")

    assert palette.color(QPalette.ColorRole.Window).name() == "#f4f6fa"
    assert palette.color(QPalette.ColorRole.Highlight).name() == "#4659d8"

