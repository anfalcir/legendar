"""Tradução local PT-BR ↔ EN com NLLB-200 distilled 600M.

Um único checkpoint multilíngue atende os dois sentidos: o código do idioma de
origem é definido no tokenizador e o de destino via ``forced_bos_token_id``.
Os pesos são carregados sob demanda no cache local (``<models>/nllb``) e
reaproveitados entre jobs; nenhum texto sai para a rede.

A porta devolve exatamente um texto por unidade recebida e nunca altera tempos:
o vínculo temporal pertence às cues produzidas pela segmentação.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable, Sequence
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

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
from legendar.infrastructure.diagnostics.performance import (
    collect_torch_thread_settings,
)

MODEL_NAME = "facebook/nllb-200-distilled-600M"
DEFAULT_DEVICE = "auto"
SUPPORTED_DEVICES = frozenset({"auto", "cpu", "cuda"})
#: Códigos de idioma do NLLB para os idiomas de produto.
NLLB_CODES: dict[Language, str] = {
    Language.PORTUGUESE: "por_Latn",
    Language.ENGLISH: "eng_Latn",
}
#: Unidades por lote: memória estável e ponto de cancelamento a cada lote.
MAX_UNITS_PER_BATCH = 16
MAX_INPUT_TOKENS = 256
MAX_NEW_TOKENS = 256
NUM_BEAMS = 4

TokenizerLoader = Callable[[str, Path], Any]
ModelLoader = Callable[[str, str, Path], Any]
BatchTranslator = Callable[..., Sequence[str]]
DeviceResolver = Callable[[str], str]
VersionProvider = Callable[[], str]


def _package_version() -> str:
    try:
        return version("transformers")
    except PackageNotFoundError:
        return "unknown"


def _import_transformers() -> Any:
    try:
        import transformers
    except ImportError as exc:
        raise ModelError(
            "transformers não está instalado para a tradução local. "
            "Sincronize o perfil runtime-cpu ou runtime-cu128."
        ) from exc
    return transformers


def _import_torch() -> Any:
    try:
        import torch
    except ImportError as exc:
        raise ModelError(
            "PyTorch não está instalado para a tradução NLLB. "
            "Sincronize o perfil runtime-cpu ou runtime-cu128."
        ) from exc
    return torch


def _resolve_device(requested: str) -> str:
    """Tradução usa CPU ou CUDA; MPS não é assumido compatível."""
    torch = _import_torch()
    if requested == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    if requested == "cuda" and not torch.cuda.is_available():
        raise ModelError(
            "CUDA foi solicitada para a tradução, mas não está disponível. "
            "Selecione auto/cpu ou valide o driver NVIDIA."
        )
    return requested


def _load_tokenizer(model_name: str, cache_dir: Path) -> Any:
    """Tokenizador lento: usa SentencePiece direto, sem camada de conversão."""
    transformers = _import_transformers()
    return transformers.AutoTokenizer.from_pretrained(
        model_name,
        cache_dir=str(cache_dir),
        use_fast=False,
    )


def _load_model(model_name: str, device: str, cache_dir: Path) -> Any:
    transformers = _import_transformers()
    _import_torch()
    model = transformers.AutoModelForSeq2SeqLM.from_pretrained(
        model_name,
        cache_dir=str(cache_dir),
    )
    model.to(device)
    model.eval()
    return model


def _model_device(model: Any) -> str:
    device = getattr(model, "device", None)
    return str(device) if device is not None else "cpu"


def _run_nllb_batch(
    texts: Sequence[str],
    tokenizer: Any,
    model: Any,
    *,
    source_code: str,
    target_code: str,
    metrics_callback: Callable[[str, int | float], None] | None = None,
) -> Sequence[str]:
    """Inferência de um lote com token de origem e de destino explícitos."""
    torch = _import_torch()
    tokenizer.src_lang = source_code
    phase_started = time.perf_counter()
    encoded = tokenizer(
        list(texts),
        return_tensors="pt",
        padding=True,
        truncation=False,
    )
    input_ids = encoded.get("input_ids")
    if input_ids is None:
        raise TranslationError("NLLB não retornou IDs tokenizados para a entrada.")
    input_length = int(input_ids.shape[1])
    if input_length > MAX_INPUT_TOKENS:
        raise TranslationError(
            "Uma unidade de tradução excede o limite de "
            f"{MAX_INPUT_TOKENS} tokens do NLLB; nenhuma entrada foi truncada."
        )
    if metrics_callback is not None:
        metrics_callback("tokenization_seconds", time.perf_counter() - phase_started)
        attention_mask = encoded.get("attention_mask")
        input_ids = encoded.get("input_ids")
        if attention_mask is not None:
            metrics_callback("input_tokens", int(attention_mask.sum().item()))
        if input_ids is not None:
            metrics_callback("padded_input_tokens", int(input_ids.numel()))

    device = _model_device(model)
    phase_started = time.perf_counter()
    inputs = {name: value.to(device) for name, value in encoded.items()}
    if metrics_callback is not None:
        metrics_callback("device_transfer_seconds", time.perf_counter() - phase_started)

    bos_token_id = tokenizer.convert_tokens_to_ids(target_code)
    if not isinstance(bos_token_id, int) or bos_token_id < 0:
        raise ModelError(f"Token de idioma NLLB inválido: {target_code!r}")
    input_length = int(inputs["input_ids"].shape[1])
    phase_started = time.perf_counter()
    with torch.inference_mode():
        generated = model.generate(
            **inputs,
            forced_bos_token_id=bos_token_id,
            max_new_tokens=min(MAX_NEW_TOKENS, input_length * 2 + 8),
            num_beams=NUM_BEAMS,
        )
    if metrics_callback is not None:
        metrics_callback("generation_seconds", time.perf_counter() - phase_started)
        metrics_callback("generated_tokens", int(generated.numel()))

    phase_started = time.perf_counter()
    decoded = tuple(tokenizer.batch_decode(generated, skip_special_tokens=True))
    if metrics_callback is not None:
        metrics_callback("batch_decode_seconds", time.perf_counter() - phase_started)
    return decoded


class NllbTranslator:
    """Adaptador ``Translator`` com cache persistente e pesos reutilizados.

    O carregamento é preguiçoso e protegido por lock: jobs simultâneos não
    baixam nem duplicam pesos. A tradução percorre as unidades em lotes, então
    o cancelamento é observado entre lotes além do início e do fim.
    """

    def __init__(
        self,
        models_dir: Path,
        *,
        device: str = DEFAULT_DEVICE,
        model_name: str = MODEL_NAME,
        batch_size: int = MAX_UNITS_PER_BATCH,
        tokenizer_loader: TokenizerLoader = _load_tokenizer,
        model_loader: ModelLoader = _load_model,
        batch_translator: BatchTranslator = _run_nllb_batch,
        device_resolver: DeviceResolver = _resolve_device,
        version_provider: VersionProvider = _package_version,
    ) -> None:
        normalized_device = (device or "").strip().lower()
        if normalized_device not in SUPPORTED_DEVICES:
            raise ValueError(
                f"Dispositivo de tradução inválido: {device!r}. "
                f"Opções: {', '.join(sorted(SUPPORTED_DEVICES))}."
            )
        normalized_model = (model_name or "").strip()
        if not normalized_model:
            raise ValueError("Modelo de tradução inválido: informe um repositório HF.")
        if batch_size < 1:
            raise ValueError("O tamanho do lote de tradução deve ser positivo.")

        self.requested_device = normalized_device
        self.model_name = normalized_model
        self.download_root = Path(models_dir) / "nllb"
        self._batch_size = batch_size
        self._tokenizer_loader = tokenizer_loader
        self._model_loader = model_loader
        self._batch_translator = batch_translator
        self._device_resolver = device_resolver
        self._version_provider = version_provider
        self._lock = threading.Lock()
        self._tokenizer: Any | None = None
        self._model: Any | None = None
        self._device: str | None = None
        self._revision: str | None = None
        self._metrics_lock = threading.Lock()
        self._metrics: dict[str, int | float] = {
            "model_load_attempts": 0,
            "model_load_successes": 0,
            "model_load_seconds": 0.0,
            "batch_calls": 0,
            "batch_units": 0,
            "max_batch_units": 0,
            "batch_inference_seconds": 0.0,
            "tokenization_seconds": 0.0,
            "device_transfer_seconds": 0.0,
            "generation_seconds": 0.0,
            "batch_decode_seconds": 0.0,
            "input_tokens": 0,
            "padded_input_tokens": 0,
            "generated_tokens": 0,
        }

    @classmethod
    def from_environment(cls, models_dir: Path) -> NllbTranslator:
        return cls(
            models_dir=models_dir,
            device=os.environ.get("LEGENDAR_TRANSLATE_DEVICE", DEFAULT_DEVICE),
            model_name=os.environ.get("LEGENDAR_TRANSLATE_MODEL", MODEL_NAME),
        )

    @property
    def loaded_device(self) -> str | None:
        """Dispositivo efetivo; ``None`` enquanto os pesos não foram carregados."""
        return self._device

    @property
    def is_loaded(self) -> bool:
        return self._model is not None and self._tokenizer is not None

    def release_resources(self) -> None:
        """Descarta pesos/tokenizador residentes; o checkpoint em disco permanece."""
        with self._lock:
            model = self._model
            tokenizer = self._tokenizer
            self._model = None
            self._tokenizer = None
            self._device = None
            self._revision = None
        if model is not None:
            from legendar.infrastructure.resources.lifecycle import (
                release_model_resources,
            )

            release_model_resources(model)
        del tokenizer

    @property
    def revision(self) -> str | None:
        """Versão do ``transformers`` usada no último carregamento."""
        return self._revision

    @property
    def batch_size(self) -> int:
        return self._batch_size

    def performance_snapshot(self) -> dict[str, Any]:
        """Snapshot acumulado de inferência, sem textos de entrada/saída."""
        with self._metrics_lock:
            counters = dict(self._metrics)
        return {
            "loaded": self.is_loaded,
            "configuration": {
                "adapter": "nllb-transformers",
                "model": self.model_name,
                "package_version": self._revision or self._version_provider(),
                "requested_device": self.requested_device,
                "loaded_device": self._device,
                "batch_size": self._batch_size,
                "num_beams": NUM_BEAMS,
                "max_input_tokens": MAX_INPUT_TOKENS,
                "max_new_tokens": MAX_NEW_TOKENS,
                "dtype": str(getattr(self._model, "dtype", "unknown"))
                if self._model is not None
                else None,
                **collect_torch_thread_settings(),
            },
            "counters": counters,
        }

    def _record_metric(self, name: str, value: int | float) -> None:
        with self._metrics_lock:
            if name == "max_batch_units":
                self._metrics[name] = max(self._metrics.get(name, 0), value)
            else:
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
        source_code = self._code(source_language, "origem")
        target_code = self._code(target_language, "destino")
        if source_code == target_code:
            raise UnsupportedLanguageError(
                "Origem e destino da tradução usam o mesmo idioma."
            )

        texts = [unit.text for unit in units]
        total = len(texts)
        translated: list[str] = []
        for start in range(0, total, self._batch_size):
            self._check(token)
            batch = texts[start : start + self._batch_size]
            outputs = list(self._translate_batch(batch, source_code, target_code))
            if len(outputs) != len(batch):
                raise TranslationError(
                    f"O tradutor devolveu {len(outputs)} textos para {len(batch)} "
                    "legendas enviadas."
                )
            translated.extend(outputs)
            done = start + len(batch)
            progress.report(done / total, f"Legenda {done}/{total} traduzida")
        self._check(token)

        cleaned = [" ".join((text or "").split()) for text in translated]
        empty = [
            unit.index for unit, text in zip(units, cleaned, strict=True) if not text
        ]
        if empty:
            raise TranslationError(
                "A tradução retornou texto vazio para as legendas: "
                + ", ".join(str(index) for index in empty)
                + "."
            )
        return TranslationResult(
            language=target_language,
            texts=tuple(cleaned),
            unit_indexes=tuple(unit.index for unit in units),
        )

    # -- internos ---------------------------------------------------------

    def _translate_batch(
        self,
        texts: Sequence[str],
        source_code: str,
        target_code: str,
    ) -> Sequence[str]:
        tokenizer, model = self._ensure_model()
        self._record_metric("batch_calls", 1)
        self._record_metric("batch_units", len(texts))
        self._record_metric("max_batch_units", len(texts))
        batch_started = time.perf_counter()
        try:
            if self._batch_translator is _run_nllb_batch:
                return self._batch_translator(
                    texts,
                    tokenizer,
                    model,
                    source_code=source_code,
                    target_code=target_code,
                    metrics_callback=self._record_metric,
                )
            return self._batch_translator(
                texts,
                tokenizer,
                model,
                source_code=source_code,
                target_code=target_code,
            )
        except (ModelError, UnsupportedLanguageError):
            raise
        except Exception as exc:
            raise TranslationError(f"Falha ao traduzir com NLLB: {exc}") from exc
        finally:
            self._record_metric(
                "batch_inference_seconds", time.perf_counter() - batch_started
            )

    def _ensure_model(self) -> tuple[Any, Any]:
        if self._tokenizer is not None and self._model is not None:
            return self._tokenizer, self._model

        with self._lock:
            if self._tokenizer is not None and self._model is not None:
                return self._tokenizer, self._model
            load_started = time.perf_counter()
            self._record_metric("model_load_attempts", 1)
            try:
                device = self._device or self._device_resolver(self.requested_device)
                self.download_root.mkdir(parents=True, exist_ok=True)
                tokenizer = self._tokenizer_loader(self.model_name, self.download_root)
                model = self._model_loader(self.model_name, device, self.download_root)
                revision = self._version_provider()
            except (ModelError, UnsupportedLanguageError):
                raise
            except Exception as exc:
                raise ModelError(
                    f"Não foi possível carregar o modelo de tradução "
                    f"{self.model_name}: {exc}"
                ) from exc
            finally:
                self._record_metric(
                    "model_load_seconds", time.perf_counter() - load_started
                )

            self._record_metric("model_load_successes", 1)
            self._tokenizer = tokenizer
            self._model = model
            self._device = device
            self._revision = revision
            return tokenizer, model

    @staticmethod
    def _code(language: Language, label: str) -> str:
        if not isinstance(language, Language):
            raise UnsupportedLanguageError(f"Idioma de {label} inválido para tradução.")
        code = NLLB_CODES.get(language)
        if code is None:
            raise UnsupportedLanguageError(
                f"Sem modelo de tradução configurado para o idioma de {label}: "
                f"{language.value!r}."
            )
        return code

    @staticmethod
    def _check(token: CancellationToken | None) -> None:
        if token is not None:
            token.raise_if_cancelled()
