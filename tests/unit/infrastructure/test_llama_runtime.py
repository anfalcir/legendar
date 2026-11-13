"""Testes determinísticos do lifecycle do servidor TranslateGemma."""

from __future__ import annotations

import hashlib
import io
import subprocess
import tarfile
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

import legendar.infrastructure.translation.llama_runtime as llama_runtime
from legendar.domain.errors.catalog import JobCancelledError, ModelError
from legendar.infrastructure.translation.llama_runtime import (
    DEFAULT_MODEL_ALIAS,
    MODEL_DOWNLOAD_URL,
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

    def read(self, _size: int = -1) -> bytes:
        return ('{"data":[{"id":"' + DEFAULT_MODEL_ALIAS + '"}]}').encode("utf-8")


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
        "model_sha256": (
            hashlib.sha256(b"model").hexdigest()
            if "model_path" not in overrides
            else llama_runtime.MODEL_SHA256
        ),
        "sleep": lambda _seconds: None,
    }
    options.update(overrides)
    return LlamaCppRuntimeManager(**options), processes


def _runtime_archive(*, unsafe_symlink: bool = False) -> bytes:
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w:gz") as archive:
        root = tarfile.TarInfo(f"{llama_runtime.LLAMA_CPP_RELEASE}/")
        root.type = tarfile.DIRTYPE
        archive.addfile(root)

        lib_dir = tarfile.TarInfo(f"{llama_runtime.LLAMA_CPP_RELEASE}/lib/")
        lib_dir.type = tarfile.DIRTYPE
        archive.addfile(lib_dir)

        library = tarfile.TarInfo(
            f"{llama_runtime.LLAMA_CPP_RELEASE}/lib/libggml-base.so.0.9.0"
        )
        library.mode = 0o644
        library.size = len(b"fake library")
        archive.addfile(library, io.BytesIO(b"fake library"))

        versioned_link = tarfile.TarInfo(
            f"{llama_runtime.LLAMA_CPP_RELEASE}/lib/libggml-base.so.0"
        )
        versioned_link.type = tarfile.SYMTYPE
        versioned_link.linkname = (
            "../../../outside" if unsafe_symlink else "libggml-base.so.0.9.0"
        )
        archive.addfile(versioned_link)

        unversioned_link = tarfile.TarInfo(
            f"{llama_runtime.LLAMA_CPP_RELEASE}/lib/libggml-base.so"
        )
        unversioned_link.type = tarfile.SYMTYPE
        unversioned_link.linkname = "libggml-base.so.0"
        archive.addfile(unversioned_link)

        binary = tarfile.TarInfo(f"{llama_runtime.LLAMA_CPP_RELEASE}/llama-server")
        binary.mode = 0o755
        binary.size = len(b"fake server")
        archive.addfile(binary, io.BytesIO(b"fake server"))
    return payload.getvalue()


def test_runtime_install_requires_consent_and_is_idempotent(
    tmp_path, monkeypatch
) -> None:
    archive = _runtime_archive()
    monkeypatch.setattr(
        llama_runtime,
        "LLAMA_CPP_SHA256",
        hashlib.sha256(archive).hexdigest(),
    )
    monkeypatch.setattr(
        llama_runtime, "LLAMA_CPP_ARCHIVE_SIZE", len(archive)
    )
    response = DownloadResponse(
        [archive],
        headers={"Content-Length": str(len(archive))},
    )
    manager = LlamaCppRuntimeManager(
        tmp_path / "models",
        executable=tmp_path / "missing-llama",
        model_path=tmp_path / "model.gguf",
        runtime_opener=lambda *_args, **_kwargs: response,
    )
    monkeypatch.setattr(llama_runtime.sys, "platform", "linux")
    monkeypatch.setattr(llama_runtime.platform, "machine", lambda: "x86_64")

    with pytest.raises(ModelError, match="autorização explícita"):
        manager.ensure_runtime(consent=False)

    installed = manager.ensure_runtime(consent=True)
    assert installed.name == "llama-server"
    assert installed.is_file()
    assert manager.discover_executable(tmp_path / "models") == installed
    library_dir = installed.parent / "lib"
    assert (library_dir / "libggml-base.so").is_symlink()
    assert (library_dir / "libggml-base.so.0").is_symlink()
    assert (library_dir / "libggml-base.so").read_bytes() == b"fake library"
    assert manager.ensure_runtime(consent=True) == installed


