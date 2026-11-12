"""Forced alignment local por palavra com WhisperX 3.8.6.

Janelas do Whisper limitam a busca, mas nunca viram timestamps finais. Somente
tempos devolvidos pelo CTC alinhado são promovidos a TranscriptWord.range.
A interpolação automática do WhisperX é desativada para não criar timestamps.
"""

from __future__ import annotations

import contextlib
import math
import os
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from importlib.metadata import PackageNotFoundError, version
from numbers import Real
from pathlib import Path
from typing import Any

from legendar.application.ports.protocols import CancellationToken, ProgressSink
from legendar.domain.entities.media import AudioAsset
from legendar.domain.entities.transcript import (
    AlignmentDiagnostics,
    AlignmentResult,
    Transcript,
    TranscriptSegment,
    TranscriptWord,
)
from legendar.domain.errors.catalog import (
    JobCancelledError,
    ModelError,
    UnsupportedLanguageError,
)
from legendar.domain.value_objects.time import TemporalError, TimelineMapping, TimeRange
from legendar.infrastructure.diagnostics.performance import (
    collect_torch_thread_settings,
)
from legendar.infrastructure.filesystem.paths import ensure_private_directory
from legendar.infrastructure.transcription.whisper import load_pcm_waveform

SUPPORTED_DEVICES = frozenset({"auto", "cpu", "cuda"})
DEFAULT_DEVICE = "auto"
ALIGNMENT_MODELS = {
    "pt": "jonatasgrosman/wav2vec2-large-xlsr-53-portuguese",
    "en": "WAV2VEC2_ASR_BASE_960H",
}
MAX_ALIGNMENT_WINDOW_SECONDS = 90.0
DEFAULT_RECOVERY_PADDING_SECONDS = 0.75

ModelLoader = Callable[[str, str, Path], tuple[Any, Mapping[str, Any]]]
AlignFunction = Callable[..., Mapping[str, Any]]
DeviceResolver = Callable[[str], str]
AudioLoader = Callable[[AudioAsset], Any]
VersionProvider = Callable[[], str]
PunktPreparer = Callable[[str, Path], None]


def _package_version() -> str:
    try:
        return version("whisperx")
    except PackageNotFoundError:
        return "unknown"


def _resolve_device(requested: str) -> str:
    """WhisperX alignment uses CPU or CUDA; MPS is not assumed compatible."""
    try:
        import torch
    except ImportError as exc:
        raise ModelError(
            "PyTorch não está instalado para o WhisperX. "
            "Sincronize o perfil runtime-cpu ou runtime-cu128."
        ) from exc

    if requested == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    if requested == "cuda" and not torch.cuda.is_available():
        raise ModelError(
            "CUDA foi solicitada para o alinhamento, mas não está disponível. "
            "Selecione auto/cpu ou valide o driver NVIDIA."
        )
    return requested


def _load_whisperx_model(
    language_code: str,
    device: str,
    model_dir: Path,
) -> tuple[Any, Mapping[str, Any]]:
    try:
        import whisperx
    except ImportError as exc:
        raise ModelError(
            "WhisperX não está instalado. Instale o perfil runtime-cpu "
            "ou runtime-cu128 do projeto."
        ) from exc

    model_name = ALIGNMENT_MODELS.get(language_code)
    if model_name is None:
        raise UnsupportedLanguageError(
            f"Não há modelo de alinhamento configurado para {language_code!r}."
        )
    return whisperx.load_align_model(
        language_code=language_code,
        device=device,
        model_name=model_name,
        model_dir=str(model_dir),
        model_cache_only=False,
    )


def _run_whisperx_alignment(
    segments: Sequence[Mapping[str, Any]],
    model: Any,
    metadata: Mapping[str, Any],
    waveform: Any,
    device: str,
    *,
    progress_callback: Callable[[float], None] | None = None,
) -> Mapping[str, Any]:
    try:
        import whisperx
    except ImportError as exc:
        raise ModelError("WhisperX não está instalado.") from exc

    return whisperx.align(
        segments,
        model,
        metadata,
        waveform,
        device,
        interpolate_method="ignore",
        return_char_alignments=False,
        print_progress=False,
        progress_callback=progress_callback,
    )


