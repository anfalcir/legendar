from __future__ import annotations

from pathlib import Path

import pytest


from scripts.phase4_model_benchmark import (
    _load_manifest_rows,
    _normalize_text,
    _parse_language,
)


def test_normalizes_recognition_text_without_losing_words() -> None:
    assert _normalize_text("Olá, MUNDO!  2026") == "olá mundo 2026"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("pt-BR", "pt"),
        ("pt_br", "pt"),
        ("Português", "pt"),
        ("en-US", "en"),
        ("English", "en"),
    ],
)
def test_normalizes_supported_manifest_languages(value: str, expected: str) -> None:
    assert _parse_language(value) == expected


def test_rejects_manifest_language_outside_product_scope() -> None:
    with pytest.raises(ValueError, match="não suportado"):
        _parse_language("es")


def test_loads_local_manifest_relative_paths_and_synthetic_ids(tmp_path: Path) -> None:
    audio = tmp_path / "sermao.wav"
    audio.write_bytes(b"fixture")
    manifest = tmp_path / "samples.tsv"
    manifest.write_text(
        "language\taudio\treference\npt-BR\tsermao.wav\tUma frase de referência.\n",
        encoding="utf-8",
    )

    rows = _load_manifest_rows(manifest)

    assert rows == [
        {
            "sample_id": "local-0001",
            "language": "pt",
            "reference": "Uma frase de referência.",
            "audio_path": str(audio.resolve()),
        }
    ]


def test_manifest_rejects_missing_audio_and_empty_reference(tmp_path: Path) -> None:
    manifest = tmp_path / "samples.tsv"
    manifest.write_text(
        "language\taudio\treference\npt\tmissing.wav\tTexto\n",
        encoding="utf-8",
    )
    with pytest.raises(FileNotFoundError, match="áudio não encontrado"):
        _load_manifest_rows(manifest)

    manifest.write_text(
        "language\taudio\treference\npt\t\tTexto\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="áudio e transcrição"):
        _load_manifest_rows(manifest)


def test_manifest_requires_expected_header(tmp_path: Path) -> None:
    manifest = tmp_path / "samples.tsv"
    manifest.write_text("idioma\tarquivo\ttexto\n", encoding="utf-8")

    with pytest.raises(ValueError, match="cabeçalho"):
        _load_manifest_rows(manifest)
