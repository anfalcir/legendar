"""Apoio dos testes end-to-end determinísticos.

Os testes E2E exercitam o caminho real de aplicação (controlador, pipeline,
workspace, validação e publicação SRT) com adaptadores externos substituídos:
nenhum modelo, rede ou binário externo é necessário.
"""

from __future__ import annotations

from legendar.application.pipeline.serial_pipeline import (
    JobRequest,
    PipelinePorts,
    SerialPipeline,
)
from legendar.domain.entities.media import MediaKind, MediaSource
from legendar.domain.entities.transcript import (
    AlignmentDiagnostics,
    AlignmentResult,
    Transcript,
    TranscriptSegment,
    TranscriptWord,
)
from legendar.domain.value_objects.language import Language
from legendar.domain.value_objects.time import TimeRange
from legendar.infrastructure.filesystem.publisher import SrtPublisher
from tests.helpers.fakes import (
    FakeAligner,
    FakeAudioPreparer,
    FakeInspector,
    FakeTranscriber,
    FakeTranslator,
    make_media_info,
)

#: Falas de referência: frases longas, números e nome próprio.
SENTENCES: tuple[str, ...] = (
    "A graça transforma o coração de quem ouve a palavra.",
    "Números como 3.14 e 2026 precisam sobreviver à tradução.",
    "O nome próprio João Calvino permanece intacto no texto.",
)

#: Duração declarada da mídia sintética usada na inspeção.
MEDIA_DURATION_SECONDS = 60.0


def reference_transcript(language: Language = Language.PORTUGUESE) -> Transcript:
    """Transcrição com palavras temporizadas em várias frases contíguas."""
    segments: list[TranscriptSegment] = []
    cursor = 0.4
    for sentence in SENTENCES:
        words: list[TranscriptWord] = []
        for token in sentence.split():
            words.append(
                TranscriptWord(
                    text=token,
                    range=TimeRange(start=cursor, end=cursor + 0.36),
                )
            )
            cursor += 0.52
        segments.append(
            TranscriptSegment(
                text=sentence,
                range=TimeRange(start=words[0].range.start, end=words[-1].range.end),
                words=tuple(words),
            )
        )
        cursor += 0.8
    return Transcript(segments=tuple(segments), language=language, model_name="small")


def reference_alignment(
    language: Language = Language.PORTUGUESE,
) -> AlignmentResult:
    transcript = reference_transcript(language)
    aligned = sum(len(segment.words) for segment in transcript.segments)
    return AlignmentResult(
        transcript=transcript,
        diagnostics=AlignmentDiagnostics(aligned_words=aligned),
    )


def request_for(
    *,
    output_language: Language,
    source_language: Language | None = None,
    translate: bool = False,
    source: MediaSource | None = None,
) -> JobRequest:
    return JobRequest(
        source=source
        or MediaSource(kind=MediaKind.LOCAL_FILE, location="/midia/aula.mkv"),
        output_language=output_language,
        source_language=source_language,
        translate=translate,
    )


def reference_pipeline(
    *,
    translate: bool = False,
    audio: bool = True,
    duration: float = MEDIA_DURATION_SECONDS,
    language: Language = Language.PORTUGUESE,
    transcriber: FakeTranscriber | None = None,
    aligner: FakeAligner | None = None,
    translator: FakeTranslator | None = None,
    publisher: SrtPublisher | None = None,
) -> SerialPipeline:
    """Monta o pipeline real com dependências externas controladas."""
    ports = PipelinePorts(
        inspector=FakeInspector(info=make_media_info(audio=audio, duration=duration)),
        audio_preparer=FakeAudioPreparer(),
        transcriber=transcriber
        or FakeTranscriber(transcript=reference_transcript(language)),
        aligner=aligner or FakeAligner(alignment=reference_alignment(language)),
        publisher=publisher or SrtPublisher(),
        translator=translator if translate else None,
    )
    return SerialPipeline(ports)