def test_runtime_install_rejects_symlink_escaping_staging(tmp_path) -> None:
    archive = _runtime_archive(unsafe_symlink=True)
    archive_path = tmp_path / "unsafe.tar.gz"
    archive_path.write_bytes(archive)
    destination = tmp_path / "staging"
    destination.mkdir()

    with pytest.raises(ModelError, match="tenta sair do staging"):
        LlamaCppRuntimeManager._extract_runtime_archive(archive_path, destination)

    assert not (tmp_path / "outside").exists()


def test_runtime_install_reuses_verified_archive_after_extraction_failure(
    tmp_path, monkeypatch
) -> None:
    archive = _runtime_archive()
    monkeypatch.setattr(
        llama_runtime, "LLAMA_CPP_SHA256", hashlib.sha256(archive).hexdigest()
    )
    monkeypatch.setattr(llama_runtime, "LLAMA_CPP_ARCHIVE_SIZE", len(archive))
    requests = []
    response = DownloadResponse(
        [archive],
        headers={"Content-Length": str(len(archive))},
    )

    def opener(*_args, **_kwargs):
        requests.append(True)
        return response

    manager = LlamaCppRuntimeManager(
        tmp_path / "models",
        executable=tmp_path / "missing-llama",
        model_path=tmp_path / "model.gguf",
        runtime_opener=opener,
    )
    monkeypatch.setattr(llama_runtime.sys, "platform", "linux")
    monkeypatch.setattr(llama_runtime.platform, "machine", lambda: "x86_64")
    extract = manager._extract_runtime_archive
    attempts = []

    def fail_once(*_args, **_kwargs):
        attempts.append(True)
        if len(attempts) == 1:
            raise ModelError("falha simulada na extração")
        return extract(*_args, **_kwargs)

    monkeypatch.setattr(
        LlamaCppRuntimeManager, "_extract_runtime_archive", staticmethod(fail_once)
    )
    with pytest.raises(ModelError, match="falha simulada"):
        manager.ensure_runtime(consent=True)

    cached_archive = (
        tmp_path
        / "models"
        / "runtime"
        / f"{llama_runtime.LLAMA_CPP_ARCHIVE}.part"
    )
    assert cached_archive.is_file()
    assert len(requests) == 1

    installed = manager.ensure_runtime(consent=True)
    assert installed.is_file()
    assert len(requests) == 1
    assert len(attempts) == 2


def test_ensure_model_reuses_valid_cached_weights_without_consent(
    tmp_path,
) -> None:
    manager, _ = _manager(tmp_path)

    assert manager.ensure_model() == manager.model_path
    assert not manager.download_authorized


def test_ensure_model_requires_session_consent_when_weights_are_missing(
    tmp_path,
) -> None:
    manager, _ = _manager(tmp_path, model_path=tmp_path / "missing.gguf")

    assert manager.needs_download_authorization
    with pytest.raises(ModelError, match="Autorize o download"):
        manager.ensure_model()


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


def test_invalid_existing_model_is_quarantined_and_redownloaded(
    tmp_path, monkeypatch
) -> None:
    payload = b"approved-model"
    monkeypatch.setattr(
        llama_runtime, "MODEL_SHA256", hashlib.sha256(payload).hexdigest()
    )
    model_path = tmp_path / "models" / "translategemma.gguf"
    model_path.parent.mkdir()
    model_path.write_bytes(b"corrupted-model")
    response = DownloadResponse(
        [payload],
        headers={"Content-Length": str(len(payload))},
    )
    manager, _ = _manager(
        tmp_path,
        model_path=model_path,
        opener=lambda *_args, **_kwargs: response,
    )

    assert manager.download_model(consent=True) == model_path

    assert model_path.read_bytes() == payload
    quarantined = list(model_path.parent.glob("translategemma.gguf.invalid.*"))
    assert len(quarantined) == 1
    assert quarantined[0].read_bytes() == b"corrupted-model"


def test_invalid_model_hash_prevents_server_start(tmp_path) -> None:
    manager, processes = _manager(tmp_path, model_sha256="0" * 64)

    with pytest.raises(ModelError, match="SHA-256"):
        manager.ensure_running()

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


