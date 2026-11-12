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
DEFAULT_MAX_INPUT_TOKENS = 200_000
DEFAULT_MAX_OUTPUT_TOKENS = 8192
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
obras e universos ficcionais. Não traduza, translitere nem adapte esses
nomes; preserve sua grafia canônica original. Se houver provável erro de
reconhecimento de um nome, use contexto e pesquisa para inferir a grafia
original somente quando houver evidência forte; se houver dúvida, mantenha a
forma da transcrição. Preserve números, datas, siglas, referências, nomes de
usuário e termos específicos do universo.

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
MAX_CONTENT_RETRIES = 2
MAX_SPLIT_DEPTH = 8
SAFETY_FINISH_REASONS = frozenset(
    {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII"}
)


class _GeminiResponseFailure(TranslationError):
    """Falha estruturada que informa se o lote pode ser recuperado com segurança."""

    def __init__(
        self,
        message: str,
        category: str,
        *,
        split: bool = False,
        retry_same: bool = False,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.split = split
        self.retry_same = retry_same


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
        max_input_tokens: int = DEFAULT_MAX_INPUT_TOKENS,
        max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
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
        if max_input_tokens < 4096 or max_input_tokens > 900_000:
            raise ValueError(
                "O orçamento de entrada Gemini deve ficar entre 4096 e 900000 tokens."
            )
        if max_output_tokens < 512 or max_output_tokens > 8192:
            raise ValueError(
                "O teto de saída Gemini deve ficar entre 512 e 8192 tokens."
            )
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
        self.max_input_tokens = max_input_tokens
        self.max_output_tokens = max_output_tokens
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
            "content_retries": 0,
            "split_batches": 0,
            "item_retries": 0,
            "recovered_units": 0,
            "response_failures": 0,
            "estimated_input_tokens": 0,
            "estimated_output_tokens": 0,
            "token_budget_splits": 0,
            "largest_batch_units": 0,
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
            max_input_tokens = int(
                os.environ.get(
                    "LEGENDAR_GEMINI_MAX_INPUT_TOKENS", DEFAULT_MAX_INPUT_TOKENS
                )
            )
            max_output_tokens = int(
                os.environ.get(
                    "LEGENDAR_GEMINI_MAX_OUTPUT_TOKENS", DEFAULT_MAX_OUTPUT_TOKENS
                )
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
            max_input_tokens=max_input_tokens,
            max_output_tokens=max_output_tokens,
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
                "max_input_tokens": self.max_input_tokens,
                "max_output_tokens": self.max_output_tokens,
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

    def _record_max(self, name: str, value: int) -> None:
        with self._metrics_lock:
            self._metrics[name] = max(int(self._metrics.get(name, 0)), value)

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

        if len({unit.index for unit in units}) != len(units):
            raise TranslationError("IDs de cue duplicados na entrada da tradução.")

        translated_by_id: dict[int, str] = {}
        positions = {unit.index: index for index, unit in enumerate(units)}
        total = len(units)
        start = 0
        while start < total:
            self._check_cancelled(token)
            batch = self._select_batch(
                units,
                start=start,
                positions=positions,
                translated_by_id=translated_by_id,
                source_language=source_language,
                target_language=target_language,
            )
            self._translate_batch(
                batch,
                all_units=units,
                positions=positions,
                translated_by_id=translated_by_id,
                source_language=source_language,
                target_language=target_language,
                token=token,
            )
            start += len(batch)
            done = start
            self._record("translated_units", len(batch))
            progress.report(done / total, f"Legenda {done}/{total} traduzida")

        self._check_cancelled(token)
        if len(translated_by_id) != total:
            missing = [
                unit.index for unit in units if unit.index not in translated_by_id
            ]
            raise TranslationError(
                "Gemini não concluiu todas as unidades; IDs pendentes: "
                + ", ".join(map(str, missing))
                + "."
            )
        outputs = tuple(translated_by_id[unit.index] for unit in units)
        if any(not text for text in outputs):
            raise TranslationError("Gemini deixou texto vazio após a recuperação.")
        return TranslationResult(language=target_language, texts=outputs)

    def _select_batch(
        self,
        units: Sequence[TranslationUnit],
        *,
        start: int,
        positions: Mapping[int, int],
        translated_by_id: Mapping[int, str],
        source_language: Language,
        target_language: Language,
    ) -> tuple[TranslationUnit, ...]:
        """Escolhe o maior lote que cabe nos limites de itens e orçamento."""
        selected: tuple[TranslationUnit, ...] = ()
        stop = min(start + self.batch_size, len(units))
        for end in range(start + 1, stop + 1):
            candidate = units[start:end]
            payload = self._prepare_payload(
                candidate,
                all_units=units,
                positions=positions,
                translated_by_id=translated_by_id,
                source_language=source_language,
                target_language=target_language,
            )
            input_estimate, output_reserve = self._estimate_payload_budget(
                payload, candidate
            )
            fits = (
                input_estimate <= self.max_input_tokens
                and output_reserve <= self.max_output_tokens
            )
            if not fits:
                self._record("token_budget_splits", 1)
                if not selected:
                    raise TranslationError(
                        "A cue "
                        f"{candidate[0].index} excede o orçamento de entrada/saída "
                        "configurado para o Gemini."
                    )
                break
            selected = tuple(candidate)
        return selected

    def _prepare_payload(
        self,
        batch: Sequence[TranslationUnit],
        *,
        all_units: Sequence[TranslationUnit],
        positions: Mapping[int, int],
        translated_by_id: Mapping[int, str],
        source_language: Language,
        target_language: Language,
    ) -> dict[str, Any]:
        before, after, translated_context = self._context_for_batch(
            batch, all_units, positions, translated_by_id
        )
        _, output_reserve = self._estimate_output_reserve(batch)
        return self._payload(
            batch,
            before=before,
            after=after,
            translated_context=translated_context,
            source_language=source_language,
            target_language=target_language,
            max_output_tokens=output_reserve,
        )

    def _estimate_payload_budget(
        self,
        payload: Mapping[str, Any],
        batch: Sequence[TranslationUnit],
    ) -> tuple[int, int]:
        """Estima entrada pelo tamanho UTF-8 e reserva saída com margem.

        O tamanho em bytes UTF-8 é usado como limite superior conservador para
        a quantidade de tokens de entrada. Não adiciona uma chamada remota de
        contagem de tokens; o uso real da API continua registrado em usageMetadata.
        """
        serialized = json.dumps(
            payload, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        input_estimate = len(serialized)
        output_reserve = self._estimate_output_reserve(batch)[1]
        return input_estimate, output_reserve

    def _estimate_output_reserve(
        self,
        batch: Sequence[TranslationUnit],
    ) -> tuple[int, int]:
        source_bytes = sum(len(unit.text.encode("utf-8")) for unit in batch)
        estimated = (
            (source_bytes * 3 + 3) // 4
            + 32 * len(batch)
            + 256
        )
        reserve = max(512, estimated)
        return estimated, reserve

    def _payload(
        self,
        batch: Sequence[TranslationUnit],
        *,
        before: Sequence[TranslationUnit],
        after: Sequence[TranslationUnit],
        translated_context: Sequence[tuple[str, str]],
        source_language: Language,
        target_language: Language,
        max_output_tokens: int | None = None,
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
                "maxOutputTokens": max_output_tokens or self.max_output_tokens,
                "responseMimeType": "application/json",
                "responseJsonSchema": _response_schema(),
            },
        }
        if self.model.startswith("gemini-3"):
            payload["generationConfig"]["thinkingConfig"] = {"thinkingLevel": "LOW"}
        if self.grounding:
            payload["tools"] = [{"googleSearch": {}}]
        return payload

    def _translate_batch(
        self,
        batch: Sequence[TranslationUnit],
        *,
        all_units: Sequence[TranslationUnit],
        positions: Mapping[int, int],
        translated_by_id: dict[int, str],
        source_language: Language,
        target_language: Language,
        token: CancellationToken | None,
        content_attempt: int = 0,
        split_depth: int = 0,
    ) -> dict[int, str]:
        """Traduz um lote com staging por ID e recuperação limitada."""
        self._check_cancelled(token)
        self._record_max("largest_batch_units", len(batch))
        payload = self._prepare_payload(
            batch,
            all_units=all_units,
            positions=positions,
            translated_by_id=translated_by_id,
            source_language=source_language,
            target_language=target_language,
        )
        input_estimate, output_reserve = self._estimate_payload_budget(
            payload, batch
        )
        self._record("estimated_input_tokens", input_estimate)
        self._record("estimated_output_tokens", output_reserve)
        response = self._request_with_retry(payload, token=token)

        try:
            valid, invalid_ids = self._parse_response(response, batch)
        except _GeminiResponseFailure as exc:
            self._record("response_failures", 1)
            self._record(f"response_failure_{exc.category}", 1)
            if (
                exc.split
                and len(batch) > 1
                and split_depth < MAX_SPLIT_DEPTH
            ):
                self._record("split_batches", 1)
                midpoint = len(batch) // 2
                left = self._translate_batch(
                    batch[:midpoint],
                    all_units=all_units,
                    positions=positions,
                    translated_by_id=translated_by_id,
                    source_language=source_language,
                    target_language=target_language,
                    token=token,
                    split_depth=split_depth + 1,
                )
                translated_by_id.update(left)
                right = self._translate_batch(
                    batch[midpoint:],
                    all_units=all_units,
                    positions=positions,
                    translated_by_id=translated_by_id,
                    source_language=source_language,
                    target_language=target_language,
                    token=token,
                    split_depth=split_depth + 1,
                )
                translated_by_id.update(right)
                return {**left, **right}

            if exc.retry_same and content_attempt < MAX_CONTENT_RETRIES:
                self._record("content_retries", 1)
                self._record("retries", 1)
                self._sleep_before_retry(min(2**content_attempt, 4), token=token)
                return self._translate_batch(
                    batch,
                    all_units=all_units,
                    positions=positions,
                    translated_by_id=translated_by_id,
                    source_language=source_language,
                    target_language=target_language,
                    token=token,
                    content_attempt=content_attempt + 1,
                    split_depth=split_depth,
                )
            raise TranslationError(
                f"Falha de conteúdo Gemini ({exc.category}): {exc} "
                "Nenhum resultado parcial será publicado."
            ) from None

        translated_by_id.update(valid)
        if invalid_ids:
            self._record("response_failure_item_empty_or_missing", len(invalid_ids))
            if not valid and content_attempt < MAX_CONTENT_RETRIES:
                self._record("content_retries", 1)
                self._record("retries", 1)
                self._sleep_before_retry(min(2**content_attempt, 4), token=token)
                return self._translate_batch(
                    batch,
                    all_units=all_units,
                    positions=positions,
                    translated_by_id=translated_by_id,
                    source_language=source_language,
                    target_language=target_language,
                    token=token,
                    content_attempt=content_attempt + 1,
                    split_depth=split_depth,
                )

            if len(batch) == 1:
                self._record("failed_units", len(invalid_ids))
                raise TranslationError(
                    "Gemini não recuperou texto vazio ou ausente para as cues: "
                    + ", ".join(map(str, invalid_ids))
                    + ". Nenhum resultado parcial será publicado."
                )

            recovered: dict[int, str] = {}
            for cue_id in invalid_ids:
                self._check_cancelled(token)
                unit = next(unit for unit in batch if unit.index == cue_id)
                self._record("item_retries", 1)
                result = self._translate_batch(
                    (unit,),
                    all_units=all_units,
                    positions=positions,
                    translated_by_id=translated_by_id,
                    source_language=source_language,
                    target_language=target_language,
                    token=token,
                )
                translated_by_id.update(result)
                recovered.update(result)
                self._record("recovered_units", 1)
            valid.update(recovered)

        expected = [unit.index for unit in batch]
        missing = [cue_id for cue_id in expected if cue_id not in valid]
        if missing:
            self._record("failed_units", len(missing))
            raise TranslationError(
                "Gemini não recuperou todas as cues; IDs pendentes: "
                + ", ".join(map(str, missing))
                + ". Nenhum resultado parcial será publicado."
            )
        self._record("batches", 1)
        return {cue_id: valid[cue_id] for cue_id in expected}

    @staticmethod
    def _context_for_batch(
        batch: Sequence[TranslationUnit],
        all_units: Sequence[TranslationUnit],
        positions: Mapping[int, int],
        translated_by_id: Mapping[int, str],
    ) -> tuple[
        Sequence[TranslationUnit],
        Sequence[TranslationUnit],
        Sequence[tuple[str, str]],
    ]:
        first = positions[batch[0].index]
        last = positions[batch[-1].index]
        before = all_units[max(0, first - 2) : first]
        after = all_units[last + 1 : last + 3]
        translated_context = [
            (unit.text, translated_by_id[unit.index])
            for unit in all_units[:first]
            if unit.index in translated_by_id
        ][-12:]
        return before, after, translated_context

    def _request_with_retry(
        self,
        payload: Mapping[str, Any],
        *,
        token: CancellationToken | None = None,
    ) -> Mapping[str, Any]:
        assert self.api_key is not None
        for attempt in range(self.max_retries + 1):
            self._check_cancelled(token)
            started = time.perf_counter()
            try:
                self._record("requests", 1)
                response = self._requester(
                    self.model, payload, self.api_key, self.timeout_seconds
                )
                self._record("request_seconds", time.perf_counter() - started)
                self._check_cancelled(token)
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
                self._check_cancelled(token)
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
                self._sleep_before_retry(delay, token=token)
        raise TranslationError("Gemini excedeu o limite de tentativas.")

    def _sleep_before_retry(
        self,
        delay: float,
        *,
        token: CancellationToken | None,
    ) -> None:
        if token is None:
            self._sleeper(delay)
            return
        deadline = time.monotonic() + delay
        while True:
            self._check_cancelled(token)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            self._sleeper(min(0.1, remaining))

    def _parse_response(
        self,
        response: Mapping[str, Any],
        batch: Sequence[TranslationUnit],
    ) -> tuple[dict[int, str], list[int]]:
        candidates = response.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise _GeminiResponseFailure(
                "Gemini não retornou candidato de tradução.",
                "candidate_missing",
                retry_same=True,
            )
        candidate = candidates[0]
        if not isinstance(candidate, Mapping):
            raise _GeminiResponseFailure(
                "Gemini retornou candidato inválido.",
                "candidate_invalid",
                split=True,
            )
        finish_reason = candidate.get("finishReason")
        if finish_reason not in {None, "STOP"}:
            if finish_reason in SAFETY_FINISH_REASONS:
                raise _GeminiResponseFailure(
                    "Gemini bloqueou a geração por política de segurança.",
                    "safety_block",
                )
            message = (
                "Gemini interrompeu a geração antes de concluir o lote "
                f"({finish_reason})."
            )
            raise _GeminiResponseFailure(
                message,
                (
                    "output_truncated"
                    if finish_reason == "MAX_TOKENS"
                    else "finish_reason"
                ),
                split=len(batch) > 1,
                retry_same=len(batch) == 1,
            )
        content = candidate.get("content")
        if not isinstance(content, Mapping):
            raise _GeminiResponseFailure(
                "Gemini retornou conteúdo estruturado inválido.",
                "content_missing",
                split=len(batch) > 1,
                retry_same=len(batch) == 1,
            )
        parts = content.get("parts", [])
        if not isinstance(parts, list):
            raise _GeminiResponseFailure(
                "Gemini retornou partes estruturadas inválidas.",
                "parts_invalid",
                split=len(batch) > 1,
                retry_same=len(batch) == 1,
            )
        text_parts = [
            part.get("text", "") for part in parts if isinstance(part, Mapping)
        ]
        raw = "".join(text_parts).strip()
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            raise _GeminiResponseFailure(
                "Gemini não respeitou o JSON estruturado.",
                "invalid_json",
                split=len(batch) > 1,
                retry_same=len(batch) == 1,
            ) from None
        items = decoded.get("translations") if isinstance(decoded, Mapping) else None
        if not isinstance(items, list):
            raise _GeminiResponseFailure(
                "Gemini não retornou uma lista de traduções.",
                "translations_missing",
                split=len(batch) > 1,
                retry_same=len(batch) == 1,
            )

        expected = [unit.index for unit in batch]
        expected_set = set(expected)
        seen: set[int] = set()
        actual: list[int] = []
        valid: dict[int, str] = {}
        invalid: set[int] = set()
        for item in items:
            if not isinstance(item, Mapping):
                raise _GeminiResponseFailure(
                    "Gemini retornou uma cue em formato inválido.",
                    "item_invalid",
                    split=len(batch) > 1,
                    retry_same=len(batch) == 1,
                )
            cue_id = item.get("cue_id")
            if not isinstance(cue_id, int) or isinstance(cue_id, bool):
                raise _GeminiResponseFailure(
                    "Gemini retornou cue_id inválido.",
                    "cue_id_invalid",
                    split=len(batch) > 1,
                    retry_same=len(batch) == 1,
                )
            if cue_id not in expected_set or cue_id in seen:
                raise _GeminiResponseFailure(
                    "Gemini alterou ou duplicou IDs de cues; a resposta foi rejeitada.",
                    "cue_id_mismatch",
                    split=len(batch) > 1,
                )
            seen.add(cue_id)
            actual.append(cue_id)
            translated = item.get("text")
            if not isinstance(translated, str):
                invalid.add(cue_id)
                continue
            normalized = " ".join(translated.split())
            if normalized:
                valid[cue_id] = normalized
            else:
                invalid.add(cue_id)

        expected_returned = [cue_id for cue_id in expected if cue_id in seen]
        if actual != expected_returned:
            raise _GeminiResponseFailure(
                "Gemini reordenou IDs de cues; a resposta foi rejeitada.",
                "cue_order_mismatch",
                split=len(batch) > 1,
            )
        missing = [cue_id for cue_id in expected if cue_id not in seen]
        invalid_ids = [
            cue_id for cue_id in expected if cue_id in invalid or cue_id in missing
        ]
        return valid, invalid_ids

    @staticmethod
    def _check_cancelled(token: CancellationToken | None) -> None:
        if token is not None:
            token.raise_if_cancelled()
