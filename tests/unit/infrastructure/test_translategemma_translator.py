from __future__ import annotations

import re
from urllib.error import HTTPError, URLError

import pytest

import legendar.infrastructure.translation.translategemma as translategemma_module
from legendar.application.pipeline.translation import TranslationContext, TranslationUnit
from legendar.domain.errors.catalog import TranslationError, UnsupportedLanguageError
from legendar.domain.value_objects.language import Language
from legendar.infrastructure.translation.translategemma import TranslateGemmaTranslator


_MARKER_PATTERN = re.compile(r"\[\[LG[0-9a-f]{10}_[A-Z0-9_]+\]\]")


class FakeProgress:
    def __init__(self) -> None:
        self.updates = []

    def report(self, fraction: float, message: str = "") -> None:
        self.updates.append((fraction, message))


class FakeRuntime:
    def __init__(self, url: str = "http://127.0.0.1:43210") -> None:
        self.url = url
        self.calls = []

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


def _markers(payload: dict[str, object]) -> list[str]:
    messages = payload["messages"]
    assert isinstance(messages, list)
    message = messages[0]
    assert isinstance(message, dict)
    content = message["content"]
    assert isinstance(content, str)
    return _MARKER_PATTERN.findall(content)


def _response_for_batch(
    payload: dict[str, object],
    target_texts: tuple[str, ...],
) -> dict[str, object]:
    messages = payload["messages"]
    assert isinstance(messages, list)
    message = messages[0]
    assert isinstance(message, dict)
    source = message["content"]
    assert isinstance(source, str)
    markers = _markers(payload)
    target_markers = [marker for marker in markers if "_UNIT_" in marker]
    assert len(target_markers) == len(target_texts)
    translated = dict(zip(target_markers, target_texts, strict=True))
    output: list[str] = []
    for position, marker in enumerate(markers):
        start = source.index(marker) + len(marker)
        end = (
            source.index(markers[position + 1])
            if position + 1 < len(markers)
            else len(source)
        )
        fallback_context = " ".join(source[start:end].split())
        value = translated.get(marker, fallback_context)
        output.append(f"{marker}\n{value}")
    return {
        "choices": [
            {
                "message": {"content": "\n\n".join(output)},
                "finish_reason": "stop",
            }
        ]
    }


def _counter(_url: str, _payload: dict[str, object], _timeout: float) -> int:
    return 64


def _translator(runtime=None, requester=None, token_counter=_counter):
    return TranslateGemmaTranslator(
        runtime or FakeRuntime(),
        requester=requester
        or (lambda _url, _payload, _timeout: {
            "choices": [{"message": {"content": "Eu voltei."}, "finish_reason": "stop"}]
        }),
        token_counter=token_counter,
    )


def test_translate_batches_units_with_official_language_metadata_and_preserves_ids() -> None:
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
    assert len(requests) == 1
    assert len(token_payloads) == 1
    assert requests[0][0] == runtime.url
    payload = requests[0][1]
    assert payload["chat_template_kwargs"] == {
        "source_lang_code": "en",
        "target_lang_code": "pt-BR",
    }
    assert payload["temperature"] == 0.0
    assert payload["stream"] is False
    assert payload["max_tokens"] >= 128
    assert len(_markers(payload)) == 2
    fractions = [fraction for fraction, _message in progress.updates]
    assert fractions == sorted(fractions)
    assert progress.updates[-1][0] == 1.0


def test_batch_includes_neighboring_context_without_returning_context_as_units() -> None:
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

    content = payloads[0]["messages"][0]["content"]
    assert "We heard a noise." in content
    assert "Do not be afraid." in content
    assert result.unit_indexes == (7, 8)
    assert result.texts == ("Primeira.", "Segunda.")


def test_reverse_language_direction_uses_single_cue_request() -> None:
    payloads = []

    def requester(_url, payload, _timeout):
        payloads.append(payload)
        return {"choices": [{"message": {"content": "I am ready."}}]}

    result = _translator(requester=requester).translate(
        (TranslationUnit(index=1, text="Estou pronto."),),
        source_language=Language.PORTUGUESE,
        target_language=Language.ENGLISH,
        progress=FakeProgress(),
    )

    assert result.texts == ("I am ready.",)
    assert payloads[0]["messages"] == [
        {"role": "user", "content": "Estou pronto."}
    ]
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


def test_translate_rejects_duplicate_unit_indexes_before_starting_runtime() -> None:
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


def test_malformed_batch_is_split_and_recovered_without_backend_fallback() -> None:
    requests = []

    def requester(_url, payload, _timeout):
        requests.append(payload)
        if len(requests) == 1:
            return {"choices": []}
        text = payload["messages"][0]["content"]
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            "Eu voltarei."
                            if text == "I will be back."
                            else "Estamos seguros."
                        )
                    },
                    "finish_reason": "stop",
                }
            ]
        }

    result = _translator(requester=requester).translate(
        _units(),
        source_language=Language.ENGLISH,
        target_language=Language.PORTUGUESE,
        progress=FakeProgress(),
    )

    assert result.unit_indexes == (4, 5)
    assert result.texts == ("Eu voltarei.", "Estamos seguros.")
    assert len(requests) == 3
    assert all("nllb" not in str(payload).lower() for payload in requests)


