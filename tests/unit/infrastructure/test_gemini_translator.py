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
    assert calls[0][1]["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "LOW"}
    assert "temperature" not in calls[0][1]["generationConfig"]


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
    assert "Não traduza, translitere nem adapte esses" in system
    assert "grafia canônica original" in system
    assert "português brasileiro (PT-BR)" in prompt


def test_grounding_is_added_only_when_enabled_on_adapter() -> None:
    plain_calls: list = []
    grounded_calls: list = []
    plain = _translator(calls=plain_calls)
    grounded = _translator(
        calls=grounded_calls, grounding=True, model="gemini-3.8-flash"
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
    assert grounded_calls[0][1]["generationConfig"]["thinkingConfig"] == {
        "thinkingLevel": "LOW"
    }
    assert grounded.performance_snapshot()["configuration"]["grounding"]


def test_environment_enables_grounding_by_default_and_allows_opt_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-secret")
    monkeypatch.delenv("LEGENDAR_GEMINI_GROUNDING", raising=False)
    assert GeminiTranslator.from_environment(tmp_path).grounding

    monkeypatch.setenv("LEGENDAR_GEMINI_GROUNDING", "false")
    assert not GeminiTranslator.from_environment(tmp_path).grounding


def test_environment_configuration_is_read_without_logging_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "private-key")
    monkeypatch.setenv("LEGENDAR_GEMINI_MODEL", "gemini-3.5-flash-lite")
    monkeypatch.setenv("LEGENDAR_GEMINI_BATCH_SIZE", "24")
    monkeypatch.setenv("LEGENDAR_GEMINI_MAX_INPUT_TOKENS", "64000")
    monkeypatch.setenv("LEGENDAR_GEMINI_MAX_OUTPUT_TOKENS", "4096")
    monkeypatch.setenv("LEGENDAR_GEMINI_GROUNDING", "true")

    translator = GeminiTranslator.from_environment(tmp_path)

    snapshot = translator.performance_snapshot()
    assert translator.model == "gemini-3.5-flash-lite"
    assert translator.batch_size == 24
    assert translator.max_input_tokens == 64000
    assert translator.max_output_tokens == 4096
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


def _request_ids(payload: dict) -> list[int]:
    prompt = payload["contents"][0]["parts"][0]["text"]
    source = json.loads(prompt.split("\n", 3)[-1])
    return [item["cue_id"] for item in source["cues_a_traduzir"]]


def test_recovers_only_the_empty_cue_from_phase_8_1_fixture() -> None:
    fixture_path = (
        Path(__file__).resolve().parents[2]
        / "fixtures"
        / "phase_8_1"
        / "gemini_responses.json"
    )
    fixtures = json.loads(fixture_path.read_text(encoding="utf-8"))
    initial = next(
        case["response"]
        for case in fixtures["cases"]
        if case["id"] == "gemini_one_empty_item"
    )
    attempts: list[list[int]] = []

    def requester(_model, payload, _api_key, _timeout):
        ids = _request_ids(payload)
        attempts.append(ids)
        if len(attempts) == 1:
            return initial
        assert ids == [71]
        return _response([{"cue_id": 71, "text": "Muito obrigado."}])

    units = (
        TranslationUnit(index=70, text="Thank you."),
        TranslationUnit(index=71, text="Thank you."),
        TranslationUnit(index=72, text="We are safe."),
    )
    translator = GeminiTranslator(api_key="test", requester=requester)
    result = translator.translate(
        units,
        source_language=Language.ENGLISH,
        target_language=Language.PORTUGUESE,
        progress=ProgressRecorder(),
    )

    assert result.texts == ("Obrigado.", "Muito obrigado.", "Estamos seguros.")
    assert attempts == [[70, 71, 72], [71]]
    counters = translator.performance_snapshot()["counters"]
    assert counters["item_retries"] == 1
    assert counters["recovered_units"] == 1
    assert counters["translated_units"] == 3


def test_recovers_missing_cue_without_repeating_valid_cues() -> None:
    attempts: list[list[int]] = []

    def requester(_model, payload, _api_key, _timeout):
        ids = _request_ids(payload)
        attempts.append(ids)
        if ids == [1, 2, 3]:
            return _response(
                [
                    {"cue_id": 1, "text": "First."},
                    {"cue_id": 3, "text": "Third."},
                ]
            )
        assert ids == [2]
        return _response([{"cue_id": 2, "text": "Second."}])

    translator = GeminiTranslator(api_key="test", requester=requester)
    result = translator.translate(
        _units("um", "dois", "três"),
        source_language=Language.PORTUGUESE,
        target_language=Language.ENGLISH,
        progress=ProgressRecorder(),
    )

    assert result.texts == ("First.", "Second.", "Third.")
    assert attempts == [[1, 2, 3], [2]]


def test_truncated_batch_is_split_and_reassembled_in_original_order() -> None:
    attempts: list[list[int]] = []

    def requester(_model, payload, _api_key, _timeout):
        ids = _request_ids(payload)
        attempts.append(ids)
        if len(ids) > 1:
            return _response(
                [{"cue_id": ids[0], "text": "partial"}],
                finish="MAX_TOKENS",
            )
        return _response([{"cue_id": ids[0], "text": f"translated-{ids[0]}"}])

    translator = GeminiTranslator(
        api_key="test",
        requester=requester,
        batch_size=3,
    )
    result = translator.translate(
        _units("um", "dois", "três"),
        source_language=Language.PORTUGUESE,
        target_language=Language.ENGLISH,
        progress=ProgressRecorder(),
    )

    assert result.texts == ("translated-1", "translated-2", "translated-3")
    assert attempts == [[1, 2, 3], [1], [2, 3], [2], [3]]
    assert translator.performance_snapshot()["counters"]["split_batches"] == 2


def test_missing_candidate_is_retried_with_a_bounded_content_retry() -> None:
    attempts = []

    def requester(_model, _payload, _api_key, _timeout):
        attempts.append(1)
        if len(attempts) == 1:
            return {"candidates": []}
        return _response([{"cue_id": 1, "text": "Good morning."}])

    translator = GeminiTranslator(api_key="test", requester=requester)
    result = translator.translate(
        _units("bom dia"),
        source_language=Language.PORTUGUESE,
        target_language=Language.ENGLISH,
        progress=ProgressRecorder(),
    )

    assert result.texts == ("Good morning.",)
    assert len(attempts) == 2
    assert translator.performance_snapshot()["counters"]["content_retries"] == 1


def test_safety_block_is_not_retried() -> None:
    attempts = []

    def requester(*_args):
        attempts.append(1)
        return _response([], finish="SAFETY")

    translator = GeminiTranslator(
        api_key="test",
        requester=requester,
        sleeper=lambda _seconds: pytest.fail("bloqueio de segurança não deve repetir"),
    )
    with pytest.raises(TranslationError, match="segurança"):
        translator.translate(
            _units("bom dia"),
            source_language=Language.PORTUGUESE,
            target_language=Language.ENGLISH,
            progress=ProgressRecorder(),
        )

    assert len(attempts) == 1


def test_cancellation_during_rate_limit_backoff_stops_retries() -> None:
    token = CancellationTokenImpl()
    attempts = []

    def requester(*_args):
        attempts.append(1)
        raise GeminiApiError(429, retry_after=5)

    def cancel_during_sleep(_seconds: float) -> None:
        token.cancel("cancelado durante backoff")

    translator = GeminiTranslator(
        api_key="test",
        requester=requester,
        sleeper=cancel_during_sleep,
    )
    with pytest.raises(JobCancelledError, match="backoff"):
        translator.translate(
            _units("bom dia"),
            source_language=Language.PORTUGUESE,
            target_language=Language.ENGLISH,
            progress=ProgressRecorder(),
            token=token,
        )

    assert len(attempts) == 1


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


@pytest.mark.parametrize(
    ("batch_size", "expected_requests"),
    [(64, 15), (96, 10), (100, 10)],
)
def test_larger_gemini_batches_reduce_requests_for_927_cues(
    batch_size: int,
    expected_requests: int,
) -> None:
    calls: list = []
    translator = _translator(calls=calls, batch_size=batch_size)
    units = tuple(
        TranslationUnit(index=index, text="A short subtitle.")
        for index in range(1, 928)
    )

    result = translator.translate(
        units,
        source_language=Language.ENGLISH,
        target_language=Language.PORTUGUESE,
        progress=ProgressRecorder(),
    )

    assert len(result.texts) == 927
    assert len(calls) == expected_requests
    assert all(len(_request_ids(call[1])) <= batch_size for call in calls)
    assert translator.performance_snapshot()["counters"]["estimated_input_tokens"] > 0


def test_output_token_reserve_splits_batches_before_the_api_call() -> None:
    calls: list = []

    def requester(_model, payload, _api_key, _timeout):
        calls.append(payload)
        ids = _request_ids(payload)
        return _response(
            [{"cue_id": cue_id, "text": f"translated-{cue_id}"} for cue_id in ids]
        )

    translator = GeminiTranslator(
        api_key="test",
        batch_size=3,
        max_output_tokens=512,
        requester=requester,
    )
    result = translator.translate(
        _units("a" * 200, "b" * 200, "c" * 200),
        source_language=Language.ENGLISH,
        target_language=Language.PORTUGUESE,
        progress=ProgressRecorder(),
    )

    assert result.texts == ("translated-1", "translated-2", "translated-3")
    assert [_request_ids(payload) for payload in calls] == [[1], [2], [3]]
    assert all(
        payload["generationConfig"]["maxOutputTokens"] == 512 for payload in calls
    )
    assert translator.performance_snapshot()["counters"]["token_budget_splits"] == 2


def test_input_byte_budget_limits_batch_size_conservatively() -> None:
    units = _units("A" * 3000, "B" * 3000, "C" * 3000, "D" * 3000)
    translator = GeminiTranslator(api_key="test", batch_size=4)
    positions = {unit.index: index for index, unit in enumerate(units)}
    single_payload = translator._prepare_payload(
        units[:1],
        all_units=units,
        positions=positions,
        translated_by_id={},
        source_language=Language.ENGLISH,
        target_language=Language.PORTUGUESE,
    )
    single_input_estimate, _ = translator._estimate_payload_budget(
        single_payload, units[:1]
    )
    translator.max_input_tokens = max(4096, single_input_estimate)

    batch = translator._select_batch(
        units,
        start=0,
        positions=positions,
        translated_by_id={},
        source_language=Language.ENGLISH,
        target_language=Language.PORTUGUESE,
    )

    assert batch == units[:1]
    assert translator.performance_snapshot()["counters"]["token_budget_splits"] == 1


def test_single_cue_over_input_budget_fails_before_network() -> None:
    calls: list = []
    translator = GeminiTranslator(
        api_key="test",
        max_input_tokens=4096,
        requester=lambda *args: calls.append(args) or {},
    )

    with pytest.raises(TranslationError, match="excede o orçamento"):
        translator.translate(
            _units("x" * 10_000),
            source_language=Language.ENGLISH,
            target_language=Language.PORTUGUESE,
            progress=ProgressRecorder(),
        )

    assert calls == []


def test_invalid_configuration_is_rejected() -> None:
    with pytest.raises(ValueError, match="Modelo Gemini"):
        GeminiTranslator(model=" ")
    with pytest.raises(ValueError, match="entre 1 e 100"):
        GeminiTranslator(batch_size=0)
    with pytest.raises(ValueError, match="entrada Gemini"):
        GeminiTranslator(max_input_tokens=4095)
    with pytest.raises(ValueError, match="saída Gemini"):
        GeminiTranslator(max_output_tokens=511)
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
    with pytest.raises(ValueError, match="não habilita Google Search grounding"):
        GeminiTranslator(api_key="test", grounding=True, model="gemini-2.5-flash")
