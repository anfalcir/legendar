"""Composição explícita da Fase 1: caminhos, preflight, pipeline e janela.

O bootstrap é a única camada que importa infraestrutura e apresentação ao
mesmo tempo. A janela recebe tudo pronto por ``UiDependencies`` e continua sem
conhecer FFmpeg, modelos ou o cache compartilhado.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Mapping, Sequence

from PySide6.QtWidgets import QApplication

from legendar import __version__
from legendar.application.pipeline.serial_pipeline import SerialPipeline
from legendar.domain.errors.catalog import ModelError
from legendar.infrastructure.config.settings import AppSettings, suggest_output_path
from legendar.infrastructure.filesystem.workspace import TempWorkspaceFactory
from legendar.infrastructure.logging.setup import configure_logging
from legendar.infrastructure.media.tools import ToolStatus, locate_tools
from legendar.presentation.qt.main_window import MainWindow, UiDependencies

ToolLocator = Callable[[tuple[str, ...]], Mapping[str, ToolStatus]]

#: A integração real de mídia/modelos é entregue na Fase 3. Até lá, o botão
#: inicia um job que falha de forma explícita e amigável, em vez de a janela
#: fingir que processou algo.
_PENDING_PIPELINE_MESSAGE = (
    "O processamento de mídia (áudio, transcrição e alinhamento) será "
    "conectado na Fase 3. Nesta fase, o fluxo da janela pode ser exercitado "
    "com os dublês da suíte de testes."
)


def _pipeline_factory() -> SerialPipeline:
    raise ModelError(_PENDING_PIPELINE_MESSAGE)


def build_ui_dependencies(
    settings: AppSettings,
    *,
    tool_locator: ToolLocator = locate_tools,
) -> UiDependencies:
    """Monta as dependências da janela a partir de ``settings``.

    ``tool_locator`` é injetável para que os testes não executem ``--version``
    de ferramentas externas. O preflight nunca levanta exceção: ausência de
    FFmpeg é um estado explícito exibido na própria janela.
    """
    statuses = tool_locator(("ffmpeg", "ffprobe"))
    details = tuple(status.label_pt for status in statuses.values())
    readiness_ok = bool(statuses) and all(
        status.available for status in statuses.values()
    )
    return UiDependencies(
        output_dir=settings.output_dir,
        cache_dir=settings.models_dir,
        workspace_factory=TempWorkspaceFactory(settings.temp_dir),
        pipeline_factory=_pipeline_factory,
        output_path_factory=lambda stem, _language: suggest_output_path(settings, stem),
        translate_available=False,
        readiness_ok=readiness_ok,
        readiness_details=details,
        app_version=__version__,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Ponto de entrada de desenvolvimento: prepara diretórios e abre a GUI."""
    settings = AppSettings.load()
    settings.ensure_directories()
    configure_logging(settings.logs_dir)

    app = QApplication(list(argv) if argv is not None else sys.argv)
    app.setApplicationName("Legendar")
    app.setApplicationVersion(__version__)
    window = MainWindow(build_ui_dependencies(settings))
    window.show()
    return int(app.exec())
