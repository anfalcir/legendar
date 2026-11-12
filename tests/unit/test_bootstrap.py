"""Testes da composição inicial: preflight, caminhos e portas reais por etapa."""

from __future__ import annotations

from pathlib import Path

from legendar.application.pipeline.serial_pipeline import SerialPipeline
from legendar.bootstrap.app import build_ui_dependencies
from legendar.domain.value_objects.language import Language
from legendar.infrastructure.alignment.whisperx import WhisperXAligner
from legendar.infrastructure.config.settings import AppSettings
from legendar.infrastructure.filesystem.publisher import SrtPublisher
from legendar.infrastructure.media.ffmpeg import FfmpegAudioPreparer
from legendar.infrastructure.media.probe import FfprobeInspector
from legendar.infrastructure.media.tools import ToolStatus
from legendar.infrastructure.media.youtube import YtDlpDownloader
from legendar.infrastructure.transcription.faster_whisper import (
    FasterWhisperTranscriber,
)
from legendar.infrastructure.transcription.whisper import WhisperTranscriber
from legendar.infrastructure.translation.gemini import GeminiTranslator
from legendar.infrastructure.translation.nllb import NllbTranslator


def _settings(tmp_path: Path) -> AppSettings:
    return AppSettings(cache_dir=tmp_path / "cache", output_dir=tmp_path / "fora")


def _locator(*statuses: ToolStatus):
    def locate(names: tuple[str, ...]):
        by_name = {status.name: status for status in statuses}
        return {name: by_name.get(name, ToolStatus(name=name)) for name in names}

    return locate


def _patch_modules(monkeypatch, *installed: str) -> None:
    """Simula pacotes instalados sem importar as dependências pesadas."""

    def find_spec(name: str, *_args, **_kwargs):
        return object() if name in installed else None

    monkeypatch.setattr("legendar.bootstrap.app.importlib.util.find_spec", find_spec)


def test_readiness_ok_when_ffmpeg_and_ffprobe_are_present(
    tmp_path, monkeypatch
) -> None:
    _patch_modules(monkeypatch)
    dependencies = build_ui_dependencies(
        _settings(tmp_path),
        tool_locator=_locator(
            ToolStatus(name="ffmpeg", path="/usr/bin/ffmpeg", version="7.0"),
            ToolStatus(name="ffprobe", path="/usr/bin/ffprobe", version="7.0"),
        ),
    )

    assert dependencies.readiness_ok
    assert "ffmpeg" in dependencies.readiness_details[0]
    assert dependencies.translate_available is False
    assert dependencies.cache_dir == tmp_path / "cache" / "models"
    assert dependencies.output_dir == tmp_path / "fora"


def test_missing_tool_is_reported_without_raising(tmp_path, monkeypatch) -> None:
    _patch_modules(monkeypatch)
    dependencies = build_ui_dependencies(
        _settings(tmp_path),
        tool_locator=_locator(
            ToolStatus(name="ffmpeg"),
            ToolStatus(name="ffprobe", path="/usr/bin/ffprobe"),
        ),
    )

    assert not dependencies.readiness_ok
    assert "não encontrado" in dependencies.readiness_details[0]


def test_pipeline_composes_real_adapters_for_every_stage(tmp_path, monkeypatch) -> None:
    _patch_modules(monkeypatch)
    dependencies = build_ui_dependencies(
        _settings(tmp_path),
        tool_locator=_locator(
            ToolStatus(name="ffmpeg", path="/usr/bin/ffmpeg"),
            ToolStatus(name="ffprobe", path="/usr/bin/ffprobe"),
            ToolStatus(name="deno", path="/usr/bin/deno", version="deno 2.3.0"),
        ),
    )

    pipeline = dependencies.pipeline_factory()

    assert isinstance(pipeline, SerialPipeline)
    assert isinstance(pipeline._ports.inspector, FfprobeInspector)
    assert isinstance(pipeline._ports.audio_preparer, FfmpegAudioPreparer)
    assert isinstance(pipeline._ports.downloader, YtDlpDownloader)
    assert isinstance(pipeline._ports.transcriber, WhisperTranscriber)
    assert isinstance(pipeline._ports.aligner, WhisperXAligner)
    assert isinstance(pipeline._ports.translator, NllbTranslator)
    assert isinstance(pipeline._ports.publisher, SrtPublisher)
    assert dependencies.youtube_readiness_details[1].startswith(
        "Runtime EJS selecionado: deno"
    )
    assert pipeline._ports.downloader._js_runtime == "deno"
    assert pipeline._ports.downloader._js_runtime_path == "/usr/bin/deno"


