"""Máquina de estados explícita do pipeline.

A máquina é *pura*: não conhece Qt, threads ou I/O. Ela é a autoridade formal
sobre quais transições são válidas e serve de base para o controlador de job.
Estados e tabela de transições derivam do plano mestre (seções 4.2 e 3.2 do
handoff) com refinamentos documentados abaixo.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from legendar.domain.errors.catalog import InvalidTransitionError


class JobState(str, Enum):
    """Estados observáveis do trabalho único da aplicação."""

    IDLE = "idle"
    VALIDATING_INPUT = "validating_input"
    INSPECTING_MEDIA = "inspecting_media"
    PREPARING_AUDIO = "preparing_audio"
    TRANSCRIBING = "transcribing"
    ALIGNING = "aligning"
    SEGMENTING = "segmenting"
    TRANSLATING = "translating"
    VALIDATING_SRT = "validating_srt"
    PUBLISHING = "publishing"
    COMPLETED = "completed"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        return self in {JobState.COMPLETED, JobState.CANCELLED, JobState.FAILED}

    @property
    def is_active(self) -> bool:
        """Estado com trabalho em andamento (bloqueia o início de outro job)."""
        return self in {
            JobState.VALIDATING_INPUT,
            JobState.INSPECTING_MEDIA,
            JobState.PREPARING_AUDIO,
            JobState.TRANSCRIBING,
            JobState.ALIGNING,
            JobState.SEGMENTING,
            JobState.TRANSLATING,
            JobState.VALIDATING_SRT,
            JobState.PUBLISHING,
        }

    @property
    def is_cancellable(self) -> bool:
        """Estados em que um pedido de cancelamento cooperativo é aceito.

        ``PUBLISHING`` não é cancelável: a troca atômica é o ponto de não retorno.
        ``CANCELLING`` já teve o pedido aceito e não deve recebê-lo novamente.
        """
        return self.is_active and self is not JobState.PUBLISHING

    @property
    def label_pt(self) -> str:
        return _LABELS_PT[self]


_LABELS_PT: dict[JobState, str] = {
    JobState.IDLE: "Aguardando",
    JobState.VALIDATING_INPUT: "Validando entrada",
    JobState.INSPECTING_MEDIA: "Inspecionando mídia",
    JobState.PREPARING_AUDIO: "Preparando áudio",
    JobState.TRANSCRIBING: "Transcrevendo",
    JobState.ALIGNING: "Alinhando",
    JobState.SEGMENTING: "Segmentando",
    JobState.TRANSLATING: "Traduzindo",
    JobState.VALIDATING_SRT: "Validando SRT",
    JobState.PUBLISHING: "Publicando",
    JobState.COMPLETED: "Concluído",
    JobState.CANCELLING: "Cancelando",
    JobState.CANCELLED: "Cancelado",
    JobState.FAILED: "Falha",
}


#: Sequência normal do pipeline (sem desvios de cancelamento/falha).
PIPELINE_SEQUENCE: tuple[JobState, ...] = (
    JobState.VALIDATING_INPUT,
    JobState.INSPECTING_MEDIA,
    JobState.PREPARING_AUDIO,
    JobState.TRANSCRIBING,
    JobState.ALIGNING,
    JobState.SEGMENTING,
    JobState.TRANSLATING,
    JobState.VALIDATING_SRT,
    JobState.PUBLISHING,
    JobState.COMPLETED,
)

#: Estados alcançáveis diretamente do IDLE ao iniciar um job.
_STARTABLE = {JobState.VALIDATING_INPUT}

#: Sucessores permitidos em fluxo normal. ``TRANSLATING`` pode ser pulado
#: (tradução opcional) e ``SEGMENTING`` aceita ``VALIDATING_SRT`` direto.
_SUCCESSORS: dict[JobState, frozenset[JobState]] = {
    JobState.IDLE: frozenset(_STARTABLE),
    JobState.VALIDATING_INPUT: frozenset({JobState.INSPECTING_MEDIA}),
    JobState.INSPECTING_MEDIA: frozenset({JobState.PREPARING_AUDIO}),
    JobState.PREPARING_AUDIO: frozenset({JobState.TRANSCRIBING}),
    JobState.TRANSCRIBING: frozenset({JobState.ALIGNING}),
    JobState.ALIGNING: frozenset({JobState.SEGMENTING}),
    JobState.SEGMENTING: frozenset({JobState.TRANSLATING, JobState.VALIDATING_SRT}),
    JobState.TRANSLATING: frozenset({JobState.VALIDATING_SRT}),
    JobState.VALIDATING_SRT: frozenset({JobState.PUBLISHING}),
    JobState.PUBLISHING: frozenset({JobState.COMPLETED}),
    JobState.COMPLETED: frozenset(),
    JobState.CANCELLING: frozenset({JobState.CANCELLED}),
    JobState.CANCELLED: frozenset(),
    JobState.FAILED: frozenset(),
}

#: Estados a partir dos quais o trabalho pode ser reiniciado (IDLE/terminais).
_RESTARTABLE_FROM = {
    JobState.IDLE,
    JobState.COMPLETED,
    JobState.CANCELLED,
    JobState.FAILED,
}


def can_transition(source: JobState, target: JobState) -> bool:
    """``True`` se ``source -> target`` é válida segundo as regras do produto."""
    if source == target:
        return False
    # Cancelamento cooperativo a partir de qualquer etapa cancelável.
    if target == JobState.CANCELLING:
        return source.is_cancellable
    # Falha a partir de qualquer etapa ativa (exceto publicação já confirmada).
    if target == JobState.FAILED:
        return source == JobState.PUBLISHING or source.is_active
    # Reinício explícito a partir de estado ocioso ou terminal.
    if target == JobState.VALIDATING_INPUT:
        return source in _RESTARTABLE_FROM and source != JobState.VALIDATING_INPUT
    return target in _SUCCESSORS.get(source, frozenset())


@dataclass(frozen=True, slots=True)
class Transition:
    source: JobState
    target: JobState
    reason: str | None = None


class StateMachine:
    """Guarda o estado atual e valida transições de forma determinística.

    Não é thread-safe por si só; o controlador de job serializa o acesso.
    """

    def __init__(self, initial: JobState = JobState.IDLE) -> None:
        self._state = initial
        self._history: list[Transition] = []

    @property
    def state(self) -> JobState:
        return self._state

    @property
    def history(self) -> tuple[Transition, ...]:
        return tuple(self._history)

    def can(self, target: JobState) -> bool:
        return can_transition(self._state, target)

    def transition(self, target: JobState, *, reason: str | None = None) -> Transition:
        if not self.can(target):
            raise InvalidTransitionError(
                f"Transição inválida: {self._state.value} -> {target.value}"
            )
        change = Transition(source=self._state, target=target, reason=reason)
        self._history.append(change)
        self._state = target
        return change

    def reset(self) -> None:
        """Volta a ``IDLE`` descartando histórico.

        Usado apenas pelo controlador após limpeza confirmada do job.
        """
        self._state = JobState.IDLE
        self._history.clear()