def _ensure_punkt_data(language_code: str, cache_dir: Path) -> None:
    """Instala punkt_tab no cache do produto, não no diretório arbitrário do usuário."""
    punkt_languages = {"pt": "portuguese", "en": "english"}
    punkt_language = punkt_languages.get(language_code)
    if punkt_language is None:
        raise UnsupportedLanguageError(
            f"WhisperX não possui tokenizador Punkt configurado para {language_code!r}."
        )

    try:
        import nltk
    except ImportError as exc:
        raise ModelError("NLTK, exigido pelo WhisperX, não está instalado.") from exc

    cache_dir.mkdir(parents=True, exist_ok=True)
    # O NLTK 3.10 recusa baixar em diretório gravável pelo grupo (umask 002 em
    # várias distribuições). Garantir 0o700 aqui evita a falha que só aparecia
    # no fim do alinhamento, depois de muitos minutos de trabalho.
    ensure_private_directory(cache_dir)
    cache_value = str(cache_dir.resolve())
    if cache_value not in nltk.data.path:
        nltk.data.path.insert(0, cache_value)

    resource = f"tokenizers/punkt_tab/{punkt_language}.pickle"
    try:
        nltk.data.load(resource)
        return
    except LookupError:
        pass

    try:
        downloaded = nltk.download(
            "punkt_tab",
            download_dir=cache_value,
            quiet=True,
        )
    except Exception as exc:
        raise ModelError(
            "Não foi possível preparar o tokenizador de frases do WhisperX. "
            "Verifique a conexão e as permissões do cache de modelos."
        ) from exc
    if not downloaded:
        raise ModelError("O download do recurso punkt_tab do NLTK não foi concluído.")
    try:
        nltk.data.load(resource)
    except LookupError as exc:
        raise ModelError(
            f"O pacote punkt_tab foi baixado, mas o recurso {punkt_language!r} "
            "não está disponível."
        ) from exc
    for archive in cache_dir.glob("tokenizers/punkt_tab*.zip"):
        with contextlib.suppress(OSError):
            archive.unlink()


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _normalized_word(value: str) -> str:
    return " ".join(value.split()).casefold()


