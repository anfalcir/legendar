from __future__ import annotations

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
