from __future__ import annotations

import importlib
import json
from urllib.error import HTTPError, URLError

import pytest

from legendar.application.pipeline.translation import (
    TranslationContext,
    TranslationUnit,
)
from legendar.domain.errors.catalog import TranslationError, UnsupportedLanguageError
from legendar.domain.value_objects.language import Language
from legendar.infrastructure.translation.translategemma import TranslateGemmaTranslator


def _module():
    return importlib.import_module("legendar.infrastructure.translation.translategemma")


class FakeProgress:
    def __init__(self) -> None:
        self.updates: list[tuple[float, str]] = []

    def report(self, fraction: float, message: str = "") -> None:
        self.updates.append((fraction, message))


class FakeRuntime:
    def __init__(self, url: str = "http://127.0.0.1:43210") -> None:
        self.url = url
        self.calls = []
        self.context_size = 2048
        self.threads = 4

    @property
    def runtime_download_authorized(self) -> bool:
        return True

    def ensure_runtime(self, *, consent, token=None, progress=None) -> None:
        self.calls.append(("runtime", consent, progress))

    def ensure_model(self, *, token=None, progress=None) -> None:
        self.calls.append(("model", token, progress))

    def ensure_running(self, *, token=None, progress=None) -> str:
        self.calls.append(("server", token, progress))
        return self.url


def _units() -> tuple[TranslationUnit, ...]:
    return (
        TranslationUnit(index=4, text="I will be back."),
        TranslationUnit(index=5, text="We are safe."),
    )


def _content(payload: dict[str, object]) -> str:
    messages = payload["messages"]
    assert isinstance(messages, list)
    message = messages[0]
    assert isinstance(message, dict)
    value = message["content"]
    assert isinstance(value, str)
    return value


def _source_document(payload: dict[str, object]) -> dict[str, object]:
    content = _content(payload)
    input_json = content.rsplit("\n", 1)[-1]
    decoded = json.loads(input_json)
    assert isinstance(decoded, dict)
    return decoded


def _response_for_batch(
    payload: dict[str, object],
    target_texts: tuple[str, ...],
) -> dict[str, object]:
    cues = _source_document(payload)["cues"]
    assert isinstance(cues, dict)
    keys = tuple(cues)
    assert len(keys) == len(target_texts)
    return {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        dict(zip(keys, target_texts, strict=True)),
                        ensure_ascii=False,
                    )
                },
                "finish_reason": "stop",
            }
        ],
        "timings": {"prompt_n": 50, "predicted_n": 20},
    }


def _counter(_url: str, _payload: dict[str, object], _timeout: float) -> int:
    return 64


def _translator(runtime=None, requester=None, token_counter=_counter):
    return TranslateGemmaTranslator(
        runtime or FakeRuntime(),
        requester=requester
        or (
            lambda _url, _payload, _timeout: {
                "choices": [
                    {
                        "message": {"content": '{"1": "Eu voltei."}'},
                        "finish_reason": "stop",
                    }
                ]
            }
        ),
        token_counter=token_counter,
    )


