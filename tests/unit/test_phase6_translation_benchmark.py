from __future__ import annotations

from pathlib import Path

import pytest
from scripts import phase6_translation_benchmark as benchmark

from legendar.application.pipeline.translation import TranslationResult, TranslationUnit
from legendar.domain.value_objects.language import Language


def test_manifest_loads_units_and_optional_human_references(tmp_path: Path) -> None:
    manifest = tmp_path / "cues.tsv"
    manifest.write_text(
        "cue_id\tsource_text\treference_text\n"
        "1\tHello there.\tOlá.\n"
        "2\tHow are you?\tComo vai?\n",
        encoding="utf-8",
    )

    units, references = benchmark.load_manifest(manifest)

    assert units == (
        TranslationUnit(index=1, text="Hello there."),
        TranslationUnit(index=2, text="How are you?"),
    )
    assert references == ("Olá.", "Como vai?")


def test_manifest_allows_performance_only_without_references(tmp_path: Path) -> None:
    manifest = tmp_path / "cues.tsv"
    manifest.write_text(
        "cue_id\tsource_text\treference_text\n1\tHello.\t\n",
        encoding="utf-8",
    )

    units, references = benchmark.load_manifest(manifest)

    assert len(units) == 1
    assert references is None


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        ("source_text\nHello\n", "cue_id e source_text"),
        ("cue_id\tsource_text\n1\tHello\n1\tAgain\n", "duplicado"),
        ("cue_id\tsource_text\n0\tHello\n", "duplicado"),
        ("cue_id\tsource_text\n1\t \n", "vazio"),
        (
            "cue_id\tsource_text\treference_text\n1\tHello\tHi\n2\tBye\t\n",
            "todas vazias",
        ),
    ],
)
def test_manifest_rejects_invalid_input(
    tmp_path: Path, contents: str, message: str
) -> None:
    manifest = tmp_path / "invalid.tsv"
    manifest.write_text(contents, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        benchmark.load_manifest(manifest)


class FakeTranslator:
    def __init__(self, backend: str) -> None:
        self.backend = backend

    def translate(self, units, **kwargs):
        return TranslationResult(
            language=kwargs["target_language"],
            texts=tuple(f"translated {unit.index}" for unit in units),
            unit_indexes=tuple(unit.index for unit in units),
        )

    def performance_snapshot(self):
        return {
            "configuration": {"model": f"{self.backend}-model", "batch_size": 32},
            "counters": {"requests": 1},
        }


def test_benchmark_uses_identical_units_and_emits_sanitized_metrics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    created: list[str] = []

    def factory(backend: str, _models_dir: Path):
        created.append(backend)
        return FakeTranslator(backend)

    monkeypatch.setattr(benchmark, "_translator", factory)
    units = (
        TranslationUnit(index=1, text="First cue."),
        TranslationUnit(index=2, text="Second cue."),
    )
    result = benchmark.run_benchmark(
        units=units,
        references=None,
        source_language=Language.ENGLISH,
        target_language=Language.PORTUGUESE,
        backends=("nllb", "gemini"),
        models_dir=tmp_path,
        repeats=2,
    )

    assert created == ["nllb", "gemini"]
    assert [item["units"] for item in result["results"]] == [2, 2]
    assert result["comparison"]["gemini_speedup_vs_nllb"] > 0
    assert result["comparison"]["gemini_time_reduction_percent"] is not None
    assert result["comparison"]["wer_delta_vs_nllb"] is None
    assert all(
        item["wer"] is None and item["cer"] is None for item in result["results"]
    )
    assert result["privacy"] == {
        "contains_source_text": False,
        "contains_translations": False,
        "contains_human_references": False,
        "contains_api_keys": False,
    }


def test_benchmark_scores_against_human_reference() -> None:
    wer, cer = benchmark._score(
        ("Olá mundo", "Até logo"),
        ("Olá mundo", "Até logo"),
    )
    assert wer == 0.0
    assert cer == 0.0


def test_unknown_backend_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Backend desconhecido"):
        benchmark._translator("other", tmp_path)
