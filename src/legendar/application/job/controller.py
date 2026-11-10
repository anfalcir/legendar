"""Controlador de job: dono do estado, do progresso e dos eventos.

O pipeline não conhece estado terminal nem eventos; o controlador:
* aplica as transições pela máquina de estados (única autoridade);
* garante progresso monotônico e deduplicado;
* traduz erros de domínio em ``JobFailed`` com categoria estável;
* garante que apenas **um** evento terminal seja emitido por job.

Todos os eventos de subtipo usam argumentos nomeados: ``JobEvent`` declara
``occurred_at`` entre ``sequence`` e os campos do subtipo, então posicionais
seriam ambíguos.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from legendar.application.job.context import JobContext
from legendar.application.pipeline.serial_pipeline import (
    JobRequest,
    PipelineResult,
    SerialPipeline,
)
from legendar.domain.errors.base import DomainError, ErrorCategory
from legendar.domain.errors.catalog import JobCancelledError
from legendar.domain.events.job_events import (
    JobCancelled,
    JobCompleted,
    JobEvent,
    JobFailed,
    JobStarted,
    ProgressReported,
    StateChanged,
)
from legendar.domain.state.machine import JobState, StateMachine

EventSink = Callable[[JobEvent], None]

#: Incremento mínimo de progresso para emitir um evento (evita inundar a UI).
MIN_PROGRESS_DELTA = 0.01


class JobController:
    """Orquestra um job único; não é reutilizável após o estado terminal.

    A thread que chama ``run`` é a thread de trabalho. ``cancel`` pode ser
    chamado de qualquer thread; ele apenas sinaliza o token.
    """

    def __init__(
        self,
        pipeline: SerialPipeline,
        emit: EventSink,
        *,
        min_progress_delta: float = MIN_PROGRESS_DELTA,
        context: JobContext | None = None,
    ) -> None:
        self._pipeline = pipeline
        self._emit = emit
        self._min_progress_delta = min_progress_delta
        self._lock = threading.RLock()
        self._sequence = 0
        self._machine = StateMachine()
        # O worker pode vincular o contexto antes da thread iniciar, evitando
        # perder um pedido de cancelamento recebido imediatamente após start().
        self._context = context
        self._started = False
        self._terminal_emitted = False
        self._last_progress = -1.0
        self._last_message = ""

    # -- consulta ---------------------------------------------------------

    @property
    def state(self) -> JobState:
        with self._lock:
            return self._machine.state

    @property
    def is_cancelled(self) -> bool:
        with self._lock:
            context = self._context
            return context is not None and context.token.is_cancelled

    # -- controle ---------------------------------------------------------

    def cancel(self) -> bool:
        """Solicita cancelamento; retorna ``False`` se não há job ativo."""
        with self._lock:
            context = self._context
            if context is None or self._terminal_emitted:
                return False
            state = self._machine.state
            # IDLE só aceita cancelamento quando o worker já vinculou um
            # contexto, mas ainda não entrou em run(); o token será consumido
            # na primeira fronteira segura do pipeline.
            if state is not JobState.IDLE and not state.is_cancellable:
                return False
            return context.token.cancel("Cancelado pelo usuário.")

    def run(self, request: JobRequest, context: JobContext) -> PipelineResult | None:
        """Executa o job até o fim, emitindo eventos; ``None`` se cancelado/falhou."""
        with self._lock:
            if self._started:
                raise RuntimeError("Este JobController já foi iniciado.")
            if self._context is not None and self._context is not context:
                raise ValueError(
                    "JobContext difere do contexto vinculado ao controller."
                )
            self._context = context
            self._started = True
            self._emit_event(
                JobStarted(
                    job_id=context.job_id,
                    sequence=self._next_sequence(),
                    source_label=context.source_label,
                )
            )
            self._transition(JobState.VALIDATING_INPUT)

        try:
            result = self._pipeline.execute(
                request,
                context,
                on_state=self._on_pipeline_state,
                on_progress=self.report_progress,
            )
        except JobCancelledError as exc:
            self._finish_cancelled(str(exc))
            return None
        except DomainError as exc:
            self._finish_failed(exc.category, exc.message, exc.technical_detail)
            return None
        except Exception as exc:  # noqa: BLE001 - fronteira: nenhum erro escapa
            self._finish_failed(
                ErrorCategory.UNEXPECTED,
                "Ocorreu um erro inesperado ao processar o trabalho.",
                f"{type(exc).__name__}: {exc}",
            )
            return None

        self._finish_completed(result)
        return result

    # -- transições e eventos --------------------------------------------

    def _on_pipeline_state(self, state: JobState) -> None:
        with self._lock:
            if self._terminal_emitted:
                return
            self._transition(state)

    def _transition(self, target: JobState) -> None:
        previous = self._machine.state
        self._machine.transition(target)
        self._emit_event(
            StateChanged(
                job_id=self._job_id(),
                sequence=self._next_sequence(),
                previous=previous,
                current=target,
            )
        )

    def _finish_completed(self, result: PipelineResult) -> None:
        with self._lock:
            if self._terminal_emitted:
                return
            self._transition(JobState.COMPLETED)
            self._emit_event(
                JobCompleted(
                    job_id=self._job_id(),
                    sequence=self._next_sequence(),
                    output_path=result.output_path,
                    cue_count=len(result.track.cues),
                )
            )
            self._terminal_emitted = True

    def _finish_cancelled(self, message: str) -> None:
        with self._lock:
            if self._terminal_emitted:
                return
            # A máquina exige passar por CANCELLING antes de CANCELLED.
            self._transition(JobState.CANCELLING)
            self._transition(JobState.CANCELLED)
            self._emit_event(
                JobCancelled(
                    job_id=self._job_id(),
                    sequence=self._next_sequence(),
                    message=message or "Trabalho cancelado.",
                )
            )
            self._terminal_emitted = True

    def _finish_failed(
        self, category: ErrorCategory, message: str, detail: str | None
    ) -> None:
        with self._lock:
            if self._terminal_emitted:
                return
            self._transition(JobState.FAILED)
            self._emit_event(
                JobFailed(
                    job_id=self._job_id(),
                    sequence=self._next_sequence(),
                    category=category,
                    message=message,
                    technical_detail=detail,
                )
            )
            self._terminal_emitted = True

    def report_progress(self, fraction: float, message: str = "") -> None:
        """Publica progresso monotônico, deduplicado por delta e mensagem."""
        with self._lock:
            if self._terminal_emitted:
                return
            if fraction < self._last_progress:
                return
            delta = fraction - max(self._last_progress, 0.0)
            if message == self._last_message and delta < self._min_progress_delta:
                return
            self._last_progress = fraction
            self._last_message = message
            self._emit_event(
                ProgressReported(
                    job_id=self._job_id(),
                    sequence=self._next_sequence(),
                    fraction=fraction,
                    message=message,
                )
            )

    # -- utilidades -------------------------------------------------------

    def _job_id(self) -> str:
        if self._context is None:
            raise RuntimeError("Job sem contexto.")
        return self._context.job_id

    def _next_sequence(self) -> int:
        self._sequence += 1
        return self._sequence

    def _emit_event(self, event: JobEvent) -> None:
        self._emit(event)
