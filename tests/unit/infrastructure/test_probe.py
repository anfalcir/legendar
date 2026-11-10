from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from legendar.domain.entities.media import MediaKind, MediaSource
from legendar.application.job.context import CancellationTokenImpl
from legendar.domain.errors.catalog import (
    InvalidInputError,
    JobCancelledError,
    MediaToolError,
)
from legendar.infrastructure.media.probe import (
    FfprobeInspector,
    build_ffprobe_command,
)

PAYLOAD = {
    "streams": [
        {"index": 0, "codec_type": "video", "codec_name": "h264"},
        {
            "index": 1,
            "codec_type": "audio",
            "codec_name": "aac",
            "channels": 2,
            "sample_rate": "48000",
        },
    ],
    "format": {"format_name": "mp4", "duration": "9.5"},
}


class RecordingRunner:
    def __init__(self, completed: subprocess.CompletedProcess[str]) -> None:
        self.completed = completed
        self.calls: list[tuple[list[str], dict]] = []

    def __call__(self, args, **kwargs):
        self.calls.append((list(args), kwargs))
        return self.completed


def _completed(
    returncode: int = 0, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["ffprobe"], returncode=returncode, stdout=stdout, stderr=stderr
    )


def test_command_is_non_interactive_and_requests_json() -> None:
    command = build_ffprobe_command("ffprobe", Path("/tmp/a.mp4"))

    assert command[0] == "ffprobe"
    assert "-print_format" in command
    assert command[command.index("-print_format") + 1] == "json"
    assert "-show_streams" in command
    assert "-show_format" in command
    assert command[-1] == "/tmp/a.mp4"


def test_inspect_returns_domain_info(tmp_path: Path) -> None:
    media = tmp_path / "video.mp4"
    media.write_bytes(b"\x00")
    runner = RecordingRunner(_completed(stdout=json.dumps(PAYLOAD)))

    info = FfprobeInspector(runner=runner).inspect(
        MediaSource(kind=MediaKind.LOCAL_FILE, location=str(media))
    )

    assert info.container == "mp4"
    assert info.duration_seconds == 9.5
    assert info.has_audio
    assert runner.calls[0][0][-1] == str(media)
    assert runner.calls[0][1]["check"] is False



def test_inspect_terminates_ffprobe_when_job_is_cancelled(tmp_path: Path) -> None:
    media = tmp_path / "video.mp4"
    media.write_bytes(b"\\x00")
    token = CancellationTokenImpl()

    class BlockingProcess:
        def __init__(self) -> None:
            self.returncode = None
            self.terminated = False
            self.terminate_calls = 0

        def poll(self):
            return self.returncode

        def communicate(self, timeout=None):
            if not self.terminated:
                token.cancel("cancelar ffprobe")
                raise subprocess.TimeoutExpired(cmd="ffprobe", timeout=timeout)
            return "", ""

        def terminate(self) -> None:
            self.terminate_calls += 1
            self.terminated = True
            self.returncode = -15

        def kill(self) -> None:
            self.terminated = True
            self.returncode = -9

    process = BlockingProcess()

    def process_factory(*_args, **_kwargs):
        return process

    inspector = FfprobeInspector(process_factory=process_factory)

    with pytest.raises(JobCancelledError, match="cancelar ffprobe"):
        inspector.inspect(
            MediaSource(kind=MediaKind.LOCAL_FILE, location=str(media)),
            token=token,
        )

    assert process.terminate_calls == 1
    assert process.returncode == -15


def test_inspect_rejects_missing_file(tmp_path: Path) -> None:
    inspector = FfprobeInspector(runner=RecordingRunner(_completed()))

    with pytest.raises(InvalidInputError):
        inspector.inspect(
            MediaSource(kind=MediaKind.LOCAL_FILE, location=str(tmp_path / "nada.mp4"))
        )


def test_inspect_rejects_remote_source() -> None:
    inspector = FfprobeInspector(runner=RecordingRunner(_completed()))

    with pytest.raises(InvalidInputError) as excinfo:
        inspector.inspect(
            MediaSource(kind=MediaKind.YOUTUBE, location="https://youtu.be/x")
        )

    assert "arquivo local" in excinfo.value.message


def test_non_zero_exit_is_a_tool_error(tmp_path: Path) -> None:
    media = tmp_path / "video.mp4"
    media.write_bytes(b"\x00")
    runner = RecordingRunner(_completed(returncode=1, stderr="invalid data"))

    with pytest.raises(MediaToolError) as excinfo:
        FfprobeInspector(runner=runner).inspect(
            MediaSource(kind=MediaKind.LOCAL_FILE, location=str(media))
        )

    assert "invalid data" in (excinfo.value.technical_detail or "")


def test_missing_binary_is_a_tool_error(tmp_path: Path) -> None:
    media = tmp_path / "video.mp4"
    media.write_bytes(b"\x00")

    def runner(*_args, **_kwargs):
        raise FileNotFoundError("ffprobe")

    with pytest.raises(MediaToolError) as excinfo:
        FfprobeInspector(runner=runner).inspect(
            MediaSource(kind=MediaKind.LOCAL_FILE, location=str(media))
        )

    assert "não foi encontrado" in excinfo.value.message


def test_timeout_is_a_tool_error(tmp_path: Path) -> None:
    media = tmp_path / "video.mp4"
    media.write_bytes(b"\x00")

    def runner(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="ffprobe", timeout=1)

    with pytest.raises(MediaToolError) as excinfo:
        FfprobeInspector(runner=runner).inspect(
            MediaSource(kind=MediaKind.LOCAL_FILE, location=str(media))
        )

    assert "tempo limite" in excinfo.value.message
