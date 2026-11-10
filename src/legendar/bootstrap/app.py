"""Composição do aplicativo: portas reais de entrada e placeholders de fases futuras."""

from __future__ import annotations

import importlib.util
import re
import sys
from collections.abc import Callable, Mapping, Sequence

from PySide6.QtWidgets import QApplication

from legendar import __version__
from legendar.application.pipeline.serial_pipeline import (
    PipelinePorts,
    SerialPipeline,
)
from legendar.domain.entities.media import AudioAsset
from legendar.domain.entities.subtitle import SubtitleTrack
from legendar.domain.entities.transcript import Transcript
from legendar.domain.errors.catalog import ModelError
from legendar.domain.value_objects.language import Language
from legendar.infrastructure.config.settings import AppSettings, suggest_output_path
from legendar.infrastructure.filesystem.workspace import TempWorkspaceFactory
from legendar.infrastructure.logging.setup import configure_logging
from legendar.infrastructure.media.ffmpeg import FfmpegAudioPreparer
from legendar.infrastructure.media.probe import FfprobeInspector
from legendar.infrastructure.media.tools import ToolStatus, locate_tools
from legendar.infrastructure.media.youtube import YtDlpDownloader
from legendar.presentation.qt.main_window import MainWindow, UiDependencies

ToolLocator = Callable[[tuple[str, ...]], Mapping[str, ToolStatus]]
_JS_RUNTIME_MINIMUMS = {"deno": (2, 3, 0), "node": (22, 0, 0)}


def _runtime_version(status: ToolStatus) -> tuple[int, int, int] | None:
    """Extrai a versão sem assumir que um executável encontrado é compatível."""
    if not status.version:
        return None
    parts = re.findall("[0-9]+", status.version)
    if len(parts) < 2:
        return None
    values = [int(part) for part in parts[:3]]
    return tuple((values + [0, 0, 0])[:3])


def _select_js_runtime(
    statuses: Mapping[str, ToolStatus],
) -> tuple[str, ToolStatus] | None:
    """Prefere Deno >=2.3; Node >=22 é alternativa explícita."""
    for name in ("deno", "node"):
        status = statuses.get(name, ToolStatus(name=name))
        version = _runtime_version(status)
        if (
            status.available
            and version is not None
            and version >= _JS_RUNTIME_MINIMUMS[name]
        ):
            return name, status
    return None


def _js_runtime_details(
    statuses: Mapping[str, ToolStatus],
) -> tuple[str, ...]:
    details: list[str] = []
    for name in ("deno", "node"):
        status = statuses.get(name, ToolStatus(name=name))
        minimum = _JS_RUNTIME_MINIMUMS[name]
        minimum_label = ".".join(str(part) for part in minimum[:2])
        version = _runtime_version(status)
        if not status.available:
            details.append(f"{name}: não encontrado (mínimo {minimum_label})")
        elif version is None:
            details.append(f"{name}: versão não identificada (mínimo {minimum_label})")
        elif version < minimum:
            details.append(f"{status.version}: abaixo do mínimo {minimum_label}")
        else:
            details.append(f"{status.version}: compatível")
    return tuple(details)


class _PendingTranscriber:
    """Motor de fala reservado à Fase 4."""

    def transcribe(
        self, audio: AudioAsset, *, language: Language | None, progress, token=None
    ) -> Transcript:
        if token is not None:
            token.raise_if_cancelled()
        raise ModelError(
            "A entrada e a preparação do áudio foram concluídas. "
            "O reconhecimento Whisper será conectado na Fase 4."
        )


class _PendingAligner:
    """Motor de alinhamento reservado à Fase 5."""

    def align(self, audio: AudioAsset, transcript: Transcript, *, progress, token=None):
        raise ModelError("O alinhamento temporal será conectado na Fase 5.")


class _PendingPublisher:
    """Publicação final SRT reservada à Fase 6/7."""

    def publish(self, track: SubtitleTrack, destination_path: str) -> str:
        raise ModelError("A geração e publicação SRT serão concluídas nas Fases 6/7.")


def _pipeline_factory(
    inspector: FfprobeInspector, downloader: YtDlpDownloader
) -> SerialPipeline:
    """Monta aquisição, inspeção e normalização reais.

    Os motores posteriores são placeholders explícitos; o pipeline pode
    completar a Fase 3, mas nunca finge transcrição ou alinhamento.
    """

    return SerialPipeline(
        PipelinePorts(
            inspector=inspector,
            audio_preparer=FfmpegAudioPreparer(inspector=inspector),
            transcriber=_PendingTranscriber(),
            aligner=_PendingAligner(),
            publisher=_PendingPublisher(),
            downloader=downloader,
        )
    )


def build_ui_dependencies(
    settings: AppSettings,
    *,
    tool_locator: ToolLocator = locate_tools,
) -> UiDependencies:
    """Monta dependências da janela e executáveis observáveis pelo preflight."""

    statuses = tool_locator(("ffmpeg", "ffprobe", "deno", "node"))
    ffmpeg = statuses.get("ffmpeg", ToolStatus(name="ffmpeg"))
    ffprobe = statuses.get("ffprobe", ToolStatus(name="ffprobe"))
    readiness_details = (ffmpeg.label_pt, ffprobe.label_pt)
    readiness_ok = ffmpeg.available and ffprobe.available

    try:
        ytdlp_installed = importlib.util.find_spec("yt_dlp") is not None
    except (ImportError, ValueError):
        ytdlp_installed = False
    selected_runtime = _select_js_runtime(statuses)
    youtube_available = ytdlp_installed and selected_runtime is not None
    runtime_details = _js_runtime_details(statuses)
    youtube_details = (
        ("yt-dlp instalado" if ytdlp_installed else "yt-dlp não instalado"),
        (
            f"Runtime EJS selecionado: {selected_runtime[0]} {selected_runtime[1].version}"
            if selected_runtime is not None
            else "Nenhum runtime EJS compatível encontrado"
        ),
        *runtime_details,
    )

    inspector = FfprobeInspector()
    downloader = YtDlpDownloader(
        js_runtime=selected_runtime[0] if selected_runtime else None,
        js_runtime_path=selected_runtime[1].path if selected_runtime else None,
    )
    return UiDependencies(
        output_dir=settings.output_dir,
        cache_dir=settings.models_dir,
        workspace_factory=TempWorkspaceFactory(settings.temp_dir),
        pipeline_factory=lambda: _pipeline_factory(inspector, downloader),
        output_path_factory=lambda stem, _language: suggest_output_path(settings, stem),
        translate_available=False,
        readiness_ok=readiness_ok,
        readiness_details=readiness_details,
        app_version=__version__,
        media_inspector=inspector,
        youtube_available=youtube_available,
        youtube_readiness_details=youtube_details,
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
