"""Gerenciamento do processo local llama.cpp para TranslateGemma.

O módulo não instala o binário llama.cpp. O download do GGUF é explícito,
retomável e validado por SHA-256; a camada de aplicação/UI deve solicitar
consentimento antes de chamá-lo. Locks de arquivo evitam downloads e servidores
duplicados entre instâncias; somente o processo próprio é encerrado.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from legendar.application.ports.protocols import CancellationToken, ProgressSink
from legendar.domain.errors.catalog import ModelError

DEFAULT_MODEL_FILENAME = "translategemma-4b-it-Q4_K_M.gguf"
MODEL_REPOSITORY = "bullerwins/translategemma-4b-it-GGUF"
MODEL_REVISION = "7c938465a870d8624bcfa98a8e4a3510053c19a8"
MODEL_SHA256 = "7f7357c14abd9da4eb200b38b05da502cd6e10d7e1d403fbc9f78c19f3209b72"
MODEL_DOWNLOAD_URL = (
    "https://huggingface.co/"
    f"{MODEL_REPOSITORY}/resolve/{MODEL_REVISION}/{DEFAULT_MODEL_FILENAME}"
)
DEFAULT_MODEL_ALIAS = "translategemma-4b"
DEFAULT_CONTEXT_SIZE = 2048
DEFAULT_THREADS = 4
DEFAULT_STARTUP_TIMEOUT = 90.0
_HEALTH_TIMEOUT = 1.5
_POLL_INTERVAL = 0.25


def _huggingface_token() -> str | None:
    """Lê token já configurado pelo usuário, sem persistir ou expor o segredo."""
    try:
        from huggingface_hub import get_token
    except ImportError:
        return (
            os.environ.get("HF_TOKEN")
            or os.environ.get("HUGGING_FACE_HUB_TOKEN")
            or None
        )
    return get_token()


class _InterProcessLock:
    """Lock de arquivo não bloqueante, liberado automaticamente se o processo cair."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._file: Any | None = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        if self.path.stat().st_size == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return False
        self._file = handle
        return True

    def release(self) -> None:
        handle, self._file = self._file, None
        if handle is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()

    def __enter__(self) -> _InterProcessLock:
        if not self.acquire():
            raise ModelError(
                "Outra instância do Legendar já está preparando o modelo "
                "TranslateGemma."
            )
        return self

    def __exit__(self, *_args: object) -> None:
        self.release()


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
        model_sha256: str = MODEL_SHA256,
        token_provider: Callable[[], str | None] = _huggingface_token,
    ) -> None:
        if host != "127.0.0.1":
            raise ValueError(
                "O servidor TranslateGemma deve escutar somente em 127.0.0.1."
            )
        if context_size < 512 or context_size > 2048:
            raise ValueError("O contexto TranslateGemma deve ficar entre 512 e 2048.")
        if threads < 1:
            raise ValueError("O número de threads deve ser positivo.")
        if startup_timeout <= 0:
            raise ValueError("O timeout de inicialização deve ser positivo.")
        self.models_dir = Path(models_dir).expanduser()
        self.model_path = (
            Path(model_path)
            if model_path
            else (self.models_dir / "translategemma" / DEFAULT_MODEL_FILENAME)
        )
        self.host = host
        self.context_size = context_size
        self.threads = threads
        self.startup_timeout = startup_timeout
        self.model_sha256 = model_sha256
        self._token_provider = token_provider
        self._configured_executable = (
            Path(executable).expanduser() if executable else None
        )
        self._popen_factory = popen_factory
        self._opener = opener
        self._sleep = sleep
        self._monotonic = monotonic
        self._lock = threading.RLock()
        self._download_lock = _InterProcessLock(
            self.model_path.parent / ".translategemma-download.lock"
        )
        self._runtime_lock: _InterProcessLock | None = None
        self._process: Any | None = None
        self._port: int | None = None
        self._validated_model_signature: tuple[int, int, int] | None = None
        self._download_authorized = False
        self._download_required = False

    @property
    def needs_download_authorization(self) -> bool:
        """Indica ausência ou corrupção detectada dos pesos locais."""
        return self._download_required or not self.model_path.is_file()

    @property
    def download_authorized(self) -> bool:
        """Consentimento de download concedido nesta sessão do aplicativo."""
        return self._download_authorized

    def authorize_model_download(self) -> None:
        """Registra consentimento explícito apenas em memória."""
        self._download_authorized = True

    def ensure_model(
        self,
        *,
        token: CancellationToken | None = None,
        progress: ProgressSink | None = None,
    ) -> Path:
        """Garante pesos íntegros; baixa somente após consentimento nesta sessão."""
        if self.model_path.is_file():
            try:
                self._validate_model_integrity(token)
            except ModelError:
                if not self._download_authorized:
                    raise
            else:
                return self.model_path
        if not self._download_authorized:
            raise ModelError(
                "Os pesos TranslateGemma ainda não estão instalados. "
                "Autorize o download nas Preferências para prepará-los "
                "automaticamente na próxima tradução."
            )
        return self.download_model(consent=True, token=token, progress=progress)

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

    def download_model(
        self,
        *,
        consent: bool,
        token: CancellationToken | None = None,
        progress: ProgressSink | None = None,
    ) -> Path:
        """Baixa o GGUF fixado após consentimento, com retomada e validação SHA-256.

        Um arquivo parcial nunca é considerado instalado. Interrupções preservam
        o .part para retomada; somente o hash esperado permite publicação atômica.
        """
        if not consent:
            raise ModelError(
                "O download do TranslateGemma exige autorização explícita."
            )
        with self._lock, self._download_lock:
            self._raise_if_cancelled(token)
            self.model_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if os.name != "nt":
                os.chmod(self.model_path.parent, 0o700)
            if self.model_path.is_file():
                if self._sha256_file(self.model_path, token) == self.model_sha256:
                    if progress is not None:
                        progress.report(1.0, "Modelo TranslateGemma já está íntegro")
                    return self.model_path
                quarantine = self.model_path.with_name(
                    f"{self.model_path.name}.invalid.{time.time_ns()}"
                )
                os.replace(self.model_path, quarantine)
                self._validated_model_signature = None

            partial_path = self.model_path.with_suffix(self.model_path.suffix + ".part")
            offset = partial_path.stat().st_size if partial_path.is_file() else 0
            headers = {"Range": f"bytes={offset}-"} if offset else {}
            hf_token = self._token_provider()
            if hf_token:
                headers["Authorization"] = f"Bearer {hf_token}"
            request = Request(MODEL_DOWNLOAD_URL, headers=headers, method="GET")
            try:
                with self._opener(request, timeout=60.0) as response:
                    status = self._response_status(response)
                    if offset and status == 200:
                        # Sem suporte a Range, reiniciar para não duplicar bytes.
                        offset = 0
                    elif offset and status != 206:
                        raise ModelError(
                            "O servidor não aceitou a retomada do download "
                            "TranslateGemma (resposta HTTP inesperada)."
                        )
                    elif not offset and status != 200:
                        raise ModelError(
                            "O servidor respondeu de forma inesperada ao download "
                            "TranslateGemma."
                        )

                    content_range = self._response_header(response, "Content-Range")
                    if offset and (
                        not content_range
                        or not content_range.startswith(f"bytes {offset}-")
                    ):
                        raise ModelError(
                            "A resposta de retomada não corresponde ao trecho "
                            "solicitado; o arquivo parcial foi preservado."
                        )
                    content_length = self._response_header(response, "Content-Length")
                    try:
                        remaining = int(content_length or "")
                    except ValueError:
                        raise ModelError(
                            "O servidor não informou o tamanho do arquivo; "
                            "o download foi interrompido por segurança."
                        ) from None
                    if remaining <= 0:
                        raise ModelError("O servidor informou um tamanho inválido.")
                    total = offset + remaining
                    if shutil.disk_usage(self.model_path.parent).free < remaining:
                        raise ModelError(
                            "Espaço livre insuficiente para baixar o modelo "
                            "TranslateGemma."
                        )

                    digest = self._sha256_prefix(partial_path, offset, token)
                    mode = "ab" if offset else "wb"
                    downloaded = offset
                    if progress is not None:
                        progress.report(0.0, "Baixando TranslateGemma (aprox. 2,49 GB)")
                    with partial_path.open(mode) as output:
                        while True:
                            self._raise_if_cancelled(token)
                            chunk = response.read(8 * 1024 * 1024)
                            if not chunk:
                                break
                            output.write(chunk)
                            digest.update(chunk)
                            downloaded += len(chunk)
                            if progress is not None:
                                progress.report(
                                    min(0.99, downloaded / total),
                                    "Baixando TranslateGemma",
                                )
                        output.flush()
                        os.fsync(output.fileno())
            except ModelError:
                raise
            except HTTPError as exc:
                if exc.code in {401, 403}:
                    raise ModelError(
                        "O Hugging Face recusou o acesso ao TranslateGemma. "
                        "Aceite os termos/licença Gemma na página do modelo e "
                        "autentique-se localmente com o Hugging Face CLI ou HF_TOKEN. "
                        "O Legendar reutiliza a credencial local existente, mas não "
                        "armazena nem registra o token."
                    ) from None
                raise ModelError(
                    "O Hugging Face respondeu com HTTP "
                    f"{exc.code} durante o download do TranslateGemma."
                ) from None
            except (OSError, TimeoutError, URLError) as exc:
                raise ModelError(
                    "Falha de rede durante o download do TranslateGemma "
                    f"({type(exc).__name__}); o arquivo parcial foi preservado."
                ) from None

            if downloaded != total:
                raise ModelError(
                    "O download TranslateGemma terminou incompleto; "
                    "o arquivo parcial poderá ser retomado."
                )
            if digest.hexdigest() != self.model_sha256:
                partial_path.unlink(missing_ok=True)
                raise ModelError(
                    "O SHA-256 do TranslateGemma não corresponde ao artefato "
                    "fixado; o arquivo inválido foi descartado."
                )
            os.replace(partial_path, self.model_path)
            if os.name != "nt":
                os.chmod(self.model_path, 0o600)
            self._remember_validated_model()
            self._download_required = False
            if progress is not None:
                progress.report(1.0, "Modelo TranslateGemma baixado e validado")
            return self.model_path

    def _remember_validated_model(self) -> None:
        stat = self.model_path.stat()
        self._validated_model_signature = (
            stat.st_size,
            stat.st_mtime_ns,
            getattr(stat, "st_ino", 0),
        )

    def _validate_model_integrity(self, token: CancellationToken | None) -> None:
        """Valida o GGUF antes do spawn e evita re-hash durante a mesma sessão."""
        try:
            stat = self.model_path.stat()
        except OSError as exc:
            raise ModelError(
                "Não foi possível acessar os pesos TranslateGemma."
            ) from exc
        signature = (
            stat.st_size,
            stat.st_mtime_ns,
            getattr(stat, "st_ino", 0),
        )
        if signature == self._validated_model_signature:
            return
        if (
            stat.st_size <= 0
            or self._sha256_file(self.model_path, token) != self.model_sha256
        ):
            self._validated_model_signature = None
            self._download_required = True
            raise ModelError(
                "O arquivo local TranslateGemma não corresponde ao SHA-256 "
                "do modelo aprovado. Faça novamente o download autorizado."
            )
        self._validated_model_signature = signature

    @staticmethod
    def _response_status(response: Any) -> int:
        status = getattr(response, "status", None)
        if status is None:
            status = response.getcode()
        return int(status)

    @staticmethod
    def _response_header(response: Any, name: str) -> str | None:
        headers = getattr(response, "headers", None)
        if headers is None:
            return None
        value = headers.get(name)
        return str(value) if value is not None else None

    @staticmethod
    def _sha256_prefix(path: Path, size: int, token: CancellationToken | None) -> Any:
        import hashlib

        digest = hashlib.sha256()
        if size:
            with path.open("rb") as source:
                remaining = size
                while remaining:
                    LlamaCppRuntimeManager._raise_if_cancelled(token)
                    chunk = source.read(min(8 * 1024 * 1024, remaining))
                    if not chunk:
                        raise ModelError(
                            "O arquivo parcial do TranslateGemma está truncado."
                        )
                    digest.update(chunk)
                    remaining -= len(chunk)
        return digest

    @staticmethod
    def _sha256_file(path: Path, token: CancellationToken | None) -> str:
        import hashlib

        digest = hashlib.sha256()
        with path.open("rb") as source:
            while True:
                LlamaCppRuntimeManager._raise_if_cancelled(token)
                chunk = source.read(8 * 1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    @property
    def base_url(self) -> str | None:
        """URL privada da instância pertencente a este gerenciador."""
        with self._lock:
            if (
                self._port is None
                or self._process is None
                or self._process.poll() is not None
            ):
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
                raise ModelError(
                    "TranslateGemma ainda não está instalado. "
                    + " ".join(inspection.details)
                )

            if self._process is not None:
                if (
                    self._process.poll() is None
                    and self._port is not None
                    and self._is_healthy(self._port)
                    and self._process.poll() is None
                ):
                    if progress is not None:
                        progress.report(1.0, "Servidor TranslateGemma já está pronto")
                    return f"http://{self.host}:{self._port}"
                self._stop_process_locked()

            self._validate_model_integrity(token)

            port = self._available_port()
            executable_name = inspection.executable.name.casefold()
            is_standalone_server = executable_name in {
                "llama-server",
                "llama-server.exe",
            }
            command = [str(inspection.executable)]
            if not is_standalone_server:
                command.append("serve")
            command.extend(
                [
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
                ]
            )
            if progress is not None:
                progress.report(0.05, "Iniciando servidor local TranslateGemma")
            runtime_lock = _InterProcessLock(
                self.models_dir / ".translategemma-runtime.lock"
            )
            if not runtime_lock.acquire():
                raise ModelError(
                    "Outra instância do Legendar já gerencia o servidor "
                    "TranslateGemma. Feche a outra instância ou aguarde."
                )
            self._runtime_lock = runtime_lock
            try:
                process = self._popen_factory(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    close_fds=True,
                )
            except Exception as exc:
                self._release_runtime_lock_locked()
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
            if process is None or process.poll() is not None:
                self._process = None
                self._port = None
                self._release_runtime_lock_locked()
                return
            try:
                process.terminate()
                try:
                    process.wait(timeout=grace_seconds)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            except Exception:
                if process.poll() is not None:
                    self._process = None
                    self._port = None
                    self._release_runtime_lock_locked()
                raise
            self._process = None
            self._port = None
            self._release_runtime_lock_locked()

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
                fraction = min(
                    0.95, 0.1 + 0.85 * (1 - remaining / self.startup_timeout)
                )
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
        if process is None or process.poll() is not None:
            self._process = None
            self._port = None
            self._release_runtime_lock_locked()
            return
        try:
            process.terminate()
            try:
                process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        except Exception:
            if process.poll() is not None:
                self._process = None
                self._port = None
                self._release_runtime_lock_locked()
            raise
        self._process = None
        self._port = None
        self._release_runtime_lock_locked()

    def _release_runtime_lock_locked(self) -> None:
        lock, self._runtime_lock = self._runtime_lock, None
        if lock is not None:
            lock.release()