def test_reordered_batch_markers_trigger_safe_split() -> None:
    requests = []

    def requester(_url, payload, _timeout):
        requests.append(payload)
        if len(requests) == 1:
            return _response_for_batch(payload, ("Estamos seguros.", "Eu voltarei.")) | {
                "choices": [
                    {
                        "message": {
                            "content": "\n\n".join(
                                reversed(
                                    _response_for_batch(
                                        payload,
                                        ("Estamos seguros.", "Eu voltarei."),
                                    )["choices"][0]["message"]["content"].split("\n\n")
                                )
                            )
                        },
                        "finish_reason": "stop",
                    }
                ]
            }
        text = payload["messages"][0]["content"]
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            "Eu voltarei."
                            if text == "I will be back."
                            else "Estamos seguros."
                        )
                    }
                }
            ]
        }

    result = _translator(requester=requester).translate(
        _units(),
        source_language=Language.ENGLISH,
        target_language=Language.PORTUGUESE,
        progress=FakeProgress(),
    )
    assert result.texts == ("Eu voltarei.", "Estamos seguros.")
    assert len(requests) == 3


def test_prompt_over_budget_is_split_before_generation() -> None:
    requests = []
    counted = []

    def requester(_url, payload, _timeout):
        requests.append(payload)
        text = payload["messages"][0]["content"]
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            "Eu voltarei."
                            if text == "I will be back."
                            else "Estamos seguros."
                        )
                    }
                }
            ]
        }

    def counter(_url, payload, _timeout):
        counted.append(payload)
        content = payload["messages"][0]["content"]
        return 1900 if "[[LG" in content else 20

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
    assert all("[[LG" not in payload["messages"][0]["content"] for payload in requests)


def test_single_unit_empty_response_is_an_explicit_error() -> None:
    translator = _translator(
        requester=lambda *_args: {
            "choices": [{"message": {"content": "  "}, "finish_reason": "stop"}]
        }
    )
    with pytest.raises(TranslationError, match="resposta inválida"):
        translator.translate(
            (TranslationUnit(index=9, text="Hello"),),
            source_language=Language.ENGLISH,
            target_language=Language.PORTUGUESE,
            progress=FakeProgress(),
        )


def test_cancellation_is_checked_between_groups(monkeypatch) -> None:
    class CancelAfterFirst:
        def __init__(self) -> None:
            self.calls = 0

        @property
        def is_cancelled(self) -> bool:
            return self.calls >= 1

        def raise_if_cancelled(self) -> None:
            if self.is_cancelled:
                raise RuntimeError("cancelled")

    monkeypatch.setattr(
        "legendar.infrastructure.translation.translategemma._MAX_BATCH_UNITS",
        1,
    )
    token = CancelAfterFirst()
    requests = []

    def requester(_url, payload, _timeout):
        requests.append(True)
        token.calls += 1
        return {"choices": [{"message": {"content": "Volto."}, "finish_reason": "stop"}]}

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
        translategemma_module,
        "urlopen",
        lambda *_args, **_kwargs: _FakeHttpResponse(b'{"ok": true}'),
    )
    assert translategemma_module._post_json(
        "http://127.0.0.1:8080",
        "/test",
        {"value": 1},
        1.0,
    ) == {"ok": True}


@pytest.mark.parametrize("body", [b"not-json", b"[]"])
def test_post_json_rejects_invalid_json_shapes(monkeypatch, body) -> None:
    monkeypatch.setattr(
        translategemma_module,
        "urlopen",
        lambda *_args, **_kwargs: _FakeHttpResponse(body),
    )
    with pytest.raises(TranslationError):
        translategemma_module._post_json(
            "http://127.0.0.1:8080",
            "/test",
            {},
            1.0,
        )


def test_post_json_normalizes_http_and_network_errors(monkeypatch) -> None:
    def http_failure(*_args, **_kwargs):
        raise HTTPError("http://127.0.0.1:8080/test", 503, "unavailable", None, None)

    monkeypatch.setattr(translategemma_module, "urlopen", http_failure)
    with pytest.raises(TranslationError, match="HTTP 503"):
        translategemma_module._post_json(
            "http://127.0.0.1:8080",
            "/test",
            {},
            1.0,
        )

    def network_failure(*_args, **_kwargs):
        raise URLError("connection refused")

    monkeypatch.setattr(translategemma_module, "urlopen", network_failure)
    with pytest.raises(TranslationError, match="URLError"):
        translategemma_module._post_json(
            "http://127.0.0.1:8080",
            "/test",
            {},
            1.0,
        )


def test_count_prompt_tokens_rejects_invalid_count(monkeypatch) -> None:
    monkeypatch.setattr(
        translategemma_module,
        "_post_json",
        lambda *_args, **_kwargs: {"input_tokens": True},
    )
    with pytest.raises(TranslationError, match="contagem válida"):
        translategemma_module._count_prompt_tokens(
            "http://127.0.0.1:8080",
            {},
            1.0,
        )
