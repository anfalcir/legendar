"""Testes do adaptador NLLB com carregadores e tradutor dublês (sem pesos reais)."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from legendar.application.job.context import CancellationTokenImpl
from legendar.application.pipeline.translation import TranslationUnit
from legendar.application.ports.protocols import Translator
from legendar.domain.errors.catalog import (
    JobCancelledError,
    ModelError,
    TranslationError,
    UnsupportedLanguageError,
)
from legendar.domain.value_objects.language import Language
from legendar.infrastructure.translation.nllb import (
    MAX_UNITS_PER_BATCH,
    MODEL_NAME,
    NLLB_CODES,
    NllbTranslator,
)


class ProgressRecorder:
    def __init__(self) -> None:
        self.reports: list[tuple[float, str]] = []

    def report(self, fraction: float, message: str = "") -> None:
        self.reports.append((fraction, message))


def _units(*texts: str) -> tuple[TranslationUnit, ...]:
    return tuple(
        TranslationUnit(index=index, text=text)
        for index, text in enumerate(texts, start=1)
    )


def _make_translator(
    tmp_path: Path,
    *,
    outputs: list[str] | None = None,
    loader_calls: list | None = None,
    batch_calls: list | None = None,
    model_error: Exception | None = None,
    translate_error: Exception | None = None,
    on_batch=None,
    device: str = "cpu",
    **kwargs,
) -> NllbTranslator:
    model_loads = loader_calls if loader_calls is not None else []
    calls = batch_calls if batch_calls is not None else []
    served = [0]
    fake_tokenizer = object()
    fake_model = object()

    def tokenizer_loader(model_name: str, cache_dir: Path):
        model_loads.append(("tokenizer", model_name, cache_dir))
        return fake_tokenizer

    def model_loader(model_name: str, resolved: str, cache_dir: Path):
        model_loads.append(("model", model_name, resolved, cache_dir))
        if model_error is not None:
            raise model_error
        return fake_model

    def batch_translator(texts, tokenizer, model, *, source_code, target_code):
        calls.append((tuple(texts), source_code, target_code))
        if on_batch is not None:
            on_batch()
        if translate_error is not None:
            raise translate_error
        if outputs is None:
            return [f"[{text}]" for text in texts]
        offset = served[0]
        served[0] += len(texts)
        return outputs[offset : offset + len(texts)]

    return NllbTranslator(
        tmp_path / "models",
        device=device,
        tokenizer_loader=tokenizer_loader,
        model_loader=model_loader,
        batch_translator=batch_translator,
        device_resolver=lambda requested: "cpu" if requested == "auto" else requested,
        version_provider=lambda: "4.57.1",
        **kwargs,
    )


def test_satisfies_the_translator_port(tmp_path: Path) -> None:
    assert isinstance(_make_translator(tmp_path), Translator)


def test_translates_units_with_explicit_language_codes(tmp_path: Path) -> None:
    calls: list = []
    translator = _make_translator(
        tmp_path, outputs=["Good morning", "See you soon"], batch_calls=calls
    )
    progress = ProgressRecorder()

    result = translator.translate(
        _units("bom dia", "até logo"),
        source_language=Language.PORTUGUESE,
        target_language=Language.ENGLISH,
        progress=progress,
    )

    assert result.language is Language.ENGLISH
    assert result.texts == ("Good morning", "See you soon")
    assert calls == [
        (
            ("bom dia", "até logo"),
            NLLB_CODES[Language.PORTUGUESE],
            NLLB_CODES[Language.ENGLISH],
        )
    ]
    assert progress.reports[-1] == (1.0, "Legenda 2/2 traduzida")


def test_model_is_loaded_once_and_reused_across_calls(tmp_path: Path) -> None:
    loads: list = []
    translator = _make_translator(tmp_path, loader_calls=loads)
    progress = ProgressRecorder()

    assert not translator.is_loaded
    assert translator.loaded_device is None
    assert translator.revision is None

    translator.translate(
        _units("bom dia"),
        source_language=Language.PORTUGUESE,
        target_language=Language.ENGLISH,
        progress=progress,
    )
    translator.translate(
        _units("até logo"),
        source_language=Language.PORTUGUESE,
        target_language=Language.ENGLISH,
        progress=progress,
    )

    assert len(loads) == 2  # tokenizador + modelo, apenas uma vez
    assert loads[0][0] == "tokenizer"
    assert loads[1][0] == "model"
    assert loads[1][2] == "cpu"
    assert translator.is_loaded
    assert translator.loaded_device == "cpu"
    assert translator.revision == "4.57.1"
    assert translator.model_name == MODEL_NAME
    assert translator.download_root == tmp_path / "models" / "nllb"
    assert translator.download_root.is_dir()


def test_concurrent_calls_share_a_single_load(tmp_path: Path) -> None:
    loads: list = []
    started = threading.Barrier(4, timeout=10)

    def tokenizer_loader(model_name: str, cache_dir: Path):
        loads.append("tokenizer")
        return object()

    def model_loader(model_name: str, device: str, cache_dir: Path):
        loads.append("model")
        return object()

    translator = NllbTranslator(
        tmp_path / "models",
        tokenizer_loader=tokenizer_loader,
        model_loader=model_loader,
        batch_translator=lambda texts, *a, **k: [f"[{text}]" for text in texts],
        device_resolver=lambda requested: "cpu",
        version_provider=lambda: "4.57.1",
    )
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            started.wait()
            translator.translate(
                _units("bom dia"),
                source_language=Language.PORTUGUESE,
                target_language=Language.ENGLISH,
                progress=ProgressRecorder(),
            )
        except BaseException as exc:  # pragma: no cover - falha inesperada
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)

    assert errors == []
    assert loads == ["tokenizer", "model"]


def test_units_are_sent_in_batches(tmp_path: Path) -> None:
    calls: list = []
    translator = _make_translator(tmp_path, batch_calls=calls, batch_size=2)
    progress = ProgressRecorder()

    translator.translate(
        _units("um", "dois", "tres", "quatro", "cinco"),
        source_language=Language.PORTUGUESE,
        target_language=Language.ENGLISH,
        progress=progress,
    )

    assert [len(call[0]) for call in calls] == [2, 2, 1]
    assert [fraction for fraction, _ in progress.reports] == [0.4, 0.8, 1.0]


def test_default_batch_size_is_exposed(tmp_path: Path) -> None:
    assert NllbTranslator(tmp_path).batch_size == MAX_UNITS_PER_BATCH


def test_cancellation_between_batches_stops_the_translation(tmp_path: Path) -> None:
    token = CancellationTokenImpl()
    calls: list = []
    translator = _make_translator(
        tmp_path, batch_calls=calls, batch_size=1, on_batch=token.cancel
    )

    with pytest.raises(JobCancelledError):
        translator.translate(
            _units("um", "dois", "tres"),
            source_language=Language.PORTUGUESE,
            target_language=Language.ENGLISH,
            progress=ProgressRecorder(),
            token=token,
        )

    assert len(calls) == 1


def test_cancellation_before_the_first_batch_skips_loading(tmp_path: Path) -> None:
    token = CancellationTokenImpl()
    token.cancel("usuário desistiu")
    loads: list = []
    translator = _make_translator(tmp_path, loader_calls=loads)

    with pytest.raises(JobCancelledError, match="usuário desistiu"):
        translator.translate(
            _units("bom dia"),
            source_language=Language.PORTUGUESE,
            target_language=Language.ENGLISH,
            progress=ProgressRecorder(),
            token=token,
        )

    assert loads == []
    assert not translator.is_loaded


def test_empty_units_are_rejected(tmp_path: Path) -> None:
    translator = _make_translator(tmp_path)

    with pytest.raises(TranslationError, match="Nenhuma unidade"):
        translator.translate(
            (),
            source_language=Language.PORTUGUESE,
            target_language=Language.ENGLISH,
            progress=ProgressRecorder(),
        )


def test_same_source_and_target_are_rejected_before_loading(tmp_path: Path) -> None:
    loads: list = []
    translator = _make_translator(tmp_path, loader_calls=loads)

    with pytest.raises(UnsupportedLanguageError, match="mesmo idioma"):
        translator.translate(
            _units("bom dia"),
            source_language=Language.PORTUGUESE,
            target_language=Language.PORTUGUESE,
            progress=ProgressRecorder(),
        )

    assert loads == []


def test_language_without_nllb_code_is_rejected(tmp_path: Path) -> None:
    translator = _make_translator(tmp_path)

    with pytest.raises(UnsupportedLanguageError, match="Idioma de origem"):
        translator.translate(
            _units("bom dia"),
            source_language="fr",  # type: ignore[arg-type]
            target_language=Language.ENGLISH,
            progress=ProgressRecorder(),
        )


def test_empty_model_output_is_rejected(tmp_path: Path) -> None:
    translator = _make_translator(tmp_path, outputs=["   ", "ok"])

    with pytest.raises(TranslationError, match="texto vazio para as legendas: 1"):
        translator.translate(
            _units("bom dia", "até logo"),
            source_language=Language.PORTUGUESE,
            target_language=Language.ENGLISH,
            progress=ProgressRecorder(),
        )


def test_output_count_mismatch_is_rejected(tmp_path: Path) -> None:
    translator = _make_translator(tmp_path, outputs=["apenas um"])

    with pytest.raises(TranslationError, match="1 textos para 2 legendas"):
        translator.translate(
            _units("bom dia", "até logo"),
            source_language=Language.PORTUGUESE,
            target_language=Language.ENGLISH,
            progress=ProgressRecorder(),
        )


def test_whitespace_from_the_model_is_normalized(tmp_path: Path) -> None:
    translator = _make_translator(tmp_path, outputs=["  Good \n morning  "])

    result = translator.translate(
        _units("bom dia"),
        source_language=Language.PORTUGUESE,
        target_language=Language.ENGLISH,
        progress=ProgressRecorder(),
    )

    assert result.texts == ("Good morning",)


def test_backend_failure_becomes_a_translation_error(tmp_path: Path) -> None:
    translator = _make_translator(
        tmp_path, translate_error=RuntimeError("CUDA out of memory")
    )

    with pytest.raises(TranslationError, match="Falha ao traduzir com NLLB"):
        translator.translate(
            _units("bom dia"),
            source_language=Language.PORTUGUESE,
            target_language=Language.ENGLISH,
            progress=ProgressRecorder(),
        )


def test_model_errors_from_the_backend_are_preserved(tmp_path: Path) -> None:
    translator = _make_translator(
        tmp_path, translate_error=ModelError("Token de idioma NLLB inválido")
    )

    with pytest.raises(ModelError, match="Token de idioma NLLB inválido"):
        translator.translate(
            _units("bom dia"),
            source_language=Language.PORTUGUESE,
            target_language=Language.ENGLISH,
            progress=ProgressRecorder(),
        )


def test_loading_failures_become_model_errors(tmp_path: Path) -> None:
    translator = _make_translator(tmp_path, model_error=OSError("disco cheio"))

    with pytest.raises(ModelError, match="Não foi possível carregar o modelo"):
        translator.translate(
            _units("bom dia"),
            source_language=Language.PORTUGUESE,
            target_language=Language.ENGLISH,
            progress=ProgressRecorder(),
        )

    assert not translator.is_loaded


def test_model_errors_from_the_device_resolver_are_preserved(tmp_path: Path) -> None:
    def resolver(_requested: str) -> str:
        raise ModelError(
            "CUDA foi solicitada para a tradução, mas não está disponível."
        )

    translator = NllbTranslator(
        tmp_path / "models",
        device="cuda",
        tokenizer_loader=lambda *_: object(),
        model_loader=lambda *_: object(),
        batch_translator=lambda texts, *a, **k: texts,
        device_resolver=resolver,
        version_provider=lambda: "4.57.1",
    )

    with pytest.raises(ModelError, match="CUDA"):
        translator.translate(
            _units("bom dia"),
            source_language=Language.PORTUGUESE,
            target_language=Language.ENGLISH,
            progress=ProgressRecorder(),
        )


def test_invalid_configuration_is_rejected_at_construction(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Dispositivo de tradução inválido"):
        NllbTranslator(tmp_path, device="mps")
    with pytest.raises(ValueError, match="Modelo de tradução inválido"):
        NllbTranslator(tmp_path, model_name="  ")
    with pytest.raises(ValueError, match="tamanho do lote"):
        NllbTranslator(tmp_path, batch_size=0)


def test_from_environment_reads_device_and_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LEGENDAR_TRANSLATE_DEVICE", "cpu")
    monkeypatch.setenv("LEGENDAR_TRANSLATE_MODEL", "facebook/nllb-200-distilled-1.3B")

    translator = NllbTranslator.from_environment(tmp_path / "models")

    assert translator.requested_device == "cpu"
    assert translator.model_name == "facebook/nllb-200-distilled-1.3B"


def test_from_environment_defaults_and_rejects_invalid_device(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LEGENDAR_TRANSLATE_DEVICE", raising=False)
    monkeypatch.delenv("LEGENDAR_TRANSLATE_MODEL", raising=False)

    translator = NllbTranslator.from_environment(tmp_path / "models")

    assert translator.requested_device == "auto"
    assert translator.model_name == MODEL_NAME

    monkeypatch.setenv("LEGENDAR_TRANSLATE_DEVICE", "tpu")
    with pytest.raises(ValueError, match="Dispositivo de tradução inválido"):
        NllbTranslator.from_environment(tmp_path / "models")


def test_performance_snapshot_tracks_model_load_and_batch_inference(
    tmp_path: Path,
) -> None:
    translator = _make_translator(tmp_path)
    translator.translate(
        _units("olá", "até logo"),
        source_language=Language.PORTUGUESE,
        target_language=Language.ENGLISH,
        progress=ProgressRecorder(),
    )

    snapshot = translator.performance_snapshot()

    assert snapshot["loaded"] is True
    assert snapshot["configuration"]["adapter"] == "nllb-transformers"
    assert snapshot["configuration"]["batch_size"] == MAX_UNITS_PER_BATCH
    assert snapshot["configuration"]["num_beams"] == 4
    assert snapshot["counters"]["model_load_attempts"] == 1
    assert snapshot["counters"]["model_load_successes"] == 1
    assert snapshot["counters"]["batch_calls"] == 1
    assert snapshot["counters"]["batch_units"] == 2
    assert snapshot["counters"]["model_load_seconds"] >= 0
    assert snapshot["counters"]["batch_inference_seconds"] >= 0
