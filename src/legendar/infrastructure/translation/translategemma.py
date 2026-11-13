"""Adaptador local TranslateGemma com batching seguro e recuperação por unidade.

O conteúdo segue no campo de texto do schema especializado TranslateGemma.
Lotes usam marcadores estáveis para preservar o vínculo cue↔resultado; respostas
que alterem, percam ou reordenem marcadores são divididas recursivamente. Cada
sub-lote só é aceito quando os marcadores correspondem exatamente aos esperados.
"""

from __future__ import annotations

import hashlib
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
_MIN_OUTPUT_TOKENS = 128
_CONTEXT_MARGIN_TOKENS = 64
_DEFAULT_CONTEXT_SIZE = 2048
_MAX_BATCH_UNITS = 32
_MAX_BATCH_CHARS = 8_000
_LANGUAGE_CODES = {
    Language.ENGLISH: "en",
    Language.PORTUGUESE: "pt-BR",
}

Requester = Callable[[str, dict[str, object], float], dict[str, object]]
TokenCounter = Callable[[str, dict[str, object], float], int]


class _RecoverableBatchError(Exception):
    """Resposta em lote não preservou uma estrutura verificável."""


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
    """Executa uma chamada local sem registrar o conteúdo da legenda."""
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
    """Conta o prompt já renderizado pelo template oficial do llama.cpp."""
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


def _marker_prefix(units: tuple[TranslationUnit, ...]) -> str:
    seed = "\0".join(f"{unit.index}:{unit.text}" for unit in units)
    before = units[0].context.before[-2:]
    after = units[-1].context.after[:2]
    seed += "\0" + "\0".join((*before, *after))
    counter = 0
    all_source = [unit.text for unit in units] + list(before) + list(after)
    while True:
        digest = hashlib.sha256(f"{seed}:{counter}".encode()).hexdigest()[:10]
        prefix = f"[[LG{digest}_"
        if not any(prefix in text for text in all_source):
            return prefix
        counter += 1


def _build_batch_content(
    units: tuple[TranslationUnit, ...],
) -> tuple[str, tuple[tuple[str, int | None], ...], str]:
    """Serializa contexto e cues com IDs protegidos por marcadores únicos."""
    prefix = _marker_prefix(units)
    entries: list[tuple[str, str, int | None]] = []
    first_context = units[0].context.before[-2:]
    last_context = units[-1].context.after[:2]

    for position, text in enumerate(first_context, start=1):
        if text.strip():
            entries.append(
                (f"{prefix}CTX_PRE_{position:02d}]]", text.strip(), None)
            )

    for unit in units:
        marker = f"{prefix}UNIT_{unit.index:010d}]]"
        entries.append((marker, unit.text.strip(), unit.index))

    for position, text in enumerate(last_context, start=1):
        if text.strip():
            entries.append(
                (f"{prefix}CTX_POST_{position:02d}]]", text.strip(), None)
            )

    content = "\n\n".join(f"{marker}\n{text}" for marker, text, _ in entries)
    specs = tuple((marker, index) for marker, _text, index in entries)
    return content, specs, prefix


def _parse_batch_output(
    raw_text: str,
    marker_specs: tuple[tuple[str, int | None], ...],
    prefix: str,
) -> dict[int, str]:
    """Aceita apenas marcadores únicos, ordenados e com conteúdo não vazio."""
    output = raw_text.strip()
    positions: list[int] = []
    expected_markers = {marker for marker, _ in marker_specs}
    if len(expected_markers) != len(marker_specs):
        raise _RecoverableBatchError("Marcadores duplicados no lote de entrada.")

    for marker, _index in marker_specs:
        if output.count(marker) != 1:
            raise _RecoverableBatchError(
                "TranslateGemma removeu ou duplicou um marcador do lote."
            )
        positions.append(output.find(marker))

    if positions != sorted(positions) or not positions:
        raise _RecoverableBatchError(
            "TranslateGemma alterou a ordem dos marcadores do lote."
        )
    if output[: positions[0]].strip():
        raise _RecoverableBatchError(
            "TranslateGemma acrescentou conteúdo antes do primeiro marcador."
        )

    observed_family = output.count(prefix)
    if observed_family != len(marker_specs):
        raise _RecoverableBatchError(
            "TranslateGemma acrescentou ou alterou marcadores do lote."
        )

    translated: dict[int, str] = {}
    for position, (marker, index) in enumerate(marker_specs):
        start = positions[position] + len(marker)
        end = (
            positions[position + 1]
            if position + 1 < len(positions)
            else len(output)
        )
        value = " ".join(output[start:end].split())
        if not value:
            raise _RecoverableBatchError(
                "TranslateGemma devolveu um item vazio dentro do lote."
            )
        if index is not None:
            translated[index] = value

    expected_indexes = {
        index for _marker, index in marker_specs if index is not None
    }
    if set(translated) != expected_indexes:
        raise _RecoverableBatchError(
            "TranslateGemma não preservou todos os IDs do lote."
        )
    return translated


def _response_content(
    response: dict[str, object],
    *,
    indexes: tuple[int, ...],
) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise _RecoverableBatchError("Resposta TranslateGemma sem escolha única.")
    choice = choices[0]
    if not isinstance(choice, dict):
        raise _RecoverableBatchError("Escolha TranslateGemma em formato inválido.")
    finish_reason = choice.get("finish_reason")
    if finish_reason not in {None, "stop"}:
        raise _RecoverableBatchError(
            f"TranslateGemma encerrou a geração ({finish_reason})."
        )
    message = choice.get("message")
    text = message.get("content") if isinstance(message, dict) else None
    if not isinstance(text, str) or not text.strip():
        raise _RecoverableBatchError(
            f"TranslateGemma retornou texto vazio para as unidades {indexes}."
        )
    return text.strip()


