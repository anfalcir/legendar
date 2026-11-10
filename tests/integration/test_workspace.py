"""Testes de integração do diretório de trabalho: isolamento e limpeza segura."""

from __future__ import annotations

from pathlib import Path
from shutil import rmtree as real_rmtree

import pytest

from legendar.application.job.context import JobContext
from legendar.infrastructure.filesystem.workspace import (
    TempWorkspaceFactory,
    UnsafeWorkspaceError,
)


def test_create_gives_unique_directory_under_root(tmp_path: Path):
    factory = TempWorkspaceFactory(root=tmp_path)
    cache = tmp_path / "cache"
    first = factory.create(
        job_id="a",
        source_label="a.mp4",
        output_path=tmp_path / "a.srt",
        cache_dir=cache,
    )
    second = factory.create(
        job_id="b",
        source_label="b.mp4",
        output_path=tmp_path / "b.srt",
        cache_dir=cache,
    )

    assert first.work_dir != second.work_dir
    assert first.work_dir.parent == tmp_path
    assert first.work_dir.name.startswith("legendar-a-")
    assert first.audio_cache_path.parent == first.work_dir


def test_cleanup_removes_only_job_workspace(tmp_path: Path):
    factory = TempWorkspaceFactory(root=tmp_path / "tmp")
    cache = tmp_path / "cache"
    cache.mkdir()
    model_file = cache / "model.bin"
    model_file.write_text("pesos", encoding="utf-8")

    context = factory.create(
        job_id="c",
        source_label="c.mp4",
        output_path=tmp_path / "c.srt",
        cache_dir=cache,
    )
    (context.work_dir / "audio.wav").write_text("x", encoding="utf-8")

    factory.cleanup(context)
    factory.cleanup(context)  # limpeza repetida é idempotente

    assert not context.work_dir.exists()
    assert model_file.exists()



def test_cleanup_surfaces_filesystem_errors_for_ui_diagnostics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    factory = TempWorkspaceFactory(root=tmp_path / "tmp")
    context = factory.create(
        job_id="cleanup-error",
        source_label="aula.mp4",
        output_path=tmp_path / "aula.srt",
        cache_dir=tmp_path / "models",
    )

    def fail_cleanup(_path: Path) -> None:
        raise PermissionError("permissão negada")

    monkeypatch.setattr("legendar.infrastructure.filesystem.workspace.shutil.rmtree", fail_cleanup)

    with pytest.raises(PermissionError, match="permissão negada"):
        factory.cleanup(context)

    monkeypatch.setattr("legendar.infrastructure.filesystem.workspace.shutil.rmtree", real_rmtree)
    real_rmtree(context.work_dir)


def test_cleanup_refuses_directory_outside_root(tmp_path: Path):
    factory = TempWorkspaceFactory(root=tmp_path / "root")
    outside = tmp_path / "legendar-evil"
    outside.mkdir()
    context = JobContext(
        job_id="e",
        source_label="e.mp4",
        work_dir=outside,
        cache_dir=tmp_path / "cache",
        output_path=tmp_path / "e.srt",
    )

    with pytest.raises(UnsafeWorkspaceError):
        factory.cleanup(context)
    assert outside.exists()


def test_cleanup_refuses_unexpected_prefix(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    strange = root / "outro-nome"
    strange.mkdir()
    factory = TempWorkspaceFactory(root=root)
    context = JobContext(
        job_id="f",
        source_label="f.mp4",
        work_dir=strange,
        cache_dir=tmp_path / "cache",
        output_path=tmp_path / "f.srt",
    )

    with pytest.raises(UnsafeWorkspaceError):
        factory.cleanup(context)
    assert strange.exists()


def test_cleanup_refuses_root_itself(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    factory = TempWorkspaceFactory(root=root)
    context = JobContext(
        job_id="g",
        source_label="g.mp4",
        work_dir=root,
        cache_dir=tmp_path / "cache",
        output_path=tmp_path / "g.srt",
    )

    with pytest.raises(UnsafeWorkspaceError):
        factory.cleanup(context)
    assert root.exists()
