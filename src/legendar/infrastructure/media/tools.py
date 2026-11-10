"""Detecção de ferramentas externas obrigatórias (ffmpeg, ffprobe, runtimes JS).

Nenhuma ferramenta é instalada silenciosamente. A detecção é injetável para
testes e nunca levanta exceção: ausência é um estado explícito consumido pelo
preflight da inicialização.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

Which = Callable[[str], str | None]
Runner = Callable[..., subprocess.CompletedProcess[str]]

_VERSION_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class ToolStatus:
    """Resultado observável da detecção de uma ferramenta externa."""

    name: str
    path: str | None = None
    version: str | None = None
    detail: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Status de ferramenta sem nome.")

    @property
    def available(self) -> bool:
        return self.path is not None

    @property
    def label_pt(self) -> str:
        if not self.available:
            return f"{self.name}: não encontrado"
        version = f" {self.version}" if self.version else ""
        return f"{self.name}:{version} ({self.path})"


def _first_line(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def read_version(
    path: str,
    *,
    runner: Runner = subprocess.run,
    timeout: float = _VERSION_TIMEOUT_SECONDS,
) -> str | None:
    """Executa ``<path> --version`` e devolve a primeira linha, se possível."""
    try:
        completed = runner(
            [path, "--version"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return _first_line(completed.stdout or completed.stderr or "")


def locate_tool(
    name: str,
    *,
    which: Which = shutil.which,
    runner: Runner = subprocess.run,
) -> ToolStatus:
    """Localiza ``name`` no PATH e tenta registrar sua versão."""
    try:
        resolved = which(name)
    except OSError as exc:  # pragma: no cover - PATH inacessível é raro
        return ToolStatus(name=name, detail=f"Falha ao consultar o PATH: {exc}")
    if not resolved:
        return ToolStatus(name=name)
    version = read_version(resolved, runner=runner)
    detail = "" if version else "Versão não pôde ser determinada por --version."
    return ToolStatus(name=name, path=resolved, version=version, detail=detail)


def locate_tools(
    names: Iterable[str],
    *,
    which: Which = shutil.which,
    runner: Runner = subprocess.run,
) -> Mapping[str, ToolStatus]:
    """Localiza várias ferramentas preservando a ordem solicitada."""
    return {name: locate_tool(name, which=which, runner=runner) for name in names}