class TranslateGemmaTranslator:
    """Implementa a porta Translator com runtime local gerenciado e batching."""

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

    @staticmethod
    def _groups(units: tuple[TranslationUnit, ...]):
        """Agrupa em ordem, limitando tamanho mesmo antes da contagem exata."""
        batch: list[TranslationUnit] = []
        char_count = 0
        for unit in units:
            item_chars = len(unit.text) + 32
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
            raise TranslationError(
                "TranslateGemma recebeu IDs de unidade duplicados."
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
            getattr(self.runtime, "context_size", _DEFAULT_CONTEXT_SIZE)
        )
        if context_size < _MIN_OUTPUT_TOKENS + _CONTEXT_MARGIN_TOKENS + 1:
            raise TranslationError(
                "O contexto configurado para TranslateGemma é insuficiente."
            )

        translated_by_index: dict[int, str] = {}
        completed_units = 0
        generation_requests = 0
        total = len(units)

        def check_cancelled() -> None:
            if token is not None:
                token.raise_if_cancelled()

        def recover(batch: tuple[TranslationUnit, ...]) -> dict[int, str]:
            if len(batch) <= 1:
                raise TranslationError(
                    "TranslateGemma não conseguiu devolver uma tradução íntegra "
                    f"para a unidade {batch[0].index}."
                )
            middle = len(batch) // 2
            left = recover_batch(batch[:middle])
            right = recover_batch(batch[middle:])
            left.update(right)
            return left

        def recover_batch(
            batch: tuple[TranslationUnit, ...],
        ) -> dict[int, str]:
            nonlocal completed_units, generation_requests
            check_cancelled()
            batch_indexes = tuple(unit.index for unit in batch)

            if len(batch) == 1:
                content = batch[0].text.strip()
                payload: dict[str, object] = {
                    "model": self.model,
                    "messages": [{"role": "user", "content": content}],
                    "chat_template_kwargs": {
                        "source_lang_code": source_code,
                        "target_lang_code": target_code,
                    },
                }
                marker_specs: tuple[tuple[str, int | None], ...] = ()
                prefix = ""
            else:
                content, marker_specs, prefix = _build_batch_content(batch)
                payload = {
                    "model": self.model,
                    "messages": [{"role": "user", "content": content}],
                    "chat_template_kwargs": {
                        "source_lang_code": source_code,
                        "target_lang_code": target_code,
                    },
                }

            prompt_tokens = self._token_counter(
                base_url,
                payload,
                min(self.timeout_seconds, 30.0),
            )
            if isinstance(prompt_tokens, bool) or not isinstance(prompt_tokens, int):
                raise TranslationError(
                    "Contagem de tokens do TranslateGemma retornou valor inválido."
                )
            if prompt_tokens < 0:
                raise TranslationError(
                    "Contagem de tokens do TranslateGemma retornou valor negativo."
                )
            max_output_tokens = min(
                _MAX_OUTPUT_TOKENS,
                max(_MIN_OUTPUT_TOKENS, prompt_tokens),
            )
            if (
                prompt_tokens + max_output_tokens + _CONTEXT_MARGIN_TOKENS
                > context_size
            ):
                if len(batch) > 1:
                    return recover(batch)
                raise TranslationError(
                    "A unidade de tradução "
                    f"{batch[0].index} excede o contexto de 2K do TranslateGemma."
                )

            payload.update(
                {
                    "temperature": 0.0,
                    "max_tokens": max_output_tokens,
                    "stream": False,
                }
            )
            check_cancelled()
            generation_requests += 1
            try:
                response = self._requester(
                    base_url,
                    payload,
                    self.timeout_seconds,
                )
                raw_text = _response_content(response, indexes=batch_indexes)
                if len(batch) == 1:
                    values = {
                        batch[0].index: " ".join(raw_text.split())
                    }
                else:
                    values = _parse_batch_output(
                        raw_text,
                        marker_specs,
                        prefix,
                    )
            except _RecoverableBatchError:
                if len(batch) > 1:
                    return recover(batch)
                raise TranslationError(
                    "TranslateGemma retornou uma resposta inválida para a unidade "
                    f"{batch[0].index}."
                ) from None

            if set(values) != set(batch_indexes):
                if len(batch) > 1:
                    return recover(batch)
                raise TranslationError(
                    f"TranslateGemma não devolveu a unidade {batch[0].index}."
                )
            for unit in batch:
                value = values.get(unit.index, "").strip()
                if not value:
                    if len(batch) > 1:
                        return recover(batch)
                    raise TranslationError(
                        f"TranslateGemma retornou texto vazio na unidade {unit.index}."
                    )
                translated_by_index[unit.index] = value

            completed_units += len(batch)
            progress.report(
                0.9 + 0.1 * completed_units / total,
                "TranslateGemma · "
                f"{completed_units}/{total} unidades · "
                f"{generation_requests} chamadas de geração",
            )
            return values

        for group in self._groups(units):
            recover_batch(group)

        if set(translated_by_index) != set(indexes):
            raise TranslationError(
                "TranslateGemma não concluiu todas as unidades esperadas."
            )

        return TranslationResult(
            language=target_language,
            texts=tuple(translated_by_index[index] for index in indexes),
            unit_indexes=indexes,
        )
