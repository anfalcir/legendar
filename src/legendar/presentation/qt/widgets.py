"""Ajustes de widget compartilhados por janela, diálogos e testes de GUI.

Os combos do produto são estilizados por QSS. O Qt mede o popup pelo delegate
padrão, que ignora o ``padding`` declarado no QSS: o resultado é popup estreito
(texto cortado) e linhas menores que o próprio respiro (texto sobreposto). O
delegate abaixo soma esse respiro à medida, corrigindo todas as combos de uma
vez em vez de remendar cada uma.
"""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, QSize, Qt
from PySide6.QtWidgets import QComboBox, QStyledItemDelegate, QStyleOptionViewItem

COMBO_ITEM_MIN_HEIGHT = 28
COMBO_ITEM_HORIZONTAL_PADDING = 36


class ComboItemDelegate(QStyledItemDelegate):
    """Delegate que inclui o respiro do QSS no ``sizeHint`` usado pelo popup."""

    def sizeHint(  # noqa: N802 - assinatura herdada do Qt
        self, option: QStyleOptionViewItem, index: QModelIndex
    ) -> QSize:
        size = super().sizeHint(option, index)
        return QSize(
            size.width() + COMBO_ITEM_HORIZONTAL_PADDING,
            max(size.height(), COMBO_ITEM_MIN_HEIGHT),
        )


def prepare_combo(combo: QComboBox) -> QComboBox:
    """Aplica o delegate e as políticas que evitam texto cortado no popup."""

    combo.setItemDelegate(ComboItemDelegate(combo))
    view = combo.view()
    view.setUniformItemSizes(False)
    view.setTextElideMode(Qt.TextElideMode.ElideNone)
    view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    return combo
