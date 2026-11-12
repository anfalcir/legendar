"""Composição do aplicativo: portas reais de media, fala, alinhamento, tradução e SRT."""

from __future__ import annotations

import importlib.util
import os
import re
import sys
from collections.abc import Callable, Mapping, Sequence

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from legendar import __version__
from legendar.application.pipeline.serial_pipeline import (
    PipelinePorts,
    SerialPipeline,
)
from legendar.application.ports.protocols import Aligner, Transcriber, Translator
from legendar.infrastructure.alignment.whisperx import WhisperXAligner
from legendar.infrastructure.config.credentials import load_gemini_api_key
from legendar.infrastructure.config.settings import AppSettings, suggest_output_path
from legendar.infrastructure.diagnostics.performance import JsonPerformanceReporter
from legendar.infrastructure.filesystem.publisher import SrtPublisher
from legendar.infrastructure.filesystem.workspace import TempWorkspaceFactory
from legendar.infrastructure.logging.setup import configure_logging
from legendar.infrastructure.media.ffmpeg import FfmpegAudioPreparer
from legendar.infrastructure.media.probe import FfprobeInspector
from legendar.infrastructure.media.tools import ToolStatus, locate_tools
from legendar.infrastructure.media.youtube import YtDlpDownloader
from legendar.infrastructure.transcription.faster_whisper import (
    FasterWhisperTranscriber,
)
from legendar.infrastructure.transcription.whisper import WhisperTranscriber
from legendar.infrastructure.translation.gemini import GeminiTranslator
from legendar.infrastructure.translation.nllb import NllbTranslator
from legendar.presentation.qt.branding import app_icon
from legendar.presentation.qt.main_window import MainWindow, UiDependencies
from legendar.presentation.qt.preferences import load_preferences

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


def _pipeline_factory(
    inspector: FfprobeInspector,
    downloader: YtDlpDownloader,
    transcriber: Transcriber,
    aligner: Aligner,
    translator: Translator,
    performance_reporter: JsonPerformanceReporter | None = None,
) -> SerialPipeline:
    """Monta aquisição, reconhecimento, alinhamento, tradução e publicação."""

    return SerialPipeline(
        PipelinePorts(
            inspector=inspector,
            audio_preparer=FfmpegAudioPreparer(inspector=inspector),
            transcriber=transcriber,
            aligner=aligner,
            publisher=SrtPublisher(),
            translator=translator,
            downloader=downloader,
        ),
        performance_reporter=performance_reporter,
    )


