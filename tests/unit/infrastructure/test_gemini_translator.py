"""Testes do adaptador Gemini sem chamadas de rede ou credenciais reais."""

from __future__ import annotations

import json
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
from legendar.infrastructure.translation.gemini import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_MODEL,
    GeminiApiError,
    GeminiTranslator,
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


def _response(items: list[dict], *, finish: str = "STOP") -> dict:
    return {
        "candidates": [
            {
                "finishReason": finish,
                "content": {
                    "parts": [
                        {
                            "text": json.dumps(
                                {"translations": items}, ensure_ascii=False
                            )
                        }
                    ]
                },
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 120,
            "candidatesTokenCount": 80,
        },
    }


def _translator(
    *,
    items: list[dict] | None = None,
    calls: list | None = None,
    on_request=None,
    **kwargs,
) -> GeminiTranslator:
    requests = calls if calls is not None else []

    def requester(model, payload, api_key, timeout):
        requests.append((model, payload, api_key, timeout))
        if on_request is not None:
            on_request()
        if items is None:
            source = json.loads(
                payload["contents"][0]["parts"][0]["text"].split("\n", 3)[-1]
            )
            outputs = [
                {"cue_id": item["cue_id"], "text": f"[{item['text']}]"}
                for item in source["cues_a_traduzir"]
            ]
            return _response(outputs)
        return _response(items)

    return GeminiTranslator(
        api_key="test-secret",
        requester=requester,
        sleeper=lambda _seconds: None,
        **kwargs,
    )


def test_satisfies_the_translator_port() -> None:
    assert isinstance(_translator(), Translator)


def test_default_configuration_is_explicit_and_batched() -> None:
    translator = GeminiTranslator(api_key="x")
    assert translator.model == DEFAULT_MODEL
    assert translator.batch_size == DEFAULT_BATCH_SIZE
    assert translator.is_configured


def test_translates_portuguese_to_english_and_preserves_cue_order() -> None:
    translator = _translator(
        items=[
            {"cue_id": 1, "text": "Good morning"},
            {"cue_id": 2, "text": "See you soon"},
        ]
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
    assert progress.reports[-1] == (1.0, "Legenda 2/2 traduzida")


def test_contextual_batches_keep_ids_and_use_prior_translations() -> None:
    calls: list = []
    translator = _translator(calls=calls, batch_size=2)
    units = tuple(
        TranslationUnit(index=index, text=text)
        for index, text in enumerate(
            ("O capitão chegou.", "Ele abriu o portão.", "A cidade dormia."),
            start=1,
        )
    )

    result = translator.translate(
        units,
        source_language=Language.PORTUGUESE,
        target_language=Language.ENGLISH,
        progress=ProgressRecorder(),
    )

    assert result.texts == (
        "[O capitão chegou.]",
        "[Ele abriu o portão.]",
        "[A cidade dormia.]",
    )
    assert len(calls) == 2
    second_prompt = calls[1][1]["contents"][0]["parts"][0]["text"]
    assert "contexto_anterior_traduzido" in second_prompt
    assert "O capitão chegou." in second_prompt
    assert "cues_anteriores" in second_prompt
    assert calls[0][1]["generationConfig"]["responseMimeType"] == "application/json"


def test_pt_br_instruction_and_entity_preservation_are_sent() -> None:
    calls: list = []
    translator = _translator(calls=calls)
    translator.translate(
        _units("The elves reached Minas Tirith."),
        source_language=Language.ENGLISH,
        target_language=Language.PORTUGUESE,
        progress=ProgressRecorder(),
    )

    system = calls[0][1]["systemInstruction"]["parts"][0]["text"]
    prompt = calls[0][1]["contents"][0]["parts"][0]["text"]
    assert "PT-BR" in system
    assert "Preserve nomes próprios" in system
    assert "português brasileiro (PT-BR)" in prompt


def test_grounding_is_opt_in() -> None:
    plain_calls: list = []
    grounded_calls: list = []
    plain = _translator(calls=plain_calls)
    grounded = _translator(
        calls=grounded_calls, grounding=True, model="gemini-3.5-flash-lite"
    )
    unit = _units("The city is old.")

    plain.translate(
        unit,
        source_language=Language.ENGLISH,
        target_language=Language.PORTUGUESE,
        progress=ProgressRecorder(),
    )
    grounded.translate(
        unit,
        source_language=Language.ENGLISH,
        target_language=Language.PORTUGUESE,
        progress=ProgressRecorder(),
    )

    assert "tools" not in plain_calls[0][1]
    assert grounded_calls[0][1]["tools"] == [{"googleSearch": {}}]
    assert grounded.performance_snapshot()["configuration"]["grounding"]


def test_environment_configuration_is_read_without_logging_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "private-key")
    monkeypatch.setenv("LEGENDAR_GEMINI_MODEL", "gemini-3.5-flash-lite")
    monkeypatch.setenv("LEGENDAR_GEMINI_BATCH_SIZE", "24")
    monkeypatch.setenv("LEGENDAR_GEMINI_GROUNDING", "true")

    translator = GeminiTranslator.from_environment(tmp_path)

    snapshot = translator.performance_snapshot()
    assert translator.model == "gemini-3.5-flash-lite"
    assert translator.batch_size == 24
    assert translator.grounding
    assert snapshot["configuration"]["api_key_configured"]
    assert "private-key" not in repr(snapshot)


def test_missing_api_key_fails_before_any_request() -> None:
    calls: list = []
    translator = GeminiTranslator(requester=lambda *args: calls.append(args) or {})
    with pytest.raises(ModelError, match="GEMINI_API_KEY"):
        translator.translate(
            _units("bom dia"),
            source_language=Language.PORTUGUESE,
            target_language=Language.ENGLISH,
            progress=ProgressRecorder(),
        )
    assert calls == []


def test_empty_units_are_rejected() -> None:
    with pytest.raises(TranslationError, match="Nenhuma unidade"):
        _translator().translate(
            (),
            source_language=Language.PORTUGUESE,
            target_language=Language.ENGLISH,
            progress=ProgressRecorder(),
        )


def test_same_language_is_rejected_before_request() -> None:
    calls: list = []
    with pytest.raises(UnsupportedLanguageError, match="mesmo idioma"):
        _translator(calls=calls).translate(
            _units("bom dia"),
            source_language=Language.PORTUGUESE,
            target_language=Language.PORTUGUESE,
            progress=ProgressRecorder(),
        )
    assert calls == []


def test_unsupported_language_is_rejected() -> None:
    with pytest.raises(UnsupportedLanguageError):
        _translator().translate(
            _units("bonjour"),
            source_language="fr",  # type: ignore[arg-type]
            target_language=Language.PORTUGUESE,
            progress=ProgressRecorder(),
        )


def test_duplicate_missing_or_reordered_cue_ids_are_rejected() -> None:
    for items in (
        [{"cue_id": 1, "text": "one"}, {"cue_id": 1, "text": "duplicate"}],
        [{"cue_id": 1, "text": "one"}],
        [{"cue_id": 2, "text": "two"}, {"cue_id": 1, "text": "one"}],
    ):
        with pytest.raises(TranslationError, match="quantidade|IDs"):
            _translator(items=items).translate(
                _units("um", "dois"),
                source_language=Language.PORTUGUESE,
                target_language=Language.ENGLISH,
                progress=ProgressRecorder(),
            )


def test_empty_translation_is_rejected() -> None:
    with pytest.raises(TranslationError, match="texto vazio"):
        _translator(items=[{"cue_id": 1, "text": "  "}]).translate(
            _units("bom dia"),
            source_language=Language.PORTUGUESE,
            target_language=Language.ENGLISH,
            progress=ProgressRecorder(),
        )


def test_truncated_or_blocked_generation_is_rejected() -> None:
    translator = GeminiTranslator(
        api_key="test",
        requester=lambda *_args: _response(
            [{"cue_id": 1, "text": "partial"}], finish="MAX_TOKENS"
        ),
    )
    with pytest.raises(TranslationError, match="interrompeu"):
        translator.translate(
            _units("bom dia"),
            source_language=Language.PORTUGUESE,
            target_language=Language.ENGLISH,
            progress=ProgressRecorder(),
        )


def test_invalid_json_is_rejected() -> None:
    translator = _translator()
    translator._requester = lambda *args: {
        "candidates": [
            {
                "finishReason": "STOP",
                "content": {"parts": [{"text": "not json"}]},
            }
        ]
    }
    with pytest.raises(TranslationError, match="JSON estruturado"):
        translator.translate(
            _units("bom dia"),
            source_language=Language.PORTUGUESE,
            target_language=Language.ENGLISH,
            progress=ProgressRecorder(),
        )


def test_retry_on_rate_limit_then_success() -> None:
    attempts = []

    def requester(*_args):
        attempts.append(1)
        if len(attempts) == 1:
            raise GeminiApiError(429, retry_after=2)
        return _response([{"cue_id": 1, "text": "Good morning"}])

    delays: list[float] = []
    translator = GeminiTranslator(
        api_key="test",
        requester=requester,
        sleeper=delays.append,
    )
    result = translator.translate(
        _units("bom dia"),
        source_language=Language.PORTUGUESE,
        target_language=Language.ENGLISH,
        progress=ProgressRecorder(),
    )

    assert result.texts == ("Good morning",)
    assert len(attempts) == 2
    assert delays == [2]
    assert translator.performance_snapshot()["counters"]["retries"] == 1


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_non_retryable_http_errors_fail_without_exposing_secret(status: int) -> None:
    translator = GeminiTranslator(
        api_key="never-log-this",
        requester=lambda *_args: (_ for _ in ()).throw(GeminiApiError(status)),
        sleeper=lambda _seconds: pytest.fail("não deveria repetir"),
    )
    with pytest.raises(TranslationError, match=f"HTTP {status}") as error:
        translator.translate(
            _units("bom dia"),
            source_language=Language.PORTUGUESE,
            target_language=Language.ENGLISH,
            progress=ProgressRecorder(),
        )
    assert "never-log-this" not in str(error.value)


def test_server_errors_retry_up_to_configured_limit() -> None:
    attempts = []

    def requester(*_args):
        attempts.append(1)
        raise GeminiApiError(503)

    translator = GeminiTranslator(
        api_key="test",
        max_retries=2,
        requester=requester,
        sleeper=lambda _seconds: None,
    )
    with pytest.raises(TranslationError, match="HTTP 503"):
        translator.translate(
            _units("bom dia"),
            source_language=Language.PORTUGUESE,
            target_language=Language.ENGLISH,
            progress=ProgressRecorder(),
        )
    assert len(attempts) == 3


def test_cancellation_between_batches_stops_requests() -> None:
    token = CancellationTokenImpl()
    calls: list = []

    def cancel_after_request():
        token.cancel("cancelado")

    translator = _translator(calls=calls, batch_size=1, on_request=cancel_after_request)
    with pytest.raises(JobCancelledError):
        translator.translate(
            _units("um", "dois", "três"),
            source_language=Language.PORTUGUESE,
            target_language=Language.ENGLISH,
            progress=ProgressRecorder(),
            token=token,
        )
    assert len(calls) == 1


def test_metrics_are_sanitized_and_include_token_counts() -> None:
    translator = _translator()
    translator.translate(
        _units("bom dia"),
        source_language=Language.PORTUGUESE,
        target_language=Language.ENGLISH,
        progress=ProgressRecorder(),
    )

    snapshot = translator.performance_snapshot()
    assert snapshot["counters"]["requests"] == 1
    assert snapshot["counters"]["input_tokens"] == 120
    assert snapshot["counters"]["output_tokens"] == 80
    assert "bom dia" not in repr(snapshot)
    assert "test-secret" not in repr(snapshot)


def test_invalid_configuration_is_rejected() -> None:
    with pytest.raises(ValueError, match="Modelo Gemini"):
        GeminiTranslator(model=" ")
    with pytest.raises(ValueError, match="entre 1 e 100"):
        GeminiTranslator(batch_size=0)
    with pytest.raises(ValueError, match="timeout"):
        GeminiTranslator(timeout_seconds=0)
    with pytest.raises(ValueError, match="retries"):
        GeminiTranslator(max_retries=9)


def test_environment_numeric_configuration_is_validated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LEGENDAR_GEMINI_BATCH_SIZE", "not-an-int")
    with pytest.raises(ValueError, match="numérica Gemini"):
        GeminiTranslator.from_environment(tmp_path)



def test_grounding_rejects_models_without_search_support() -> None:
    with pytest.raises(ValueError, match="grounding não está disponível"):
        GeminiTranslator(api_key="test", grounding=True, model="gemini-3.8-flash")
