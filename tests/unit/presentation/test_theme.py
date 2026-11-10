from legendar.presentation.qt.theme import stylesheet_for


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
