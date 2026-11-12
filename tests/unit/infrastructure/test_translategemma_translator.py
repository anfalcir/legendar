from __future__ import annotations

import pytest

from legendar.application.pipeline.translation import TranslationUnit
from legendar.domain.errors.catalog import TranslationError, UnsupportedLanguageError
from legendar.domain.value_objects.language import Language
from legendar.infrastructure.translation.translategemma import (
    TranslateGemmaTranslator,
)


class FakeProgress:
    def __init__(self) -> None:
        self.updates = []

    def report(self, fraction: float, message: str = "") -> None:
        self.updates.append((fraction, message))


class FakeRuntime:
    def __init__(self, url: str = "http://127.0.0.1:43210") -> None:
        self.url = url
        self.calls = []

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


def test_translate_uses_official_template_language_metadata_and_preserves_ids() -> None:
    runtime = FakeRuntime()
    requests = []
    progress = FakeProgress()

    def requester(base_url, payload, timeout):
        requests.append((base_url, payload, timeout))
        return {
            "choices": [
                {"message": {"content": "Eu voltarei." if len(requests) == 1 else "Estamos seguros."}}
            ]
        }

    translator = TranslateGemmaTranslator(runtime, requester=requester)

    result = translator.translate(
        _units(),
        source_language=Language.ENGLISH,
        target_language=Language.PORTUGUESE,
        progress=progress,
    )

    assert result.language is Language.PORTUGUESE
    assert result.unit_indexes == (4, 5)
    assert result.texts == ("Eu voltarei.", "Estamos seguros.")
    assert [call[0] for call in runtime.calls] == ["model", "server"]
    assert runtime.calls[0][2]._start == 0.0
    assert runtime.calls[0][2]._span == 0.75
    assert runtime.calls[1][2]._start == 0.75
    assert runtime.calls[1][2]._span == 0.15
    assert len(requests) == 2
    assert requests[0][0] == runtime.url
    assert requests[0][1]["messages"] == [
        {"role": "user", "content": "I will be back."}
    ]
    assert requests[0][1]["chat_template_kwargs"] == {
        "source_lang_code": "en",
        "target_lang_code": "pt-BR",
    }
    assert requests[0][1]["temperature"] == 0.0
    assert progress.updates[-1][0] == 1.0


def test_translate_supports_reverse_language_direction() -> None:
    runtime = FakeRuntime()
    payloads = []

    def requester(_url, payload, _timeout):
        payloads.append(payload)
        return {"choices": [{"message": {"content": "I am ready."}}]}

    translator = TranslateGemmaTranslator(runtime, requester=requester)
    result = translator.translate(
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


def test_translate_rejects_same_language_and_empty_response() -> None:
    translator = TranslateGemmaTranslator(
        FakeRuntime(),
        requester=lambda *_args: {"choices": [{"message": {"content": "  "}}]},
    )
    with pytest.raises(UnsupportedLanguageError):
        translator.translate(
            (TranslationUnit(index=1, text="Hello"),),
            source_language=Language.ENGLISH,
            target_language=Language.ENGLISH,
            progress=FakeProgress(),
        )

    with pytest.raises(TranslationError, match="texto vazio"):
        translator.translate(
            (TranslationUnit(index=1, text="Hello"),),
            source_language=Language.ENGLISH,
            target_language=Language.PORTUGUESE,
            progress=FakeProgress(),
        )


def test_translate_rejects_malformed_response_and_empty_units() -> None:
    translator = TranslateGemmaTranslator(
        FakeRuntime(),
        requester=lambda *_args: {"choices": []},
    )
    with pytest.raises(TranslationError, match="Nenhuma unidade"):
        translator.translate(
            (),
            source_language=Language.ENGLISH,
            target_language=Language.PORTUGUESE,
            progress=FakeProgress(),
        )
    with pytest.raises(TranslationError, match="resposta inválida"):
        translator.translate(
            (TranslationUnit(index=1, text="Hello"),),
            source_language=Language.ENGLISH,
            target_language=Language.PORTUGUESE,
            progress=FakeProgress(),
        )


def test_translate_checks_cancellation_between_units() -> None:
    class CancelAfterFirst:
        def __init__(self) -> None:
            self.calls = 0

        @property
        def is_cancelled(self) -> bool:
            return self.calls >= 1

        def raise_if_cancelled(self) -> None:
            if self.is_cancelled:
                raise RuntimeError("cancelled")

    token = CancelAfterFirst()
    requests = []

    def requester(*_args):
        requests.append(True)
        token.calls += 1
        return {"choices": [{"message": {"content": "Volto."}}]}

    translator = TranslateGemmaTranslator(FakeRuntime(), requester=requester)
    with pytest.raises(RuntimeError, match="cancelled"):
        translator.translate(
            _units(),
            source_language=Language.ENGLISH,
            target_language=Language.PORTUGUESE,
            progress=FakeProgress(),
            token=token,
        )
    assert len(requests) == 1