def _extract_segment_alignment(
    source_segment: TranscriptSegment,
    result: Mapping[str, Any],
    *,
    waveform_duration: float,
    timeline: TimelineMapping,
    window: TimeRange,
    previous_global_end: float | None,
) -> tuple[
    TranscriptSegment,
    tuple[TranscriptWord, ...],
    tuple[str, ...],
    int,
    float | None,
]:
    """Converte uma resposta WhisperX em palavras, sem preencher lacunas."""
    raw_words = result.get("word_segments")
    if not isinstance(raw_words, (list, tuple)):
        aligned_segments = result.get("segments", [])
        if not isinstance(aligned_segments, (list, tuple)):
            raise ModelError("WhisperX retornou segmentos em formato inválido.")
        raw_words = [
            word
            for item in aligned_segments
            if isinstance(item, Mapping)
            for word in item.get("words", [])
        ]

    expected_words = source_segment.text.split()
    segment_words: list[TranscriptWord] = []
    local_ranges: list[TimeRange] = []
    unmatched_words: list[TranscriptWord] = []
    issues: list[str] = []
    raw_word_cursor = 0
    aligned_word_count = 0
    current_previous_end = previous_global_end

    for expected_text in expected_words:
        matching_index = next(
            (
                candidate_index
                for candidate_index in range(raw_word_cursor, len(raw_words))
                if isinstance(raw_words[candidate_index], Mapping)
                and isinstance(raw_words[candidate_index].get("word"), str)
                and _normalized_word(raw_words[candidate_index]["word"])
                == _normalized_word(expected_text)
            ),
            None,
        )
        if matching_index is None:
            unmatched_words.append(TranscriptWord(text=expected_text))
            segment_words.append(TranscriptWord(text=expected_text))
            issues.append("unmatched_word")
            continue

        if matching_index > raw_word_cursor:
            issues.append("unexpected_aligned_word")
        raw_word_cursor = matching_index + 1
        raw_word = raw_words[matching_index]

        start = _finite_number(raw_word.get("start"))
        end = _finite_number(raw_word.get("end"))
        score = _finite_number(raw_word.get("score"))
        if start is None or end is None:
            unmatched_words.append(TranscriptWord(text=expected_text))
            segment_words.append(TranscriptWord(text=expected_text))
            issues.append("unmatched_word")
            continue
        if start < 0.0 or end > waveform_duration or end <= start:
            unmatched_words.append(TranscriptWord(text=expected_text))
            segment_words.append(TranscriptWord(text=expected_text))
            issues.append("out_of_bounds")
            continue
        if start < window.start - 0.02 or end > window.end + 0.02:
            unmatched_words.append(TranscriptWord(text=expected_text))
            segment_words.append(TranscriptWord(text=expected_text))
            issues.append("out_of_bounds")
            continue
        if score is None or not 0.0 <= score <= 1.0:
            unmatched_words.append(TranscriptWord(text=expected_text))
            segment_words.append(TranscriptWord(text=expected_text))
            issues.append("invalid_word_score")
            continue

        try:
            local_range = TimeRange(start=start, end=end)
            global_range = timeline.range_to_global(local_range)
            word = TranscriptWord(
                text=expected_text,
                range=global_range,
                confidence=score,
            )
        except (TemporalError, ValueError):
            unmatched_words.append(TranscriptWord(text=expected_text))
            segment_words.append(TranscriptWord(text=expected_text))
            issues.append("out_of_bounds")
            continue

        if (
            current_previous_end is not None
            and global_range.start < current_previous_end - 0.05
        ):
            issues.append("overlap")
        current_previous_end = (
            global_range.end
            if current_previous_end is None
            else max(current_previous_end, global_range.end)
        )
        local_ranges.append(global_range)
        segment_words.append(word)
        aligned_word_count += 1

    if raw_word_cursor < len(raw_words):
        issues.append("unexpected_aligned_word")

    segment_range = (
        TimeRange(
            start=min(item.start for item in local_ranges),
            end=max(item.end for item in local_ranges),
        )
        if local_ranges
        else None
    )
    segment = TranscriptSegment(
        text=source_segment.text,
        range=segment_range,
        words=tuple(segment_words),
        confidence=source_segment.confidence,
        alignment_window=window,
    )
    return (
        segment,
        tuple(unmatched_words),
        tuple(dict.fromkeys(issues)),
        aligned_word_count,
        current_previous_end,
    )


