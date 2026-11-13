"""Adaptador TranslateGemma com lotes JSON compactos e GBNF no llama.cpp.

O texto mantém o contrato de chat_template_kwargs do parser especializado
TranslateGemma do llama.cpp. IDs locais numéricos preservam o vínculo cue↔texto;
a gramática GBNF restringe a estrutura da resposta sem marcadores artificiais.
Respostas incompletas são validadas e recuperadas com limite por lote.
"""

from __future__ import annotations

import json
import math
import threading
import time
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from legendar.application.pipeline.translation import (
    TranslationResult,
    TranslationUnit,
)
from legendar.application.ports.protocols import CancellationToken, ProgressSink
from legendar.domain.errors.catalog import (
    TranslationError,
    UnsupportedLanguageError,
)
from legendar.domain.value_objects.language import Language
from legendar.infrastructure.translation.llama_runtime import (
    DEFAULT_CONTEXT_SIZE,
    DEFAULT_MODEL_ALIAS,
    LlamaCppRuntimeManager,
)

_REQUEST_TIMEOUT_SECONDS = 600.0
_MAX_OUTPUT_TOKENS = 1024
_MIN_OUTPUT_TOKENS = 128
_CONTEXT_MARGIN_TOKENS = 64
_MAX_BATCH_UNITS = 32
_MAX_BATCH_CHARS = 8_000
_MAX_RECOVERY_SPLIT_DEPTH = 3
_LANGUAGE_CODES = {
    Language.ENGLISH: "en",
    Language.PORTUGUESE: "pt-BR",
}

Requester = Callable[[str, dict[str, object], float], dict[str, object]]
TokenCounter = Callable[[str, dict[str, object], float], int]


class _RecoverableBatchError(Exception):
    """Resposta estruturada incompleta ou inválida, recuperável por subdivisão."""

    def __init__(self, category: str, message: str) -> None:
        self.category = category
        super().__init__(message)


class _ProgressSlice:
    """Mapeia uma subetapa para faixa monotônica do progresso total."""

    def __init__(self, sink: ProgressSink, start: float, end: float) -> None:
        self._sink = sink
        self._start = start
        self._span = end - start

    def report(self, fraction: float, message: str = "") -> None:
        bounded = min(1.0, max(0.0, fraction))
        self._sink.report(self._start + self._span * bounded, message)


def _post_json(
    base_url: str,
    endpoint: str,
    payload: dict[str, object],
    timeout: float,
) -> dict[str, object]:
    """Executa uma chamada local sem registrar conteúdo das legendas."""
    request = Request(
        f"{base_url.rstrip('/')}{endpoint}",
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


def _chat_completion(
    base_url: str,
    payload: dict[str, object],
    timeout: float,
) -> dict[str, object]:
    return _post_json(base_url, "/v1/chat/completions", payload, timeout)


def _count_prompt_tokens(
    base_url: str,
    payload: dict[str, object],
    timeout: float,
) -> int:
    """Conta o prompt renderizado pelo chat template real do llama.cpp."""
    result = _post_json(
        base_url,
        "/v1/chat/completions/input_tokens",
        payload,
        min(timeout, 30.0),
    )
    count = result.get("input_tokens")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise TranslationError(
            "O llama.cpp não devolveu uma contagem válida de tokens do prompt."
        )
    return count


def _batch_keys(size: int) -> tuple[str, ...]:
    return tuple(str(position) for position in range(1, size + 1))


def _rule_suffix(index: int) -> str:
    """Converte índice em identificador GBNF formado somente por letras."""
    letters = "abcdefghijklmnopqrstuvwxyz"
    result = ""
    value = index + 1
    while value:
        value, remainder = divmod(value - 1, len(letters))
        result = letters[remainder] + result
    return result


def _json_grammar(keys: tuple[str, ...]) -> str:
    """Restringe a saída a JSON com chaves fixas e strings não vazias.

    O parser especializado TranslateGemma do llama.cpp b12321 não transfere
    response_format/json_schema para o sampler. O parâmetro GBNF direto é
    aplicado pelo servidor e mantém os IDs sem depender de marcadores no texto.
    """
    entry_names = [f'entry{_rule_suffix(index)}' for index in range(len(keys))]
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
            'char ::= [^"\\\\\\x7F\\x00-\\x1F] | '
            '[\\\\] (["\\\\bfnrt] | "u" [0-9a-fA-F]{4})',
            'ws ::= [ \\t\\n]*',
        )
    )