def test_publishing_is_available_without_model_runtimes(tmp_path, monkeypatch) -> None:
    _patch_modules(monkeypatch)
    dependencies = build_ui_dependencies(
        _settings(tmp_path),
        tool_locator=_locator(
            ToolStatus(name="ffmpeg", path="/usr/bin/ffmpeg"),
            ToolStatus(name="ffprobe", path="/usr/bin/ffprobe"),
        ),
    )

    assert dependencies.publishing_available
    assert "round-trip" in dependencies.publishing_readiness_details[1]


def test_translation_is_available_when_transformers_is_installed(
    tmp_path, monkeypatch
) -> None:
    _patch_modules(monkeypatch, "transformers")
    monkeypatch.delenv("LEGENDAR_TRANSLATE_DEVICE", raising=False)
    monkeypatch.delenv("LEGENDAR_TRANSLATE_MODEL", raising=False)

    dependencies = build_ui_dependencies(
        _settings(tmp_path),
        tool_locator=_locator(
            ToolStatus(name="ffmpeg", path="/usr/bin/ffmpeg"),
            ToolStatus(name="ffprobe", path="/usr/bin/ffprobe"),
        ),
    )

    translator = dependencies.pipeline_factory()._ports.translator

    assert dependencies.translate_available
    assert "NLLB" in dependencies.translate_readiness_details[0]
    assert isinstance(translator, NllbTranslator)
    assert translator.requested_device == "auto"
    assert translator.download_root == tmp_path / "cache" / "models" / "nllb"


def test_invalid_translation_device_keeps_the_ui_usable(tmp_path, monkeypatch) -> None:
    _patch_modules(monkeypatch, "transformers")
    monkeypatch.setenv("LEGENDAR_TRANSLATE_DEVICE", "mps")

    dependencies = build_ui_dependencies(
        _settings(tmp_path),
        tool_locator=_locator(
            ToolStatus(name="ffmpeg", path="/usr/bin/ffmpeg"),
            ToolStatus(name="ffprobe", path="/usr/bin/ffprobe"),
        ),
    )

    assert not dependencies.translate_available
    assert "Configuração NLLB inválida" in dependencies.translate_readiness_details[0]
    assert isinstance(dependencies.pipeline_factory()._ports.translator, NllbTranslator)


def test_youtube_runtime_requires_supported_version_and_falls_back_to_node(
    tmp_path, monkeypatch
) -> None:
    _patch_modules(monkeypatch, "yt_dlp")
    dependencies = build_ui_dependencies(
        _settings(tmp_path),
        tool_locator=_locator(
            ToolStatus(name="ffmpeg", path="/usr/bin/ffmpeg", version="7.0"),
            ToolStatus(name="ffprobe", path="/usr/bin/ffprobe", version="7.0"),
            ToolStatus(name="deno", path="/usr/bin/deno", version="deno 2.2.9"),
            ToolStatus(name="node", path="/usr/bin/node", version="v22.1.0"),
        ),
    )

    pipeline = dependencies.pipeline_factory()

    assert dependencies.youtube_available
    assert pipeline._ports.downloader._js_runtime == "node"
    assert pipeline._ports.downloader._js_runtime_path == "/usr/bin/node"
    assert "deno 2.2.9: abaixo do mínimo 2.3" in dependencies.youtube_readiness_details


