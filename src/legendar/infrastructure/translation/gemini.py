"""Adaptador Gemini Developer API para tradução contextual em lotes.

A API é chamada diretamente via urllib: não há dependência adicional nem
credencial em URL/log. Cada lote preserva IDs de cue e é validado antes de
seguir. O NLLB permanece disponível como backend local alternativo.
"""

from __future__ import annotations

import contextlib
import json
import os
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any
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

DEFAULT_MODEL = "gemini-3.8-flash"
DEFAULT_BATCH_SIZE = 32
DEFAULT_TIMEOUT_SECONDS = 120
DEFAULT_MAX_RETRIES = 3
SUPPORTED_LANGUAGES = frozenset({Language.PORTUGUESE, Language.ENGLISH})
# Stable Gemini 3 Flash models supported by this adapter expose Google Search grounding.
GROUNDING_SUPPORTED_MODELS = frozenset(
    {
        "gemini-3.8-flash",
        "gemini-3.7-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
    }
)
SYSTEM_INSTRUCTION = """Você é um tradutor profissional de legendas.
Traduza para o idioma de destino solicitado, preservando integralmente o
significado, a intenção, a negação, o sujeito, o tempo verbal, o tom e o
registro oral. Quando o destino for português, escreva PT-BR natural,
contemporâneo e idiomático; nunca faça tradução palavra por palavra se ela
produzir uma frase artificial.

Preserve nomes próprios e entidades nomeadas: pessoas, personagens, cidades,
lugares, povos, raças, clãs, famílias, facções, organizações, títulos próprios,
obras e universos ficcionais. Não traduza nem adapte esses nomes, salvo forma
consagrada inequívoca ou glossário explícito. Preserve números, datas, siglas,
referências, nomes de usuário e termos específicos do universo. Em caso de
ambiguidade sem evidência suficiente, mantenha o termo original.

Use as cues anteriores traduzidas e as cues vizinhas como contexto para
consistência terminológica e continuidade. Não acrescente explicações, notas,
fatos externos ou conteúdo que não foi falado. Use a pesquisa Google disponível
via grounding para investigar nomes próprios, cidades, povos, raças, clãs,
facções, obras e termos de universo quando houver ambiguidade ou incerteza.
Priorize fontes confiáveis e confronte os resultados com as cues e o contexto;
a pesquisa serve apenas para identificar a referência correta, nunca para
acrescentar fatos à legenda. Se não houver evidência suficiente, preserve o
termo original. Não resuma, suavize ou censure.

Retorne somente JSON conforme o esquema fornecido. Cada cue atual deve aparecer
exatamente uma vez, com o mesmo cue_id e na mesma ordem. Não altere IDs."""


class GeminiApiError(Exception):
    """Erro HTTP sanitizado da API Gemini, sem URL, chave ou corpo do prompt."""

    def __init__(self, status: int, retry_after: float | None = None) -> None:
        self.status = status
        self.retry_after = retry_after
        super().__init__(f"Gemini API retornou HTTP {status}.")


Requester = Callable[[str, Mapping[str, Any], str, float], Mapping[str, Any]]
Sleeper = Callable[[float], None]


def _http_request(
    model: str,
    payload: Mapping[str, Any],
    api_key: str,
    timeout: float,
) -> Mapping[str, Any]:
    """Executa generateContent sem expor a chave em URL ou mensagens de erro."""
    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent"
    )
    request = Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except HTTPError as exc:
        retry_after = None
        with contextlib.suppress(TypeError, ValueError):
            retry_after = float(exc.headers.get("Retry-After", ""))
        raise GeminiApiError(exc.code, retry_after) from None
    except (TimeoutError, URLError, OSError) as exc:
        raise TranslationError(
            f"Falha de comunicação com Gemini ({type(exc).__name__})."
        ) from None
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise TranslationError("Gemini retornou uma resposta JSON inválida.") from None
    if not isinstance(decoded, dict):
        raise TranslationError("Gemini retornou uma resposta em formato inválido.")
    return decoded


