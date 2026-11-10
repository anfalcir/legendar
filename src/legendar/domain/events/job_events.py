"""Eventos de domínio imutáveis emitidos pelo job.

Eventos são dados puros: não carregam referência a widget, callback ou thread.
A camada de apresentação os traduz em sinais Qt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from legendar.domain.errors.base import ErrorCategory
from legendar.domain.state.machine import JobState


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True, slots=True)
class JobEvent:
    """Base de todos os eventos de um job."""

    job_id: str
    sequence: int
    occurred_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        if not self.job_id:
            raise ValueError("Evento sem job_id.")
        if self.sequence < 0:
            raise ValueError("Sequência de evento não pode ser negativa.")


@dataclass(frozen=True, slots=True)
class JobStarted(JobEvent):
    source_label: str = ""


@dataclass(frozen=True, slots=True)
class StateChanged(JobEvent):
    previous: JobState = JobState.IDLE
    current: JobState = JobState.IDLE

    def __post_init__(self) -> None:
        # ``slots=True`` recria a classe, então ``super()`` sem argumentos falha;
        # a validação da base é chamada explicitamente.
        JobEvent.__post_init__(self)
        if self.previous is self.current:
            raise ValueError("StateChanged exige estados diferentes.")


@dataclass(frozen=True, slots=True)
class ProgressReported(JobEvent):
    """Progresso monotônico em ``[0, 1]`` com rótulo amigável opcional."""

    fraction: float = 0.0
    message: str = ""

    def __post_init__(self) -> None:
        JobEvent.__post_init__(self)
        if not 0.0 <= self.fraction <= 1.0:
            raise ValueError("Progresso deve estar em [0, 1].")


@dataclass(frozen=True, slots=True)
class LogRecorded(JobEvent):
    """Mensagem de log já formatada para exibição (sem dados sensíveis)."""

    level: str = "info"
    message: str = ""

    def __post_init__(self) -> None:
        JobEvent.__post_init__(self)
        if self.level not in {"debug", "info", "warning", "error"}:
            raise ValueError(f"Nível de log inválido: {self.level!r}")


@dataclass(frozen=True, slots=True)
class JobFailed(JobEvent):
    category: ErrorCategory = ErrorCategory.UNEXPECTED
    message: str = ""
    technical_detail: str | None = None


@dataclass(frozen=True, slots=True)
class JobCancelled(JobEvent):
    message: str = "Trabalho cancelado."


@dataclass(frozen=True, slots=True)
class JobCompleted(JobEvent):
    """Publicação confirmada; emitido somente após a troca atômica."""

    output_path: str = ""
    cue_count: int = 0