def test_translate_uses_llama_cpp_language_kwargs_and_compact_gbnf_mapping() -> None:
    runtime = FakeRuntime()
    requests = []
    token_payloads = []
    progress = FakeProgress()

    def requester(base_url, payload, timeout):
        requests.append((base_url, payload, timeout))
        return _response_for_batch(
            payload,
            ("Eu voltarei.", "Estamos seguros."),
        )

    def counter(base_url, payload, timeout):
        token_payloads.append((base_url, payload, timeout))
        return 48

    translator = _translator(
        runtime,
        requester=requester,
        token_counter=counter,
    )
    result = translator.translate(
        _units(),
        source_language=Language.ENGLISH,
        target_language=Language.PORTUGUESE,
        progress=progress,
    )

    assert result.language is Language.PORTUGUESE
    assert result.unit_indexes == (4, 5)
    assert result.texts == ("Eu voltarei.", "Estamos seguros.")
    assert [call[0] for call in runtime.calls] == ["runtime", "model", "server"]
    assert runtime.calls[0][2]._start == 0.0
    assert runtime.calls[0][2]._span == pytest.approx(0.15)
    assert runtime.calls[1][2]._start == pytest.approx(0.15)
    assert runtime.calls[1][2]._span == pytest.approx(0.60)
    assert len(requests) == len(token_payloads) == 1
    assert requests[0][0] == runtime.url

    payload = requests[0][1]
    assert payload["chat_template_kwargs"] == {
        "source_lang_code": "en",
        "target_lang_code": "pt-BR",
    }
    assert "natural Brazilian Portuguese" in _content(payload)
    assert "races, clans, species" in _content(payload)
    assert "Preserve negation, intent, numbers" in _content(payload)
    assert _source_document(payload)["cues"] == {
        "1": "I will be back.",
        "2": "We are safe.",
    }
    grammar = payload["grammar"]
    assert 'root ::= "{" ws entrya "," ws entryb "}" ws' in grammar
    assert 'entrya ::= "\\"1\\"" ws ":" ws string' in grammar
    assert 'entryb ::= "\\"2\\"" ws ":" ws string' in grammar
    assert 'string ::= "\\"" char+ "\\""' in grammar
    assert payload["temperature"] == 0.0
    assert payload["stream"] is False
    assert 128 <= payload["max_tokens"] <= 1024

    fractions = [fraction for fraction, _message in progress.updates]
    assert fractions == sorted(fractions)
    assert progress.updates[-1][0] == 1.0
    assert "1 lotes aceitos" in progress.updates[-1][1]


def test_batch_includes_boundary_context_as_non_output_input() -> None:
    payloads = []

    def requester(_url, payload, _timeout):
        payloads.append(payload)
        return _response_for_batch(payload, ("Primeira.", "Segunda."))

    units = (
        TranslationUnit(
            index=7,
            text="The door is open.",
            context=TranslationContext(before=("We heard a noise.",)),
        ),
        TranslationUnit(
            index=8,
            text="Come in.",
            context=TranslationContext(after=("Do not be afraid.",)),
        ),
    )
    result = _translator(requester=requester).translate(
        units,
        source_language=Language.ENGLISH,
        target_language=Language.PORTUGUESE,
        progress=FakeProgress(),
    )

    source = _source_document(payloads[0])
    assert source["context_before"] == ["We heard a noise."]
    assert source["context_after"] == ["Do not be afraid."]
    assert source["cues"] == {"1": "The door is open.", "2": "Come in."}
    assert result.unit_indexes == (7, 8)
    assert result.texts == ("Primeira.", "Segunda.")


def test_reverse_language_direction_uses_chat_template_kwargs() -> None:
    payloads = []

    def requester(_url, payload, _timeout):
        payloads.append(payload)
        return _response_for_batch(payload, ("I am ready.",))

    result = _translator(requester=requester).translate(
        (TranslationUnit(index=1, text="Estou pronto."),),
        source_language=Language.PORTUGUESE,
        target_language=Language.ENGLISH,
        progress=FakeProgress(),
    )

    assert result.texts == ("I am ready.",)
    assert payloads[0]["chat_template_kwargs"] == {
        "source_lang_code": "pt-BR",
        "target_lang_code": "en",
    }


def test_translate_rejects_same_language_and_empty_units() -> None:
    translator = _translator()
    with pytest.raises(UnsupportedLanguageError):
        translator.translate(
            (TranslationUnit(index=1, text="Hello"),),
            source_language=Language.ENGLISH,
            target_language=Language.ENGLISH,
            progress=FakeProgress(),
        )

    with pytest.raises(TranslationError, match="Nenhuma unidade"):
        translator.translate(
            (),
            source_language=Language.ENGLISH,
            target_language=Language.PORTUGUESE,
            progress=FakeProgress(),
        )


