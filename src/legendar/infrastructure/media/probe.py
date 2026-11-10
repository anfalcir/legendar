"""Adaptador de inspeção de mídia baseado em ``ffprobe``.

O processo externo é injetável para que a suíte rode sem FFmpeg. A execução
normal usa ``Popen.communicate(timeout=...)`` em pequenos intervalos, permitindo
encerrar o subprocesso quando o token de cancelamento é sinalizado.
"""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from legendar.application.ports.protocols import CancellationToken
from legendar.domain.entities.media import MediaInfo, MediaSource
from legendar.domain.errors.catalog import InvalidInputError, MediaToolError
from legendar.infrastructure.media.ffprobe import parse_ffprobe_document

Runner = Callable[..., subprocess.CompletedProcess[str]]
ProcessFactory = Callable[..., subprocess.Popen[str]]
DEFAULT_TIMEOUT_SECONDS = 60.0
_CANCEL_POLL_INTERVAL_SECONDS = 0.1
_TERMINATE_GRACE_SECONDS = 2.0


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
        str(Path(media_path).expanduser().resolve()),
    ]


def _stop_process(process: subprocess.Popen[str]) -> None:
    """Encerra o processo sem deixá-lo órfão ou bloqueado nos pipes."""
    if process.poll() is not None:
        return
    try:
        process.terminate()
    except ProcessLookupError:
        return
    try:
        process.communicate(timeout=_TERMINATE_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except ProcessLookupError:
            return
        process.communicate()


class FfprobeInspector:
    """Implementação de ``MediaInspector`` com ffprobe do PATH."""

    __slots__ = ("_binary", "_runner", "_process_factory", "_timeout")

    def __init__(
        self,
        binary: str = "ffprobe",
        *,
        runner: Runner | None = None,
        process_factory: ProcessFactory = subprocess.Popen,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if timeout <= 0:
            raise ValueError("O timeout do ffprobe deve ser positivo.")
        self._binary = binary
        # Runner é uma seam determinística para testes; produção usa Popen,
        # que permite polling e encerramento cooperativo do subprocesso.
        self._runner = runner
        self._process_factory = process_factory
        self._timeout = timeout

    def _run_process(
        self, command: list[str], token: CancellationToken | None
    ) -> subprocess.CompletedProcess[str]:
        process = self._process_factory(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        deadline = time.monotonic() + self._timeout
        while True:
            if token is not None and token.is_cancelled:
                _stop_process(process)
                token.raise_if_cancelled()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _stop_process(process)
                raise subprocess.TimeoutExpired(command, self._timeout)
            try:
                stdout, stderr = process.communicate(
                    timeout=min(_CANCEL_POLL_INTERVAL_SECONDS, remaining)
                )
                break
            except subprocess.TimeoutExpired:
                continue
        return subprocess.CompletedProcess(
            args=command,
            returncode=process.returncode or 0,
            stdout=stdout,
            stderr=stderr,
        )

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
        media_path = Path(source.location).expanduser().resolve()
        if not media_path.is_file():
            raise InvalidInputError(f"Arquivo de mídia não encontrado: {media_path}")

        command = build_ffprobe_command(self._binary, media_path)
        try:
            if self._runner is not None:
                completed = self._runner(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=self._timeout,
                    check=False,
                )
            else:
                completed = self._run_process(command, token)
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
