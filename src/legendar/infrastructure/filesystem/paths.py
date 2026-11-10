"""Utilitários de caminho sem efeitos colaterais implícitos.

A regra de unicidade abaixo caracteriza o comportamento da baseline
(``gui/worker.py``) antes de aposentá-la: o primeiro candidato é
``<nome><sufixo>`` e, se já existir, ``<nome>_1<sufixo>``, ``_2``, ...
"""

from __future__ import annotations

from pathlib import Path


def unique_path(directory: str | Path, stem: str, suffix: str) -> Path:
    """Devolve o primeiro caminho livre em ``directory`` para ``stem + suffix``.

    A função apenas consulta a existência; não cria diretórios nem arquivos.
    Isso permite decidir o nome antes de qualquer escrita e repetir a operação
    com segurança no mesmo instante.
    """
    clean_stem = (stem or "").strip()
    if not clean_stem:
        raise ValueError("Informe um nome de arquivo.")
    if not suffix.startswith("."):
        raise ValueError("O sufixo deve começar com ponto (ex.: '.srt').")
    if Path(clean_stem).name != clean_stem:
        raise ValueError("O nome do arquivo não pode conter separadores de caminho.")

    base = Path(directory)
    candidate = base / f"{clean_stem}{suffix}"
    counter = 1
    while candidate.exists():
        candidate = base / f"{clean_stem}_{counter}{suffix}"
        counter += 1
    return candidate


def ensure_directory(path: Path) -> Path:
    """Cria ``path`` se necessário e devolve o próprio caminho."""
    path.mkdir(parents=True, exist_ok=True)
    return path
