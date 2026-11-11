"""Marca do produto: ícone da janela e do aplicativo.

O SVG é o formato canônico. Quando o plugin de imagem SVG não está disponível
(instalações mínimas de Qt), um ícone equivalente é desenhado em tempo de
execução — a janela nunca fica sem identidade visual.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
)

_ASSET_DIR = Path(__file__).resolve().with_name("assets")
ICON_FILE = _ASSET_DIR / "legendar.svg"
BRAND_ACCENT = "#4659d8"
BRAND_ACCENT_DEEP = "#2b39a8"


def asset_path(name: str) -> Path:
    """Caminho de um asset da apresentação (não cria nada em disco)."""

    return _ASSET_DIR / name


def _painted_icon(size: int = 256) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        gradient = QLinearGradient(0, 0, size, size)
        gradient.setColorAt(0.0, QColor(BRAND_ACCENT))
        gradient.setColorAt(1.0, QColor(BRAND_ACCENT_DEEP))
        painter.setBrush(gradient)
        painter.setPen(Qt.PenStyle.NoPen)
        radius = size * 0.26
        painter.drawRoundedRect(
            QRectF(size * 0.06, size * 0.06, size * 0.88, size * 0.88),
            radius,
            radius,
        )
        font = QFont("DejaVu Sans")
        font.setBold(True)
        font.setPixelSize(int(size * 0.46))
        painter.setFont(font)
        painter.setPen(QPen(QColor("#ffffff")))
        painter.drawText(
            QRectF(0, -size * 0.06, size, size),
            Qt.AlignmentFlag.AlignCenter,
            "L",
        )
        bar = QPen(QColor(255, 255, 255, 215), size * 0.045)
        bar.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(bar)
        painter.drawLine(
            int(size * 0.30), int(size * 0.66), int(size * 0.70), int(size * 0.66)
        )
        painter.drawLine(
            int(size * 0.30), int(size * 0.76), int(size * 0.56), int(size * 0.76)
        )
    finally:
        painter.end()
    return pixmap


def app_icon() -> QIcon:
    """Ícone da marca, com desenho de reserva quando o SVG não carrega."""

    icon = QIcon(str(ICON_FILE))
    if icon.isNull() or icon.pixmap(64, 64).isNull():
        icon = QIcon(_painted_icon())
    return icon


def brand_pixmap(size: int) -> QPixmap:
    """Marca quadrada para cabeçalhos, sempre rasterizada em memória."""

    return _painted_icon(size)
