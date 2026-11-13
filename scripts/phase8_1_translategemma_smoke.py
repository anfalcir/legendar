#!/usr/bin/env python3
"""Smoke test local do TranslateGemma via API OpenAI-compatible do llama.cpp.

O servidor deve estar iniciado em loopback com o GGUF TranslateGemma 4B.
O modo --batch-check valida, com uma única geração, a preservação dos
marcadores usados pelo adaptador de produção.
"""

from __future__ import annotations

import argparse
import hashlib
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
        data=json.dumps(payload, ensure_ascii=False).encode(),
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
    """Valida o par e mantém o texto puro, como exige o chat template oficial."""
    if source not in LANGUAGES or target not in LANGUAGES:
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
    endpoint = _validate_endpoint(base_url, timeout)
    user_content = build_user_content(text, source, target)
    payload = _base_payload(
        user_content,
        model=model,
        source=source,
        target=target,
    )
    payload.update({"temperature": 0, "max_tokens": 256, "stream": False})
    result = _post_json(endpoint, "/v1/chat/completions", payload, timeout)
    try:
        output = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Resposta do TranslateGemma sem conteúdo traduzido.") from exc
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
    """Valida contagem de contexto e marcadores em três cues consecutivas."""
    endpoint = _validate_endpoint(base_url, timeout)
    if source not in LANGUAGES or target not in LANGUAGES or source == target:
        raise ValueError("Par de idiomas não suportado pelo smoke test.")

    seed = "\0".join(_BATCH_SAMPLE)
    digest = hashlib.sha256(seed.encode()).hexdigest()[:10]
    prefix = f"[[LG{digest}_"
    markers = tuple(f"{prefix}UNIT_{position:010d}]]" for position in range(1, 4))
    content = "\n\n".join(
        f"{marker}\n{text}"
        for marker, text in zip(markers, _BATCH_SAMPLE, strict=True)
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
    if input_tokens + 512 + 64 > 2048:
        raise RuntimeError(
            "O teste de lote excede o contexto de 2K; reduza o conjunto de smoke."
        )

    payload.update({"temperature": 0, "max_tokens": 512, "stream": False})
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

    positions = []
    for marker in markers:
        if output.count(marker) != 1:
            raise RuntimeError(
                "TranslateGemma removeu ou duplicou marcador; lote não é confiável."
            )
        positions.append(output.index(marker))
    if positions != sorted(positions) or output[: positions[0]].strip():
        raise RuntimeError("TranslateGemma alterou a ordem dos marcadores.")

    translations = []
    for index, marker in enumerate(markers):
        start = positions[index] + len(marker)
        end = positions[index + 1] if index + 1 < len(positions) else len(output)
        translated = " ".join(output[start:end].split())
        if not translated:
            raise RuntimeError(f"Tradução vazia no item {index + 1} do lote.")
        translations.append(translated)
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
