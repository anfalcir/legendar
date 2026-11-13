from __future__ import annotations

import json
from urllib.error import URLError

import pytest

from scripts.phase8_1_translategemma_smoke import (
    _json_grammar,
    build_user_content,
    main,
    translate,
    translate_batch_check,
)


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


def test_translate_sends_plain_text_and_language_codes_per_request(monkeypatch) -> None:
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
        assert "grammar" not in payload
        assert payload["stream"] is False
        return _Response(
            {
                "choices": [
                    {
                        "message": {"content": "Eu vou voltar."},
                        "finish_reason": "stop",
                    }
                ]
            }
        )

    monkeypatch.setattr(
        "scripts.phase8_1_translategemma_smoke.urlopen",
        fake_urlopen,
    )
    result = translate("I will be back.", timeout=42)

    assert result == "Eu vou voltar."
    assert calls[0][1] == 42
    assert calls[0][0].full_url == "http://127.0.0.1:8080/v1/chat/completions"


def test_translate_rejects_empty_model_output(monkeypatch) -> None:
    monkeypatch.setattr(
        "scripts.phase8_1_translategemma_smoke.urlopen",
        lambda *_args, **_kwargs: _Response(
            {"choices": [{"message": {"content": "  "}, "finish_reason": "stop"}]}
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


def test_batch_check_uses_token_count_and_direct_grammar(monkeypatch) -> None:
    calls = []

    def fake_urlopen(request, timeout):
        payload = json.loads(request.data.decode("utf-8"))
        calls.append((request.full_url, payload, timeout))
        if request.full_url.endswith("/input_tokens"):
            return _Response({"input_tokens": 180})
        assert payload["chat_template_kwargs"] == {
            "source_lang_code": "en",
            "target_lang_code": "pt-BR",
        }
        assert "natural Brazilian Portuguese" in payload["messages"][0]["content"]
        assert "Preserve negation, intent, numbers" in payload["messages"][0]["content"]
        assert payload["messages"][0]["content"].endswith(
            '{"context_before":[],"cues":{"1":"We are safe.","2":"I will be back.",'
            '"3":"Do not be afraid."},"context_after":[]}'
        )
        grammar = payload["grammar"]
        assert 'root ::= "{" ws entrya "," ws entryb "," ws entryc "}" ws' in grammar
        assert payload["max_tokens"] == 256
        return _Response(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "1": "Estamos seguros.",
                                    "2": "Eu voltarei.",
                                    "3": "Não tenha medo.",
                                }
                            )
                        },
                        "finish_reason": "stop",
                    }
                ]
            }
        )

    monkeypatch.setattr(
        "scripts.phase8_1_translategemma_smoke.urlopen",
        fake_urlopen,
    )
    result = translate_batch_check(timeout=50)

    assert result == ("Estamos seguros.", "Eu voltarei.", "Não tenha medo.")
    assert len(calls) == 2
    assert calls[0][0].endswith("/input_tokens")
    assert calls[1][0].endswith("/chat/completions")
    assert calls[0][2] == 30
    assert calls[1][2] == 50
    assert "response_format" not in calls[1][1]


def test_batch_check_rejects_missing_or_duplicate_ids(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        if request.full_url.endswith("/input_tokens"):
            return _Response({"input_tokens": 100})
        return _Response(
            {
                "choices": [
                    {
                        "message": {
                            "content": '{"1":"Um.","2":"Dois."}'
                        },
                        "finish_reason": "stop",
                    }
                ]
            }
        )

    monkeypatch.setattr(
        "scripts.phase8_1_translategemma_smoke.urlopen",
        fake_urlopen,
    )
    with pytest.raises(RuntimeError, match="não preservou os IDs"):
        translate_batch_check()


def test_gbnf_has_fixed_json_keys_and_non_empty_values() -> None:
    grammar = _json_grammar(("1", "2"))
    assert 'root ::= "{" ws entrya "," ws entryb "}" ws' in grammar
    assert 'entrya ::= "\\"1\\"" ws ":" ws string' in grammar
    assert 'entryb ::= "\\"2\\"" ws ":" ws string' in grammar
    assert 'string ::= "\\"" char+ "\\""' in grammar


def test_cli_smoke_uses_local_server(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "scripts.phase8_1_translategemma_smoke.translate",
        lambda text, **kwargs: f"Traduzido: {text}",
    )
    assert main(["Hello.", "--timeout", "12"]) == 0
    assert capsys.readouterr().out.strip() == "Traduzido: Hello."
