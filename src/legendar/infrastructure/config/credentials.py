"""Armazenamento local de credenciais da aplicação.

As chaves não são gravadas em QSettings, logs, relatórios de performance ou
arquivos do repositório. O segredo Gemini fica em um arquivo privado do perfil
do usuário, com permissão 0600 quando o sistema operacional suporta esse modo.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from PySide6.QtCore import QStandardPaths

_GEMINI_KEY_FILENAME = "gemini_api_key"


def _credentials_dir() -> Path:
    """Retorna o diretório privado de configuração do usuário."""

    location = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppConfigLocation
    )
    if not location:
        location = str(Path.home() / ".config" / "Legendar")
    path = Path(location) / "credentials"
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        path.chmod(0o700)
    except OSError:
        pass
    return path


def _key_path() -> Path:
    return _credentials_dir() / _GEMINI_KEY_FILENAME


def load_gemini_api_key() -> str | None:
    """Lê a chave local, sem registrar o conteúdo em logs ou configurações Qt."""

    path = _key_path()
    try:
        value = path.read_text(encoding="utf-8").strip()
    except (FileNotFoundError, OSError):
        return None
    return value or None


def save_gemini_api_key(api_key: str) -> None:
    """Salva a chave atomicamente e restringe o arquivo ao usuário."""

    value = api_key.strip()
    if not value:
        raise ValueError("A chave Gemini não pode ser vazia.")

    destination = _key_path()
    fd, temporary = tempfile.mkstemp(
        prefix=".gemini_api_key.",
        dir=destination.parent,
        text=True,
    )
    temporary_path = Path(temporary)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(value + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.replace(destination)
        try:
            destination.chmod(0o600)
        except OSError:
            pass
    except Exception:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def delete_gemini_api_key() -> None:
    """Remove a credencial local, se existir."""

    try:
        _key_path().unlink()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise RuntimeError("Não foi possível remover a chave Gemini local.") from exc


def gemini_api_key_configured() -> bool:
    return load_gemini_api_key() is not None
