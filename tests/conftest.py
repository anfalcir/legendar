"""Fixtures compartilhadas dos testes de domínio e aplicação."""

from __future__ import annotations

from pathlib import Path

import pytest

from legendar.application.job.context import JobContext
from legendar.domain.entities.media import MediaKind, MediaSource
from legendar.domain.value_objects.language import Language


@pytest.fixture()
def job_context(tmp_path: Path) -> JobContext:
    work_dir = tmp_path / "work"
    cache_dir = tmp_path / "cache"
    work_dir.mkdir()
    cache_dir.mkdir()
    return JobContext(
        job_id="job-1",
        source_label="aula.mp4",
        work_dir=work_dir,
        cache_dir=cache_dir,
        output_path=tmp_path / "aula.srt",
    )


@pytest.fixture()
def local_source() -> MediaSource:
    return MediaSource(kind=MediaKind.LOCAL_FILE, location="/tmp/aula.mp4")


@pytest.fixture()
def pt_language() -> Language:
    return Language.PORTUGUESE
