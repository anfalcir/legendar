"""Consistência da documentação viva, arquivo histórico e links relativos."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

from check_doc_links import check_repository, markdown_files  # noqa: E402

LIVING_DOCUMENTS = (
    "README.md",
    "docs/README.md",
    "docs/PLANO_CORRECAO_MELHORIA.md",
    "docs/FASE_5_PLANO.md",
    "docs/FASE_6_PLANO.md",
    "docs/ESTADO_ATUAL.md",
    "docs/ARQUITETURA.md",
    "docs/OPERACAO.md",
    "docs/INSTALACAO.md",
    "docs/HOMOLOGACAO.md",
    "docs/DECISOES.md",
    "docs/MATRIZ_DEPENDENCIAS.md",
)

ARCHIVED_DOCUMENTS = (
    "docs/archive/README.md",
    "docs/archive/previous-remodeling/README.md",
    "docs/archive/previous-remodeling/PLANO_REMODELAGEM.md",
    "docs/archive/previous-remodeling/FASE_0_PROTOCOLO.md",
    "docs/archive/previous-remodeling/FASE_1_PLANO.md",
    "docs/archive/previous-remodeling/FASE_2_PLANO.md",
    "docs/archive/previous-remodeling/FASE_3_PLANO.md",
    "docs/archive/previous-remodeling/FASE_4_PLANO.md",
    "docs/archive/previous-remodeling/FASE_5_PLANO.md",
    "docs/archive/previous-remodeling/FASE_6_PLANO.md",
    "docs/archive/previous-remodeling/FASE_7_PLANO.md",
    "docs/archive/previous-remodeling/FASE_8_PLANO.md",
    "docs/archive/previous-remodeling/FASE_9_PLANO.md",
    "docs/archive/previous-remodeling/FASE_10_PLANO.md",
    "docs/archive/previous-remodeling/HANDOFF_FASE_1.md",
    "docs/archive/previous-remodeling/HANDOFF_FASE_2.md",
    "docs/archive/previous-remodeling/HANDOFF_FASE_3.md",
    "docs/archive/previous-remodeling/HANDOFF_FASE_4.md",
    "docs/archive/previous-remodeling/HANDOFF_FASE_5.md",
    "docs/archive/previous-remodeling/HANDOFF_FASE_6.md",
    "docs/archive/previous-remodeling/HANDOFF_FASE_7.md",
    "docs/archive/previous-remodeling/HANDOFF_FASE_8.md",
    "docs/archive/previous-remodeling/HANDOFF_FASE_9.md",
    "docs/archive/previous-remodeling/HANDOFF_FASE_10.md",
    "docs/archive/previous-remodeling/RELATORIO_FASE_8.md",
    "docs/archive/previous-remodeling/LEGACY_BASELINE.md",
)

DOCS_ROOT_LIVING_FILES = {
    "README.md",
    "PLANO_CORRECAO_MELHORIA.md",
    "FASE_5_PLANO.md",
    "FASE_6_PLANO.md",
    "ESTADO_ATUAL.md",
    "ARQUITETURA.md",
    "OPERACAO.md",
    "INSTALACAO.md",
    "HOMOLOGACAO.md",
    "DECISOES.md",
    "MATRIZ_DEPENDENCIAS.md",
}


def test_legacy_requirements_snapshot_was_retired() -> None:
    assert not (REPOSITORY_ROOT / "requirements.txt").exists()
    assert (REPOSITORY_ROOT / "pyproject.toml").is_file()
    assert (REPOSITORY_ROOT / "uv.lock").is_file()


def test_repository_has_no_broken_relative_links() -> None:
    assert check_repository(REPOSITORY_ROOT) == []


@pytest.mark.parametrize("document", LIVING_DOCUMENTS + ARCHIVED_DOCUMENTS)
def test_required_document_exists(document: str) -> None:
    assert (REPOSITORY_ROOT / document).is_file()


def test_docs_root_contains_only_living_documents() -> None:
    docs_root = REPOSITORY_ROOT / "docs"
    found = {path.name for path in docs_root.iterdir() if path.is_file()}
    assert found == DOCS_ROOT_LIVING_FILES


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
        "[site](https://example.com/x.md) e [secao](#titulo)\n",
        encoding="utf-8",
    )

    assert check_repository(tmp_path) == []