def _build_batch_payload(
    batch: tuple[TranslationUnit, ...],
    *,
    model: str,
    source_code: str,
    target_code: str,
) -> tuple[dict[str, object], tuple[str, ...]]:
    """Cria entrada compacta e schema de saída com IDs locais determinísticos."""
    keys = _batch_keys(len(batch))
    cues = {
        key: unit.text.strip()
        for key, unit in zip(keys, batch, strict=True)
    }
    source_document = {
        "context_before": list(batch[0].context.before[-2:]),
        "cues": cues,
        "context_after": list(batch[-1].context.after[:2]),
    }
    input_json = json.dumps(
        source_document,
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
    payload: dict[str, object] = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "chat_template_kwargs": {
            "source_lang_code": source_code,
            "target_lang_code": target_code,
        },
        "grammar": _json_grammar(keys),
        "temperature": 0.0,
        "stream": False,
    }
    return payload, keys


def _parse_batch_output(
    raw_text: str,
    keys: tuple[str, ...],
) -> tuple[str, ...]:
    """Valida cardinalidade, chaves, tipos e conteúdo sem confiar na ordem JSON."""
    try:
        decoded = json.loads(raw_text)
    except json.JSONDecodeError:
        raise _RecoverableBatchError(
            "invalid_json",
            "TranslateGemma não devolveu JSON válido.",
        ) from None
    if not isinstance(decoded, dict):
        raise _RecoverableBatchError(
            "invalid_shape",
            "TranslateGemma não devolveu um objeto JSON.",
        )
    if set(decoded) != set(keys):
        raise _RecoverableBatchError(
            "invalid_ids",
            "TranslateGemma não preservou todos os IDs do lote.",
        )
    values: list[str] = []
    for key in keys:
        value = decoded.get(key)
        if not isinstance(value, str) or not value.strip():
            raise _RecoverableBatchError(
                "empty_value",
                "TranslateGemma devolveu uma tradução vazia.",
            )
        values.append(" ".join(value.split()))
    return tuple(values)


