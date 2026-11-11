"""Pipeline serial de um job: etapas explícitas, cancelamento cooperativo.

O pipeline executa as portas em sequência e é a *única* camada que conhece a
ordem das etapas. Ele não decide estado nem emite eventos de UI: devolve um
resultado ou levanta erro de domínio. Quem traduz isso em eventos é o
controlador de job.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from legendar.application.job.context import JobContext
from legendar.application.pipeline.segmentation import (
    SegmentationPolicy,
    SegmentationResult,
    segment_alignment,
)
from legendar.application.ports.protocols import (
    Aligner,
    AudioPreparer,
    CancellationToken,
    MediaDownloader,
    MediaInspector,
    SubtitlePublisher,
    Transcriber,
    Translator,
)
from legendar.application.progress.sink import MonotonicProgress, ScaledProgress
from legendar.domain.entities.media import MediaKind, MediaSource
from legendar.domain.entities.subtitle import SubtitleCue, SubtitleTrack
from legendar.domain.entities.transcript import AlignmentResult, Transcript
from legendar.domain.errors.catalog import (
    AlignmentInsufficientError,
    InvalidInputError,
    ModelError,
    TranslationError,
    UnsupportedLanguageError,
)
from legendar.domain.state.machine import JobState
from legendar.domain.value_objects.language import Language

#: Faixas de progresso por etapa (somam 1.0 no caminho completo com tradução).
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

    def __init__(self, ports: PipelinePorts) -> None:
        self._ports = ports

    def execute(
        self,
        request: JobRequest,
        context: JobContext,
        *,
        on_state: Callable[[JobState], None] | None = None,
        on_progress: Callable[[float, str], None] | None = None,
    ) -> PipelineResult:
        token = context.token
        progress = MonotonicProgress(on_progress)
        warnings: list[str] = []

        def enter(state: JobState) -> ScaledProgress:
            token.raise_if_cancelled()
            if on_state is not None:
                on_state(state)
            start, end = _STAGE_RANGES[state]
            return ScaledProgress(progress, start, end)

        # 1. Aquisição (download quando necessário) + inspeção
        stage = enter(JobState.INSPECTING_MEDIA)
        media_path = self._acquire(request, context, stage, token)
        media_info = self._ports.inspector.inspect(
            _as_local_source(request.source, media_path), token=token
        )
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
        audio = self._ports.audio_preparer.prepare(
            media_path,
            stream=stream,
            destination_path=str(context.audio_cache_path),
            token=token,
            progress=stage,
        )
        token.raise_if_cancelled()
        stage.report(1.0, "Áudio preparado")

        # 3. Transcrição no idioma de origem
        stage = enter(JobState.TRANSCRIBING)
        transcript = self._ports.transcriber.transcribe(
            audio, language=request.source_language, progress=stage, token=token
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
        alignment = self._ports.aligner.align(
            audio, transcript, progress=stage, token=token
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
        segmentation = segment_alignment(alignment, policy=SegmentationPolicy())
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
            track = self._translate(request, alignment, track, enter, warnings, token)

        # 7. Validação estrutural do trilho final
        self._validate(track, enter)

        # 8. Publicação atômica (ponto de não retorno)
        return self._publish(context, track, alignment, segmentation, warnings, enter)

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
        if self._ports.translator is None:
            raise UnsupportedLanguageError(
                "Tradução solicitada, mas nenhum tradutor está configurado."
            )
        stage = enter(JobState.TRANSLATING)
        translated = self._ports.translator.translate(
            alignment.transcript,
            target_language=request.output_language,
            progress=stage,
            token=token,
        )
        token.raise_if_cancelled()
        stage.report(1.0, "Tradução concluída")
        if translated.is_empty:
            raise TranslationError("A tradução retornou texto vazio.")
        return _apply_translation(track, translated, warnings)

    def _validate(
        self, track: SubtitleTrack, enter: Callable[[JobState], ScaledProgress]
    ) -> None:
        stage = enter(JobState.VALIDATING_SRT)
        if track.is_empty:
            raise InvalidInputError("Trilho de legendas vazio.")
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


def _apply_translation(
    original: SubtitleTrack,
    translated: Transcript,
    warnings: list[str],
) -> SubtitleTrack:
    """Aplica os textos traduzidos às cues originais preservando os tempos.

    Traduzir não pode mover legendas: o vínculo temporal vem do alinhamento.
    Quando o tradutor não devolve exatamente uma unidade por cue, o
    mapeamento 1:1 não é seguro e o job falha de forma explícita — nenhuma
    cue é descartada nem tem texto redistribuído.
    """
    if len(translated.segments) != len(original.cues):
        raise TranslationError(
            "A tradução não manteve a correspondência 1:1 com as legendas "
            f"({len(translated.segments)} unidades para {len(original.cues)} cues)."
        )
    cues = tuple(
        SubtitleCue(
            index=cue.index,
            text=segment.text,
            range=cue.range,
            language=translated.language,
            source_segments=cue.source_segments,
        )
        for cue, segment in zip(original.cues, translated.segments, strict=True)
    )
    if any(not cue.text.strip() for cue in cues):
        warnings.append("Tradução produziu cue(s) sem texto.")
    return SubtitleTrack(language=translated.language, cues=cues)
