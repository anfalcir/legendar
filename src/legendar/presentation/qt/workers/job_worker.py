"""Execução do job em thread de trabalho, sem tocar em widgets.

O ``JobWorker`` é o único ponto que roda na thread secundária. Ele traduz o
callback de eventos do controlador em um sinal Qt; nenhum método de widget é
chamado nesta classe.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

from legendar.application.job.context import JobContext
from legendar.application.job.controller import JobController
from legendar.application.pipeline.serial_pipeline import JobRequest, SerialPipeline


class JobWorker(QObject):
    """Roda ``JobController.run`` e reemite eventos para a thread da UI.

    O controlador recebe ``event_received.emit`` como destino de eventos: o
    sinal é a única travessia entre a thread de trabalho e a UI.
    """

    event_received = Signal(object)
    completed = Signal()

    def __init__(
        self,
        pipeline: SerialPipeline,
        request: JobRequest,
        context: JobContext,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._request = request
        self._context = context
        self._controller = JobController(\n            pipeline, self.event_received.emit, context=context\n        )

    @property
    def controller(self) -> JobController:
        return self._controller

    @Slot()
    def run(self) -> None:
        """Ponto de entrada da thread; garante ``completed`` mesmo em erro."""
        try:
            self._controller.run(self._request, self._context)
        finally:
            self.completed.emit()

    @Slot()
    def request_cancel(self) -> None:
        """Sinaliza cancelamento cooperativo (seguro em qualquer thread)."""
        self._controller.cancel()
