"""Adaptador de inspeção de mídia baseado em ``ffprobe``.

O processo externo é injetável para que a suíte rode sem FFmpeg. O adaptador
é deliberadamente fino: valida a origem local, executa o comando, confere o
código de saída e entrega o JSON ao parser puro.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

from legendar.application.ports.protocols import CancellationToken
from legendar.domain.entities.media import MediaInfo, MediaSource
from legendar.domain.errors.catalog import InvalidInputError, MediaToolError
from legendar.infrastructure.media.ffprobe import parse_ffprobe_document

Runner = Callable[..., subprocess.CompletedProcess[str]]
DEFAULT_TIMEOUT_SECONDS = 60.0


def build_ffprobe_command(binary: str, media_path: str | Path) -> list[str]:
    """Comando canônico: JSON por stdout, sem interação e sem anexos."""
    return [
        binary,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(media_path),
    ]


class FfprobeInspector:
    """Implementação de ``MediaInspector`` com ffprobe do PATH."""

    __slots__ = ("_binary", "_runner", "_timeout")

    def __init__(
        self,
        binary: str = "ffprobe",
        *,
        runner: Runner = subprocess.run,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._binary = binary
        self._runner = runner
        self._timeout = timeout

    def inspect(
        self,
        source: MediaSource,
        *,
        token: CancellationToken | None = None,
    ) -> MediaInfo:
        if token is not None:
            token.raise_if_cancelled()
        if not source.is_local:
            raise InvalidInputError(
                "A inspeção exige um arquivo local; baixe a mídia remota antes."
            )
        media_path = Path(source.location).expanduser()
        if not media_path.is_file():
            raise InvalidInputError(f"Arquivo de mídia não encontrado: {media_path}")

        try:
            completed = self._runner(
                build_ffprobe_command(self._binary, media_path),
                capture_output=True,
                text=True,
                timeout=self._timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise MediaToolError(
                "O ffprobe não foi encontrado. Instale o FFmpeg e tente novamente.",
                technical_detail=str(exc),
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise MediaToolError(
                "O ffprobe excedeu o tempo limite ao ler a mídia."
            ) from exc
        except OSError as exc:
            raise MediaToolError(
                "Não foi possível executar o ffprobe.",
                technical_detail=str(exc),
            ) from exc

        if token is not None:
            token.raise_if_cancelled()
        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            raise MediaToolError(
                "O ffprobe não conseguiu ler a mídia selecionada.",
                technical_detail=stderr[-500:] or f"código {completed.returncode}",
            )
        return parse_ffprobe_document(completed.stdout or "", kind=source.kind)
