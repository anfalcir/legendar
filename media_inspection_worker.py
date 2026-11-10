"""Inspeção prévia de mídia em uma QThread dedicada.

A própria thread executa a inspeção e possui o token de cancelamento. Evitar
um QObject worker separado removido durante o encerramento da event loop reduz
ambiguidades de ownership/lifetime entre dois objetos Qt em threads distintas.
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from legendar.application.job.context import CancellationTokenImpl
from legendar.application.ports.protocols import MediaInspector
from legendar.domain.entities.media import MediaInfo, MediaSource


class MediaInspectionWorker(QThread):
    """Executa ffprobe fora da GUI e publica somente dados/erros de domínio."""

    completed = Signal(object)
    failed = Signal(object)

    def __init__(
        self,
        inspector: MediaInspector,
        source: MediaSource,
        parent: QThread | None = None,
    ) -> None:
        super().__init__(parent)
        self._inspector = inspector
        self._source = source
        self._token = CancellationTokenImpl()

    def request_cancel(self) -> bool:
        """Solicita cancelamento cooperativo do subprocesso ffprobe."""
        return self._token.cancel("Inspeção cancelada pelo usuário.")

    def run(self) -> None:
        try:
            self._token.raise_if_cancelled()
            info: MediaInfo = self._inspector.inspect(self._source, token=self._token)
            self._token.raise_if_cancelled()
        except Exception as exc:  # noqa: BLE001 - fronteira da ferramenta externa
            self.failed.emit(exc)
        else:
            self.completed.emit(info)