def test_translate_rejects_duplicate_unit_indexes_before_runtime() -> None:
    runtime = FakeRuntime()
    translator = _translator(runtime)
    units = (
        TranslationUnit(index=1, text="First."),
        TranslationUnit(index=1, text="Second."),
    )
    with pytest.raises(TranslationError, match="IDs de unidade duplicados"):
        translator.translate(
            units,
            source_language=Language.ENGLISH,
            target_language=Language.PORTUGUESE,
            progress=FakeProgress(),
        )
    assert runtime.calls == []


def test_translation_unit_rejects_blank_source_before_runtime() -> None:
    runtime = FakeRuntime()
    with pytest.raises(TranslationError, match="sem texto"):
        TranslationUnit(index=1, text="   ")
    assert runtime.calls == []


def test_invalid_json_batch_is_split_and_recovered_with_same_engine() -> None:
    requests = []

    def requester(_url, payload, _timeout):
        requests.append(payload)
        if len(requests) == 1:
            return {"choices": []}
        source = _source_document(payload)["cues"]
        only_text = next(iter(source.values()))
        translated = (
            "Eu voltarei." if only_text == "I will be back." else "Estamos seguros."
        )
        return _response_for_batch(payload, (translated,))

    result = _translator(requester=requester).translate(
        _units(),
        source_language=Language.ENGLISH,
        target_language=Language.PORTUGUESE,
        progress=FakeProgress(),
    )

    assert result.unit_indexes == (4, 5)
    assert result.texts == ("Eu voltarei.", "Estamos seguros.")
    assert len(requests) == 3
    assert all(payload["model"] == "translategemma-4b" for payload in requests)
    assert all("nllb" not in str(payload).lower() for payload in requests)


def test_context_budget_splits_before_expensive_generation() -> None:
    requests = []
    counted = []

    def requester(_url, payload, _timeout):
        requests.append(payload)
        source = _source_document(payload)["cues"]
        translated = tuple(
            "Eu voltarei." if value == "I will be back." else "Estamos seguros."
            for value in source.values()
        )
        return _response_for_batch(payload, translated)

    def counter(_url, payload, _timeout):
        counted.append(payload)
        return 1900 if len(_source_document(payload)["cues"]) > 1 else 64

    result = _translator(
        requester=requester,
        token_counter=counter,
    ).translate(
        _units(),
        source_language=Language.ENGLISH,
        target_language=Language.PORTUGUESE,
        progress=FakeProgress(),
    )

    assert result.texts == ("Eu voltarei.", "Estamos seguros.")
    assert len(counted) == 3
    assert len(requests) == 2
    assert all(len(_source_document(payload)["cues"]) == 1 for payload in requests)


def test_output_budget_is_bounded_by_real_remaining_context() -> None:
    captured = []

    def requester(_url, payload, _timeout):
        captured.append(payload)
        return _response_for_batch(payload, ("Tradução.",))

    def counter(_url, _payload, _timeout):
        return 1800

    result = _translator(
        requester=requester,
        token_counter=counter,
    ).translate(
        (TranslationUnit(index=1, text="A short cue."),),
        source_language=Language.ENGLISH,
        target_language=Language.PORTUGUESE,
        progress=FakeProgress(),
    )
    assert result.texts == ("Tradução.",)
    assert captured[0]["max_tokens"] + 1800 + 64 <= 2048


def test_output_estimate_over_cap_splits_batch_before_generation() -> None:
    generated = []

    def requester(_url, payload, _timeout):
        generated.append(payload)
        keys = tuple(_source_document(payload)["cues"])
        return _response_for_batch(
            payload,
            tuple(f"Tradução {key}." for key in keys),
        )

    units = (
        TranslationUnit(index=1, text="A" * 1400),
        TranslationUnit(index=2, text="B" * 1300),
    )
    result = _translator(
        requester=requester,
        token_counter=lambda *_args: 64,
    ).translate(
        units,
        source_language=Language.ENGLISH,
        target_language=Language.PORTUGUESE,
        progress=FakeProgress(),
    )

    assert result.unit_indexes == (1, 2)
    assert len(result.texts) == 2
    assert len(generated) == 2
    assert all(len(_source_document(item)["cues"]) == 1 for item in generated)
    assert all(item["max_tokens"] <= 1024 for item in generated)


