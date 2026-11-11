"""Consistência da documentação: links relativos e documentos obrigatórios."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

from check_doc_links import check_repository, markdown_files  # noqa: E402

REQUIRED_DOCUMENTS = (
    "README.md",
    "LICENSE",
    "docs/PLANO_REMODELAGEM.md",
    "docs/ESTADO_ATUAL.md",
    "docs/ARQUITETURA.md",
    "docs/OPERACAO.md",
    "docs/INSTALACAO.md",
    "docs/HOMOLOGACAO.md",
    "docs/DECISOES.md",
    "docs/MATRIZ_DEPENDENCIAS.md",
    "docs/FASE_0_PROTOCOLO.md",
    "docs/FASE_1_PLANO.md",
    "docs/FASE_2_PLANO.md",
    "docs/FASE_3_PLANO.md",
    "docs/FASE_4_PLANO.md",
    "docs/FASE_5_PLANO.md",
    "docs/FASE_6_PLANO.md",
    "docs/FASE_7_PLANO.md",
    "docs/FASE_8_PLANO.md",
    "docs/FASE_9_PLANO.md",
    "docs/FASE_10_PLANO.md",
    "docs/HANDOFF_FASE_1.md",
    "docs/HANDOFF_FASE_2.md",
    "docs/HANDOFF_FASE_3.md",
    "docs/HANDOFF_FASE_4.md",
    "docs/HANDOFF_FASE_5.md",
    "docs/HANDOFF_FASE_6.md",
    "docs/HANDOFF_FASE_7.md",
    "docs/HANDOFF_FASE_8.md",
    "docs/HANDOFF_FASE_9.md",
    "docs/RELATORIO_FASE_8.md",
    "docs/LEGACY_BASELINE.md",
)


def test_legacy_requirements_snapshot_was_retired() -> None:
    assert not (REPOSITORY_ROOT / "requirements.txt").exists()
    assert (REPOSITORY_ROOT / "pyproject.toml").is_file()
    assert (REPOSITORY_ROOT / "uv.lock").is_file()


def test_repository_has_no_broken_relative_links() -> None:
    problems = check_repository(REPOSITORY_ROOT)

    assert problems == []


def test_markdown_discovery_skips_ignored_directories(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guia.md").write_text("# guia\n", encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "ignorado.md").write_text("# x\n", encoding="utf-8")

    found = {path.relative_to(tmp_path).as_posix() for path in markdown_files(tmp_path)}

    assert found == {"docs/guia.md"}


def test_broken_link_is_reported(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    document = tmp_path / "docs" / "guia.md"
    document.write_text("[ok](existente.md) e [ruim](ausente.md)\n", encoding="utf-8")
    (tmp_path / "docs" / "existente.md").write_text("# ok\n", encoding="utf-8")

    problems = check_repository(tmp_path)

    assert len(problems) == 1
    assert "ausente.md" in problems[0]


def test_external_and_anchor_links_are_ignored(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "[site](https://example.com/x.md) e [secao](#titulo)\n", encoding="utf-8"
    )

    assert check_repository(tmp_path) == []


@pytest.mark.parametrize("document", REQUIRED_DOCUMENTS)
def test_required_document_exists(document: str) -> None:
    assert (REPOSITORY_ROOT / document).is_file()
