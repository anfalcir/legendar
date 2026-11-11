from __future__ import annotations

from pathlib import Path

import pytest
from scripts.phase5_asr_benchmark import _load_local_manifest, run_benchmark


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"backends": ()}, "backends únicos"),
        ({"backends": ("openai-whisper", "openai-whisper")}, "backends únicos"),
        ({"backends": ("unknown",)}, "Backends não permitidos"),
        ({"models": ()}, "modelos únicos"),
        ({"models": ("base", "base")}, "modelos únicos"),
        ({"models": ("unknown",)}, "Modelos não permitidos"),
        ({"samples_per_language": 0}, "samples_per_language"),
        ({"device": "mps"}, "device"),
        ({"cpu_threads": 0}, "cpu_threads"),
        ({"beam_size": 0}, "beam_size"),
    ],
)
def test_benchmark_rejects_invalid_configuration(kwargs, message) -> None:
    with pytest.raises(ValueError, match=message):
        run_benchmark(**kwargs)


def test_local_manifest_supports_performance_only_audio(tmp_path: Path) -> None:
    audio = tmp_path / "sermon.wav"
    audio.write_bytes(b"placeholder")
    manifest = tmp_path / "manifest.tsv"
    manifest.write_text(
        "language\\taudio\\treference\\npt-BR\\tsermon.wav\\t\\n",
        encoding="utf-8",
    )

    samples = _load_local_manifest(manifest)

    assert samples == [
        {
            "sample_id": "local-0001",
            "language": "pt",
            "reference": None,
            "audio_path": str(audio),
        }
    ]


def test_local_manifest_preserves_optional_human_reference(tmp_path: Path) -> None:
    audio = tmp_path / "sermon.wav"
    audio.write_bytes(b"placeholder")
    manifest = tmp_path / "manifest.tsv"
    manifest.write_text(
        "language\\taudio\\treference\\npt-BR\\tsermon.wav\\tTexto revisado.\\n",
        encoding="utf-8",
    )

    samples = _load_local_manifest(manifest)

    assert samples[0]["reference"] == "Texto revisado."


def test_local_manifest_requires_language_and_audio_columns(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.tsv"
    manifest.write_text("language\\treference\\npt-BR\\tTexto.\\n", encoding="utf-8")

    with pytest.raises(ValueError, match="colunas language e audio"):
        _load_local_manifest(manifest)
