"""Pipeline serial de um job: etapas explícitas, cancelamento cooperativo.

O pipeline executa as portas em sequência e é a *única* camada que conhece a
ordem das etapas. Ele não decide estado nem emite eventos de UI: devolve um
resultado ou levanta erro de domínio. Quem traduz isso em eventos é o
controlador de job.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from legendar.application.job.context import JobContext
from legendar.application.pipeline.segmentation import (
    SegmentationPolicy,
    SegmentationResult,
    segment_alignment,
)
from legendar.application.pipeline.translation import (
    apply_translation,
    build_translation_units,
)
from legendar.application.pipeline.validation import validate_track
from legendar.application.ports.protocols import (
    Aligner,
    AudioPreparer,
    CancellationToken,
    MediaDownloader,
    MediaInspector,
    PerformanceReporter,
    SubtitlePublisher,
    Transcriber,
    Translator,
)
from legendar.application.pipeline.performance import (
    PipelinePerformanceSession,
    snapshot_adapter_metrics,
)
from legendar.application.progress.sink import MonotonicProgress, ScaledProgress
from legendar.domain.entities.media import MediaInfo, MediaKind, MediaSource
from legendar.domain.entities.subtitle import SubtitleTrack
from legendar.domain.entities.transcript import AlignmentResult
from legendar.domain.errors.catalog import (
    AlignmentInsufficientError,
    JobCancelledError,
    InvalidInputError,
    ModelError,
    TranslationError,
    UnsupportedLanguageError,
)
from legendar.domain.state.machine import JobState
from legendar.domain.value_objects.language import Language

#: Faixas de progresso por etapa (somam 1.0 no caminho completo com tradução).
LOGGER = logging.getLogger(__name__)


_STAGE_RANGES: dict[JobState, tuple[float, float]] = {
    JobState.INSPECTING_MEDIA: (0.00, 0.05),
    JobState.PREPARING_AUDIO: (0.05, 0.15),
    JobState.TRANSCRIBING: (0.15, 0.55),
    JobState.ALIGNING: (0.55, 0.82),
    JobState.SEGMENTING: (0.82, 0.86),
    JobState.TRANSLATING: (0.86, 0.97),
    JobState.VALIDATING_SRT: (0.97, 0.99),
    JobState.PUBLISHING: (0.99, 1.00),
}


@dataclass(frozen=True, slots=True)
class JobRequest:
    """Parâmetros declarados pelo usuário para um job.

    ``output_language`` é o idioma final do SRT. ``translate`` só pode ser
    verdadeiro quando o idioma final difere do idioma de origem conhecido.
    """

    source: MediaSource
    output_language: Language
    source_language: Language | None = None
    translate: bool = False
    stream_index: int | None = None

    def __post_init__(self) -> None:
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


@dataclass(frozen=True, slots=True)
class PipelineResult:
    """Resultado de um job concluído até a publicação atômica."""

    output_path: str
    track: SubtitleTrack
    segmentation: SegmentationResult
    source_language: Language
    final_language: Language
    warnings: tuple[str, ...] = field(default_factory=tuple)


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

    def execute(
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
        try:
            result = self._execute(
                request,
                context,
                on_state=on_state,
                on_progress=on_progress,
                performance=performance,
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
                    LOGGER.exception("Não foi possível persistir o relatório de desempenho.")

    def _execute(
        self,
        request: JobRequest,
        context: JobContext,
        *,
        on_state: Callable[[JobState], None] | None,
        on_progress: Callable[[float, str], None] | None,
        performance: PipelinePerformanceSession,
    ) -> PipelineResult:
        token = context.token
        progress = MonotonicProgress(on_progress)
        warnings: list[str] = []
        performance.set_metadata(
            media_kind=request.source.kind.value,
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
            start, end = _STAGE_RANGES[state]
            return ScaledProgress(progress, start, end)

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
        with performance.measure("transcription"):
            transcript = self._ports.transcriber.transcribe(
                audio, language=request.source_language, progress=stage, token=token
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
        with performance.measure("alignment"):
            alignment = self._ports.aligner.align(
                audio, transcript, progress=stage, token=token
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
            warnings.append(
                f"{len(alignment.diagnostics.unmatched_words)} palavra(s) sem alinhamento."
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
        if segmentation.has_dropped_segments:
            warnings.append(
                f"{len(segmentation.dropped_segments)} segmento(s) sem tempo descartado(s)."
            )

        # 6. Tradução opcional (preserva tempos)
        track = segmentation.track
        if request.translate:
            performance.set_count("translation_units", len(track.cues))
            with performance.measure("translation"):
                track = self._translate(
                    request, alignment, track, enter, warnings, token
                )

        # 7. Validação estrutural do trilho final
        with performance.measure("srt_validation"):
            self._validate(track, media_info, enter, warnings)
        performance.set_count("warning_count", len(warnings))

        # 8. Publicação atômica (ponto de não retorno)
        with performance.measure("srt_publication"):
            return self._publish(
                context, track, alignment, segmentation, warnings, enter
            )

    # -- etapas auxiliares -------------------------------------------------

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
        translator = self._ports.translator
        if translator is None:
            raise UnsupportedLanguageError(
                "Tradução solicitada, mas nenhum tradutor está configurado."
            )
        # O texto a traduzir está no idioma detectado na transcrição, não no
        # idioma que o usuário declarou (que pode ter sido corrigido por aviso).
        source_language = alignment.transcript.language
        if source_language is request.output_language:
            raise TranslationError(
                "A mídia já está no idioma final; desabilite a tradução para publicar."
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
    ) -> None:
        stage = enter(JobState.VALIDATING_SRT)
        report = validate_track(track, media_duration=media_info.duration_seconds)
        warnings.extend(report.warnings)
        stage.report(1.0, "Legendas validadas")

    def _publish(
        self,
        context: JobContext,
        track: SubtitleTrack,
        alignment: AlignmentResult,
        segmentation: SegmentationResult,
        warnings: list[str],
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
        )


def _as_local_source(source: MediaSource, media_path: str) -> MediaSource:
    """Após o download, a inspeção sempre recebe um caminho local."""
    if source.kind is MediaKind.LOCAL_FILE:
        return source
    return MediaSource(kind=MediaKind.LOCAL_FILE, location=media_path)
