"""View model puro do job: eventos de domínio -> estado exibível.

Sem Qt, sem widgets e sem I/O. A janela apenas lê ``snapshot`` e desenha; a
regra de quais botões habilitar e qual texto mostrar fica testável aqui.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from legendar.domain.events.job_events import (
    JobCancelled,
    JobCompleted,
    JobEvent,
    JobFailed,
    JobStarted,
    LogRecorded,
    ProgressReported,
    StateChanged,
)
from legendar.domain.state.machine import JobState

MAX_LOG_LINES = 500
IDLE_STATUS = "Aguardando um arquivo de mídia."

_LEVEL_PREFIX = {
    "warning": "Aviso: ",
    "error": "Erro: ",
    "debug": "Detalhe: ",
}


def _is_running(state: JobState) -> bool:
    return state.is_active or state is JobState.CANCELLING


@dataclass(frozen=True, slots=True)
class JobViewSnapshot:
    """Estado imutável que a janela desenha a cada evento."""

    state: JobState = JobState.IDLE
    progress: float = 0.0
    status_text: str = IDLE_STATUS
    log_lines: tuple[str, ...] = ()
    output_path: str = ""
    error_message: str = ""

    @property
    def progress_percent(self) -> int:
        return int(round(self.progress * 100))

    @property
    def is_running(self) -> bool:
        return _is_running(self.state)

    @property
    def can_start(self) -> bool:
        return not self.is_running

    @property
    def can_cancel(self) -> bool:
        return self.state.is_cancellable

    @property
    def is_finished(self) -> bool:
        return self.state.is_terminal


class JobViewModel:
    """Reduz uma sequência ordenada de ``JobEvent`` a snapshots para a UI."""

    __slots__ = ("_snapshot", "_last_sequence", "_terminal_seen")

    def __init__(self) -> None:
        self._snapshot = JobViewSnapshot()
        self._last_sequence = -1
        self._terminal_seen = False

    @property
    def snapshot(self) -> JobViewSnapshot:
        return self._snapshot

    def reset(self) -> JobViewSnapshot:
        """Volta ao estado ocioso; usado antes de cada novo job."""
        self._snapshot = JobViewSnapshot()
        self._last_sequence = -1
        self._terminal_seen = False
        return self._snapshot

    def report_error(self, message: str) -> JobViewSnapshot:
        """Exibe um erro de validação local, sem iniciar um job.

        Não marca a sequência nem o estado terminal: o próximo job começa com
        ``reset()`` e o erro local não pode bloquear eventos reais.
        """
        self._snapshot = replace(
            self._snapshot,
            status_text=f"Falha: {message}",
            error_message=message,
            log_lines=_append_text(self._snapshot.log_lines, f"Erro: {message}"),
        )
        return self._snapshot

    def report_warning(self, message: str) -> JobViewSnapshot:
        """Registra um aviso operacional sem alterar o estado do processamento."""
        self._snapshot = replace(
            self._snapshot,
            log_lines=_append_text(self._snapshot.log_lines, f"Aviso: {message}"),
        )
        return self._snapshot

    def apply(self, event: JobEvent) -> JobViewSnapshot:
        """Aplica um evento fora de ordem/duplicado de forma conservadora."""
        if event.sequence <= self._last_sequence or self._terminal_seen:
            return self._snapshot
        self._last_sequence = event.sequence
        self._snapshot = self._reduce(self._snapshot, event)
        if isinstance(event, (JobCompleted, JobFailed, JobCancelled)):
            self._terminal_seen = True
        return self._snapshot

    # -- redução ----------------------------------------------------------

    def _reduce(self, snapshot: JobViewSnapshot, event: JobEvent) -> JobViewSnapshot:
        if isinstance(event, JobStarted):
            return replace(
                snapshot,
                status_text=f"Processando: {event.source_label or 'mídia'}",
                error_message="",
                output_path="",
            )
        if isinstance(event, StateChanged):
            return replace(
                snapshot, state=event.current, status_text=event.current.label_pt
            )
        if isinstance(event, ProgressReported):
            return replace(
                snapshot,
                progress=max(snapshot.progress, event.fraction),
                status_text=event.message or snapshot.status_text,
            )
        if isinstance(event, LogRecorded):
            return replace(snapshot, log_lines=_append_log(snapshot.log_lines, event))
        if isinstance(event, JobCompleted):
            return replace(
                snapshot,
                state=JobState.COMPLETED,
                progress=1.0,
                status_text=f"Legenda publicada: {event.output_path}",
                output_path=event.output_path,
                error_message="",
                log_lines=_append_text(
                    snapshot.log_lines,
                    f"Concluído com {event.cue_count} legenda(s).",
                ),
            )
        if isinstance(event, JobFailed):
            return replace(
                snapshot,
                state=JobState.FAILED,
                status_text=f"Falha: {event.message}",
                error_message=event.message,
                output_path="",
                log_lines=_append_text(snapshot.log_lines, f"Erro: {event.message}"),
            )
        if isinstance(event, JobCancelled):
            return replace(
                snapshot,
                state=JobState.CANCELLED,
                status_text=event.message or "Trabalho cancelado.",
                log_lines=_append_text(snapshot.log_lines, "Trabalho cancelado."),
            )
        return snapshot


def _append_log(lines: tuple[str, ...], event: LogRecorded) -> tuple[str, ...]:
    prefix = _LEVEL_PREFIX.get(event.level, "")
    return _append_text(lines, f"{prefix}{event.message}")


def _append_text(lines: tuple[str, ...], text: str) -> tuple[str, ...]:
    if not text:
        return lines
    return (*lines, text)[-MAX_LOG_LINES:]