def test_readiness_rejects_a_different_model_on_a_healthy_port(tmp_path) -> None:
    class ForeignModelResponse(FakeResponse):
        def read(self, _size: int = -1) -> bytes:
            return b'{"data":[{"id":"some-other-model"}]}'

    manager, _ = _manager(
        tmp_path,
        opener=lambda *_args, **_kwargs: ForeignModelResponse(),
    )

    assert not manager._is_ready(12345)


def test_standalone_llama_server_uses_server_cli_arguments(tmp_path) -> None:
    executable = tmp_path / "llama-server"
    executable.write_text("fake server", encoding="utf-8")
    executable.chmod(0o755)
    model = tmp_path / "model.gguf"
    model.write_bytes(b"model")
    commands = []

    def popen(command, **_kwargs):
        commands.append(command)
        return FakeProcess(command)

    manager = LlamaCppRuntimeManager(
        tmp_path / "models",
        executable=executable,
        model_path=model,
        popen_factory=popen,
        opener=lambda *_args, **_kwargs: FakeResponse(),
        model_sha256=hashlib.sha256(b"model").hexdigest(),
    )

    manager.ensure_running()

    assert commands[0][0] == str(executable)
    assert commands[0][1] == "-m"
    assert "serve" not in commands[0]
    manager.shutdown()


class DownloadResponse:
    def __init__(
        self,
        chunks,
        *,
        status=200,
        headers=None,
        fail_after_chunks=False,
    ) -> None:
        self.chunks = list(chunks)
        self.status = status
        self.headers = headers or {}
        self.fail_after_chunks = fail_after_chunks

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _size):
        if self.chunks:
            return self.chunks.pop(0)
        if self.fail_after_chunks:
            self.fail_after_chunks = False
            raise URLError("connection interrupted")
        return b""


def test_model_download_requires_explicit_consent(tmp_path) -> None:
    called = []
    manager, _ = _manager(
        tmp_path,
        opener=lambda *_args, **_kwargs: called.append(True),
    )

    with pytest.raises(ModelError, match="autorização explícita"):
        manager.download_model(consent=False)

    assert called == []


def test_model_download_reuses_existing_huggingface_token(
    tmp_path, monkeypatch
) -> None:
    payload = b"authenticated-model"
    monkeypatch.setattr(
        llama_runtime, "MODEL_SHA256", hashlib.sha256(payload).hexdigest()
    )
    requests = []
    response = DownloadResponse(
        [payload],
        headers={"Content-Length": str(len(payload))},
    )

    def opener(request, **_kwargs):
        requests.append(request)
        return response

    manager, _ = _manager(
        tmp_path,
        model_path=tmp_path / "models" / "translategemma" / "model.gguf",
        opener=opener,
        token_provider=lambda: "local-test-token",
    )

    manager.download_model(consent=True)

    assert requests[0].get_header("Authorization") == "Bearer local-test-token"


def test_model_download_explains_huggingface_access_denial(tmp_path) -> None:
    def opener(*_args, **_kwargs):
        raise HTTPError(
            MODEL_DOWNLOAD_URL,
            403,
            "Forbidden",
            hdrs=None,
            fp=None,
        )

    manager, _ = _manager(
        tmp_path,
        model_path=tmp_path / "models" / "translategemma" / "model.gguf",
        opener=opener,
        token_provider=lambda: None,
    )

    with pytest.raises(ModelError, match="Aceite os termos/licença Gemma"):
        manager.download_model(consent=True)


def test_model_download_is_atomic_and_validates_sha256(tmp_path, monkeypatch) -> None:
    payload = b"TranslateGemma test payload"
    monkeypatch.setattr(
        llama_runtime, "MODEL_SHA256", hashlib.sha256(payload).hexdigest()
    )
    model_path = tmp_path / "models" / "translategemma.gguf"
    response = DownloadResponse(
        [payload],
        headers={"Content-Length": str(len(payload))},
    )
    manager, _ = _manager(
        tmp_path,
        model_path=model_path,
        opener=lambda *_args, **_kwargs: response,
    )

    result = manager.download_model(consent=True)

    assert result == model_path
    assert result.read_bytes() == payload
    assert not result.with_suffix(".gguf.part").exists()


