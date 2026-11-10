from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from legendar.application.job.context import CancellationTokenImpl
from legendar.domain.entities.media import (
    AudioStreamInfo,
    MediaInfo,
    MediaKind,
    MediaSourceType,
)
from legendar.domain.errors.catalog import (
    InvalidInputError,
    JobCancelledError,
    MediaToolError,
    UnsupportedMediaError,
)
from legendar.infrastructure.media.ffmpeg import (
    FfmpegAudioPreparer,
    build_ffmpeg_command,
)


class FixedInspector:
    def __init__(self, *, codec: str = "pcm_s16le") -> None:
        self.codec = codec
        self.calls = []

    def inspect(self, source, *, token=None):
        self.calls.append(source)
        if token is not None:
            token.raise_if_cancelled()
        return MediaInfo(
            kind=MediaKind.LOCAL_FILE,
            source_type=MediaSourceType.AUDIO,
            container="wav",
            duration_seconds=2.5,
            audio_streams=(
                AudioStreamInfo(
                    index=0,
                    codec=self.codec,
                    channels=1,
                    sample_rate_hz=16_000,
                ),
            ),
        )


class FakeProcess:
    def __init__(self, command, *, stderr, returncode=0, token=None) -> None:
        self.command = command
        self.stderr = stderr
        self.returncode = None
        self.final_returncode = returncode
        self.token = token
        self.terminated = False
        Path(command[-1]).write_bytes(b"RIFF" + b"x" * 128)
        if returncode:
            stderr.write(b"synthetic ffmpeg failure")

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        if self.token is not None and not self.terminated and self.returncode is None:
            self.token.cancel("cancelar FFmpeg")
            raise subprocess.TimeoutExpired(cmd="ffmpeg", timeout=timeout)
        if self.terminated:
            self.returncode = -15
        else:
            self.returncode = self.final_returncode
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def kill(self):
        self.terminated = True
        self.returncode = -9


def test_ffmpeg_command_maps_global_stream_and_uses_safe_wav_contract(
    tmp_path: Path,
) -> None:
    command = build_ffmpeg_command(
        "ffmpeg", tmp_path / "origem.mp4", 4, tmp_path / "audio.wav"
    )

    assert command[:5] == [
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
    ]
    assert command[command.index("-map") + 1] == "0:4"
    assert command[command.index("-ac") + 1] == "1"
    assert command[command.index("-ar") + 1] == "16000"
    assert command[command.index("-c:a") + 1] == "pcm_s16le"
    assert "-n" in command
    assert "-y" not in command


def test_ffmpeg_preparer_publishes_only_validated_audio_and_preserves_offset(
    tmp_path: Path,
) -> None:
    source = tmp_path / "origem.mp4"
    source.write_bytes(b"original-media-bytes")
    source_before = source.read_bytes()
    destination = tmp_path / "job" / "audio.wav"
    inspector = FixedInspector()
    stream = AudioStreamInfo(
        index=3,
        codec="aac",
        channels=2,
        sample_rate_hz=48_000,
        start_time_seconds=1.25,
        offset_source="stream.start_pts*time_base",
    )
    preparer = FfmpegAudioPreparer(
        inspector=inspector,
        process_factory=lambda command, **kwargs: FakeProcess(command, **kwargs),
    )

    asset = preparer.prepare(
        str(source),
        stream=stream,
        destination_path=str(destination),
    )

    assert destination.is_file()
    assert asset.path == str(destination.resolve())
    assert asset.sample_rate_hz == 16_000
    assert asset.channels == 1
    assert asset.sample_format == "pcm_s16le"
    assert asset.duration_seconds == 2.5
    assert asset.timeline_start_seconds == 1.25
    assert asset.timeline_offset_source == "stream.start_pts*time_base"
    assert source.read_bytes() == source_before
    assert list(destination.parent.glob("*.partial.wav")) == []
    assert len(inspector.calls) == 1


def test_ffmpeg_preparer_removes_partial_file_when_cancelled(tmp_path: Path) -> None:
    source = tmp_path / "origem.mp4"
    source.write_bytes(b"original")
    destination = tmp_path / "job" / "audio.wav"
    token = CancellationTokenImpl()
    process_holder = {}

    def factory(command, **kwargs):
        process = FakeProcess(command, token=token, **kwargs)
        process_holder["process"] = process
        return process

    preparer = FfmpegAudioPreparer(
        inspector=FixedInspector(),
        process_factory=factory,
    )

    with pytest.raises(JobCancelledError, match="cancelar FFmpeg"):
        preparer.prepare(
            str(source),
            stream=AudioStreamInfo(
                index=0, codec="aac", channels=2, sample_rate_hz=48_000
            ),
            destination_path=str(destination),
            token=token,
        )

    assert process_holder["process"].terminated
    assert not destination.exists()
    assert not list(destination.parent.glob("*.partial.wav"))


def test_ffmpeg_preparer_removes_partial_file_on_process_failure(
    tmp_path: Path,
) -> None:
    source = tmp_path / "origem.mp4"
    source.write_bytes(b"original")
    destination = tmp_path / "job" / "audio.wav"
    preparer = FfmpegAudioPreparer(
        inspector=FixedInspector(),
        process_factory=lambda command, **kwargs: FakeProcess(
            command, returncode=1, **kwargs
        ),
    )

    with pytest.raises(MediaToolError, match="normalizar"):
        preparer.prepare(
            str(source),
            stream=AudioStreamInfo(
                index=0, codec="aac", channels=2, sample_rate_hz=48_000
            ),
            destination_path=str(destination),
        )

    assert not destination.exists()
    assert not list(destination.parent.glob("*.partial.wav"))


def test_ffmpeg_preparer_rejects_unexpected_output_format(tmp_path: Path) -> None:
    source = tmp_path / "origem.mp4"
    source.write_bytes(b"original")
    destination = tmp_path / "job" / "audio.wav"
    preparer = FfmpegAudioPreparer(
        inspector=FixedInspector(codec="aac"),
        process_factory=lambda command, **kwargs: FakeProcess(command, **kwargs),
    )

    with pytest.raises(UnsupportedMediaError, match="Codec WAV inesperado"):
        preparer.prepare(
            str(source),
            stream=AudioStreamInfo(
                index=0, codec="aac", channels=2, sample_rate_hz=48_000
            ),
            destination_path=str(destination),
        )

    assert not destination.exists()
    assert not list(destination.parent.glob("*.partial.wav"))


def test_ffmpeg_preparer_never_overwrites_existing_destination(tmp_path: Path) -> None:
    source = tmp_path / "origem.mp4"
    source.write_bytes(b"original")
    destination = tmp_path / "job" / "audio.wav"
    destination.parent.mkdir()
    destination.write_bytes(b"already-there")
    preparer = FfmpegAudioPreparer(inspector=FixedInspector())

    with pytest.raises(InvalidInputError, match="já existe"):
        preparer.prepare(
            str(source),
            stream=AudioStreamInfo(
                index=0, codec="aac", channels=2, sample_rate_hz=48_000
            ),
            destination_path=str(destination),
        )

    assert destination.read_bytes() == b"already-there"
