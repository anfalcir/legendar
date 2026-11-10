"""Cache local de modelos de fala, somente leitura do ponto de vista do job.

Política de segurança:
* o cache é compartilhado entre jobs e **nunca** é removido por cancelamento,
  falha ou limpeza de diretório de trabalho;
* esta classe não expõe operação de exclusão — limpeza é uma decisão manual,
  fora do ciclo de vida do job;
* nomes de modelo não podem escapar do diretório raiz.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


def _tree_size(path: Path) -> int:
    """Soma o tamanho dos arquivos sob ``path``; ``0`` se não existir."""
    if path.is_file():
        return path.stat().st_size
    if not path.is_dir():
        return 0
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            total += child.stat().st_size
    return total


@dataclass(frozen=True, slots=True)
class CachedModel:
    """Estado observável de um modelo no cache, sem baixá-lo."""

    name: str
    path: Path
    exists: bool
    size_bytes: int = 0


class ModelCache:
    """Resolve caminhos de modelos dentro de um diretório compartilhado."""

    __slots__ = ("_root",)

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).expanduser()

    @property
    def root(self) -> Path:
        return self._root

    def path_for(self, model_name: str) -> Path:
        """Caminho canônico de ``model_name``, validado contra a raiz."""
        name = (model_name or "").strip()
        if not name:
            raise ValueError("Informe o nome do modelo.")
        if Path(name).name != name or name in {".", ".."}:
            raise ValueError("O nome do modelo não pode conter caminhos.")
        resolved = (self._root / name).resolve()
        root = self._root.resolve()
        if resolved != root and root not in resolved.parents:
            raise ValueError("O modelo resolveria para fora do cache.")
        return resolved

    def describe(self, model_names: tuple[str, ...] = ()) -> tuple[CachedModel, ...]:
        """Descreve os modelos pedidos (ou o conteúdo atual da raiz)."""
        names = model_names
        if not names and self._root.is_dir():
            names = tuple(
                sorted(entry.name for entry in self._root.iterdir() if entry.is_dir())
            )
        described: list[CachedModel] = []
        for name in names:
            path = self.path_for(name)
            described.append(
                CachedModel(
                    name=name,
                    path=path,
                    exists=path.exists(),
                    size_bytes=_tree_size(path) if path.exists() else 0,
                )
            )
        return tuple(described)

    def ensure_root(self) -> Path:
        """Cria a raiz do cache, sem tocar no conteúdo existente."""
        self._root.mkdir(parents=True, exist_ok=True)
        return self._root
