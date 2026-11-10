from __future__ import annotations

import subprocess

from legendar.infrastructure.media.tools import (
    ToolStatus,
    locate_tool,
    locate_tools,
    read_version,
)


def _completed(
    returncode: int = 0, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["tool", "--version"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def test_locate_tool_absent() -> None:
    status = locate_tool("ffmpeg", which=lambda _name: None)

    assert status == ToolStatus(name="ffmpeg")
    assert not status.available
    assert "não encontrado" in status.label_pt


def test_locate_tool_reads_first_non_empty_version_line() -> None:
    def runner(*_args, **_kwargs) -> subprocess.CompletedProcess[str]:
        return _completed(stdout="\nffmpeg version 7.1.1\nbuilt with gcc\n")

    status = locate_tool("ffmpeg", which=lambda _name: "/usr/bin/ffmpeg", runner=runner)

    assert status.available
    assert status.path == "/usr/bin/ffmpeg"
    assert status.version == "ffmpeg version 7.1.1"
    assert status.label_pt == "ffmpeg: ffmpeg version 7.1.1 (/usr/bin/ffmpeg)"


def test_locate_tool_keeps_path_when_version_fails() -> None:
    def runner(*_args, **_kwargs) -> subprocess.CompletedProcess[str]:
        return _completed(returncode=1)

    status = locate_tool("ffprobe", which=lambda _name: "/bin/ffprobe", runner=runner)

    assert status.available
    assert status.version is None
    assert status.detail


def test_read_version_handles_missing_binary() -> None:
    def runner(*_args, **_kwargs) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("sumiu")

    assert read_version("/bin/ffmpeg", runner=runner) is None


def test_read_version_handles_timeout() -> None:
    def runner(*_args, **_kwargs) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd="ffmpeg", timeout=1)

    assert read_version("/bin/ffmpeg", runner=runner) is None


def test_locate_tools_preserves_requested_order() -> None:
    statuses = locate_tools(("ffmpeg", "ffprobe", "deno"), which=lambda _name: None)

    assert list(statuses) == ["ffmpeg", "ffprobe", "deno"]