def test_single_unit_above_output_cap_fails_without_generation() -> None:
    generated = []
    translator = _translator(
        requester=lambda *_args: generated.append(True) or {},
        token_counter=lambda *_args: 64,
    )
    with pytest.raises(TranslationError, match="capacidade de saída/contexto"):
        translator.translate(
            (TranslationUnit(index=11, text="X" * 2500),),
            source_language=Language.ENGLISH,
            target_language=Language.PORTUGUESE,
            progress=FakeProgress(),
        )
    assert generated == []


def test_single_unit_empty_response_is_an_explicit_error() -> None:
    translator = _translator(
        requester=lambda *_args: {
            "choices": [{"message": {"content": "  "}, "finish_reason": "stop"}]
        }
    )
    with pytest.raises(TranslationError, match="empty_response"):
        translator.translate(
            (TranslationUnit(index=9, text="Hello"),),
            source_language=Language.ENGLISH,
            target_language=Language.PORTUGUESE,
            progress=FakeProgress(),
        )


def test_response_recovery_is_bounded_per_branch_not_per_job() -> None:
    requests = []

    def requester(_url, payload, _timeout):
        requests.append(payload)
        cues = _source_document(payload)["cues"]
        if len(cues) == 8:
            return {"choices": []}
        translations = tuple(f"Tradução {key}." for key in cues)
        return _response_for_batch(payload, translations)

    units = tuple(
        TranslationUnit(index=index, text=f"Source sentence {index}.")
        for index in range(1, 9)
    )
    result = _translator(requester=requester).translate(
        units,
        source_language=Language.ENGLISH,
        target_language=Language.PORTUGUESE,
        progress=FakeProgress(),
    )
    assert len(result.texts) == 8
    assert len(requests) == 3


def test_recovery_stops_after_configured_depth_without_partial_result() -> None:
    requests = []

    def requester(_url, payload, _timeout):
        requests.append(payload)
        return {"choices": []}

    units = tuple(
        TranslationUnit(index=index, text=f"Source sentence {index}.")
        for index in range(1, 9)
    )
    with pytest.raises(TranslationError, match="sem publicar resultado parcial"):
        _translator(requester=requester).translate(
            units,
            source_language=Language.ENGLISH,
            target_language=Language.PORTUGUESE,
            progress=FakeProgress(),
        )
    assert len(requests) == 4


def test_cancellation_is_checked_between_batches(monkeypatch) -> None:
    class CancelAfterFirst:
        def __init__(self) -> None:
            self.calls = 0

        def raise_if_cancelled(self) -> None:
            if self.calls >= 1:
                raise RuntimeError("cancelled")

    monkeypatch.setattr(
        "legendar.infrastructure.translation.translategemma._MAX_BATCH_UNITS",
        1,
    )
    token = CancelAfterFirst()
    requests = []

    def requester(_url, payload, _timeout):
        requests.append(payload)
        token.calls += 1
        return _response_for_batch(payload, ("Volto.",))

    translator = _translator(requester=requester)
    with pytest.raises(RuntimeError, match="cancelled"):
        translator.translate(
            _units(),
            source_language=Language.ENGLISH,
            target_language=Language.PORTUGUESE,
            progress=FakeProgress(),
            token=token,
        )
    assert len(requests) == 1


