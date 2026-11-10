"""Normalização real de áudio via FFmpeg, com offset preservado separadamente."""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO

from legendar.application.ports.protocols import CancellationToken, ProgressSink
from legendar.domain.entities.media import (
    AudioAsset,
    AudioStreamInfo,
    MediaKind,
    MediaSource,
)
from legendar.domain.errors.catalog import (
    InvalidInputError,
    JobCancelledError,
    MediaToolError,
    UnsupportedMediaError,
)
from legendar.infrastructure.media.probe import FfprobeInspector

ProcessFactory = Callable[..., subprocess.Popen[bytes]]

DEFAULT_TIMEOUT_SECONDS = 1800.0
_POLL_INTERVAL_SECONDS = 0.1
_TERMINATE_GRACE_SECONDS = 2.0
_STDERR_TAIL_BYTES = 4000


def build_ffmpeg_command(
    binary: str,
    media_path: str | Path,
    stream_index: int,
    output_path: str | Path,
) -> list[str]:
    """Constrói um comando sem shell, mapeando o índice global do stream."""

    if stream_index < 0:
        raise InvalidInputError("Índice de faixa de áudio inválido.")
    return [
        binary,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-n",
        "-i",
        str(media_path),
        "-map",
        f"0:{stream_index}",
        "-vn",
        "-sn",
        "-dn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        "-map_metadata",
        "-1",
        "-f",
        "wav",
        str(output_path),
    ]


def _tail(handle: BinaryIO) -> str:
    try:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        handle.seek(max(0, size - _STDERR_TAIL_BYTES))
        value = handle.read(_STDERR_TAIL_BYTES)
    except OSError:
        return ""
    return value.decode("utf-8", errors="replace").strip()


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    """Interrompe e aguarda o FFmpeg, sem deixar subprocesso órfão."""

    if process.poll() is not None:
        return
    try:
        process.terminate()
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=_TERMINATE_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except ProcessLookupError:
            return
        process.wait()