def build_ui_dependencies(
    settings: AppSettings,
    *,
    tool_locator: ToolLocator = locate_tools,
    translation_backend: str | None = None,
    gemini_api_key: str | None = None,
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

    asr_backend = os.environ.get("LEGENDAR_ASR_BACKEND", "whisper").strip().casefold()
    transcription_configuration_ok = asr_backend in {"whisper", "faster-whisper"}
    try:
        whisper_installed = importlib.util.find_spec("whisper") is not None
    except (ImportError, ValueError):
        whisper_installed = False
    try:
        faster_whisper_installed = (
            importlib.util.find_spec("faster_whisper") is not None
        )
    except (ImportError, ValueError):
        faster_whisper_installed = False

    if asr_backend == "faster-whisper":
        if faster_whisper_installed:
            try:
                transcriber = FasterWhisperTranscriber.from_environment(
                    settings.models_dir
                )
            except ValueError as exc:
                transcriber = WhisperTranscriber(models_dir=settings.models_dir)
                transcription_configuration_ok = False
                transcription_details = (
                    f"Configuração faster-whisper inválida: {exc}",
                )
            else:
                transcription_details = (
                    f"faster-whisper/CTranslate2 instalado · modelo {transcriber.model_name}",
                    f"Dispositivo: {transcriber.requested_device} · "
                    f"compute type: {transcriber.requested_compute_type or 'automático'}",
                    f"CPU threads: {transcriber.cpu_threads} · beam: {transcriber.beam_size}",
                )
        else:
            transcriber = WhisperTranscriber(models_dir=settings.models_dir)
            transcription_configuration_ok = False
            transcription_details = (
                "faster-whisper não instalado; sincronize runtime-cpu ou runtime-cu128.",
            )
    elif asr_backend == "whisper":
        try:
            transcriber = WhisperTranscriber.from_environment(settings.models_dir)
        except ValueError as exc:
            transcriber = WhisperTranscriber(models_dir=settings.models_dir)
            transcription_configuration_ok = False
            transcription_details = (f"Configuração Whisper inválida: {exc}",)
        else:
            transcription_details = (
                f"OpenAI Whisper instalado · modelo {transcriber.model_name}",
                f"Dispositivo: {transcriber.requested_device} · pesos no cache local",
            )
    else:
        transcriber = WhisperTranscriber(models_dir=settings.models_dir)
        transcription_configuration_ok = False
        transcription_details = (
            "LEGENDAR_ASR_BACKEND inválido; use whisper ou faster-whisper.",
        )

    if asr_backend == "whisper" and not whisper_installed:
        transcription_details = (
            "openai-whisper não instalado; sincronize runtime-cpu ou runtime-cu128.",
        )
    if asr_backend == "faster-whisper" and not faster_whisper_installed:
        transcription_configuration_ok = False
    transcription_available = transcription_configuration_ok and (
        faster_whisper_installed
        if asr_backend == "faster-whisper"
        else whisper_installed
    )

    try:
        whisperx_installed = importlib.util.find_spec("whisperx") is not None
    except (ImportError, ValueError):
        whisperx_installed = False

    alignment_configuration_ok = True
    try:
        aligner = WhisperXAligner.from_environment(settings.models_dir)
    except ValueError as exc:
        aligner = WhisperXAligner(models_dir=settings.models_dir)
        alignment_configuration_ok = False
        alignment_details = (f"Configuração WhisperX inválida: {exc}",)
    else:
        alignment_details = (
            "WhisperX 3.8.6 · forced alignment PT/EN sob demanda",
            f"Dispositivo de alinhamento: {aligner.requested_device}",
            "Modelos de alinhamento no cache local",
        )

    if not whisperx_installed:
        alignment_details = (
            "WhisperX não instalado; sincronize runtime-cpu ou runtime-cu128.",
        )
    alignment_available = whisperx_installed and alignment_configuration_ok

    env_translation_backend = (
        os.environ.get("LEGENDAR_TRANSLATION_BACKEND", "nllb").strip().casefold()
    )

    def _configure_translation(
        backend: str,
        api_key: str | None,
    ) -> tuple[Translator, bool, tuple[str, ...]]:
        backend = backend.strip().casefold()
        if backend == "gemini":
            try:
                translator = GeminiTranslator(
                    api_key=api_key,
                    model=os.environ.get("LEGENDAR_GEMINI_MODEL", "gemini-3.8-flash"),
                    batch_size=int(
                        os.environ.get("LEGENDAR_GEMINI_BATCH_SIZE", "32")
                    ),
                    timeout_seconds=float(
                        os.environ.get("LEGENDAR_GEMINI_TIMEOUT", "120")
                    ),
                    max_retries=int(
                        os.environ.get("LEGENDAR_GEMINI_MAX_RETRIES", "3")
                    ),
                    grounding=os.environ.get(
                        "LEGENDAR_GEMINI_GROUNDING", "true"
                    ).strip().casefold()
                    in {"1", "true", "yes", "on"},
                )
            except (ValueError, TypeError) as exc:
                return GeminiTranslator(), False, (f"Configuração Gemini inválida: {exc}",)
            details = (
                f"Gemini API · modelo {translator.model}",
                f"Lote: {translator.batch_size} cues · timeout: "
                f"{translator.timeout_seconds:g}s · retries: {translator.max_retries}",
                (
                    "Grounding Google Search habilitado."
                    if translator.grounding
                    else "Grounding Google Search desabilitado."
                ),
                (
                    "GEMINI_API_KEY configurada localmente."
                    if api_key and api_key == load_gemini_api_key()
                    else "GEMINI_API_KEY configurada no ambiente."
                    if api_key
                    else "GEMINI_API_KEY ausente; configure-a em Preferências."
                ),
            )
            return translator, translator.is_configured, details

        if backend == "nllb":
            try:
                transformers_installed = (
                    importlib.util.find_spec("transformers") is not None
                )
            except (ImportError, ValueError):
                transformers_installed = False
            try:
                translator = NllbTranslator.from_environment(settings.models_dir)
            except ValueError as exc:
                translator = NllbTranslator(settings.models_dir)
                return translator, False, (f"Configuração NLLB inválida: {exc}",)
            details = (
                f"NLLB-200 distilled · modelo {translator.model_name}",
                f"Dispositivo de tradução: {translator.requested_device}",
                f"Pesos no cache local: {translator.download_root}",
            )
            if not transformers_installed:
                details = (
                    "transformers não instalado; sincronize runtime-cpu ou runtime-cu128.",
                )
            return translator, transformers_installed, details

        return (
            NllbTranslator(settings.models_dir),
            False,
            ("LEGENDAR_TRANSLATION_BACKEND inválido; use nllb ou gemini.",),
        )

    local_gemini_key = load_gemini_api_key()
    configured_backend = (
        translation_backend
        if translation_backend is not None
        else env_translation_backend
    ).strip().casefold()
    translator, translation_available, translation_details = _configure_translation(
        configured_backend,
        gemini_api_key
        or local_gemini_key
        or os.environ.get("GEMINI_API_KEY"),
    )
    translator_holder: dict[str, Translator] = {"translator": translator}

    def reconfigure_translation(
        backend: str,
        api_key: str | None,
    ) -> tuple[bool, tuple[str, ...]]:
        selected, available, details = _configure_translation(backend, api_key)
        translator_holder["translator"] = selected
        return available, details

    inspector = FfprobeInspector()
    downloader = YtDlpDownloader(
        js_runtime=selected_runtime[0] if selected_runtime else None,
        js_runtime_path=selected_runtime[1].path if selected_runtime else None,
    )
    performance_reporter = JsonPerformanceReporter(settings.logs_dir)
    return UiDependencies(
        output_dir=settings.output_dir,
        cache_dir=settings.models_dir,
        workspace_factory=TempWorkspaceFactory(settings.temp_dir),
        pipeline_factory=lambda: _pipeline_factory(
            inspector,
            downloader,
            transcriber,
            aligner,
            translator_holder["translator"],
            performance_reporter,
        ),
        output_path_factory=lambda stem, _language: suggest_output_path(settings, stem),
        translate_available=translation_available,
        translate_readiness_details=translation_details,
        translation_backend=configured_backend,
        translation_reconfigure=reconfigure_translation,
        readiness_ok=readiness_ok,
        readiness_details=readiness_details,
        app_version=__version__,
        media_inspector=inspector,
        youtube_available=youtube_available,
        youtube_readiness_details=youtube_details,
        transcription_available=transcription_available,
        transcription_readiness_details=transcription_details,
        alignment_available=alignment_available,
        alignment_readiness_details=alignment_details,
        publishing_available=True,
        publishing_readiness_details=(
            "Publicação SRT atômica em UTF-8 (até 2 linhas por cue).",
            "Validação round-trip concluída antes de escrever no destino.",
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Ponto de entrada de desenvolvimento: prepara diretórios e abre a GUI."""

    settings = AppSettings.load()
    settings.ensure_directories()
    configure_logging(settings.logs_dir)

    qt_settings = QSettings("Legendar", "Legendar")
    preferences = load_preferences(qt_settings, settings.output_dir)
    selected_backend = preferences.translation_backend
    if not qt_settings.contains("translation/backend"):
        selected_backend = os.environ.get(
            "LEGENDAR_TRANSLATION_BACKEND", selected_backend
        ).strip().casefold()
    gemini_key = load_gemini_api_key()

    app = QApplication(list(argv) if argv is not None else sys.argv)
    app.setApplicationName("Legendar")
    app.setApplicationVersion(__version__)
    app.setWindowIcon(app_icon())
    window = MainWindow(
        build_ui_dependencies(
            settings,
            translation_backend=selected_backend,
            gemini_api_key=gemini_key,
        ),
        settings=qt_settings,
    )
    window.show()
    return int(app.exec())
