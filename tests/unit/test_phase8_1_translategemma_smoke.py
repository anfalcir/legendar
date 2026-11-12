from __future__ import annotations

import json
from urllib.error import URLError

import pytest
from scripts.phase8_1_translategemma_smoke import build_user_content, main, translate


class _Response:
    def __init__(self, payload: dict) -> None:
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return self.payload


def test_user_content_is_the_unmodified_text_to_translate() -> None:
    content = build_user_content("  I will be back.  ", "en", "pt-BR")

    assert content == "I will be back."


def test_translate_sends_language_codes_per_request(monkeypatch) -> None:
    calls: list[tuple[object, float]] = []

    def fake_urlopen(request, timeout):
        calls.append((request, timeout))
        payload = json.loads(request.data.decode("utf-8"))
        assert payload["model"] == "translategemma-4b"
        assert payload["chat_template_kwargs"] == {
            "source_lang_code": "en",
            "target_lang_code": "pt-BR",
        }
        assert [message["role"] for message in payload["messages"]] == ["user"]
        assert payload["messages"][0]["content"] == "I will be back."
        assert payload["stream"] is False
        return _Response({"choices": [{"message": {"content": "Eu vou voltar."}}]})

    monkeypatch.setattr("scripts.phase8_1_translategemma_smoke.urlopen", fake_urlopen)

    result = translate("I will be back.", timeout=42)

    assert result == "Eu vou voltar."
    assert calls[0][1] == 42
    assert calls[0][0].full_url == "http://127.0.0.1:8080/v1/chat/completions"


def test_translate_rejects_empty_model_output(monkeypatch) -> None:
    monkeypatch.setattr(
        "scripts.phase8_1_translategemma_smoke.urlopen",
        lambda *_args, **_kwargs: _Response(
            {"choices": [{"message": {"content": "  "}}]}
        ),
    )

    with pytest.raises(RuntimeError, match="tradução vazia"):
        translate("Hello.")


def test_translate_reports_server_unavailable(monkeypatch) -> None:
    def fail(*_args, **_kwargs):
        raise URLError("offline")

    monkeypatch.setattr("scripts.phase8_1_translategemma_smoke.urlopen", fail)

    with pytest.raises(RuntimeError, match="indisponível em loopback"):
        translate("Hello.")


def test_translate_rejects_non_loopback_server() -> None:
    with pytest.raises(ValueError, match="loopback"):
        translate("Hello.", base_url="https://example.com")


def test_translate_rejects_unsupported_language_pair() -> None:
    with pytest.raises(ValueError, match="Par de idiomas"):
        build_user_content("Hello.", "fr", "pt-BR")


def test_cli_smoke_uses_local_server(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "scripts.phase8_1_translategemma_smoke.translate",
        lambda text, **kwargs: f"Traduzido: {text}",
    )

    assert main(["Hello.", "--timeout", "12"]) == 0
    assert capsys.readouterr().out.strip() == "Traduzido: Hello."