def test_youtube_runtime_is_unavailable_when_both_versions_are_too_old(
    tmp_path, monkeypatch
) -> None:
    _patch_modules(monkeypatch, "yt_dlp")
    dependencies = build_ui_dependencies(
        _settings(tmp_path),
        tool_locator=_locator(
            ToolStatus(name="ffmpeg", path="/usr/bin/ffmpeg"),
            ToolStatus(name="ffprobe", path="/usr/bin/ffprobe"),
            ToolStatus(name="deno", path="/usr/bin/deno", version="deno 2.2.9"),
            ToolStatus(name="node", path="/usr/bin/node", version="v20.0.0"),
        ),
    )

    assert not dependencies.youtube_available
    assert "Nenhum runtime EJS compatível" in dependencies.youtube_readiness_details[1]


def test_suggested_output_stays_under_the_configured_directory(
    tmp_path, monkeypatch
) -> None:
    _patch_modules(monkeypatch)
    dependencies = build_ui_dependencies(
        _settings(tmp_path),
        tool_locator=_locator(
            ToolStatus(name="ffmpeg", path="/usr/bin/ffmpeg"),
            ToolStatus(name="ffprobe", path="/usr/bin/ffprobe"),
        ),
    )

    suggestion = dependencies.output_path_factory("aula", Language.PORTUGUESE)

    assert suggestion == tmp_path / "fora" / "aula.srt"


def test_missing_runtimes_are_reported_without_crashing_application(
    tmp_path, monkeypatch
) -> None:
    _patch_modules(monkeypatch)
    dependencies = build_ui_dependencies(
        _settings(tmp_path),
        tool_locator=_locator(
            ToolStatus(name="ffmpeg", path="/usr/bin/ffmpeg"),
            ToolStatus(name="ffprobe", path="/usr/bin/ffprobe"),
        ),
    )

    assert dependencies.readiness_ok
    assert dependencies.publishing_available
    assert not dependencies.transcription_available
    assert not dependencies.alignment_available
    assert not dependencies.translate_available
    assert (
        "openai-whisper não instalado"
        in dependencies.transcription_readiness_details[0]
    )
    assert "WhisperX não instalado" in dependencies.alignment_readiness_details[0]
    assert "transformers não instalado" in dependencies.translate_readiness_details[0]
    assert isinstance(
        dependencies.pipeline_factory()._ports.transcriber, WhisperTranscriber
    )


def test_faster_whisper_backend_is_selected_explicitly(tmp_path, monkeypatch) -> None:
    _patch_modules(monkeypatch, "faster_whisper", "whisperx", "transformers")
    monkeypatch.setenv("LEGENDAR_ASR_BACKEND", "faster-whisper")
    monkeypatch.delenv("LEGENDAR_WHISPER_MODEL", raising=False)
    monkeypatch.delenv("LEGENDAR_WHISPER_DEVICE", raising=False)

    dependencies = build_ui_dependencies(
        _settings(tmp_path),
        tool_locator=_locator(
            ToolStatus(name="ffmpeg", path="/usr/bin/ffmpeg"),
            ToolStatus(name="ffprobe", path="/usr/bin/ffprobe"),
        ),
    )
    pipeline = dependencies.pipeline_factory()

    assert dependencies.transcription_available
    assert "faster-whisper" in dependencies.transcription_readiness_details[0]
    assert isinstance(pipeline._ports.transcriber, FasterWhisperTranscriber)
    assert pipeline._ports.transcriber.requested_compute_type is None


