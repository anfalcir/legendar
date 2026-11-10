"""Escrita atômica de arquivos dentro do mesmo diretório de destino.

Regra: nunca sobrescrever o arquivo final diretamente. Escrevemos em
``.<nome>.partial`` no **mesmo** diretório (para que ``os.replace`` seja
atômico no mesmo sistema de arquivos) e só então trocamos.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write_text(
    destination: Path, content: str, *, encoding: str = "utf-8"
) -> Path:
    """Escreve ``content`` em ``destination`` de forma atômica.

    Faz ``fsync`` no temporário antes do ``replace`` para reduzir risco de
    arquivo truncado após queda do processo.
    """
    destination = destination.expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding=encoding,
            newline="\n",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".partial",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, destination)
    except BaseException:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise
    return destination