def test_performance_snapshot_exposes_only_sanitized_metrics() -> None:
    translator = _translator(
        requester=lambda _url, payload, _timeout: _response_for_batch(
            payload, ("Eu voltarei.", "Estamos seguros.")
        )
    )
    translator.translate(
        _units(),
        source_language=Language.ENGLISH,
        target_language=Language.PORTUGUESE,
        progress=FakeProgress(),
    )
    snapshot = translator.performance_snapshot()
    assert snapshot["configuration"]["structured_output"] == "gbnf_json"
    assert snapshot["counters"]["generation_calls"] == 1
    assert snapshot["counters"]["accepted_batches"] == 1
    assert snapshot["counters"]["translated_units"] == 2
    assert "I will be back." not in str(snapshot)
    assert "Eu voltarei." not in str(snapshot)


class _FakeHttpResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return self.body


def test_post_json_decodes_object_response(monkeypatch) -> None:
    monkeypatch.setattr(
        _module(),
        "urlopen",
        lambda *_args, **_kwargs: _FakeHttpResponse(b'{"ok": true}'),
    )
    assert _module()._post_json(
        "http://127.0.0.1:8080",
        "/test",
        {"value": 1},
        1.0,
    ) == {"ok": True}


@pytest.mark.parametrize("body", [b"not-json", b"[]"])
def test_post_json_rejects_invalid_json_shapes(monkeypatch, body) -> None:
    monkeypatch.setattr(
        _module(),
        "urlopen",
        lambda *_args, **_kwargs: _FakeHttpResponse(body),
    )
    with pytest.raises(TranslationError):
        _module()._post_json(
            "http://127.0.0.1:8080",
            "/test",
            {},
            1.0,
        )


def test_post_json_normalizes_http_and_network_errors(monkeypatch) -> None:
    def http_failure(*_args, **_kwargs):
        raise HTTPError(
            "http://127.0.0.1:8080/test",
            503,
            "unavailable",
            None,
            None,
        )

    monkeypatch.setattr(_module(), "urlopen", http_failure)
    with pytest.raises(TranslationError, match="HTTP 503"):
        _module()._post_json(
            "http://127.0.0.1:8080",
            "/test",
            {},
            1.0,
        )

    def network_failure(*_args, **_kwargs):
        raise URLError("connection refused")

    monkeypatch.setattr(_module(), "urlopen", network_failure)
    with pytest.raises(TranslationError, match="URLError"):
        _module()._post_json(
            "http://127.0.0.1:8080",
            "/test",
            {},
            1.0,
        )


def test_count_prompt_tokens_rejects_invalid_count(monkeypatch) -> None:
    monkeypatch.setattr(
        _module(),
        "_post_json",
        lambda *_args, **_kwargs: {"input_tokens": True},
    )
    with pytest.raises(TranslationError, match="contagem válida"):
        _module()._count_prompt_tokens(
            "http://127.0.0.1:8080",
            {},
            1.0,
        )


def test_count_prompt_tokens_returns_integer_count(monkeypatch) -> None:
    monkeypatch.setattr(
        _module(),
        "_post_json",
        lambda *_args, **_kwargs: {"input_tokens": 123},
    )
    assert _module()._count_prompt_tokens(
        "http://127.0.0.1:8080",
        {},
        60.0,
    ) == 123


def test_chat_completion_uses_expected_endpoint(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        _module(),
        "_post_json",
        lambda *args: calls.append(args) or {"choices": []},
    )
    payload = {"model": "translategemma-4b"}
    assert _module()._chat_completion(
        "http://127.0.0.1:8080/",
        payload,
        10.0,
    ) == {"choices": []}
    assert calls[0][1] == "/v1/chat/completions"
    assert calls[0][2] is payload


def test_progress_slice_maps_and_clamps_fraction() -> None:
    sink = FakeProgress()
    progress = _module()._ProgressSlice(sink, 0.2, 0.6)
    progress.report(0.5, "meio")
    progress.report(2.0, "fim")
    assert sink.updates == [(0.4, "meio"), (0.6, "fim")]