def _response_content(response: dict[str, object]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise _RecoverableBatchError(
            "invalid_choice",
            "Resposta TranslateGemma sem escolha única.",
        )
    choice = choices[0]
    if not isinstance(choice, dict):
        raise _RecoverableBatchError(
            "invalid_choice",
            "Escolha TranslateGemma em formato inválido.",
        )
    finish_reason = choice.get("finish_reason")
    if finish_reason not in {None, "stop"}:
        category = "truncated" if finish_reason == "length" else "finish_reason"
        raise _RecoverableBatchError(
            category,
            f"TranslateGemma encerrou a geração ({finish_reason}).",
        )
    message = choice.get("message")
    text = message.get("content") if isinstance(message, dict) else None
    if not isinstance(text, str) or not text.strip():
        raise _RecoverableBatchError(
            "empty_response",
            "TranslateGemma retornou uma resposta vazia.",
        )
    return text.strip()


class TranslateGemmaTranslator:
    """Porta Translator com batching JSON, orçamento exato e recuperação limitada."""

    def __init__(
        self,
        runtime: LlamaCppRuntimeManager,
        *,
        model: str = DEFAULT_MODEL_ALIAS,
        timeout_seconds: float = _REQUEST_TIMEOUT_SECONDS,
        requester: Requester = _chat_completion,
        token_counter: TokenCounter = _count_prompt_tokens,
    ) -> None:
        if not model.strip():
            raise ValueError("Alias do modelo TranslateGemma não pode ser vazio.")
        if timeout_seconds <= 0:
            raise ValueError("Timeout TranslateGemma deve ser positivo.")
        self.runtime = runtime
        self.model = model.strip()
        self.timeout_seconds = timeout_seconds
        self._requester = requester
        self._token_counter = token_counter
        self._metrics_lock = threading.Lock()
        self._metrics: dict[str, int | float] = {
            "prompt_count_calls": 0,
            "prompt_count_seconds": 0.0,
            "prompt_tokens": 0,
            "generation_calls": 0,
            "generation_seconds": 0.0,
            "generation_prompt_tokens": 0,
            "generated_tokens": 0,
            "accepted_batches": 0,
            "translated_units": 0,
            "largest_batch_units": 0,
            "max_output_tokens": 0,
            "response_failures": 0,
            "split_batches": 0,
            "context_budget_splits": 0,
            "response_failure_invalid_json": 0,
            "response_failure_invalid_shape": 0,
            "response_failure_invalid_ids": 0,
            "response_failure_empty_value": 0,
            "response_failure_invalid_choice": 0,
            "response_failure_truncated": 0,
            "response_failure_finish_reason": 0,
            "response_failure_empty_response": 0,
        }

    @property
    def batch_size(self) -> int:
        return _MAX_BATCH_UNITS

    def performance_snapshot(self) -> dict[str, Any]:
        """Métricas de tradução sem texto, prompt, resposta ou credenciais."""
        with self._metrics_lock:
            counters = dict(self._metrics)
        context_size = int(
            getattr(self.runtime, "context_size", DEFAULT_CONTEXT_SIZE)
        )
        return {
            "configuration": {
                "adapter": "translategemma-llama.cpp",
                "model": self.model,
                "batch_size": _MAX_BATCH_UNITS,
                "batch_char_limit": _MAX_BATCH_CHARS,
                "context_size": context_size,
                "max_output_tokens": _MAX_OUTPUT_TOKENS,
                "context_margin_tokens": _CONTEXT_MARGIN_TOKENS,
                "recovery_split_depth": _MAX_RECOVERY_SPLIT_DEPTH,
                "structured_output": "gbnf_json",
                "content_format": "plain_text_with_chat_template_kwargs",
                "timeout_seconds": self.timeout_seconds,
                "threads": getattr(self.runtime, "threads", None),
            },
            "counters": counters,
        }

    def _record(self, name: str, value: int | float) -> None:
        with self._metrics_lock:
            self._metrics[name] = self._metrics.get(name, 0) + value

    def _record_max(self, name: str, value: int) -> None:
        with self._metrics_lock:
            self._metrics[name] = max(int(self._metrics.get(name, 0)), value)

    @staticmethod
    def _estimate_output_tokens(batch: tuple[TranslationUnit, ...]) -> int:
        """Reserva saída para texto traduzido e estrutura JSON compacta.

        A contagem de entrada é exata no llama.cpp. A reserva de saída usa uma
        estimativa conservadora baseada no texto-fonte e no número de chaves.
        Lotes cuja estimativa exceda 1.024 tokens são subdivididos antes da
        geração; uma unidade isolada acima do teto falha sem truncamento.
        """
        source_chars = sum(len(unit.text) for unit in batch)
        estimate = math.ceil(source_chars / 2.5) + 8 * len(batch) + 48
        return max(_MIN_OUTPUT_TOKENS, estimate)

    def _count_tokens(
        self,
        base_url: str,
        payload: dict[str, object],
    ) -> int:
        started = time.perf_counter()
        self._record("prompt_count_calls", 1)
        try:
            count = self._token_counter(
                base_url,
                payload,
                min(self.timeout_seconds, 30.0),
            )
        finally:
            self._record(
                "prompt_count_seconds",
                time.perf_counter() - started,
            )
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise TranslationError(
                "Contagem de tokens do TranslateGemma retornou valor inválido."
            )
        self._record("prompt_tokens", count)
        return count

    @staticmethod
    def _check_cancelled(token: CancellationToken | None) -> None:
        if token is not None:
            token.raise_if_cancelled()

    def translate(
        self,
        units: tuple[TranslationUnit, ...],
        *,
        source_language: Language,
        target_language: Language,
        progress: ProgressSink,
        token: CancellationToken | None = None,
    ) -> TranslationResult:
        if (
            source_language not in _LANGUAGE_CODES
            or target_language not in _LANGUAGE_CODES
        ):
            raise UnsupportedLanguageError(
                "TranslateGemma suporta somente PT-BR e inglês neste produto."
            )
        if source_language is target_language:
            raise UnsupportedLanguageError(
                "O idioma de origem e destino do TranslateGemma devem ser diferentes."
            )
        if not units:
            raise TranslationError("Nenhuma unidade foi enviada ao TranslateGemma.")
        indexes = tuple(unit.index for unit in units)
        if len(set(indexes)) != len(indexes):
            raise TranslationError("TranslateGemma recebeu IDs de unidade duplicados.")
        if any(not unit.text.strip() for unit in units):
            raise TranslationError(
                "TranslateGemma recebeu uma unidade de origem vazia."
            )

        source_code = _LANGUAGE_CODES[source_language]
        target_code = _LANGUAGE_CODES[target_language]
        self.runtime.ensure_runtime(
            consent=self.runtime.runtime_download_authorized,
            token=token,
            progress=_ProgressSlice(progress, 0.0, 0.15),
        )
        self.runtime.ensure_model(
            token=token,
            progress=_ProgressSlice(progress, 0.15, 0.75),
        )
        base_url = self.runtime.ensure_running(
            token=token,
            progress=_ProgressSlice(progress, 0.75, 0.9),
        )

        context_size = int(
            getattr(self.runtime, "context_size", DEFAULT_CONTEXT_SIZE)
        )
        if context_size < _MIN_OUTPUT_TOKENS + _CONTEXT_MARGIN_TOKENS + 1:
            raise TranslationError(
                "O contexto configurado para TranslateGemma é insuficiente."
            )

        translated_by_index: dict[int, str] = {}
        completed_units = 0
        generation_calls = 0
        accepted_batches = 0
        split_batches = 0
        total = len(units)

        def recover(
            batch: tuple[TranslationUnit, ...],
            *,
            recovery_depth: int = 0,
        ) -> None:
            nonlocal completed_units, generation_calls, accepted_batches
            nonlocal split_batches
            self._check_cancelled(token)

            payload, keys = _build_batch_payload(
                batch,
                model=self.model,
                source_code=source_code,
                target_code=target_code,
            )
            progress.report(
                0.9 + 0.1 * completed_units / total,
                "TranslateGemma · preparando lote de "
                f"{len(batch)} unidades · contando tokens",
            )
            prompt_tokens = self._count_tokens(base_url, payload)
            output_tokens = self._estimate_output_tokens(batch)
            if (
                output_tokens > _MAX_OUTPUT_TOKENS
                or prompt_tokens + output_tokens + _CONTEXT_MARGIN_TOKENS > context_size
            ):
                if len(batch) == 1:
                    raise TranslationError(
                        "A unidade de tradução "
                        f"{batch[0].index} excede a capacidade de saída/contexto "
                        f"do TranslateGemma ({context_size} tokens de contexto, "
                        f"teto de {_MAX_OUTPUT_TOKENS} tokens de saída); "
                        "nenhuma entrada foi truncada."
                    )
                self._record("context_budget_splits", 1)
                split_batches += 1
                middle = len(batch) // 2
                recover(batch[:middle])
                recover(batch[middle:])
                return

            payload["max_tokens"] = output_tokens
            self._record_max("largest_batch_units", len(batch))
            self._record_max("max_output_tokens", output_tokens)
            generation_calls += 1
            self._record("generation_calls", 1)
            progress.report(
                0.9 + 0.1 * completed_units / total,
                "TranslateGemma · gerando lote de "
                f"{len(batch)} unidades · {generation_calls} chamadas",
            )
            generation_started = time.perf_counter()
            try:
                response = self._requester(
                    base_url,
                    payload,
                    self.timeout_seconds,
                )
            finally:
                generation_seconds = time.perf_counter() - generation_started
                self._record("generation_seconds", generation_seconds)

            timings = response.get("timings")
            if isinstance(timings, dict):
                prompt_n = timings.get("prompt_n")
                predicted_n = timings.get("predicted_n")
                if isinstance(prompt_n, int) and not isinstance(prompt_n, bool):
                    self._record("generation_prompt_tokens", prompt_n)
                if isinstance(predicted_n, int) and not isinstance(predicted_n, bool):
                    self._record("generated_tokens", predicted_n)

            try:
                raw_text = _response_content(response)
                values = _parse_batch_output(raw_text, keys)
            except _RecoverableBatchError as exc:
                self._record("response_failures", 1)
                self._record(f"response_failure_{exc.category}", 1)
                if len(batch) > 1 and recovery_depth < _MAX_RECOVERY_SPLIT_DEPTH:
                    self._record("split_batches", 1)
                    split_batches += 1
                    middle = len(batch) // 2
                    recover(batch[:middle], recovery_depth=recovery_depth + 1)
                    recover(batch[middle:], recovery_depth=recovery_depth + 1)
                    return
                raise TranslationError(
                    "TranslateGemma não conseguiu validar um lote de "
                    f"{len(batch)} unidades ({exc.category}). "
                    "A tradução foi interrompida sem publicar resultado parcial."
                ) from None

            if len(values) != len(batch):
                raise TranslationError(
                    "TranslateGemma não preservou a cardinalidade do lote."
                )
            for unit, value in zip(batch, values, strict=True):
                translated_by_index[unit.index] = value

            completed_units += len(batch)
            accepted_batches += 1
            self._record("accepted_batches", 1)
            self._record("translated_units", len(batch))
            progress.report(
                0.9 + 0.1 * completed_units / total,
                "TranslateGemma · "
                f"{completed_units}/{total} unidades · "
                f"{accepted_batches} lotes aceitos · "
                f"{generation_calls} gerações · "
                f"{split_batches} subdivisões",
            )

        for group in self._groups(units):
            recover(group)

        if set(translated_by_index) != set(indexes):
            raise TranslationError(
                "TranslateGemma não concluiu todas as unidades esperadas."
            )

        return TranslationResult(
            language=target_language,
            texts=tuple(translated_by_index[index] for index in indexes),
            unit_indexes=indexes,
        )

    @staticmethod
    def _groups(units: tuple[TranslationUnit, ...]):
        """Agrupa em ordem, respeitando teto inicial de itens e caracteres."""
        batch: list[TranslationUnit] = []
        char_count = 0
        for unit in units:
            item_chars = len(unit.text) + 16
            if batch and (
                len(batch) >= _MAX_BATCH_UNITS
                or char_count + item_chars > _MAX_BATCH_CHARS
            ):
                yield tuple(batch)
                batch = []
                char_count = 0
            batch.append(unit)
            char_count += item_chars
        if batch:
            yield tuple(batch)