def test_faster_whisper_backend_reports_missing_dependency(
    tmp_path, monkeypatch
) -> None:
    _patch_modules(monkeypatch)
    monkeypatch.setenv("LEGENDAR_ASR_BACKEND", "faster-whisper")

    dependencies = build_ui_dependencies(
        _settings(tmp_path),
        tool_locator=_locator(
            ToolStatus(name="ffmpeg", path="/usr/bin/ffmpeg"),
            ToolStatus(name="ffprobe", path="/usr/bin/ffprobe"),
        ),
    )

    assert not dependencies.transcription_available
    assert (
        "faster-whisper não instalado"
        in dependencies.transcription_readiness_details[0]
    )
    assert isinstance(
        dependencies.pipeline_factory()._ports.transcriber, WhisperTranscriber
    )


def test_unknown_asr_backend_is_not_silently_accepted(tmp_path, monkeypatch) -> None:
    _patch_modules(monkeypatch, "whisper")
    monkeypatch.setenv("LEGENDAR_ASR_BACKEND", "unknown-backend")

    dependencies = build_ui_dependencies(
        _settings(tmp_path),
        tool_locator=_locator(
            ToolStatus(name="ffmpeg", path="/usr/bin/ffmpeg"),
            ToolStatus(name="ffprobe", path="/usr/bin/ffprobe"),
        ),
    )

    assert not dependencies.transcription_available
    assert (
        "LEGENDAR_ASR_BACKEND inválido"
        in dependencies.transcription_readiness_details[0]
    )


def test_gemini_backend_is_selected_with_api_key(tmp_path, monkeypatch) -> None:
    _patch_modules(monkeypatch)
    monkeypatch.setenv("LEGENDAR_TRANSLATION_BACKEND", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-secret")
    monkeypatch.setenv("LEGENDAR_GEMINI_MODEL", "gemini-test")
    monkeypatch.setenv("LEGENDAR_GEMINI_BATCH_SIZE", "24")

    dependencies = build_ui_dependencies(
        _settings(tmp_path),
        tool_locator=_locator(
            ToolStatus(name="ffmpeg", path="/usr/bin/ffmpeg"),
            ToolStatus(name="ffprobe", path="/usr/bin/ffprobe"),
        ),
    )
    translator = dependencies.pipeline_factory()._ports.translator

    assert dependencies.translate_available
    assert isinstance(translator, GeminiTranslator)
    assert translator.model == "gemini-test"
    assert translator.batch_size == 24
    assert "Gemini API" in dependencies.translate_readiness_details[0]
    assert "GEMINI_API_KEY configurada" in dependencies.translate_readiness_details[3]
    assert "test-secret" not in repr(dependencies.translate_readiness_details)


def test_gemini_backend_reports_missing_api_key_without_crashing(
    tmp_path, monkeypatch
) -> None:
    _patch_modules(monkeypatch)
    monkeypatch.setenv("LEGENDAR_TRANSLATION_BACKEND", "gemini")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    dependencies = build_ui_dependencies(
        _settings(tmp_path),
        tool_locator=_locator(
            ToolStatus(name="ffmpeg", path="/usr/bin/ffmpeg"),
            ToolStatus(name="ffprobe", path="/usr/bin/ffprobe"),
        ),
    )

    assert not dependencies.translate_available
    assert isinstance(
        dependencies.pipeline_factory()._ports.translator, GeminiTranslator
    )
    assert "GEMINI_API_KEY ausente" in dependencies.translate_readiness_details[3]


def test_unknown_translation_backend_is_not_silently_accepted(
    tmp_path, monkeypatch
) -> None:
    _patch_modules(monkeypatch, "transformers")
    monkeypatch.setenv("LEGENDAR_TRANSLATION_BACKEND", "unknown")

    dependencies = build_ui_dependencies(
        _settings(tmp_path),
        tool_locator=_locator(
            ToolStatus(name="ffmpeg", path="/usr/bin/ffmpeg"),
            ToolStatus(name="ffprobe", path="/usr/bin/ffprobe"),
        ),
    )

    assert not dependencies.translate_available
    assert (
        "LEGENDAR_TRANSLATION_BACKEND inválido"
        in dependencies.translate_readiness_details[0]
    )
