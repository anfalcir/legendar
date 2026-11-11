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


PRIVATE_DIRECTORY_MODE = 0o700


def ensure_private_directory(path: Path) -> Path:
    """Cria ``path`` e garante que só o dono possa listar/escrever.

    Bibliotecas de terceiros recusam cache compartilhado: o NLTK 3.10 aborta o
    ``download`` quando o diretório tem permissão de grupo, e o cache do produto
    nascia com ``0o775`` por causa do ``umask 002`` de algumas distribuições. A
    correção é explícita: cria com ``0o700`` e corrige diretórios já existentes.
    """

    path.mkdir(parents=True, exist_ok=True)
    try:
        current = path.stat().st_mode & 0o777
        if current & 0o077:
            path.chmod(PRIVATE_DIRECTORY_MODE)
    except OSError:
        # Sem permissão para ajustar: o chamador decide o que fazer; não
        # escondemos o problema nem derrubamos a aplicação por causa disso.
        return path
    return path
