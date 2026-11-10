"""Logging em arquivo com rotação, sem dados sensíveis por padrão.

O log técnico completo fica no arquivo; a UI recebe mensagens amigáveis via
eventos. Caminhos absolutos do usuário são mascarados antes de gravar.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGGER_NAME = "legendar"
_MAX_BYTES = 1_000_000
_BACKUP_COUNT = 2


def _redact(path: str) -> str:
    """Troca o home do usuário por ``~`` para não vazar caminho pessoal."""
    home = str(Path.home())
    return path.replace(home, "~") if home else path


class _RedactingFilter(logging.Filter):
    """Filtro que mascara o home do usuário em mensagens e argumentos."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _redact(record.msg)
        if record.args:
            record.args = tuple(
                _redact(arg) if isinstance(arg, str) else arg for arg in record.args
            )
        return True


def configure_logging(logs_dir: Path, *, level: int = logging.INFO) -> logging.Logger:
    """Configura o logger ``legendar`` uma única vez (idempotente)."""
    logger = logging.getLogger(LOGGER_NAME)
    if getattr(logger, "_legendar_configured", False):
        return logger

    logs_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        logs_dir / "legendar.log",
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)-8s %(name)s:%(lineno)d %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    handler.addFilter(_RedactingFilter())
    logger.setLevel(level)
    logger.addHandler(handler)
    logger.propagate = False
    logger._legendar_configured = True  # type: ignore[attr-defined]
    return logger


def get_logger(module: str) -> logging.Logger:
    return logging.getLogger(f"{LOGGER_NAME}.{module}")
