from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

import pytest

from legendar.domain.entities.media import MediaKind, MediaSource
from legendar.infrastructure.media.ffmpeg import FfmpegAudioPreparer
from legendar.infrastructure.media.probe import FfprobeInspector

pytestmark = pytest.mark.integration


@pytest.fixture
def media_tools() -> tuple[str, str]:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("FFmpeg e ffprobe não estão instalados neste ambiente.")
    return ffmpeg, ffprobe


def _run(command: list[str]) -> None:
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    if result.returncode != 0:
        pytest.fail(f"Falha ao criar fixture FFmpeg: {result.stderr[-2000:]}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def test_real_media_inspection_selects_default_and_normalizes_preserving_offset(
    tmp_path: Path,
    media_tools: tuple[str, str],
) -> None:
    ffmpeg, _ffprobe = media_tools
    source = tmp_path / "duas-faixas.mkv"
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
            "sine=frequency=440:duration=3.0",
            "-itsoffset",
            "1.25",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=880:duration=3.0",
            "-map",
            "0:a:0",
            "-map",
            "1:a:0",
            "-c:a",
            "pcm_s16le",
            "-disposition:a:0",
            "0",
            "-disposition:a:1",
            "default",
            str(source),
        ]
    )
    source_hash = _sha256(source)
    inspector = FfprobeInspector()
    info = inspector.inspect(
        MediaSource(kind=MediaKind.LOCAL_FILE, location=str(source))
    )

    assert len(info.audio_streams) == 2
    selected = info.default_stream()
    assert selected.index == 1
    assert selected.is_default
    assert selected.start_time_seconds == pytest.approx(1.25, abs=0.03)
    assert selected.offset_source in {
        "stream.start_time",
        "stream.start_pts*time_base",
    }

    destination = tmp_path / "job" / "normalized.wav"
    asset = FfmpegAudioPreparer(inspector=inspector).prepare(
        str(source),
        stream=selected,
        destination_path=str(destination),
    )

    normalized_info = inspector.inspect(
        MediaSource(kind=MediaKind.LOCAL_FILE, location=str(destination))
    )
    normalized = normalized_info.default_stream()

    assert destination.is_file()
    assert normalized.codec == "pcm_s16le"
    assert normalized.sample_rate_hz == 16_000
    assert normalized.channels == 1
    assert asset.duration_seconds == pytest.approx(
        normalized_info.duration_seconds, rel=0.01
    )
    assert asset.timeline_start_seconds == pytest.approx(1.25, abs=0.03)
    assert asset.timeline_offset_source == selected.offset_source
    assert source.is_file()
    assert _sha256(source) == source_hash


def test_explicit_non_default_stream_is_respected_by_ffmpeg(
    tmp_path: Path,
    media_tools: tuple[str, str],
) -> None:
    ffmpeg, _ffprobe = media_tools
    source = tmp_path / "duas-faixas.mkv"
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
            "sine=frequency=440:duration=2.0",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=880:duration=2.0",
            "-map",
            "0:a:0",
            "-map",
            "1:a:0",
            "-c:a",
            "pcm_s16le",
            "-disposition:a:0",
            "0",
            "-disposition:a:1",
            "default",
            str(source),
        ]
    )
    inspector = FfprobeInspector()
    info = inspector.inspect(
        MediaSource(kind=MediaKind.LOCAL_FILE, location=str(source))
    )
    non_default = info.audio_streams[0]
    assert not non_default.is_default

    destination = tmp_path / "job" / "alternate.wav"
    asset = FfmpegAudioPreparer(inspector=inspector).prepare(
        str(source),
        stream=non_default,
        destination_path=str(destination),
    )

    assert asset.sample_rate_hz == 16_000
    assert asset.channels == 1
    assert destination.is_file()
