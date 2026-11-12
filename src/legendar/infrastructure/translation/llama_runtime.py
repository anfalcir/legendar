"""Gerenciamento do processo local llama.cpp para TranslateGemma.

O módulo não instala binários nem baixa pesos: essas operações exigem um fluxo
explícito de consentimento e serão orquestradas pela camada de aplicação/UI.
Ele garante que o servidor iniciado pelo Legendar seja privado, reutilizável
durante a sessão e encerrado sem tocar em processos externos.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.error import URLError
from urllib.request import Request, urlopen

from legendar.application.ports.protocols import CancellationToken, ProgressSink
from legendar.domain.errors.catalog import ModelError

DEFAULT_MODEL_FILENAME = "translategemma-4b-it-Q4_K_M.gguf"
DEFAULT_MODEL_ALIAS = "translategemma-4b"
DEFAULT_CONTEXT_SIZE = 2048
DEFAULT_THREADS = 4
DEFAULT_STARTUP_TIMEOUT = 90.0
_HEALTH_TIMEOUT = 1.5
_POLL_INTERVAL = 0.25


@dataclass(frozen=True, slots=True)
class RuntimeInspection:
    """Diagnóstico rápido sem iniciar processos ou acessar a rede."""

    executable: Path | None
    model_path: Path
    executable_available: bool
    model_available: bool
    ready_to_start: bool
    details: tuple[str, ...]


class LlamaCppRuntimeManager:
    """Possui e gerencia no máximo um servidor llama.cpp nesta instância.

    O lock serializa chamadas concorrentes dentro do processo. Um servidor
    externo nunca é adotado: a propriedade é estabelecida somente pelo objeto
    Popen criado aqui. A porta é escolhida dinamicamente para não disputar
    silenciosamente com serviços locais de terceiros.
    """

    def __init__(
        self,
        models_dir: Path,
        *,
        executable: str | Path | None = None,
        model_path: Path | None = None,
        host: str = "127.0.0.1",
        context_size: int = DEFAULT_CONTEXT_SIZE,
        threads: int = DEFAULT_THREADS,
        startup_timeout: float = DEFAULT_STARTUP_TIMEOUT,
        popen_factory: Callable[..., Any] = subprocess.Popen,
        opener: Callable[..., Any] = urlopen,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if host != "127.0.0.1":
            raise ValueError("O servidor TranslateGemma deve escutar somente em 127.0.0.1.")
        if context_size < 512 or context_size > 2048:
            raise ValueError("O contexto TranslateGemma deve ficar entre 512 e 2048.")
        if threads < 1:
            raise ValueError("O número de threads deve ser positivo.")
        if startup_timeout <= 0:
            raise ValueError("O timeout de inicialização deve ser positivo.")
        self.models_dir = Path(models_dir).expanduser()
        self.model_path = Path(model_path) if model_path else (
            self.models_dir / "translategemma" / DEFAULT_MODEL_FILENAME
        )
        self.host = host
        self.context_size = context_size
        self.threads = threads
        self.startup_timeout = startup_timeout
        self._configured_executable = Path(executable).expanduser() if executable else None
        self._popen_factory = popen_factory
        self._opener = opener
        self._sleep = sleep
        self._monotonic = monotonic
        self._lock = threading.RLock()
        self._process: Any | None = None
        self._port: int | None = None

    @staticmethod
    def discover_executable(models_dir: Path) -> Path | None:
        """Procura primeiro uma instalação privada e depois o PATH do usuário."""
        configured = os.environ.get("LEGENDAR_LLAMA_EXECUTABLE", "").strip()
        candidates = []
        if configured:
            candidates.append(Path(configured).expanduser())
        suffix = ".exe" if os.name == "nt" else ""
        candidates.extend(
            (
                Path(models_dir) / "runtime" / "bin" / f"llama{suffix}",
                Path(models_dir) / "runtime" / "bin" / f"llama-server{suffix}",
                Path(models_dir) / "runtime" / f"llama{suffix}",
                Path(models_dir) / "runtime" / f"llama-server{suffix}",
            )
        )
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        for command in ("llama", "llama-server"):
            located = shutil.which(command)
            if located:
                return Path(located)
        return None

    def inspect(self) -> RuntimeInspection:
        """Verifica arquivos locais de forma leve; não inicia nem baixa nada."""
        executable = self._configured_executable or self.discover_executable(
            self.models_dir
        )
        executable_ok = bool(
            executable
            and executable.is_file()
            and (os.name == "nt" or os.access(executable, os.X_OK))
        )
        try:
            model_ok = self.model_path.is_file() and self.model_path.stat().st_size > 0
        except OSError:
            model_ok = False
        details: list[str] = []
        if not executable_ok:
            details.append("llama.cpp não encontrado ou não executável.")
        if not model_ok:
            details.append(f"Pesos TranslateGemma ausentes: {self.model_path}")
        if executable_ok and model_ok:
            details.append("Runtime llama.cpp e pesos TranslateGemma encontrados.")
        return RuntimeInspection(
            executable=executable if executable_ok else None,
            model_path=self.model_path,
            executable_available=executable_ok,
            model_available=model_ok,
            ready_to_start=executable_ok and model_ok,
            details=tuple(details),
        )

    @property
    def base_url(self) -> str | None:
        """URL privada da instância pertencente a este gerenciador."""
        with self._lock:
            if self._port is None or self._process is None:
                return None
            return f"http://{self.host}:{self._port}"

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._process is not None and self._process.poll() is None

    def ensure_running(
        self,
        *,
        token: CancellationToken | None = None,
        progress: ProgressSink | None = None,
    ) -> str:
        """Inicia ou reutiliza a instância saudável, sem criar duplicatas."""
        with self._lock:
            self._raise_if_cancelled(token)
            inspection = self.inspect()
            if not inspection.ready_to_start or inspection.executable is None:
                raise ModelError("TranslateGemma ainda não está instalado. " + " ".join(inspection.details))

            if self._process is not None and self._process.poll() is None:
                if (
                    self._port is not None
                    and self._is_healthy(self._port)
                    and self._process is not None
                    and self._process.poll() is None
                ):
                    if progress is not None:
                        progress.report(1.0, "Servidor TranslateGemma já está pronto")
                    return f"http://{self.host}:{self._port}"
                self._stop_process_locked()

            port = self._available_port()
            executable_name = inspection.executable.name.casefold()
            is_standalone_server = executable_name in {"llama-server", "llama-server.exe"}
            command = [str(inspection.executable)]
            if not is_standalone_server:
                command.append("serve")
            command.extend([
                "-m",
                str(inspection.model_path),
                "--host",
                self.host,
                "--port",
                str(port),
                "-c",
                str(self.context_size),
                "-np",
                "1",
                "-t",
                str(self.threads),
                "--no-webui",
                "--alias",
                DEFAULT_MODEL_ALIAS,
            ])
            if progress is not None:
                progress.report(0.05, "Iniciando servidor local TranslateGemma")
            try:
                process = self._popen_factory(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    close_fds=True,
                )
            except OSError as exc:
                raise ModelError(
                    f"Não foi possível iniciar llama.cpp ({type(exc).__name__})."
                ) from None
            self._process = process
            self._port = port
            try:
                self._wait_until_ready(token=token, progress=progress)
            except Exception:
                self._stop_process_locked()
                raise
            if progress is not None:
                progress.report(1.0, "Servidor TranslateGemma pronto")
            return f"http://{self.host}:{port}"

    def shutdown(self, *, grace_seconds: float = 5.0) -> None:
        """Encerra somente o filho criado por esta instância; preserva o cache."""
        if grace_seconds < 0:
            raise ValueError("O período de encerramento não pode ser negativo.")
        with self._lock:
            process = self._process
            self._process = None
            self._port = None
            if process is None or process.poll() is not None:
                return
            process.terminate()
            try:
                process.wait(timeout=grace_seconds)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

    def _wait_until_ready(
        self,
        *,
        token: CancellationToken | None,
        progress: ProgressSink | None,
    ) -> None:
        deadline = self._monotonic() + self.startup_timeout
        while self._monotonic() < deadline:
            self._raise_if_cancelled(token)
            process = self._process
            if process is None or process.poll() is not None:
                raise ModelError("O servidor llama.cpp encerrou antes de ficar pronto.")
            if self._port is not None and self._is_healthy(self._port):
                return
            if progress is not None:
                remaining = max(0.0, deadline - self._monotonic())
                fraction = min(0.95, 0.1 + 0.85 * (1 - remaining / self.startup_timeout))
                progress.report(fraction, "Aguardando o servidor TranslateGemma")
            self._sleep(_POLL_INTERVAL)
        raise ModelError(
            f"llama.cpp não ficou pronto em {self.startup_timeout:g} segundos."
        )

    def _is_healthy(self, port: int) -> bool:
        request = Request(f"http://{self.host}:{port}/health", method="GET")
        try:
            with self._opener(request, timeout=_HEALTH_TIMEOUT) as response:
                status = getattr(response, "status", None)
                if status is None:
                    status = response.getcode()
                return 200 <= int(status) < 300
        except (OSError, TimeoutError, URLError, ValueError):
            return False

    def _available_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind((self.host, 0))
            return int(listener.getsockname()[1])

    @staticmethod
    def _raise_if_cancelled(token: CancellationToken | None) -> None:
        if token is not None:
            token.raise_if_cancelled()

    def _stop_process_locked(self) -> None:
        process = self._process
        self._process = None
        self._port = None
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
