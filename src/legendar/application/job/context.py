"""Contexto de execução de um job: identidade, diretórios e cancelamento."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path

from legendar.domain.errors.catalog import JobCancelledError


class CancellationTokenImpl:
    """Token de cancelamento cooperativo, seguro entre threads.

    O pedido é idempotente: cancelar duas vezes não levanta erro. O consumo é
    feito por ``raise_if_cancelled`` nos pontos seguros do pipeline.
    """

    __slots__ = ("_event", "_reason")

    def __init__(self) -> None:
        self._event = threading.Event()
        self._reason: str | None = None

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    @property
    def reason(self) -> str | None:
        return self._reason

    def cancel(self, reason: str | None = None) -> bool:
        """Solicita cancelamento; retorna ``False`` se já havia sido solicitado."""
        if self._event.is_set():
            return False
        self._reason = reason
        self._event.set()
        return True

    def raise_if_cancelled(self) -> None:
        if self._event.is_set():
            raise JobCancelledError(self._reason or "Trabalho cancelado pelo usuário.")


@dataclass(frozen=True, slots=True)
class JobContext:
    """Dados imutáveis de um job em execução.

    ``work_dir`` é exclusivo do job e descartável; ``cache_dir`` é compartilhado
    (modelos) e nunca deve ser removido para cancelar um job.
    """

    job_id: str
    source_label: str
    work_dir: Path
    cache_dir: Path
    output_path: Path
    token: CancellationTokenImpl = field(default_factory=CancellationTokenImpl)

    def __post_init__(self) -> None:
        if not self.job_id:
            raise ValueError("JobContext exige job_id.")
        if self.work_dir == self.cache_dir:
            raise ValueError("Diretório de trabalho e cache devem ser distintos.")

    @property
    def audio_cache_path(self) -> Path:
        return self.work_dir / "audio.wav"

    @property
    def staged_output_path(self) -> Path:
        """Arquivo temporário usado para publicação atômica."""
        return self.output_path.with_name(f".{self.output_path.name}.partial")
