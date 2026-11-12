"""Testes determinísticos do lifecycle do servidor TranslateGemma."""

from __future__ import annotations

import subprocess
from pathlib import Path
from urllib.error import URLError

import pytest

from legendar.domain.errors.catalog import JobCancelledError, ModelError
from legendar.infrastructure.translation.llama_runtime import (
    DEFAULT_MODEL_ALIAS,
    LlamaCppRuntimeManager,
)


class FakeProcess:
    def __init__(self, *_args, **_kwargs) -> None:
        self.returncode = None
        self.terminated = False
        self.killed = False
        self.command = _args[0]

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    def kill(self):
        self.killed = True
        self.returncode = -9

    def wait(self, timeout=None):
        if self.returncode is None:
            raise subprocess.TimeoutExpired("llama", timeout)
        return self.returncode


class FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class CancelToken:
    is_cancelled = False

    def raise_if_cancelled(self):
        raise JobCancelledError()


class Progress:
    def __init__(self) -> None:
        self.events = []

    def report(self, fraction: float, message: str = "") -> None:
        self.events.append((fraction, message))


def _manager(tmp_path: Path, **overrides) -> tuple[LlamaCppRuntimeManager, list]:
    executable = tmp_path / "llama"
    executable.write_text("fake executable", encoding="utf-8")
    executable.chmod(0o755)
    model = tmp_path / "translategemma.gguf"
    model.write_bytes(b"model")
    processes = []

    def popen(command, **kwargs):
        process = FakeProcess(command, **kwargs)
        processes.append(process)
        return process

    options = {
        "models_dir": tmp_path / "models",
        "executable": executable,
        "model_path": model,
        "popen_factory": popen,
        "opener": lambda *_args, **_kwargs: FakeResponse(),
        "startup_timeout": 1.0,
        "sleep": lambda _seconds: None,
    }
    options.update(overrides)
    return LlamaCppRuntimeManager(**options), processes


def test_inspection_is_lightweight_and_reports_missing_dependencies(tmp_path) -> None:
    manager = LlamaCppRuntimeManager(
        tmp_path / "models",
        executable=tmp_path / "missing-llama",
        model_path=tmp_path / "missing.gguf",
    )

    result = manager.inspect()

    assert not result.ready_to_start
    assert not result.executable_available
    assert not result.model_available
    assert len(result.details) == 2


def test_ensure_running_starts_once_and_reuses_healthy_owned_process(tmp_path) -> None:
    manager, processes = _manager(tmp_path)
    progress = Progress()

    first = manager.ensure_running(progress=progress)
    second = manager.ensure_running(progress=progress)

    assert first == second
    assert first.startswith("http://127.0.0.1:")
    assert len(processes) == 1
    assert manager.is_running
    assert manager.base_url == first
    assert processes[0].command[1:3] == ["serve", "-m"]
    assert DEFAULT_MODEL_ALIAS in processes[0].command
    assert any("já está pronto" in message for _, message in progress.events)


def test_external_healthy_server_is_never_adopted(tmp_path) -> None:
    manager, processes = _manager(tmp_path)

    base_url = manager.ensure_running()

    assert len(processes) == 1
    assert manager.base_url == base_url
    assert processes[0].poll() is None


def test_server_listens_only_on_loopback(tmp_path) -> None:
    with pytest.raises(ValueError, match="127.0.0.1"):
        LlamaCppRuntimeManager(tmp_path, host="0.0.0.0")


def test_missing_model_prevents_process_start(tmp_path) -> None:
    manager, processes = _manager(tmp_path, model_path=tmp_path / "absent.gguf")

    with pytest.raises(ModelError, match="ausentes"):
        manager.ensure_running()

    assert processes == []


def test_cancelled_start_does_not_leave_server_running(tmp_path) -> None:
    manager, processes = _manager(tmp_path)

    with pytest.raises(JobCancelledError):
        manager.ensure_running(token=CancelToken())

    assert processes == []
    assert manager.base_url is None


def test_server_exit_before_readiness_is_reported(tmp_path) -> None:
    processes = []

    def popen(command, **kwargs):
        process = FakeProcess(command, **kwargs)
        process.returncode = 2
        processes.append(process)
        return process

    manager, _ = _manager(tmp_path, popen_factory=popen)

    with pytest.raises(ModelError, match="encerrou antes"):
        manager.ensure_running()

    assert manager.base_url is None


def test_shutdown_stops_only_the_owned_process_and_keeps_model(tmp_path) -> None:
    manager, processes = _manager(tmp_path)
    model_path = tmp_path / "translategemma.gguf"
    manager.ensure_running()

    manager.shutdown()

    assert len(processes) == 1
    assert processes[0].terminated
    assert not manager.is_running
    assert manager.base_url is None
    assert model_path.is_file()


def test_unhealthy_server_times_out_and_is_terminated(tmp_path) -> None:
    manager, processes = _manager(
        tmp_path,
        opener=lambda *_args, **_kwargs: (_ for _ in ()).throw(URLError("offline")),
        startup_timeout=0.01,
        monotonic=iter([0.0, 0.0, 0.02]).__next__,
    )

    with pytest.raises(ModelError, match="não ficou pronto"):
        manager.ensure_running()

    assert len(processes) == 1
    assert processes[0].terminated
    assert manager.base_url is None
