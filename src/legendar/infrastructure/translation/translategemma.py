"""Adaptador local TranslateGemma sobre o servidor OpenAI-compatible llama.cpp.

O runtime é iniciado sob demanda pelo gerenciador. O modelo recebe texto puro
com os códigos de idioma no chat_template_kwargs oficial; não se injeta prompt
instrucional que altere o template especializado do TranslateGemma.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from legendar.application.pipeline.translation import (
    TranslationResult,
    TranslationUnit,
)
from legendar.application.ports.protocols import CancellationToken, ProgressSink
from legendar.domain.errors.catalog import (
    ModelError,
    TranslationError,
    UnsupportedLanguageError,
)
from legendar.domain.value_objects.language import Language
from legendar.infrastructure.translation.llama_runtime import (
    DEFAULT_MODEL_ALIAS,
    LlamaCppRuntimeManager,
)

_REQUEST_TIMEOUT_SECONDS = 600.0
_MAX_OUTPUT_TOKENS = 512
_LANGUAGE_CODES = {
    Language.ENGLISH: "en",
    Language.PORTUGUESE: "pt-BR",
}

Requester = Callable[[str, dict[str, object], float], dict[str, object]]


def _chat_completion(
    base_url: str,
    payload: dict[str, object],
    timeout: float,
) -> dict[str, object]:
    """Executa uma chamada local sem registrar o conteúdo da legenda."""
    request = Request(
        f"{base_url}/v1/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except HTTPError as exc:
        raise TranslationError(
            f"Servidor TranslateGemma respondeu com HTTP {exc.code}."
        ) from None
    except (TimeoutError, URLError, OSError) as exc:
        raise TranslationError(
            f"Falha de comunicação com TranslateGemma ({type(exc).__name__})."
        ) from None
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise TranslationError(
            "TranslateGemma retornou uma resposta JSON inválida."
        ) from None
    if not isinstance(decoded, dict):
        raise TranslationError("Resposta TranslateGemma em formato inválido.")
    return decoded


class TranslateGemmaTranslator:
    """Implementa a porta Translator com runtime local gerenciado."""

    def __init__(
        self,
        runtime: LlamaCppRuntimeManager,
        *,
        model: str = DEFAULT_MODEL_ALIAS,
        timeout_seconds: float = _REQUEST_TIMEOUT_SECONDS,
        requester: Requester = _chat_completion,
    ) -> None:
        if not model.strip():
            raise ValueError("Alias do modelo TranslateGemma não pode ser vazio.")
        if timeout_seconds <= 0:
            raise ValueError("Timeout TranslateGemma deve ser positivo.")
        self.runtime = runtime
        self.model = model.strip()
        self.timeout_seconds = timeout_seconds
        self._requester = requester

    def translate(
        self,
        units: tuple[TranslationUnit, ...],
        *,
        source_language: Language,
        target_language: Language,
        progress: ProgressSink,
        token: CancellationToken | None = None,
    ) -> TranslationResult:
        if source_language not in _LANGUAGE_CODES or target_language not in _LANGUAGE_CODES:
            raise UnsupportedLanguageError(
                "TranslateGemma suporta somente PT-BR e inglês neste produto."
            )
        if source_language is target_language:
            raise UnsupportedLanguageError(
                "O idioma de origem e destino do TranslateGemma devem ser diferentes."
            )
        if not units:
            raise TranslationError("Nenhuma unidade foi enviada ao TranslateGemma.")

        source_code = _LANGUAGE_CODES[source_language]
        target_code = _LANGUAGE_CODES[target_language]
        base_url = self.runtime.ensure_running(token=token, progress=progress)
        translated: list[str] = []
        indexes: list[int] = []
        total = len(units)

        for position, unit in enumerate(units, start=1):
            if token is not None:
                token.raise_if_cancelled()
            payload: dict[str, object] = {
                "model": self.model,
                "messages": [{"role": "user", "content": unit.text}],
                "chat_template_kwargs": {
                    "source_lang_code": source_code,
                    "target_lang_code": target_code,
                },
                "temperature": 0.0,
                "max_tokens": _MAX_OUTPUT_TOKENS,
                "stream": False,
            }
            response = self._requester(
                base_url,
                payload,
                self.timeout_seconds,
            )
            choices = response.get("choices")
            if not isinstance(choices, list) or len(choices) != 1:
                raise TranslationError(
                    f"Resposta TranslateGemma inválida na unidade {unit.index}."
                )
            choice = choices[0]
            message = choice.get("message") if isinstance(choice, dict) else None
            text = message.get("content") if isinstance(message, dict) else None
            if not isinstance(text, str) or not text.strip():
                raise TranslationError(
                    f"TranslateGemma retornou texto vazio na unidade {unit.index}."
                )
            translated.append(" ".join(text.split()))
            indexes.append(unit.index)
            progress.report(
                position / total,
                f"Traduzindo com TranslateGemma · unidade {position}/{total}",
            )

        return TranslationResult(
            language=target_language,
            texts=tuple(translated),
            unit_indexes=tuple(indexes),
        )
