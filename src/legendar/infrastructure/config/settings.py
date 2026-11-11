"""Configuração de caminhos do aplicativo, sem dependências externas.

Variáveis de ambiente opcionais permitem testes hermeticos e uso portátil:
* ``LEGENDAR_CACHE_DIR`` — base para modelos e logs;
* ``LEGENDAR_OUTPUT_DIR`` — diretório sugerido para os SRTs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from legendar.infrastructure.filesystem.paths import (
    ensure_directory,
    ensure_private_directory,
)

APP_NAME = "legendar"


def _expand_base(env_var: str, default: Path) -> Path:
    raw = os.environ.get(env_var, "").strip()
    return Path(raw).expanduser() if raw else default


@dataclass(frozen=True, slots=True)
class AppSettings:
    """Caminhos resolvidos usados pela composição e pela GUI."""

    cache_dir: Path
    output_dir: Path

    @property
    def models_dir(self) -> Path:
        return self.cache_dir / "models"

    @property
    def logs_dir(self) -> Path:
        return self.cache_dir / "logs"

    @property
    def temp_dir(self) -> Path:
        return self.cache_dir / "tmp"

    @classmethod
    def load(
        cls, *, cache_dir: Path | None = None, output_dir: Path | None = None
    ) -> AppSettings:
        default_cache = Path.home() / ".cache" / APP_NAME
        default_output = Path.home() / "Videos"
        return cls(
            cache_dir=Path(cache_dir).expanduser()
            if cache_dir is not None
            else _expand_base("LEGENDAR_CACHE_DIR", default_cache),
            output_dir=Path(output_dir).expanduser()
            if output_dir is not None
            else _expand_base("LEGENDAR_OUTPUT_DIR", default_output),
        )

    def ensure_directories(self) -> None:
        """Cria cache/log/temp; nunca o diretório de saída.

        Cache e temporários nascem privados (``0o700``) porque ferramentas de
        terceiros recusam diretórios graváveis pelo grupo — é a causa da falha
        do ``punkt_tab`` no fim do alinhamento.
        """

        for path in (self.cache_dir, self.models_dir):
            ensure_private_directory(path)
        ensure_private_directory(self.temp_dir)
        ensure_directory(self.logs_dir)


def suggest_output_path(settings: AppSettings, source_label: str) -> Path:
    """Sugere ``<output_dir>/<nome-da-fonte>.<idioma>.srt`` sem tocar em disco."""
    stem = Path(source_label).stem if source_label else "legenda"
    stem = stem.strip() or "legenda"
    return settings.output_dir / f"{stem}.srt"