def _response_schema() -> dict[str, Any]:
    return {
        "type": "OBJECT",
        "properties": {
            "translations": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "cue_id": {"type": "INTEGER"},
                        "text": {"type": "STRING"},
                    },
                    "required": ["cue_id", "text"],
                    "propertyOrdering": ["cue_id", "text"],
                },
            }
        },
        "required": ["translations"],
        "propertyOrdering": ["translations"],
    }


class GeminiTranslator:
    """Tradutor por API, com contexto de cues, lotes e validação 1:1."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        batch_size: int = DEFAULT_BATCH_SIZE,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        grounding: bool = False,
        requester: Requester = _http_request,
        sleeper: Sleeper = time.sleep,
    ) -> None:
        normalized_model = (model or "").strip()
        if not normalized_model or "/" in normalized_model:
            raise ValueError("Modelo Gemini inválido.")
        if batch_size < 1 or batch_size > 100:
            raise ValueError("O lote Gemini deve conter entre 1 e 100 cues.")
        if timeout_seconds <= 0:
            raise ValueError("O timeout Gemini deve ser positivo.")
        if max_retries < 0 or max_retries > 8:
            raise ValueError("O número de retries Gemini deve estar entre 0 e 8.")
        if grounding and normalized_model not in GROUNDING_SUPPORTED_MODELS:
            raise ValueError(
                "O adaptador não habilita Google Search grounding para este modelo; "
                "use um modelo Gemini 3 Flash estável compatível ou desative LEGENDAR_GEMINI_GROUNDING."
            )
        self.api_key = (api_key or "").strip() or None
        self.model = normalized_model
        self.batch_size = batch_size
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.grounding = grounding
        self._requester = requester
        self._sleeper = sleeper
        self._metrics_lock = threading.Lock()
        self._metrics: dict[str, int | float] = {
            "requests": 0,
            "retries": 0,
            "batches": 0,
            "translated_units": 0,
            "request_seconds": 0.0,
            "input_tokens": 0,
            "output_tokens": 0,
            "grounding_queries": 0,
        }

    @classmethod
    def from_environment(cls, _models_dir: Path | None = None) -> GeminiTranslator:
        raw_grounding = os.environ.get("LEGENDAR_GEMINI_GROUNDING", "true")
        grounding = raw_grounding.strip().casefold() in {"1", "true", "yes", "on"}
        try:
            batch_size = int(
                os.environ.get("LEGENDAR_GEMINI_BATCH_SIZE", DEFAULT_BATCH_SIZE)
            )
            timeout = float(
                os.environ.get("LEGENDAR_GEMINI_TIMEOUT", DEFAULT_TIMEOUT_SECONDS)
            )
            retries = int(
                os.environ.get("LEGENDAR_GEMINI_MAX_RETRIES", DEFAULT_MAX_RETRIES)
            )
        except ValueError as exc:
            raise ValueError("Configuração numérica Gemini inválida.") from exc
        return cls(
            api_key=os.environ.get("GEMINI_API_KEY"),
            model=os.environ.get("LEGENDAR_GEMINI_MODEL", DEFAULT_MODEL),
            batch_size=batch_size,
            timeout_seconds=timeout,
            max_retries=retries,
            grounding=grounding,
        )

    @property
    def is_configured(self) -> bool:
        return self.api_key is not None

    def performance_snapshot(self) -> dict[str, Any]:
        """Métricas sem textos, chave, prompts, URLs ou conteúdo de cues."""
        with self._metrics_lock:
            counters = dict(self._metrics)
        return {
            "configuration": {
                "adapter": "gemini-developer-api",
                "model": self.model,
                "thinking_level": "LOW" if self.model.startswith("gemini-3") else None,
                "batch_size": self.batch_size,
                "timeout_seconds": self.timeout_seconds,
                "max_retries": self.max_retries,
                "grounding": self.grounding,
                "api_key_configured": self.is_configured,
            },
            "counters": counters,
        }

    def _record(self, name: str, value: int | float) -> None:
        with self._metrics_lock:
            self._metrics[name] = self._metrics.get(name, 0) + value

    def translate(
        self,
        units: tuple[TranslationUnit, ...],
        *,
        source_language: Language,
        target_language: Language,
        progress: ProgressSink,
        token: CancellationToken | None = None,
    ) -> TranslationResult:
        if not units:
            raise TranslationError("Nenhuma unidade de legenda para traduzir.")
        if not self.api_key:
            raise ModelError(
                "GEMINI_API_KEY não configurada. Cadastre a chave no ambiente "
                "antes de selecionar o backend Gemini."
            )
        if (
            source_language not in SUPPORTED_LANGUAGES
            or target_language not in SUPPORTED_LANGUAGES
        ):
            raise UnsupportedLanguageError(
                "Gemini oferece suporte apenas a Português (BR) e Inglês neste fluxo."
            )
        if source_language is target_language:
            raise UnsupportedLanguageError(
                "Origem e destino da tradução usam o mesmo idioma."
            )

        outputs: list[str] = []
        translated_context: list[tuple[str, str]] = []
        total = len(units)
        for start in range(0, total, self.batch_size):
            self._check_cancelled(token)
            batch = units[start : start + self.batch_size]
            before = units[max(0, start - 2) : start]
            after = units[start + len(batch) : start + len(batch) + 2]
            payload = self._payload(
                batch,
                before=before,
                after=after,
                translated_context=translated_context[-12:],
                source_language=source_language,
                target_language=target_language,
            )
            response = self._request_with_retry(payload)
            translated = self._parse_response(response, batch)
            outputs.extend(translated)
            translated_context.extend(
                (unit.text, text) for unit, text in zip(batch, translated, strict=True)
            )
            done = start + len(batch)
            self._record("batches", 1)
            self._record("translated_units", len(batch))
            progress.report(done / total, f"Legenda {done}/{total} traduzida")
        self._check_cancelled(token)
        return TranslationResult(language=target_language, texts=tuple(outputs))

    def _payload(
        self,
        batch: Sequence[TranslationUnit],
        *,
        before: Sequence[TranslationUnit],
        after: Sequence[TranslationUnit],
        translated_context: Sequence[tuple[str, str]],
        source_language: Language,
        target_language: Language,
    ) -> dict[str, Any]:
        source_label = source_language.label_pt
        target_label = (
            "português brasileiro (PT-BR)"
            if target_language is Language.PORTUGUESE
            else "inglês natural"
        )
        content = {
            "contexto_anterior_traduzido": [
                {"original": source, "traducao": translated}
                for source, translated in translated_context
            ],
            "cues_anteriores": [
                {"cue_id": unit.index, "text": unit.text} for unit in before
            ],
            "cues_a_traduzir": [
                {"cue_id": unit.index, "text": unit.text} for unit in batch
            ],
            "cues_posteriores": [
                {"cue_id": unit.index, "text": unit.text} for unit in after
            ],
        }
        prompt = (
            f"Idioma de origem: {source_label}.\n"
            f"Idioma de destino: {target_label}.\n"
            "Traduza exclusivamente cues_a_traduzir. Use os demais campos "
            "somente como contexto. Preserve nomes, termos específicos, "
            "números e referências. Retorne cada cue_id uma única vez e "
            "exatamente na ordem recebida.\n"
            + json.dumps(content, ensure_ascii=False, separators=(",", ":"))
        )
        payload: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": 8192,
                "responseMimeType": "application/json",
                "responseJsonSchema": _response_schema(),
            },
        }
        if self.model.startswith("gemini-3"):
            payload["generationConfig"]["thinkingConfig"] = {"thinkingLevel": "LOW"}
        if self.grounding:
            payload["tools"] = [{"googleSearch": {}}]
        return payload

    def _request_with_retry(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        assert self.api_key is not None
        for attempt in range(self.max_retries + 1):
            started = time.perf_counter()
            try:
                self._record("requests", 1)
                response = self._requester(
                    self.model, payload, self.api_key, self.timeout_seconds
                )
                self._record("request_seconds", time.perf_counter() - started)
                usage = response.get("usageMetadata", {})
                if isinstance(usage, Mapping):
                    self._record("input_tokens", int(usage.get("promptTokenCount", 0)))
                    self._record(
                        "output_tokens",
                        int(usage.get("candidatesTokenCount", 0)),
                    )
                candidates = response.get("candidates", [])
                grounding = response.get("groundingMetadata", {})
                if not grounding and isinstance(candidates, list) and candidates:
                    first = candidates[0]
                    if isinstance(first, Mapping):
                        grounding = first.get("groundingMetadata", {})
                if isinstance(grounding, Mapping):
                    queries = grounding.get("webSearchQueries", [])
                    if isinstance(queries, list):
                        self._record("grounding_queries", len(queries))
                return response
            except GeminiApiError as exc:
                self._record("request_seconds", time.perf_counter() - started)
                retryable = exc.status == 429 or 500 <= exc.status <= 599
                if not retryable or attempt >= self.max_retries:
                    raise TranslationError(
                        f"Falha na API Gemini (HTTP {exc.status}); "
                        "nenhum resultado foi aceito para este lote."
                    ) from None
                delay = exc.retry_after
                if delay is None or delay <= 0:
                    delay = min(2**attempt, 8)
                self._record("retries", 1)
                self._sleeper(delay)
        raise TranslationError("Gemini excedeu o limite de tentativas.")

    def _parse_response(
        self,
        response: Mapping[str, Any],
        batch: Sequence[TranslationUnit],
    ) -> list[str]:
        candidates = response.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise TranslationError("Gemini não retornou candidato de tradução.")
        candidate = candidates[0]
        if not isinstance(candidate, Mapping):
            raise TranslationError("Gemini retornou candidato inválido.")
        if candidate.get("finishReason") not in {None, "STOP"}:
            raise TranslationError(
                "Gemini interrompeu a geração antes de concluir o lote "
                f"({candidate.get('finishReason')})."
            )
        content = candidate.get("content")
        if not isinstance(content, Mapping):
            raise TranslationError("Gemini retornou conteúdo estruturado inválido.")
        parts = content.get("parts", [])
        if not isinstance(parts, list):
            raise TranslationError("Gemini retornou conteúdo estruturado inválido.")
        text_parts = [
            part.get("text", "") for part in parts if isinstance(part, Mapping)
        ]
        raw = "".join(text_parts).strip()
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            raise TranslationError("Gemini não respeitou o JSON estruturado.") from None
        items = decoded.get("translations") if isinstance(decoded, Mapping) else None
        if not isinstance(items, list) or len(items) != len(batch):
            raise TranslationError(
                "Gemini não manteve a quantidade de cues do lote "
                f"({len(items) if isinstance(items, list) else 0} para {len(batch)})."
            )
        expected = [unit.index for unit in batch]
        actual: list[int] = []
        outputs: list[str] = []
        for item in items:
            if not isinstance(item, Mapping):
                raise TranslationError("Gemini retornou uma cue em formato inválido.")
            cue_id = item.get("cue_id")
            translated = item.get("text")
            if not isinstance(cue_id, int) or isinstance(cue_id, bool):
                raise TranslationError("Gemini retornou cue_id inválido.")
            if not isinstance(translated, str):
                raise TranslationError(f"Tradução inválida para a cue {cue_id}.")
            actual.append(cue_id)
            outputs.append(" ".join(translated.split()))
        if actual != expected:
            raise TranslationError(
                "Gemini alterou, duplicou ou reordenou os IDs das cues; "
                "o lote foi rejeitado."
            )
        empty = [
            cue_id for cue_id, text in zip(actual, outputs, strict=True) if not text
        ]
        if empty:
            raise TranslationError(
                "Gemini retornou texto vazio para as cues: "
                + ", ".join(map(str, empty))
                + "."
            )
        return outputs

    @staticmethod
    def _check_cancelled(token: CancellationToken | None) -> None:
        if token is not None:
            token.raise_if_cancelled()
