#!/usr/bin/env python3
"""Smoke test local do TranslateGemma via API OpenAI-compatible do llama.cpp.

O servidor deve estar iniciado em loopback com o GGUF TranslateGemma 4B.
O teste envia os códigos de idioma em chat_template_kwargs por requisição,
não em system prompt nem em configuração global do servidor.
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


def build_user_content(text: str, source: str, target: str) -> str:
    """Valida o par e mantém o texto puro, como exige o chat template oficial."""
    if source not in LANGUAGES or target not in LANGUAGES:
        raise ValueError("Par de idiomas não suportado pelo smoke test.")
    if not text.strip():
        raise ValueError("O texto de entrada não pode ficar vazio.")
    return text.strip()


def translate(
    text: str,
    *,
    base_url: str = "http://127.0.0.1:8080",
    model: str = "translategemma-4b",
    source: str = "en",
    target: str = "pt-BR",
    timeout: float = 600,
) -> str:
    """Envia uma única mensagem com metadados de idioma por requisição."""
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
    user_content = build_user_content(text, source, target)
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": user_content}],
        "chat_template_kwargs": {
            "source_lang_code": source,
            "target_lang_code": target,
        },
        "temperature": 0,
        "max_tokens": 256,
        "stream": False,
    }
    request = Request(
        f"{base_url.rstrip('/')}/v1/chat/completions",
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
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Resposta inválida do servidor llama.cpp.") from exc

    try:
        output = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Resposta do TranslateGemma sem conteúdo traduzido.") from exc
    if not isinstance(output, str) or not output.strip():
        raise RuntimeError("TranslateGemma retornou uma tradução vazia.")
    return output.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("text", help="Texto curto para o smoke test local.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--model", default="translategemma-4b")
    parser.add_argument("--source", choices=tuple(LANGUAGES), default="en")
    parser.add_argument("--target", choices=tuple(LANGUAGES), default="pt-BR")
    parser.add_argument("--timeout", type=float, default=600)
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout deve ser positivo.")
    try:
        output = translate(
            args.text,
            base_url=args.base_url,
            model=args.model,
            source=args.source,
            target=args.target,
            timeout=args.timeout,
        )
    except RuntimeError as exc:
        parser.exit(2, f"Falha no smoke TranslateGemma: {exc}\n")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