class WhisperXAligner:
    """Adaptador Aligner com cache persistente e modelos reutilizados por idioma."""

    def __init__(
        self,
        models_dir: Path,
        *,
        device: str = DEFAULT_DEVICE,
        model_loader: ModelLoader = _load_whisperx_model,
        align_function: AlignFunction = _run_whisperx_alignment,
        device_resolver: DeviceResolver = _resolve_device,
        audio_loader: AudioLoader = load_pcm_waveform,
        version_provider: VersionProvider = _package_version,
        punkt_preparer: PunktPreparer = _ensure_punkt_data,
        max_window_seconds: float = MAX_ALIGNMENT_WINDOW_SECONDS,
        recovery_padding_seconds: float = 0.0,
    ) -> None:
        normalized_device = (device or "").strip().lower()
        if normalized_device not in SUPPORTED_DEVICES:
            raise ValueError(
                f"Dispositivo WhisperX inválido: {device!r}. "
                f"Opções: {', '.join(sorted(SUPPORTED_DEVICES))}."
            )
        if not math.isfinite(max_window_seconds) or max_window_seconds <= 0:
            raise ValueError("O limite de janela de alinhamento deve ser positivo.")
        if not math.isfinite(recovery_padding_seconds) or recovery_padding_seconds < 0:
            raise ValueError("O padding de recuperação deve ser finito e não negativo.")

        self.requested_device = normalized_device
        self.download_root = Path(models_dir).expanduser() / "whisperx-align"
        self._model_loader = model_loader
        self._align_function = align_function
        self._device_resolver = device_resolver
        self._audio_loader = audio_loader
        self._version_provider = version_provider
        self._punkt_preparer = punkt_preparer
        self._max_window_seconds = float(max_window_seconds)
        self._recovery_padding_seconds = float(recovery_padding_seconds)
        self._models: dict[str, tuple[Any, Mapping[str, Any]]] = {}
        self._device: str | None = None
        self._revision: str | None = None
        self._model_lock = threading.Lock()
        self._inference_lock = threading.Lock()
        self._punkt_lock = threading.Lock()
        self._punkt_ready: set[str] = set()
        self._metrics_lock = threading.Lock()
        self._metrics: dict[str, int | float] = {
            "model_load_attempts": 0,
            "model_load_successes": 0,
            "model_load_seconds": 0.0,
            "punkt_preparations": 0,
            "punkt_preparation_seconds": 0.0,
            "waveform_load_seconds": 0.0,
            "alignment_calls": 0,
            "alignment_seconds": 0.0,
            "aligned_words": 0,
            "unmatched_words": 0,
            "input_segments": 0,
            "recovery_attempts": 0,
            "recovery_seconds": 0.0,
            "recovered_words": 0,
        }

    @classmethod
    def from_environment(cls, models_dir: Path) -> WhisperXAligner:
        recovery_padding = os.environ.get(
            "LEGENDAR_ALIGN_RECOVERY_PADDING_SECONDS",
            str(DEFAULT_RECOVERY_PADDING_SECONDS),
        )
        try:
            recovery_padding_seconds = float(recovery_padding)
        except ValueError as exc:
            raise ValueError(
                "LEGENDAR_ALIGN_RECOVERY_PADDING_SECONDS deve ser numérico."
            ) from exc
        return cls(
            models_dir=models_dir,
            device=os.environ.get("LEGENDAR_ALIGN_DEVICE", DEFAULT_DEVICE),
            recovery_padding_seconds=recovery_padding_seconds,
        )

    @property
    def loaded_languages(self) -> tuple[str, ...]:
        return tuple(sorted(self._models))

    def release_resources(self) -> None:
        """Descarta modelos residentes sem apagar o cache em disco."""
        with self._model_lock:
            models = tuple(model for model, _metadata in self._models.values())
            self._models.clear()
            self._device = None
            self._revision = None
        if models:
            from legendar.infrastructure.resources.lifecycle import (
                release_model_resources,
            )

            for model in models:
                release_model_resources(model)

    @property
    def loaded_device(self) -> str | None:
        return self._device

    @property
    def revision(self) -> str | None:
        return self._revision

    def performance_snapshot(self) -> dict[str, Any]:
        """Snapshot acumulado de alinhamento, sem conteúdo de transcrição."""
        with self._metrics_lock:
            counters = dict(self._metrics)
        return {
            "loaded": bool(self._models),
            "configuration": {
                "adapter": "whisperx",
                "package_version": self._revision or self._version_provider(),
                "requested_device": self.requested_device,
                "loaded_device": self._device,
                "loaded_languages": sorted(self._models),
                "alignment_models": dict(ALIGNMENT_MODELS),
                "max_window_seconds": self._max_window_seconds,
                "recovery_padding_seconds": self._recovery_padding_seconds,
                "interpolate_method": "ignore",
                "dtype": "backend_default",
                **collect_torch_thread_settings(),
            },
            "counters": counters,
        }

    def _record_metric(self, name: str, value: int | float) -> None:
        with self._metrics_lock:
            self._metrics[name] = self._metrics.get(name, 0) + value

    def _get_model(self, language_code: str) -> tuple[Any, Mapping[str, Any], str]:
        if language_code in self._models and self._device is not None:
            model, metadata = self._models[language_code]
            return model, metadata, self._device

        with self._model_lock:
            if language_code in self._models and self._device is not None:
                model, metadata = self._models[language_code]
                return model, metadata, self._device

            if language_code not in ALIGNMENT_MODELS:
                raise UnsupportedLanguageError(
                    f"Idioma sem modelo de alinhamento: {language_code!r}."
                )
            load_started = time.perf_counter()
            self._record_metric("model_load_attempts", 1)
            try:
                device = self._device or self._device_resolver(self.requested_device)
                self.download_root.mkdir(parents=True, exist_ok=True)
                model, metadata = self._model_loader(
                    language_code,
                    device,
                    self.download_root,
                )
                revision = self._version_provider()
            except (ModelError, UnsupportedLanguageError):
                raise
            except Exception as exc:
                raise ModelError(
                    f"Não foi possível carregar o modelo WhisperX para "
                    f"{language_code}: {exc}"
                ) from exc
            finally:
                self._record_metric(
                    "model_load_seconds", time.perf_counter() - load_started
                )

            self._record_metric("model_load_successes", 1)
            self._device = device
            self._revision = revision
            self._models[language_code] = (model, metadata)
            return model, metadata, device

    def _prepare_punkt(self, language_code: str) -> None:
        if language_code in self._punkt_ready:
            return
        with self._punkt_lock:
            if language_code in self._punkt_ready:
                return
            preparation_started = time.perf_counter()
            self._record_metric("punkt_preparations", 1)
            try:
                self._punkt_preparer(
                    language_code,
                    self.download_root / "nltk_data",
                )
            except ModelError:
                raise
            except Exception as exc:
                raise ModelError(
                    f"Não foi possível preparar o tokenizador de frases: {exc}"
                ) from exc
            finally:
                self._record_metric(
                    "punkt_preparation_seconds",
                    time.perf_counter() - preparation_started,
                )
            self._punkt_ready.add(language_code)

    def align(
        self,
        audio: AudioAsset,
        transcript: Transcript,
        *,
        progress: ProgressSink,
        token: CancellationToken | None = None,
    ) -> AlignmentResult:
        if token is not None:
            token.raise_if_cancelled()
        if transcript.is_empty:
            raise ModelError("Não há texto para alinhar.")

        waveform_load_started = time.perf_counter()
        try:
            waveform = self._audio_loader(audio)
        except ModelError:
            raise
        except Exception as exc:
            raise ModelError(
                f"Não foi possível carregar o áudio para alinhamento: {exc}"
            ) from exc
        finally:
            self._record_metric(
                "waveform_load_seconds",
                time.perf_counter() - waveform_load_started,
            )

        waveform_size = getattr(waveform, "size", None)
        if waveform_size is None:
            try:
                waveform_size = len(waveform)
            except TypeError as exc:
                raise ModelError(
                    "O waveform do alinhamento possui formato inválido."
                ) from exc
        if waveform_size < 1:
            raise ModelError("O áudio normalizado não contém amostras.")

        waveform_duration = float(waveform_size / 16_000)
        if not math.isfinite(waveform_duration) or waveform_duration <= 0:
            raise ModelError("O áudio de alinhamento possui duração inválida.")
        if abs(waveform_duration - audio.duration_seconds) > 0.25:
            raise ModelError(
                "A duração real do WAV diverge da duração informada pelo AudioAsset "
                f"({waveform_duration:.3f}s versus {audio.duration_seconds:.3f}s)."
            )

        language_code = transcript.language.value
        model_payload: tuple[Any, Mapping[str, Any], str] | None = None
        timeline = TimelineMapping(source_offset=audio.timeline_start_seconds)
        output_segments: list[TranscriptSegment] = []
        unmatched_words: list[TranscriptWord] = []
        issues: list[str] = []
        aligned_word_count = 0
        previous_global_end: float | None = None
        total_segments = len(transcript.segments)

        for segment_index, source_segment in enumerate(transcript.segments):
            if token is not None:
                token.raise_if_cancelled()

            window = source_segment.alignment_window
            if window is None:
                issues.append("missing_alignment_window")
                segment_words = tuple(
                    TranscriptWord(text=item) for item in source_segment.text.split()
                )
                unmatched_words.extend(segment_words)
                output_segments.append(
                    TranscriptSegment(
                        text=source_segment.text,
                        words=segment_words,
                        confidence=source_segment.confidence,
                    )
                )
                progress.report(
                    (segment_index + 1) / total_segments,
                    f"Segmento {segment_index + 1}/{total_segments}: sem janela de busca",
                )
                continue

            if (
                window.end > waveform_duration
                or window.duration > self._max_window_seconds
            ):
                issue = (
                    "out_of_bounds"
                    if window.end > waveform_duration
                    else "window_too_long"
                )
                issues.append(issue)
                segment_words = tuple(
                    TranscriptWord(text=item) for item in source_segment.text.split()
                )
                unmatched_words.extend(segment_words)
                output_segments.append(
                    TranscriptSegment(
                        text=source_segment.text,
                        words=segment_words,
                        confidence=source_segment.confidence,
                        alignment_window=window,
                    )
                )
                progress.report(
                    (segment_index + 1) / total_segments,
                    f"Segmento {segment_index + 1}/{total_segments}: janela inválida",
                )
                continue

            if model_payload is None:
                model_payload = self._get_model(language_code)
                self._prepare_punkt(language_code)
            model, metadata, device = model_payload

            whisper_segment = {
                "start": window.start,
                "end": window.end,
                "text": source_segment.text,
            }

            def on_alignment_progress(
                percent: float,
                *,
                current_segment_index: int = segment_index,
            ) -> None:
                measured = _finite_number(percent)
                fraction = (
                    min(1.0, max(0.0, measured / 100.0))
                    if measured is not None
                    else 0.0
                )
                progress.report(
                    (current_segment_index + fraction) / total_segments,
                    f"Alinhando segmento {current_segment_index + 1}/{total_segments}",
                )

            alignment_started = time.perf_counter()
            self._record_metric("alignment_calls", 1)
            self._record_metric("input_segments", 1)
            try:
                with self._inference_lock:
                    if token is not None:
                        token.raise_if_cancelled()
                    result = self._align_function(
                        [whisper_segment],
                        model,
                        metadata,
                        waveform,
                        device,
                        progress_callback=on_alignment_progress,
                    )
                if token is not None:
                    token.raise_if_cancelled()
            except JobCancelledError:
                raise
            except Exception as exc:
                if token is not None:
                    token.raise_if_cancelled()
                raise ModelError(
                    f"Falha no forced alignment do segmento {segment_index + 1}: {exc}"
                ) from exc
            finally:
                self._record_metric(
                    "alignment_seconds", time.perf_counter() - alignment_started
                )

            if not isinstance(result, Mapping):
                raise ModelError("WhisperX retornou alinhamento em formato inválido.")

            (
                selected_segment,
                selected_unmatched,
                selected_issues,
                selected_aligned_count,
                selected_previous_end,
            ) = _extract_segment_alignment(
                source_segment,
                result,
                waveform_duration=waveform_duration,
                timeline=timeline,
                window=window,
                previous_global_end=previous_global_end,
            )

            # Recuperação controlada: somente segmentos com palavras sem âncora
            # recebem uma segunda tentativa. A janela é ampliada em ambos os lados,
            # mas nunca além do áudio nem do limite máximo configurado. Nenhum
            # timestamp é interpolado; a resposta alternativa passa pelo mesmo
            # validador textual/temporal da primeira tentativa.
            if selected_unmatched and self._recovery_padding_seconds > 0:
                recovery_start = max(0.0, window.start - self._recovery_padding_seconds)
                recovery_end = min(
                    waveform_duration,
                    window.end + self._recovery_padding_seconds,
                )
                recovery_window = TimeRange(start=recovery_start, end=recovery_end)
                if (
                    recovery_window.duration <= self._max_window_seconds
                    and recovery_window != window
                ):
                    recovery_started = time.perf_counter()
                    self._record_metric("recovery_attempts", 1)
                    recovery_segment = {
                        "start": recovery_window.start,
                        "end": recovery_window.end,
                        "text": source_segment.text,
                    }
                    try:
                        self._record_metric("alignment_calls", 1)
                        self._record_metric("input_segments", 1)
                        with self._inference_lock:
                            if token is not None:
                                token.raise_if_cancelled()
                            recovery_result = self._align_function(
                                [recovery_segment],
                                model,
                                metadata,
                                waveform,
                                device,
                                progress_callback=on_alignment_progress,
                            )
                        if token is not None:
                            token.raise_if_cancelled()
                        if not isinstance(recovery_result, Mapping):
                            raise ModelError(
                                "WhisperX retornou recuperação em formato inválido."
                            )
                        (
                            recovered_segment,
                            recovered_unmatched,
                            recovered_issues,
                            recovered_aligned_count,
                            recovered_previous_end,
                        ) = _extract_segment_alignment(
                            source_segment,
                            recovery_result,
                            waveform_duration=waveform_duration,
                            timeline=timeline,
                            window=recovery_window,
                            previous_global_end=previous_global_end,
                        )
                        if len(recovered_unmatched) < len(selected_unmatched):
                            recovered_count = len(selected_unmatched) - len(
                                recovered_unmatched
                            )
                            selected_segment = recovered_segment
                            selected_unmatched = recovered_unmatched
                            selected_issues = recovered_issues
                            selected_aligned_count = recovered_aligned_count
                            selected_previous_end = recovered_previous_end
                            self._record_metric("recovered_words", recovered_count)
                        else:
                            selected_issues = (
                                *selected_issues,
                                "alignment_recovery_no_improvement",
                            )
                    except JobCancelledError:
                        raise
                    except Exception:
                        # A recovery failure never destroys a valid partial result
                        # from the first attempt; it is retained and remains visible
                        # through the unmatched diagnostics.
                        selected_issues = (
                            *selected_issues,
                            "alignment_recovery_failed",
                        )
                    finally:
                        self._record_metric(
                            "recovery_seconds", time.perf_counter() - recovery_started
                        )

            output_segments.append(selected_segment)
            unmatched_words.extend(selected_unmatched)
            issues.extend(selected_issues)
            aligned_word_count += selected_aligned_count
            previous_global_end = selected_previous_end
            progress.report(
                (segment_index + 1) / total_segments,
                f"Segmento {segment_index + 1}/{total_segments} alinhado",
            )
        if unmatched_words and "unmatched_word" not in issues:
            issues.append("unmatched_word")
        diagnostics = AlignmentDiagnostics(
            aligned_words=aligned_word_count,
            unmatched_words=tuple(unmatched_words),
            issues=tuple(dict.fromkeys(issues)),
        )
        aligned_transcript = Transcript(
            segments=tuple(output_segments),
            language=transcript.language,
            model_name=transcript.model_name,
            model_revision=transcript.model_revision,
            language_probability=transcript.language_probability,
        )
        model_label = (
            f"WhisperX {self._revision or 'unknown'} / "
            f"{ALIGNMENT_MODELS.get(language_code, language_code)}"
        )
        if token is not None:
            token.raise_if_cancelled()
        self._record_metric("aligned_words", aligned_word_count)
        self._record_metric("unmatched_words", len(unmatched_words))
        progress.report(1.0, "Forced alignment WhisperX concluído")
        return AlignmentResult(
            transcript=aligned_transcript,
            diagnostics=diagnostics,
            model_name=model_label,
        )
