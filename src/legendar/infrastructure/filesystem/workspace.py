"""Criação e limpeza segura do diretório de trabalho por job.

Duas garantias:
1. cada job recebe um diretório exclusivo (``legendar-<uuid>``) sob uma raiz
   temporária conhecida;
2. a limpeza só remove caminhos que comprovadamente estão sob essa raiz —
   o cache de modelos nunca é tocado por cancelamento.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from legendar.application.job.context import JobContext


class UnsafeWorkspaceError(RuntimeError):
    """Tentativa de limpar um caminho fora da raiz de trabalho."""


class TempWorkspaceFactory:
    """Fábrica de ``JobContext`` com diretórios temporários exclusivos."""

    __slots__ = ("_root",)

    def __init__(self, root: Path | None = None) -> None:
        self._root = Path(root) if root is not None else Path(tempfile.gettempdir())

    @property
    def root(self) -> Path:
        return self._root

    def create(
        self,
        *,
        job_id: str,
        source_label: str,
        output_path: Path,
        cache_dir: Path,
    ) -> JobContext:
        self._root.mkdir(parents=True, exist_ok=True)
        work_dir = Path(tempfile.mkdtemp(prefix=f"legendar-{job_id}-", dir=self._root))
        try:
            return JobContext(
                job_id=job_id,
                source_label=source_label,
                work_dir=work_dir,
                cache_dir=Path(cache_dir).expanduser(),
                output_path=Path(output_path).expanduser(),
            )
        except Exception:
            # Não mascarar o erro que impediu a criação do contexto.
            shutil.rmtree(work_dir, ignore_errors=True)
            raise

    def cleanup(self, context: JobContext) -> None:
        """Remove apenas ``work_dir``, validando que está sob a raiz."""
        work_dir = context.work_dir.resolve()
        root = self._root.resolve()
        if work_dir == root or root not in work_dir.parents:
            raise UnsafeWorkspaceError(
                f"Recusa em remover diretório fora da raiz de trabalho: {work_dir}"
            )
        if not work_dir.name.startswith("legendar-"):
            raise UnsafeWorkspaceError(
                f"Recusa em remover diretório sem prefixo esperado: {work_dir}"
            )
        if work_dir == context.cache_dir.resolve():
            raise UnsafeWorkspaceError("Diretório de trabalho não pode ser o cache.")
        try:
            shutil.rmtree(work_dir)
        except FileNotFoundError:
            # A operação é idempotente; erros de permissão/I/O devem subir
            # para que a camada de apresentação registre o aviso.
            pass
