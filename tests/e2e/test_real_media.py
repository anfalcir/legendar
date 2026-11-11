"""Fluxo completo com mídia real, FFmpeg e ffprobe.

Requer FFmpeg/ffprobe instalados; nos ambientes sem as ferramentas os testes
são pulados explicitamente, como no restante da suíte de integração.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

import pytest

from legendar.application.job.context import JobContext
from legendar.application.job.controller import JobController
from legendar.application.pipeline.serial_pipeline import PipelinePorts, SerialPipeline
from legendar.domain.entities.media import MediaKind, MediaSource
from legendar.domain.errors.base import ErrorCategory
from legendar.domain.events.job_events import JobCompleted, JobFailed
from legendar.domain.value_objects.language import Language
from legendar.infrastructure.filesystem.publisher import SrtPublisher
from legendar.infrastructure.filesystem.srt import parse_srt
from legendar.infrastructure.media.ffmpeg import FfmpegAudioPreparer
from legendar.infrastructure.media.probe import FfprobeInspector
from tests.e2e.support import request_for
from tests.helpers.fakes import (
    FakeAligner,
    FakeTranscriber,
    make_alignment,
    make_transcript,
)

pytestmark = [pytest.mark.e2e, pytest.mark.integration]


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


def _pipeline() -> SerialPipeline:
    """Pipeline real de mídia com reconhecimento e alinhamento controlados."""
    inspector = FfprobeInspector()
    transcript = make_transcript(language=Language.PORTUGUESE, text="ola mundo")
    return SerialPipeline(
        PipelinePorts(
            inspector=inspector,
            audio_preparer=FfmpegAudioPreparer(inspector=inspector),
            transcriber=FakeTranscriber(transcript=transcript),
            aligner=FakeAligner(alignment=make_alignment(transcript)),
            publisher=SrtPublisher(),
        )
    )


def _sine_media(ffmpeg: str, destination: Path, codec: str) -> Path:
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
            "-c:a",
            codec,
            str(destination),
        ]
    )
    return destination


MEDIA_FORMATS = (
    pytest.param("wav", "pcm_s16le", id="wav-pcm"),
    pytest.param("mp3", "libmp3lame", id="mp3"),
    pytest.param("m4a", "aac", id="m4a-aac"),
    pytest.param("mkv", "pcm_s16le", id="mkv-pcm"),
    pytest.param("mp4", "aac", id="mp4-aac"),
    pytest.param("webm", "libopus", id="webm-opus"),
)


@pytest.mark.parametrize(("extension", "codec"), MEDIA_FORMATS)
def test_real_media_full_flow_publishes_a_valid_srt(
    tmp_path: Path,
    media_tools: tuple[str, str],
    job_context: JobContext,
    extension: str,
    codec: str,
) -> None:
    ffmpeg, _ffprobe = media_tools
    source = _sine_media(ffmpeg, tmp_path / f"sermao.{extension}", codec)
    source_hash = _sha256(source)
    request = request_for(
        output_language=Language.PORTUGUESE,
        source_language=Language.PORTUGUESE,
        source=MediaSource(kind=MediaKind.LOCAL_FILE, location=str(source)),
    )

    events: list = []
    controller = JobController(_pipeline(), events.append, context=job_context)
    result = controller.run(request, job_context)

    assert isinstance(events[-1], JobCompleted)
    assert result is not None
    published = Path(result.output_path)
    assert published == job_context.output_path
    assert published.is_file()
    cues = parse_srt(published.read_text(encoding="utf-8"))
    assert cues
    assert cues[-1].end <= 3.5
    assert not job_context.staged_output_path.exists()
    assert job_context.audio_cache_path.is_file()
    assert _sha256(source) == source_hash


def test_media_without_audio_stream_is_rejected_by_the_pipeline(
    tmp_path: Path, media_tools: tuple[str, str], job_context: JobContext
) -> None:
    ffmpeg, _ffprobe = media_tools
    source = tmp_path / "sem-audio.mp4"
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
            "color=c=black:s=64x64:d=1.0",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(source),
        ]
    )
    request = request_for(
        output_language=Language.PORTUGUESE,
        source=MediaSource(kind=MediaKind.LOCAL_FILE, location=str(source)),
    )

    events: list = []
    controller = JobController(_pipeline(), events.append, context=job_context)
    result = controller.run(request, job_context)

    assert result is None
    assert isinstance(events[-1], JobFailed)
    assert events[-1].category is ErrorCategory.INVALID_INPUT
    assert not job_context.output_path.exists()


def test_corrupted_media_fails_without_publishing(
    tmp_path: Path, media_tools: tuple[str, str], job_context: JobContext
) -> None:
    source = tmp_path / "quebrado.mp4"
    source.write_bytes(b"isto nao e uma midia valida" * 20)
    request = request_for(
        output_language=Language.PORTUGUESE,
        source=MediaSource(kind=MediaKind.LOCAL_FILE, location=str(source)),
    )

    events: list = []
    controller = JobController(_pipeline(), events.append, context=job_context)
    result = controller.run(request, job_context)

    assert result is None
    assert isinstance(events[-1], JobFailed)
    assert events[-1].category in {
        ErrorCategory.FFMPEG_FAILED,
        ErrorCategory.UNSUPPORTED_MEDIA,
        ErrorCategory.INVALID_INPUT,
    }
    assert not job_context.output_path.exists()
