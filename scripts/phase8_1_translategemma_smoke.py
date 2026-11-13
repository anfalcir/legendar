#!/usr/bin/env python3
"""Smoke de TranslateGemma via a API local OpenAI-compatível do llama.cpp.

O modo --batch-check exercita o mesmo protocolo do adaptador de produção:
entrada textual, chat_template_kwargs do llama.cpp, lote JSON compacto e
gramática GBNF que restringe chaves/valores da resposta sem marcadores no texto.
"""

from __future__ import annotations

import argparse
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

LANGUAGES = {
    "en": ("English", "en"),
    "pt-BR": ("Brazilian Portuguese", "pt-BR"),
}
_BATCH_SAMPLE = (
    "We are safe.",
    "I will be back.",
    "Do not be afraid.",
)


def _validate_endpoint(base_url: str, timeout: float) -> str:
    parsed_url = urlsplit(base_url)
    if (
        parsed_url.scheme != "http"
        or parsed_url.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed_url.username is not None
        or parsed_url.password is not None
    ):
        raise ValueError("O servidor de tradução deve estar em loopback HTTP.")
    if timeout <= 0:
        raise ValueError("O timeout deve ser positivo.")
    return base_url.rstrip("/")


def _post_json(
    base_url: str,
    endpoint: str,
    payload: dict[str, object],
    timeout: float,
) -> dict[str, object]:
    request = Request(
        f"{base_url}{endpoint}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(
            f"llama.cpp respondeu HTTP {exc.code}; consulte o log local do servidor."
        ) from exc
    except URLError as exc:
        raise RuntimeError(
            "Servidor llama.cpp indisponível em loopback; confirme o processo e a porta."
        ) from exc
    except (TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Falha na comunicação/resposta do llama.cpp ({type(exc).__name__})."
        ) from exc
    if not isinstance(result, dict):
        raise RuntimeError("Resposta do servidor llama.cpp em formato inválido.")
    return result


def build_user_content(text: str, source: str, target: str) -> str:
    """Valida o par e mantém texto puro; idiomas são metadados da requisição."""
    if source not in LANGUAGES or target not in LANGUAGES or source == target:
        raise ValueError("Par de idiomas não suportado pelo smoke test.")
    if not text.strip():
        raise ValueError("O texto de entrada não pode ficar vazio.")
    return text.strip()


def _base_payload(
    content: str,
    *,
    model: str,
    source: str,
    target: str,
) -> dict[str, object]:
    return {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "chat_template_kwargs": {
            "source_lang_code": source,
            "target_lang_code": target,
        },
    }


def _rule_suffix(index: int) -> str:
    letters = "abcdefghijklmnopqrstuvwxyz"
    result = ""
    value = index + 1
    while value:
        value, remainder = divmod(value - 1, len(letters))
        result = letters[remainder] + result
    return result


def _json_grammar(keys: tuple[str, ...]) -> str:
    if not keys or len(set(keys)) != len(keys):
        raise ValueError("As chaves da gramática devem ser únicas e não vazias.")
    entry_names = [f"entry{_rule_suffix(index)}" for index in range(len(keys))]
    entries = [
        f'entry{_rule_suffix(index)} ::= "\\"{key}\\"" ws ":" ws string'
        for index, key in enumerate(keys)
    ]
    root = 'root ::= "{" ws ' + ' "," ws '.join(entry_names) + ' "}" ws'
    return "\n".join(
        (
            root,
            *entries,
            'string ::= "\\\"" char+ "\\\""',
            'char ::= [^"\\\\\\x7F\\x00-\\x1F] | "\\\\" (["\\\\bfnrt] | "u" [0-9a-fA-F]{4})',
            'ws ::= [ \\t\\n]*',
        )
    )


def translate(
    text: str,
    *,
    base_url: str = "http://127.0.0.1:8080",
    model: str = "translategemma-4b",
    source: str = "en",
    target: str = "pt-BR",
    timeout: float = 600,
) -> str:
    """Envia texto simples com códigos de idioma por chat_template_kwargs."""
    endpoint = _validate_endpoint(base_url, timeout)
    content = build_user_content(text, source, target)
    payload = _base_payload(
        content,
        model=model,
        source=source,
        target=target,
    )
    payload.update({"temperature": 0, "max_tokens": 256, "stream": False})
    result = _post_json(endpoint, "/v1/chat/completions", payload, timeout)
    try:
        choice = result["choices"][0]
        output = choice["message"]["content"]
        finish_reason = choice.get("finish_reason")
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Resposta do TranslateGemma sem conteúdo traduzido.") from exc
    if finish_reason not in {None, "stop"}:
        raise RuntimeError(f"TranslateGemma encerrou a geração ({finish_reason}).")
    if not isinstance(output, str) or not output.strip():
        raise RuntimeError("TranslateGemma retornou uma tradução vazia.")
    return output.strip()