class FfmpegAudioPreparer:
    """Produz WAV PCM mono 16 kHz e mantém a origem temporal no AudioAsset.

    O FFmpeg grava primeiro em um caminho único no diretório de destino.
    Somente depois de o WAV passar pela inspeção de formato o arquivo é
    publicado com os.replace. O arquivo original nunca é modificado.
    """

    __slots__ = ("_binary", "_inspector", "_process_factory", "_timeout")

    def __init__(
        self,
        binary: str = "ffmpeg",
        *,
        inspector: FfprobeInspector | None = None,
        process_factory: ProcessFactory = subprocess.Popen,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if timeout <= 0:
            raise ValueError("O timeout do FFmpeg deve ser positivo.")
        self._binary = binary
        self._inspector = inspector or FfprobeInspector()
        self._process_factory = process_factory
        self._timeout = timeout

    def prepare(
        self,
        media_path: str,
        *,
        stream: AudioStreamInfo,
        destination_path: str,
        token: CancellationToken | None = None,
        progress: ProgressSink | None = None,
    ) -> AudioAsset:
        if token is not None:
            token.raise_if_cancelled()

        source_path = Path(media_path).expanduser().resolve()
        if not source_path.is_file():
            raise InvalidInputError(f"Arquivo de mídia não encontrado: {source_path}")

        destination = Path(destination_path).expanduser()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination = destination.resolve()
        if destination == source_path:
            raise InvalidInputError(
                "O áudio normalizado não pode sobrescrever a mídia original."
            )
        if destination.exists():
            raise InvalidInputError(
                f"O destino do áudio normalizado já existe: {destination}"
            )

        temporary = destination.with_name(
            f".{destination.stem}.{uuid.uuid4().hex}.partial{destination.suffix or '.wav'}"
        )
        command = build_ffmpeg_command(
            self._binary, source_path, stream.index, temporary
        )
        try:
            self._run(command, token)
            if token is not None:
                token.raise_if_cancelled()
            asset = self._validate_output(temporary, stream, token=token)
            if token is not None:
                token.raise_if_cancelled()
            # Hard-link publication is atomic and fails if another process
            # created the destination after the initial existence check.
            os.link(temporary, destination)
            try:
                temporary.unlink()
            except OSError:
                destination.unlink(missing_ok=True)
                raise
            if progress is not None:
                progress.report(1.0, "Áudio normalizado e validado")
            return AudioAsset(
                path=str(destination),
                sample_rate_hz=asset.sample_rate_hz,
                channels=asset.channels,
                sample_format=asset.sample_format,
                duration_seconds=asset.duration_seconds,
                timeline_start_seconds=stream.start_time_seconds,
                timeline_offset_source=stream.offset_source,
            )
        except (
            InvalidInputError,
            JobCancelledError,
            MediaToolError,
            UnsupportedMediaError,
        ):
            temporary.unlink(missing_ok=True)
            raise
        except FileExistsError as exc:
            temporary.unlink(missing_ok=True)
            raise InvalidInputError(
                "O destino do áudio normalizado foi criado durante o processamento."
            ) from exc
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise MediaToolError(
                "Não foi possível publicar o áudio normalizado no workspace.",
                technical_detail=str(exc),
            ) from exc
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    def _run(
        self, command: list[str], token: CancellationToken | None
    ) -> None:
        with tempfile.TemporaryFile(mode="w+b") as stderr_file:
            try:
                process = self._process_factory(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=stderr_file,
                )
            except FileNotFoundError as exc:
                raise MediaToolError(
                    "O FFmpeg não foi encontrado. Instale FFmpeg e tente novamente.",
                    technical_detail=str(exc),
                ) from exc
            except OSError as exc:
                raise MediaToolError(
                    "Não foi possível iniciar o FFmpeg.",
                    technical_detail=str(exc),
                ) from exc

            deadline = time.monotonic() + self._timeout
            try:
                while True:
                    if token is not None and token.is_cancelled:
                        _stop_process(process)
                        token.raise_if_cancelled()
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        _stop_process(process)
                        raise MediaToolError(
                            "O FFmpeg excedeu o tempo limite ao normalizar o áudio."
                        )
                    try:
                        process.wait(
                            timeout=min(_POLL_INTERVAL_SECONDS, remaining)
                        )
                        break
                    except subprocess.TimeoutExpired:
                        continue
            except JobCancelledError:
                raise

            if process.returncode != 0:
                detail = _tail(stderr_file)
                raise MediaToolError(
                    "O FFmpeg não conseguiu normalizar a faixa de áudio selecionada.",
                    technical_detail=detail[-_STDERR_TAIL_BYTES:]
                    or f"código {process.returncode}",
                )

    def _validate_output(
        self,
        path: Path,
        source_stream: AudioStreamInfo,
        *,
        token: CancellationToken | None = None,
    ) -> AudioAsset:
        if not path.is_file() or path.stat().st_size <= 44:
            raise MediaToolError("O FFmpeg não produziu um WAV válido.")

        info = self._inspector.inspect(
            MediaSource(kind=MediaKind.LOCAL_FILE, location=str(path)),
            token=token,
        )
        if not info.has_audio or info.video_streams_count:
            raise UnsupportedMediaError(
                "O artefato normalizado não contém somente áudio."
            )
        normalized = info.default_stream()
        if normalized.codec != "pcm_s16le":
            raise UnsupportedMediaError(
                f"Codec WAV inesperado após normalização: {normalized.codec}."
            )
        if normalized.sample_rate_hz != 16_000 or normalized.channels != 1:
            raise UnsupportedMediaError(
                "O áudio normalizado precisa ser PCM mono a 16 kHz."
            )
        if info.duration_seconds is None or info.duration_seconds <= 0:
            raise UnsupportedMediaError(
                "O ffprobe não conseguiu confirmar a duração do WAV normalizado."
            )

        return AudioAsset(
            path=str(path),
            sample_rate_hz=normalized.sample_rate_hz,
            channels=normalized.channels,
            sample_format=normalized.codec,
            duration_seconds=info.duration_seconds,
            timeline_start_seconds=source_stream.start_time_seconds,
            timeline_offset_source=source_stream.offset_source,
        )
