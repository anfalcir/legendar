from __future__ import annotations

from pathlib import Path

import pytest

from scripts.phase5_asr_benchmark import run_benchmark


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


def test_benchmark_default_configuration_is_paired_and_uses_base(tmp_path: Path) -> None:
    # Validação de parâmetros ocorre antes de carregar modelos ou buscar o dataset.
    with pytest.raises(RuntimeError, match="Benchmark exige"):
        run_benchmark(
            backends=("openai-whisper", "faster-whisper"),
            models=("base",),
            samples_per_language=1,
            cache_dir=tmp_path,
            device="cpu",
        )
