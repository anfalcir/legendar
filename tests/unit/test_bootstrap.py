"""Testes da composição inicial: preflight, caminhos e pipeline pendente."""

from __future__ import annotations

from pathlib import Path

import pytest

from legendar.bootstrap.app import build_ui_dependencies
from legendar.application.pipeline.serial_pipeline import SerialPipeline
from legendar.domain.value_objects.language import Language
from legendar.infrastructure.config.settings import AppSettings
from legendar.infrastructure.media.ffmpeg import FfmpegAudioPreparer
from legendar.infrastructure.media.probe import FfprobeInspector
from legendar.infrastructure.media.tools import ToolStatus
from legendar.infrastructure.media.youtube import YtDlpDownloader


def _settings(tmp_path: Path) -> AppSettings:
    return AppSettings(cache_dir=tmp_path / "cache", output_dir=tmp_path / "fora")


def _locator(*statuses: ToolStatus):
    def locate(names: tuple[str, ...]):
        by_name = {status.name: status for status in statuses}
        return {name: by_name.get(name, ToolStatus(name=name)) for name in names}

    return locate


def test_readiness_ok_when_ffmpeg_and_ffprobe_are_present(tmp_path) -> None:
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


def test_missing_tool_is_reported_without_raising(tmp_path) -> None:
    dependencies = build_ui_dependencies(
        _settings(tmp_path),
        tool_locator=_locator(
            ToolStatus(name="ffmpeg"),
            ToolStatus(name="ffprobe", path="/usr/bin/ffprobe"),
        ),
    )

    assert not dependencies.readiness_ok
    assert "não encontrado" in dependencies.readiness_details[0]
    assert not dependencies.readiness_ok


def test_pipeline_composes_real_media_adapters_and_future_stage_placeholders(
    tmp_path,
) -> None:
    dependencies = build_ui_dependencies(
        _settings(tmp_path),
        tool_locator=_locator(
            ToolStatus(name="ffmpeg", path="/usr/bin/ffmpeg"),
            ToolStatus(name="ffprobe", path="/usr/bin/ffprobe"),
            ToolStatus(name="deno", path="/usr/bin/deno"),
        ),
    )

    pipeline = dependencies.pipeline_factory()

    assert isinstance(pipeline, SerialPipeline)
    assert isinstance(pipeline._ports.inspector, FfprobeInspector)
    assert isinstance(pipeline._ports.audio_preparer, FfmpegAudioPreparer)
    assert isinstance(pipeline._ports.downloader, YtDlpDownloader)
    assert not dependencies.translate_available


def test_suggested_output_stays_under_the_configured_directory(tmp_path) -> None:
    dependencies = build_ui_dependencies(
        _settings(tmp_path),
        tool_locator=_locator(
            ToolStatus(name="ffmpeg", path="/usr/bin/ffmpeg"),
            ToolStatus(name="ffprobe", path="/usr/bin/ffprobe"),
        ),
    )

    suggestion = dependencies.output_path_factory("aula", Language.PORTUGUESE)

    assert suggestion == tmp_path / "fora" / "aula.srt"
