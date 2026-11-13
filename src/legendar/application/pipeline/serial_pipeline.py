"""Pipeline serial de um job: etapas explícitas, cancelamento cooperativo.

O pipeline executa as portas em sequência e é a *única* camada que conhece a
ordem das etapas. Ele não decide estado nem emite eventos de UI: devolve um
resultado ou levanta erro de domínio. Quem traduz isso em eventos é o
controlador de job.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from legendar.application.job.context import JobContext
from legendar.application.pipeline.performance import (
    PipelinePerformanceSession,
    snapshot_adapter_metrics,
)
from legendar.application.pipeline.segmentation import (
    SegmentationPolicy,
    SegmentationResult,
    segment_alignment,
)
from legendar.application.pipeline.translation import (
    apply_translation,
    build_translation_units,
)
from legendar.application.pipeline.validation import (
    TrackValidationReport,
    validate_track,
)
from legendar.application.ports.protocols import (
    Aligner,
    AudioPreparer,
    CancellationToken,
    MediaDownloader,
    MediaInspector,
    PerformanceReporter,
    SrtSourceReader,
    SubtitlePublisher,
    Transcriber,
    Translator,
)
from legendar.application.progress.sink import MonotonicProgress, ScaledProgress
from legendar.domain.entities.media import MediaInfo, MediaKind, MediaSource
from legendar.domain.entities.subtitle import SubtitleTrack
from legendar.domain.entities.transcript import AlignmentResult
from legendar.domain.errors.catalog import (
    AlignmentInsufficientError,
    InvalidInputError,
    JobCancelledError,
    ModelError,
    SrtValidationError,
    TranslationError,
    UnsupportedLanguageError,
)
from legendar.domain.state.machine import JobState
from legendar.domain.value_objects.language import Language
from legendar.infrastructure.resources.profile import (
    ResourcePolicy,
    resolve_resource_policy,
)

#: Faixas de progresso por etapa (somam 1.0 no caminho completo com tradução).
LOGGER = logging.getLogger(__name__)

# O bootstrap cria um SerialPipeline por job, mas reutiliza os mesmos
# adaptadores. Este lock torna explícita a serialização exigida pelo lifecycle.
_PIPELINE_EXECUTION_LOCK = threading.Lock()


_STAGE_RANGES: dict[JobState, tuple[float, float]] = {
    JobState.INSPECTING_MEDIA: (0.00, 0.05),
    JobState.LOADING_SUBTITLES: (0.00, 0.10),
    JobState.PREPARING_AUDIO: (0.05, 0.15),
    JobState.TRANSCRIBING: (0.15, 0.55),
    JobState.ALIGNING: (0.55, 0.82),
    JobState.SEGMENTING: (0.82, 0.86),
    JobState.TRANSLATING: (0.86, 0.97),
    JobState.VALIDATING_SRT: (0.97, 0.99),
    JobState.PUBLISHING: (0.99, 1.00),
}

_SRT_STAGE_RANGES: dict[JobState, tuple[float, float]] = {
    JobState.LOADING_SUBTITLES: (0.00, 0.12),
    JobState.TRANSLATING: (0.12, 0.88),
    JobState.VALIDATING_SRT: (0.88, 0.97),
    JobState.PUBLISHING: (0.97, 1.00),
}


@dataclass(frozen=True, slots=True)
class JobRequest:
    """Parâmetros declarados pelo usuário para um job.

    ``output_language`` é o idioma final do SRT. ``translate`` só pode ser
    verdadeiro quando o idioma final difere do idioma de origem conhecido.
    """

    source: MediaSource | None
    output_language: Language
    source_language: Language | None = None
    translate: bool = False
    stream_index: int | None = None
    subtitle_path: Path | None = None

    def __post_init__(self) -> None:
        if (self.source is None) == (self.subtitle_path is None):
            raise InvalidInputError(
                "Defina exatamente uma origem: mídia ou arquivo SRT."
            )
        if self.source is not None and not isinstance(self.source, MediaSource):
            raise InvalidInputError("Origem de mídia inválida.")
        if self.subtitle_path is not None:
            subtitle_path = Path(self.subtitle_path).expanduser()
            object.__setattr__(self, "subtitle_path", subtitle_path)
            if subtitle_path.suffix.lower() != ".srt":
                raise InvalidInputError(
                    "A origem de legenda precisa ser um arquivo .srt."
                )
            if self.source_language is None:
                raise InvalidInputError(
                    "Informe o idioma atual do SRT; não há detecção automática confiável."
                )
            if self.stream_index is not None:
                raise InvalidInputError(
                    "Seleção de faixa de áudio não se aplica ao SRT."
                )
        if not isinstance(self.output_language, Language):
            raise UnsupportedLanguageError("Selecione o idioma final da legenda.")
        if self.translate and self.source_language is self.output_language:
            raise InvalidInputError(
                "Tradução solicitada para o mesmo idioma da origem."
            )
        if self.translate and self.source_language is None:
            # Não é possível garantir que a origem difere do destino.
            raise InvalidInputError(
                "Defina o idioma de origem para solicitar tradução."
            )
        if self.stream_index is not None and self.stream_index < 0:
            raise InvalidInputError("Índice de faixa de áudio inválido.")


@dataclass(frozen=True, slots=True)
class PipelinePorts:
    """Adaptadores injetados no pipeline (composição explícita em bootstrap)."""

    inspector: MediaInspector
    audio_preparer: AudioPreparer
    transcriber: Transcriber
    aligner: Aligner
    publisher: SubtitlePublisher
    translator: Translator | None = None
    downloader: MediaDownloader | None = None
    srt_source_reader: SrtSourceReader | None = None


@dataclass(frozen=True, slots=True)
class PipelineResult:
    """Resultado de um job concluído até a publicação atômica."""

    output_path: str
    track: SubtitleTrack
    segmentation: SegmentationResult | None
    source_language: Language
    final_language: Language
    warnings: tuple[str, ...] = field(default_factory=tuple)
    quality_report: TrackValidationReport | None = None


class SerialPipeline:
    """Executa as etapas na ordem canônica, reportando progresso e cancelando."""

    def __init__(
        self,
        ports: PipelinePorts,
        *,
        performance_reporter: PerformanceReporter | None = None,
    ) -> None:
        self._ports = ports
        self._performance_reporter = performance_reporter
        self._resource_policy: ResourcePolicy = resolve_resource_policy()

    def execute(
        self,
        request: JobRequest,
        context: JobContext,
        *,
        on_state: Callable[[JobState], None] | None = None,
        on_progress: Callable[[float, str], None] | None = None,
    ) -> PipelineResult:
        with _PIPELINE_EXECUTION_LOCK:
            return self._execute_serialized(
                request,
                context,
                on_state=on_state,
                on_progress=on_progress,
            )

    def _execute_serialized(
        self,
        request: JobRequest,
        context: JobContext,
        *,
        on_state: Callable[[JobState], None] | None = None,
        on_progress: Callable[[float, str], None] | None = None,
    ) -> PipelineResult:
        reporter = self._performance_reporter
        resource_provider = reporter.capture_resources if reporter is not None else None
        performance = PipelinePerformanceSession(
            context.job_id,
            resource_provider=resource_provider,
            adapter_metrics_before=snapshot_adapter_metrics(self._ports),
        )
        status = "failed"
        error_type: str | None = None
        released_adapter_ids: set[int] = set()
        try:
            result = self._execute(
                request,
                context,
                on_state=on_state,
                on_progress=on_progress,
                performance=performance,
                released_adapter_ids=released_adapter_ids,
            )
            status = "completed"
            return result
        except JobCancelledError:
            status = "cancelled"
            error_type = "JobCancelledError"
            raise
        except Exception as exc:
            error_type = type(exc).__name__
            raise
        finally:
            if not self._resource_policy.retain_models:
                for adapter_name, adapter in self._model_adapters():
                    if id(adapter) not in released_adapter_ids:
                        self._release_after_stage(
                            "job_final_cleanup",
                            adapter_name,
                            adapter,
                            performance,
                            released_adapter_ids,
                        )
            if reporter is not None:
                report = performance.build_report(
                    status=status,
                    adapter_metrics_after=snapshot_adapter_metrics(self._ports),
                    error_type=error_type,
                )
                try:
                    reporter.write_report(report)
                except Exception:
                    # Telemetria é best-effort e nunca pode mudar o resultado do job.
                    LOGGER.exception(
                        "Não foi possível persistir o relatório de desempenho."
                    )

    def _execute(
        self,
        request: JobRequest,
        context: JobContext,
        *,
        on_state: Callable[[JobState], None] | None,
        on_progress: Callable[[float, str], None] | None,
        performance: PipelinePerformanceSession,
        released_adapter_ids: set[int],
    ) -> PipelineResult:
        token = context.token
        progress = MonotonicProgress(on_progress)
        warnings: list[str] = []
        performance.set_metadata(
            resource_profile=self._resource_policy.profile.value,
            retain_models=self._resource_policy.retain_models,
            cpu_threads=self._resource_policy.cpu_threads,
            cpu_interop_threads=self._resource_policy.cpu_interop_threads,
            logical_cpu_count=self._resource_policy.logical_cpu_count,
            physical_cpu_count=self._resource_policy.physical_cpu_count,
            cpu_topology_source=self._resource_policy.cpu_topology_source,
            media_kind=(
                request.source.kind.value if request.source is not None else "srt_file"
            ),
            requested_source_language=(
                request.source_language.value if request.source_language else None
            ),
            final_language=request.output_language.value,
            translation_requested=request.translate,
        )

        def enter(state: JobState) -> ScaledProgress:
            token.raise_if_cancelled()
            if on_state is not None:
                on_state(state)
            ranges = (
                _SRT_STAGE_RANGES
                if request.subtitle_path is not None
                else _STAGE_RANGES
            )
            start, end = ranges[state]
            return ScaledProgress(progress, start, end)

        if request.subtitle_path is not None:
            return self._execute_srt_source(
                request,
                context,
                enter=enter,
                warnings=warnings,
                performance=performance,
                released_adapter_ids=released_adapter_ids,
            )

        if request.source is None:
            raise InvalidInputError("Origem de mídia não definida.")

        # 1. Aquisição (download quando necessário) + inspeção
        stage = enter(JobState.INSPECTING_MEDIA)
        with performance.measure("media_acquisition"):
            media_path = self._acquire(request, context, stage, token)
        with performance.measure("media_inspection"):
            media_info = self._ports.inspector.inspect(
                _as_local_source(request.source, media_path), token=token
            )
        performance.set_metadata(media_duration_seconds=media_info.duration_seconds)
        token.raise_if_cancelled()
        if not media_info.has_audio:
            raise InvalidInputError("A mídia selecionada não possui áudio.")
        stream = (
            media_info.stream_by_index(request.stream_index)
            if request.stream_index is not None
            else media_info.default_stream()
        )
        stage.report(1.0, "Mídia inspecionada")

        # 2. Preparação do áudio normalizado
        stage = enter(JobState.PREPARING_AUDIO)
        with performance.measure("audio_preparation"):
            audio = self._ports.audio_preparer.prepare(
                media_path,
                stream=stream,
                destination_path=str(context.audio_cache_path),
                token=token,
                progress=stage,
            )
        performance.set_metadata(audio_duration_seconds=audio.duration_seconds)
        token.raise_if_cancelled()
        stage.report(1.0, "Áudio preparado")

        # 3. Transcrição no idioma de origem
        stage = enter(JobState.TRANSCRIBING)
        try:
            with performance.measure("transcription"):
                transcript = self._ports.transcriber.transcribe(
                    audio,
                    language=request.source_language,
                    progress=stage,
                    token=token,
                )
        finally:
            self._release_after_stage(
                "transcription",
                "transcription",
                self._ports.transcriber,
                performance,
                released_adapter_ids,
            )
        performance.set_count("transcript_segments", len(transcript.segments))
        performance.set_count(
            "recognized_words",
            sum(len(segment.text.split()) for segment in transcript.segments),
        )
        token.raise_if_cancelled()
        if transcript.is_empty:
            raise ModelError("A transcrição não produziu texto.")
        if (
            request.source_language is not None
            and transcript.language is not request.source_language
        ):
            warnings.append("O idioma detectado difere do idioma de origem informado.")
        if not request.translate and request.output_language is not transcript.language:
            raise UnsupportedLanguageError(
                "O idioma final difere do idioma da mídia; habilite a tradução."
            )
        stage.report(1.0, "Transcrição concluída")

        # 4. Alinhamento por palavra
        stage = enter(JobState.ALIGNING)
        try:
            with performance.measure("alignment"):
                alignment = self._ports.aligner.align(
                    audio, transcript, progress=stage, token=token
                )
        finally:
            self._release_after_stage(
                "alignment",
                "alignment",
                self._ports.aligner,
                performance,
                released_adapter_ids,
            )
        performance.set_count("aligned_words", alignment.diagnostics.aligned_words)
        performance.set_count(
            "unmatched_words", len(alignment.diagnostics.unmatched_words)
        )
        token.raise_if_cancelled()
        if not alignment.diagnostics.aligned_words:
            raise AlignmentInsufficientError(
                "Nenhuma palavra pôde ser alinhada ao áudio."
            )
        if alignment.diagnostics.has_unmatched:
            raise AlignmentInsufficientError(
                "O alinhamento deixou "
                f"{len(alignment.diagnostics.unmatched_words)} palavra(s) sem "
                "evidência temporal confiável; a publicação foi bloqueada."
            )
        additional_issues = tuple(
            issue for issue in alignment.diagnostics.issues if issue != "unmatched_word"
        )
        if additional_issues:
            warnings.append(
                "Anomalias no alinhamento: " + ", ".join(additional_issues) + "."
            )
        stage.report(1.0, "Alinhamento concluído")

        # 5. Segmentação visual (regra pura, sem porta)
        stage = enter(JobState.SEGMENTING)
        with performance.measure("segmentation"):
            segmentation = segment_alignment(alignment, policy=SegmentationPolicy())
        performance.set_count("subtitle_cues", len(segmentation.track.cues))
        token.raise_if_cancelled()
        stage.report(1.0, "Legendas segmentadas")
        if segmentation.track.is_empty:
            raise AlignmentInsufficientError("Não foi possível gerar legendas.")
        dropped_content_count = sum(
            1
            for index in segmentation.dropped_segments
            if index < len(alignment.transcript.segments)
            and alignment.transcript.segments[index].text.strip()
        )
        if dropped_content_count:
            warnings.append(
                f"{dropped_content_count} segmento(s) com conteúdo sem tempo "
                "foram descartados."
            )

        # 6. Tradução opcional (preserva tempos)
        source_track = segmentation.track
        track = source_track
        if request.translate:
            performance.set_count("translation_units", len(track.cues))
            try:
                with performance.measure("translation"):
                    track = self._translate(
                        request, alignment, track, enter, warnings, token
                    )
            finally:
                self._release_after_stage(
                    "translation",
                    "translation",
                    self._ports.translator,
                    performance,
                    released_adapter_ids,
                )

        # 7. Validação estrutural do trilho final
        with performance.measure("srt_validation"):
            quality_report = self._validate(
                track,
                media_info,
                enter,
                warnings,
                dropped_content_count,
                source_track if request.translate else None,
            )
        performance.set_count("warning_count", len(warnings))
        performance.set_count("editorial_issue_count", len(quality_report.issues))
        performance.set_metadata(editorial_quality_status=quality_report.status.value)

        # 8. Publicação atômica (ponto de não retorno)
        with performance.measure("srt_publication"):
            return self._publish(
                context, track, alignment, segmentation, warnings, quality_report, enter
            )

    def _execute_srt_source(
        self,
        request: JobRequest,
        context: JobContext,
        *,
        enter: Callable[[JobState], ScaledProgress],
        warnings: list[str],
        performance: PipelinePerformanceSession,
        released_adapter_ids: set[int],
    ) -> PipelineResult:
        """Traduz/republica um SRT sem tocar no pipeline de áudio ou ASR."""
        source_path = request.subtitle_path
        source_language = request.source_language
        if source_path is None or source_language is None:
            raise InvalidInputError(
                "O trabalho SRT exige arquivo e idioma de origem explícito."
            )
        if source_path.suffix.lower() != ".srt":
            raise InvalidInputError("O arquivo de origem precisa ter extensão .srt.")

        token = context.token
        reader = self._ports.srt_source_reader
        if reader is None:
            raise InvalidInputError(
                "Leitor de arquivo SRT não foi configurado no bootstrap."
            )
        stage = enter(JobState.LOADING_SUBTITLES)
        with performance.measure("srt_source_loading"):
            source_track, source_encoding = reader.read(
                source_path,
                language=source_language,
            )
        token.raise_if_cancelled()
        source_duration = max(cue.range.end for cue in source_track.cues)
        performance.set_metadata(
            source_input="srt_file",
            source_encoding=source_encoding,
            source_srt_duration_seconds=source_duration,
        )
        performance.set_count("source_subtitle_cues", len(source_track.cues))
        stage.report(
            1.0,
            f"SRT carregado · {len(source_track.cues)} cues · "
            f"origem {source_language.label_pt}",
        )

        track = source_track
        if request.translate:
            performance.set_count("translation_units", len(source_track.cues))
            try:
                with performance.measure("translation"):
                    track = self._translate_track(
                        request,
                        source_language,
                        source_track,
                        enter,
                        warnings,
                        token,
                    )
            finally:
                self._release_after_stage(
                    "translation",
                    "translation",
                    self._ports.translator,
                    performance,
                    released_adapter_ids,
                )
        elif request.output_language is not source_language:
            raise UnsupportedLanguageError(
                "O idioma final difere do idioma informado para o SRT; "
                "habilite a tradução."
            )

        stage = enter(JobState.VALIDATING_SRT)
        with performance.measure("srt_validation"):
            quality_report = validate_track(
                track,
                source_track=source_track if request.translate else None,
            )
        if quality_report.is_blocked:
            raise SrtValidationError(quality_report.summary)
        warnings.extend(quality_report.warnings)
        performance.set_count("warning_count", len(warnings))
        performance.set_count("editorial_issue_count", len(quality_report.issues))
        performance.set_metadata(
            editorial_quality_status=quality_report.status.value,
        )
        stage.report(
            1.0,
            "Revisão editorial necessária"
            if quality_report.review_required
            else "Qualidade editorial aprovada",
        )

        stage = enter(JobState.PUBLISHING)
        with performance.measure("srt_publication"):
            final_path = self._ports.publisher.publish(
                track,
                str(context.output_path),
            )
        stage.report(1.0, "SRT traduzido e publicado")
        return PipelineResult(
            output_path=final_path,
            track=track,
            segmentation=None,
            source_language=source_language,
            final_language=track.language,
            warnings=tuple(warnings),
            quality_report=quality_report,
        )

    # -- etapas auxiliares -------------------------------------------------

    def _model_adapters(self) -> tuple[tuple[str, object | None], ...]:
        return (
            ("transcription", self._ports.transcriber),
            ("alignment", self._ports.aligner),
            ("translation", self._ports.translator),
        )

    @staticmethod
    def _adapter_loaded(adapter: object | None) -> bool | None:
        if adapter is None:
            return False
        try:
            loaded = getattr(adapter, "is_loaded", None)
            if callable(loaded):
                return bool(loaded())
            if loaded is not None:
                return bool(loaded)
            snapshot = getattr(adapter, "performance_snapshot", None)
            if callable(snapshot):
                value = snapshot()
                if isinstance(value, dict) and "loaded" in value:
                    return bool(value["loaded"])
        except Exception:
            return None
        return None

    @staticmethod
    def _release_resources(adapter: object | None) -> tuple[bool, bool]:
        release = getattr(adapter, "release_resources", None)
        if not callable(release):
            return False, True
        try:
            release()
            return True, True
        except Exception:
            LOGGER.warning(
                "Não foi possível liberar recursos do adaptador %s.",
                type(adapter).__name__,
                exc_info=True,
            )
            return True, False

    def _release_after_stage(
        self,
        stage: str,
        adapter_name: str,
        adapter: object | None,
        performance: PipelinePerformanceSession,
        released_adapter_ids: set[int],
    ) -> None:
        loaded_before = self._adapter_loaded(adapter)
        if self._resource_policy.retain_models:
            performance.set_metadata(**{f"{stage}_loaded_after_stage": loaded_before})
            return

        started = time.perf_counter()
        attempted, succeeded = self._release_resources(adapter)
        elapsed = max(0.0, time.perf_counter() - started)
        if attempted and adapter is not None:
            released_adapter_ids.add(id(adapter))
        performance.set_count(f"{stage}_resource_release_seconds", elapsed)
        performance.set_count(
            f"{stage}_resource_release_attempted", 1 if attempted else 0
        )
        performance.set_count(
            f"{stage}_resource_release_failures",
            1 if attempted and not succeeded else 0,
        )
        performance.set_metadata(
            **{
                f"{stage}_loaded_before_release": loaded_before,
                f"{stage}_loaded_after_stage": self._adapter_loaded(adapter),
                f"{stage}_resource_release_adapter": adapter_name,
            }
        )

    def _acquire(
        self,
        request: JobRequest,
        context: JobContext,
        stage: ScaledProgress,
        token: CancellationToken,
    ) -> str:
        if request.source.kind is MediaKind.LOCAL_FILE:
            stage.report(1.0, "Arquivo local selecionado")
            return request.source.location
        downloader = self._ports.downloader
        if downloader is None:
            raise InvalidInputError("Download do YouTube não está disponível.")
        path = downloader.fetch(
            request.source,
            str(context.work_dir),
            token=token,
            progress=stage,
        )
        token.raise_if_cancelled()
        stage.report(1.0, "Mídia baixada")
        return path

    def _translate(
        self,
        request: JobRequest,
        alignment: AlignmentResult,
        track: SubtitleTrack,
        enter: Callable[[JobState], ScaledProgress],
        warnings: list[str],
        token: CancellationToken,
    ) -> SubtitleTrack:
        # A transcrição pode divergir do idioma declarado pelo usuário.
        return self._translate_track(
            request,
            alignment.transcript.language,
            track,
            enter,
            warnings,
            token,
        )

    def _translate_track(
        self,
        request: JobRequest,
        source_language: Language,
        track: SubtitleTrack,
        enter: Callable[[JobState], ScaledProgress],
        warnings: list[str],
        token: CancellationToken,
    ) -> SubtitleTrack:
        translator = self._ports.translator
        if translator is None:
            raise UnsupportedLanguageError(
                "Tradução solicitada, mas nenhum tradutor está configurado."
            )
        if source_language is request.output_language:
            raise TranslationError(
                "A origem já está no idioma final; desabilite a tradução."
            )
        units = build_translation_units(track)
        stage = enter(JobState.TRANSLATING)
        result = translator.translate(
            units,
            source_language=source_language,
            target_language=request.output_language,
            progress=stage,
            token=token,
        )
        token.raise_if_cancelled()
        if result.language is not request.output_language:
            raise TranslationError(
                "O tradutor devolveu um idioma diferente do idioma final solicitado."
            )
        stage.report(1.0, "Tradução concluída")
        applied = apply_translation(track, result)
        warnings.extend(applied.warnings)
        return applied.track

    def _validate(
        self,
        track: SubtitleTrack,
        media_info: MediaInfo,
        enter: Callable[[JobState], ScaledProgress],
        warnings: list[str],
        content_loss_count: int,
        source_track: SubtitleTrack | None,
    ) -> TrackValidationReport:
        stage = enter(JobState.VALIDATING_SRT)
        report = validate_track(
            track,
            media_duration=media_info.duration_seconds,
            content_loss_count=content_loss_count,
            source_track=source_track,
        )
        warnings.extend(report.warnings)
        if report.is_blocked:
            raise SrtValidationError(report.summary)
        stage.report(
            1.0,
            "Revisão editorial necessária"
            if report.review_required
            else "Qualidade editorial aprovada",
        )
        return report

    def _publish(
        self,
        context: JobContext,
        track: SubtitleTrack,
        alignment: AlignmentResult,
        segmentation: SegmentationResult,
        warnings: list[str],
        quality_report: TrackValidationReport,
        enter: Callable[[JobState], ScaledProgress],
    ) -> PipelineResult:
        # Publicação não consulta cancelamento: é o ponto de não retorno.
        stage = enter(JobState.PUBLISHING)
        final_path = self._ports.publisher.publish(track, str(context.output_path))
        stage.report(1.0, "Legenda publicada")
        return PipelineResult(
            output_path=final_path,
            track=track,
            segmentation=segmentation,
            source_language=alignment.transcript.language,
            final_language=track.language,
            warnings=tuple(warnings),
            quality_report=quality_report,
        )


def _as_local_source(source: MediaSource, media_path: str) -> MediaSource:
    """Após o download, a inspeção sempre recebe um caminho local."""
    if source.kind is MediaKind.LOCAL_FILE:
        return source
    return MediaSource(kind=MediaKind.LOCAL_FILE, location=media_path)