def test_model_download_resumes_partial_file_after_network_failure(
    tmp_path, monkeypatch
) -> None:
    payload = b"abcdefghij"
    monkeypatch.setattr(
        llama_runtime, "MODEL_SHA256", hashlib.sha256(payload).hexdigest()
    )
    responses = [
        DownloadResponse(
            [payload[:5]],
            headers={"Content-Length": str(len(payload))},
            fail_after_chunks=True,
        ),
        DownloadResponse(
            [payload[5:]],
            status=206,
            headers={
                "Content-Length": str(len(payload[5:])),
                "Content-Range": f"bytes 5-{len(payload) - 1}/{len(payload)}",
            },
        ),
    ]
    requests = []

    def opener(request, **_kwargs):
        requests.append(request)
        return responses.pop(0)

    model_path = tmp_path / "models" / "translategemma.gguf"
    manager, _ = _manager(tmp_path, model_path=model_path, opener=opener)

    with pytest.raises(ModelError, match="arquivo parcial foi preservado"):
        manager.download_model(consent=True)

    result = manager.download_model(consent=True)

    assert result.read_bytes() == payload
    assert requests[1].get_header("Range") == "bytes=5-"
    assert not result.with_suffix(".gguf.part").exists()


def test_invalid_model_hash_discards_partial_download(tmp_path, monkeypatch) -> None:
    payload = b"not-the-pinned-model"
    monkeypatch.setattr(llama_runtime, "MODEL_SHA256", "0" * 64)
    response = DownloadResponse(
        [payload],
        headers={"Content-Length": str(len(payload))},
    )
    model_path = tmp_path / "models" / "translategemma.gguf"
    manager, _ = _manager(
        tmp_path,
        model_path=model_path,
        opener=lambda *_args, **_kwargs: response,
    )

    with pytest.raises(ModelError, match="SHA-256"):
        manager.download_model(consent=True)

    assert not model_path.exists()
    assert not model_path.with_suffix(".gguf.part").exists()


def test_interprocess_lock_prevents_duplicate_managed_servers(tmp_path) -> None:
    first, first_processes = _manager(tmp_path)
    second, second_processes = _manager(tmp_path)

    first.ensure_running()

    with pytest.raises(ModelError, match="Outra instância"):
        second.ensure_running()

    first.shutdown()
    second.ensure_running()

    assert len(first_processes) == 1
    assert len(second_processes) == 1
    second.shutdown()


def test_dead_owned_process_releases_lock_before_restart(tmp_path) -> None:
    manager, processes = _manager(tmp_path)
    manager.ensure_running()
    processes[0].returncode = 1

    manager.ensure_running()

    assert len(processes) == 2
    assert manager.is_running
    manager.shutdown()


def test_existing_valid_model_download_is_idempotent(tmp_path, monkeypatch) -> None:
    payload = b"already-installed-model"
    monkeypatch.setattr(
        llama_runtime, "MODEL_SHA256", hashlib.sha256(payload).hexdigest()
    )
    model_path = tmp_path / "models" / "translategemma.gguf"
    model_path.parent.mkdir()
    model_path.write_bytes(payload)
    manager, _ = _manager(
        tmp_path,
        model_path=model_path,
        opener=lambda *_args, **_kwargs: pytest.fail("download must not run"),
    )

    assert manager.download_model(consent=True) == model_path
    assert model_path.read_bytes() == payload


def test_download_file_lock_prevents_parallel_model_downloads(
    tmp_path, monkeypatch
) -> None:
    payload = b"single-download"
    monkeypatch.setattr(
        llama_runtime, "MODEL_SHA256", hashlib.sha256(payload).hexdigest()
    )
    model_path = tmp_path / "models" / "translategemma.gguf"
    second, _ = _manager(tmp_path, model_path=model_path)
    response = DownloadResponse(
        [payload],
        headers={"Content-Length": str(len(payload))},
    )

    def opener(*_args, **_kwargs):
        with pytest.raises(ModelError, match="Outra instância"):
            second.download_model(consent=True)
        return response

    first, _ = _manager(tmp_path, model_path=model_path, opener=opener)

    assert first.download_model(consent=True) == model_path
    assert model_path.read_bytes() == payload
