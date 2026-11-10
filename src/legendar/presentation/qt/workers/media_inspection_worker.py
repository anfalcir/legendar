"""Inspeção prévia de mídia fora da thread da interface."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

from legendar.application.job.context import CancellationTokenImpl
from legendar.application.ports.protocols import MediaInspector
from legendar.domain.entities.media import MediaInfo, MediaSource


class MediaInspectionWorker(QObject):
    """Executa ffprobe e retorna somente dados de domínio por sinais Qt."""

    completed = Signal(object)
    failed = Signal(object)
    finished = Signal()

    def __init__(
        self,
        inspector: MediaInspector,
        source: MediaSource,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._inspector = inspector
        self._source = source
        self._token = CancellationTokenImpl()

    def request_cancel(self) -> bool:
        return self._token.cancel("Inspeção cancelada pelo usuário.")

    @Slot()
    def run(self) -> None:
        try:
            self._token.raise_if_cancelled()
            info: MediaInfo = self._inspector.inspect(
                self._source, token=self._token
            )
            self._token.raise_if_cancelled()
        except Exception as exc:  # noqa: BLE001 - fronteira de ferramenta externa
            self.failed.emit(exc)
        else:
            self.completed.emit(info)
        finally:
            self.finished.emit()
