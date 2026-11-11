"""Medidas dos popups de combo com o respiro aplicado pelo QSS (achado 3)."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QComboBox, QStyleOptionViewItem

from legendar.presentation.qt.widgets import COMBO_ITEM_MIN_HEIGHT, prepare_combo

pytestmark = pytest.mark.gui


def _delegate_size(combo: QComboBox) -> tuple[int, int]:
    index = combo.model().index(0, 0)
    size = combo.itemDelegate().sizeHint(QStyleOptionViewItem(), index)
    return size.width(), size.height()


def test_combo_rows_are_at_least_the_qss_minimum_height(qtbot) -> None:
    combo = prepare_combo(QComboBox())
    qtbot.addWidget(combo)
    combo.addItem("Português (BR)")

    _width, height = _delegate_size(combo)

    assert height >= COMBO_ITEM_MIN_HEIGHT


def test_combo_popup_width_covers_the_longest_label_with_padding(qtbot) -> None:
    combo = prepare_combo(QComboBox())
    qtbot.addWidget(combo)
    combo.addItem("Detectar automaticamente")
    combo.addItem("Português (BR)")

    metrics = combo.fontMetrics()
    longest = metrics.horizontalAdvance("Detectar automaticamente")
    width, _height = _delegate_size(combo)

    assert width >= longest
    assert combo.view().sizeHintForColumn(0) >= longest


def test_prepare_combo_keeps_labels_fully_visible(qtbot) -> None:
    combo = prepare_combo(QComboBox())
    qtbot.addWidget(combo)
    combo.addItem("Detectar automaticamente")

    assert combo.view().textElideMode().name == "ElideNone"
