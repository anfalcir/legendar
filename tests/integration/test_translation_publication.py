"""Integração ponta a ponta: tradução por cue + publicação SRT de duas linhas."""

from __future__ import annotations

from pathlib import Path

from legendar.application.job.context import JobContext
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
from legendar.infrastructure.filesystem.srt import parse_srt
from tests.helpers.fakes import (
    FakeAligner,
    FakeAudioPreparer,
    FakeInspector,
    FakeTranscriber,
    FakeTranslator,
)

SOURCE_TEXT = "A segmentação precisa respeitar o tempo real de fala."


def _long_alignment(language: Language = Language.PORTUGUESE) -> AlignmentResult:
    words = tuple(
        TranscriptWord(
            text=text,
            range=TimeRange(start=index * 0.45, end=index * 0.45 + 0.4),
        )
        for index, text in enumerate(SOURCE_TEXT.split())
    )
    segment = TranscriptSegment(
        text=SOURCE_TEXT,
        range=TimeRange(start=0.0, end=words[-1].range.end),
        words=words,
    )
    transcript = Transcript(segments=(segment,), language=language, model_name="small")
    return AlignmentResult(
        transcript=transcript,
        diagnostics=AlignmentDiagnostics(aligned_words=len(words)),
    )


def _translated_pipeline() -> tuple[SerialPipeline, FakeTranslator]:
    translator = FakeTranslator()
    pipeline = SerialPipeline(
        PipelinePorts(
            inspector=FakeInspector(),
            audio_preparer=FakeAudioPreparer(),
            transcriber=FakeTranscriber(
                transcript=Transcript(
                    segments=(
                        TranscriptSegment(
                            text=SOURCE_TEXT,
                            range=TimeRange(0.0, 4.0),
                        ),
                    ),
                    language=Language.PORTUGUESE,
                    model_name="small",
                )
            ),
            aligner=FakeAligner(alignment=_long_alignment()),
            publisher=SrtPublisher(),
            translator=translator,
        )
    )
    return pipeline, translator


def _request() -> JobRequest:
    return JobRequest(
        source=MediaSource(kind=MediaKind.LOCAL_FILE, location="/tmp/aula.mp4"),
        output_language=Language.ENGLISH,
        source_language=Language.PORTUGUESE,
        translate=True,
    )


def test_translated_job_publishes_an_english_two_line_srt(
    job_context: JobContext,
) -> None:
    pipeline, translator = _translated_pipeline()

    result = pipeline.execute(_request(), job_context)

    assert result.final_language is Language.ENGLISH
    assert result.source_language is Language.PORTUGUESE
    assert result.warnings == ()
    assert translator.calls[0][1] is Language.PORTUGUESE
    assert translator.calls[0][2] is Language.ENGLISH

    destination = Path(result.output_path)
    content = destination.read_text(encoding="utf-8")
    lines = content.strip("\n").split("\n")
    body = lines[2:]
    assert len(body) == 2
    assert all(len(line) <= 42 for line in body)
    assert " ".join(body) == f"[en] {SOURCE_TEXT}"

    parsed = parse_srt(content)
    assert len(parsed) == len(result.track.cues)
    assert " ".join(parsed[0].text.split()) == f"[en] {SOURCE_TEXT}"


def test_translation_preserves_every_cue_time(job_context: JobContext) -> None:
    pipeline, _translator = _translated_pipeline()

    result = pipeline.execute(_request(), job_context)

    original = [cue.range for cue in result.segmentation.track.cues]
    translated = [cue.range for cue in result.track.cues]
    assert translated == original
    assert all(cue.language is Language.ENGLISH for cue in result.track.cues)


def test_english_job_writes_an_english_srt_without_translation(
    job_context: JobContext,
) -> None:
    transcriber = FakeTranscriber(
        transcript=Transcript(
            segments=(TranscriptSegment(text=SOURCE_TEXT, range=TimeRange(0.0, 4.0)),),
            language=Language.ENGLISH,
            model_name="small",
        )
    )
    pipeline = SerialPipeline(
        PipelinePorts(
            inspector=FakeInspector(),
            audio_preparer=FakeAudioPreparer(),
            transcriber=transcriber,
            aligner=FakeAligner(alignment=_long_alignment(Language.ENGLISH)),
            publisher=SrtPublisher(),
        )
    )

    result = pipeline.execute(
        JobRequest(
            source=MediaSource(kind=MediaKind.LOCAL_FILE, location="/tmp/aula.mp4"),
            output_language=Language.ENGLISH,
            source_language=Language.ENGLISH,
            translate=False,
        ),
        job_context,
    )

    content = Path(result.output_path).read_text(encoding="utf-8")
    assert SOURCE_TEXT in " ".join(content.split())
    assert result.final_language is Language.ENGLISH
