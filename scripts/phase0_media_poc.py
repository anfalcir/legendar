#!/usr/bin/env python3
"""Phase 0 media-container and timeline preservation proof of concept.

The normalizer produces a mono 16 kHz PCM WAV for downstream speech models,
while preserving the selected source audio stream's presentation offset as
metadata. It never silently folds that offset into local word timestamps.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
import tempfile
from fractions import Fraction
from pathlib import Path
from typing import Any, Sequence


class MediaProbeError(RuntimeError):
    """Raised when FFmpeg/ffprobe cannot inspect or normalize the media."""


def _run(command: Sequence[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            list(command),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise MediaProbeError(f"Executable not found: {command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise MediaProbeError(f"Command timed out: {command[0]}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise MediaProbeError(
            f"Command failed ({result.returncode}): {command[0]}: {detail[-2000:]}"
        )
    return result


def _as_float(value: Any) -> float | None:
    if value in (None, "", "N/A"):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _stream_offset(stream: dict[str, Any], format_info: dict[str, Any]) -> tuple[float, str]:
    direct = _as_float(stream.get("start_time"))
    if direct is not None:
        return direct, "stream.start_time"

    start_pts = _as_float(stream.get("start_pts"))
    time_base = stream.get("time_base")
    if start_pts is not None and isinstance(time_base, str) and "/" in time_base:
        try:
            return float(start_pts * Fraction(time_base)), "stream.start_pts*time_base"
        except (ValueError, ZeroDivisionError):
            pass

    container_start = _as_float(format_info.get("start_time"))
    if container_start is not None:
        return container_start, "format.start_time_fallback"
    return 0.0, "assumed_zero_missing_source_timestamp"


def probe_media(
    media_path: Path,
    ffprobe: str = "ffprobe",
) -> dict[str, Any]:
    """Inspect container and streams; use global stream index for mapping."""
    if not media_path.is_file():
        raise MediaProbeError(f"Input media does not exist: {media_path}")

    result = _run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_format",
            "-show_streams",
            "-of",
            "json",
            str(media_path),
        ]
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise MediaProbeError("ffprobe returned invalid JSON") from exc

    streams = payload.get("streams")
    if not isinstance(streams, list):
        raise MediaProbeError("ffprobe output does not contain a stream list")

    audio_streams = [
        stream
        for stream in streams
        if isinstance(stream, dict) and stream.get("codec_type") == "audio"
    ]
    if not audio_streams:
        raise MediaProbeError("Input has no audio stream")

    default_stream = next(
        (stream for stream in audio_streams if stream.get("disposition", {}).get("default") == 1),
        audio_streams[0],
    )
    format_info = payload.get("format") if isinstance(payload.get("format"), dict) else {}
    offset, offset_source = _stream_offset(default_stream, format_info)

    return {
        "path": str(media_path),
        "format_name": format_info.get("format_name"),
        "container_start_time_seconds": _as_float(format_info.get("start_time")),
        "container_duration_seconds": _as_float(format_info.get("duration")),
        "audio_stream_count": len(audio_streams),
        "selected_audio_stream": {
            "index": int(default_stream["index"]),
            "codec_name": default_stream.get("codec_name"),
            "sample_rate": int(default_stream["sample_rate"])
            if str(default_stream.get("sample_rate", "")).isdigit()
            else None,
            "channels": default_stream.get("channels"),
            "time_base": default_stream.get("time_base"),
            "start_time_seconds": offset,
            "offset_source": offset_source,
            "duration_seconds": _as_float(default_stream.get("duration")),
        },
    }


def _probe_normalized_wav(path: Path, ffprobe: str) -> dict[str, Any]:
    result = _run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "format=duration,start_time:stream=codec_name,sample_rate,channels,start_time,duration",
            "-of",
            "json",
            str(path),
        ]
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise MediaProbeError("ffprobe returned invalid normalized-WAV JSON") from exc
    streams = payload.get("streams") or []
    if not streams:
        raise MediaProbeError("Normalized WAV contains no audio stream")
    stream = streams[0]
    format_info = payload.get("format") or {}
    return {
        "codec_name": stream.get("codec_name"),
        "sample_rate": int(stream.get("sample_rate", 0)),
        "channels": int(stream.get("channels", 0)),
        "start_time_seconds": _as_float(stream.get("start_time")),
        "duration_seconds": _as_float(stream.get("duration"))
        or _as_float(format_info.get("duration")),
    }


def normalize_audio(
    media_path: Path,
    output_path: Path,
    audio_stream_index: int | None = None,
    ffmpeg: str = "ffmpeg",
    ffprobe: str = "ffprobe",
    force: bool = False,
) -> dict[str, Any]:
    """Normalize audio but retain source presentation offset separately."""
    source = probe_media(media_path, ffprobe=ffprobe)
    selected = source["selected_audio_stream"]
    stream_index = (
        int(audio_stream_index) if audio_stream_index is not None else selected["index"]
    )

    if audio_stream_index is not None:
        found = _run(
            [
                ffprobe,
                "-v",
                "error",
                "-select_streams",
                f"{audio_stream_index}",
                "-show_entries",
                "stream=index,codec_type,start_time,start_pts,time_base,duration,sample_rate,channels,codec_name",
                "-of",
                "json",
                str(media_path),
            ]
        )
        try:
            explicit = json.loads(found.stdout).get("streams", [])
        except json.JSONDecodeError as exc:
            raise MediaProbeError("Cannot inspect explicitly selected audio stream") from exc
        if not explicit or explicit[0].get("codec_type") != "audio":
            raise MediaProbeError(f"Selected stream {stream_index} is not an audio stream")
        selected = explicit[0]
        offset, offset_source = _stream_offset(selected, {})
        selected = {
            **selected,
            "index": stream_index,
            "start_time_seconds": offset,
            "offset_source": offset_source,
        }

    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists() and not force:
        raise MediaProbeError(f"Output already exists (use --force): {output_path}")

    _run(
        [
            ffmpeg,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y" if force else "-n",
            "-i",
            str(media_path),
            "-map",
            f"0:{stream_index}",
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            "-map_metadata",
            "-1",
            str(output_path),
        ],
        timeout=180,
    )
    normalized = _probe_normalized_wav(output_path, ffprobe)
    if normalized["sample_rate"] != 16000 or normalized["channels"] != 1:
        raise MediaProbeError("Normalized audio does not meet mono/16 kHz PCM contract")
    if normalized["codec_name"] != "pcm_s16le":
        raise MediaProbeError("Normalized audio is not signed 16-bit PCM")

    return {
        "source": source,
        "selected_audio_stream": selected,
        "normalized_audio": {
            "path": str(output_path),
            **normalized,
        },
        "timeline_policy": {
            "source_offset_seconds": selected["start_time_seconds"],
            "word_timestamps_are_local_to_normalized_audio": True,
            "global_timestamp_rule": (
                "source_offset_seconds + chunk_offset_seconds + local_word_timestamp"
            ),
        },
    }


def map_local_interval_to_source(
    local_start: float,
    local_end: float,
    source_offset_seconds: float,
    chunk_offset_seconds: float = 0.0,
) -> tuple[float, float]:
    values = (local_start, local_end, source_offset_seconds, chunk_offset_seconds)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Timestamp values must be finite")
    if local_start < 0 or local_end <= local_start:
        raise ValueError("Local interval must satisfy 0 <= start < end")
    global_offset = source_offset_seconds + chunk_offset_seconds
    return global_offset + local_start, global_offset + local_end


def run_self_test(ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe") -> dict[str, Any]:
    """Create deterministic media with a non-zero audio offset and verify it."""
    with tempfile.TemporaryDirectory(prefix="legendar-phase0-media-") as temporary:
        root = Path(temporary)
        source_wav = root / "source.wav"
        offset_mp4 = root / "offset-audio.mp4"
        normalized_wav = root / "normalized.wav"

        _run(
            [
                ffmpeg,
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=997:duration=2.0",
                "-ar",
                "48000",
                "-ac",
                "2",
                "-c:a",
                "pcm_s16le",
                str(source_wav),
            ]
        )
        _run(
            [
                ffmpeg,
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-itsoffset",
                "1.25",
                "-i",
                str(source_wav),
                "-map",
                "0:a:0",
                "-c:a",
                "aac",
                str(offset_mp4),
            ]
        )

        report = normalize_audio(
            offset_mp4,
            normalized_wav,
            ffmpeg=ffmpeg,
            ffprobe=ffprobe,
        )
        offset = report["timeline_policy"]["source_offset_seconds"]
        if offset < 1.0:
            raise MediaProbeError(
                f"Test media did not preserve the expected non-zero offset: {offset}"
            )

        local_start, local_end = 0.5, 1.0
        global_start, global_end = map_local_interval_to_source(
            local_start,
            local_end,
            source_offset_seconds=offset,
            chunk_offset_seconds=3.0,
        )
        if not math.isclose(global_start, offset + 3.5, abs_tol=1e-6):
            raise MediaProbeError("Global timestamp mapping is incorrect")
        if not math.isclose(global_end, offset + 4.0, abs_tol=1e-6):
            raise MediaProbeError("Global end timestamp mapping is incorrect")

        return {
            "status": "passed",
            "test_media": "synthetic 48 kHz stereo AAC in MP4 with 1.25 s input offset",
            "source_offset_seconds": offset,
            "normalized_audio": {
                "codec_name": report["normalized_audio"]["codec_name"],
                "sample_rate": report["normalized_audio"]["sample_rate"],
                "channels": report["normalized_audio"]["channels"],
                "duration_seconds": report["normalized_audio"]["duration_seconds"],
            },
            "mapping_example": {
                "source_offset_seconds": offset,
                "chunk_offset_seconds": 3.0,
                "local_interval_seconds": [local_start, local_end],
                "global_interval_seconds": [global_start, global_end],
            },
        }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prova técnica FFmpeg/ffprobe de normalização e preservação de offsets."
    )
    parser.add_argument("input", nargs="?", type=Path, help="Arquivo de áudio/vídeo de entrada.")
    parser.add_argument("--output", type=Path, help="Caminho WAV de saída mono/16 kHz PCM.")
    parser.add_argument("--stream-index", type=int, help="Índice global do stream de áudio.")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Cria mídia sintética com offset e valida o fluxo completo.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.self_test:
            report = run_self_test(args.ffmpeg, args.ffprobe)
        else:
            if args.input is None or args.output is None:
                raise MediaProbeError("Informe input e --output, ou use --self-test.")
            report = normalize_audio(
                args.input,
                args.output,
                audio_stream_index=args.stream_index,
                ffmpeg=args.ffmpeg,
                ffprobe=args.ffprobe,
                force=args.force,
            )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (MediaProbeError, ValueError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