def translate_batch_check(
    *,
    base_url: str = "http://127.0.0.1:8080",
    model: str = "translategemma-4b",
    source: str = "en",
    target: str = "pt-BR",
    timeout: float = 600,
) -> tuple[str, ...]:
    """Valida contagem e saída GBNF/JSON do lote em uma única geração."""
    endpoint = _validate_endpoint(base_url, timeout)
    if source not in LANGUAGES or target not in LANGUAGES or source == target:
        raise ValueError("Par de idiomas não suportado pelo smoke test.")

    keys = tuple(str(index) for index in range(1, len(_BATCH_SAMPLE) + 1))
    input_document = {
        "context_before": [],
        "cues": dict(zip(keys, _BATCH_SAMPLE, strict=True)),
        "context_after": [],
    }
    input_json = json.dumps(
        input_document,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    content = (
        "Translate each string value in the cues object into the target language. "
        "Use context_before and context_after only to understand context. "
        "Return only a JSON object with exactly the same numeric keys and one "
        "non-empty translated string for each key. Do not translate the keys.\n"
        + input_json
    )
    payload = _base_payload(
        content,
        model=model,
        source=source,
        target=target,
    )
    token_result = _post_json(
        endpoint,
        "/v1/chat/completions/input_tokens",
        payload,
        min(timeout, 30.0),
    )
    input_tokens = token_result.get("input_tokens")
    if (
        isinstance(input_tokens, bool)
        or not isinstance(input_tokens, int)
        or input_tokens < 0
    ):
        raise RuntimeError("llama.cpp não retornou contagem válida de tokens.")
    output_reserve = 256
    if input_tokens + output_reserve + 64 > 2048:
        raise RuntimeError(
            "O teste de lote excede o contexto de 2K; reduza o conjunto de smoke."
        )

    payload.update(
        {
            "temperature": 0,
            "max_tokens": output_reserve,
            "stream": False,
            "grammar": _json_grammar(keys),
        }
    )
    result = _post_json(endpoint, "/v1/chat/completions", payload, timeout)
    try:
        choice = result["choices"][0]
        output = choice["message"]["content"]
        finish_reason = choice.get("finish_reason")
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Resposta inválida no smoke de lote TranslateGemma.") from exc
    if finish_reason not in {None, "stop"}:
        raise RuntimeError(
            f"TranslateGemma encerrou o smoke de lote com {finish_reason}."
        )
    if not isinstance(output, str) or not output.strip():
        raise RuntimeError("TranslateGemma retornou lote vazio.")
    try:
        decoded = json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError("TranslateGemma não respeitou a gramática JSON do lote.") from exc
    if not isinstance(decoded, dict) or set(decoded) != set(keys):
        raise RuntimeError("TranslateGemma não preservou os IDs do lote.")
    translations = []
    for key in keys:
        translated = decoded[key]
        if not isinstance(translated, str) or not translated.strip():
            raise RuntimeError(f"Tradução vazia no item {key} do lote.")
        translations.append(" ".join(translated.split()))
    return tuple(translations)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "text",
        nargs="?",
        help="Texto curto para smoke isolado (não usado com --batch-check).",
    )
    parser.add_argument("--batch-check", action="store_true")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--model", default="translategemma-4b")
    parser.add_argument("--source", choices=tuple(LANGUAGES), default="en")
    parser.add_argument("--target", choices=tuple(LANGUAGES), default="pt-BR")
    parser.add_argument("--timeout", type=float, default=600)
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout deve ser positivo.")
    if args.batch_check == bool(args.text):
        parser.error("Informe um texto ou use --batch-check, mas não ambos.")
    try:
        if args.batch_check:
            output = translate_batch_check(
                base_url=args.base_url,
                model=args.model,
                source=args.source,
                target=args.target,
                timeout=args.timeout,
            )
            for index, translated in enumerate(output, start=1):
                print(f"{index}: {translated}")
        else:
            print(
                translate(
                    args.text or "",
                    base_url=args.base_url,
                    model=args.model,
                    source=args.source,
                    target=args.target,
                    timeout=args.timeout,
                )
            )
    except (RuntimeError, ValueError) as exc:
        parser.exit(2, f"Falha no smoke TranslateGemma: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
