"""Modos de falha, cancelamento e preservação do SRT anterior.

Os testes usam o controlador e o pipeline reais, publicador real quando o
caminho é bem-sucedido e doubles explícitos quando a falha precisa ser forçada.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from legendar.application.job.context import JobContext
from legendar.application.job.controller import JobController
from legendar.domain.entities.transcript import (
    AlignmentDiagnostics,
    AlignmentResult,
    Transcript,
)
from legendar.domain.errors.base import ErrorCategory
from legendar.domain.errors.catalog import PublicationError
from legendar.domain.events.job_events import JobCancelled, JobFailed
from legendar.domain.value_objects.language import Language
from tests.e2e.support import (
    reference_pipeline,
    reference_transcript,
    request_for,
)
from tests.helpers.fakes import (
    FakeAligner,
    FakePublisher,
    FakeTranscriber,
    FakeTranslator,
)

pytestmark = pytest.mark.e2e


def _run_expecting_failure(context: JobContext, pipeline, request):
    events: list = []
    controller = JobController(pipeline, events.append, context=context)
    result = controller.run(request, context)
    assert result is None
    terminals = [
        event for event in events if isinstance(event, (JobFailed, JobCancelled))
    ]
    assert len(terminals) == 1
    return terminals[0]


def test_media_without_audio_fails_before_publication(job_context: JobContext) -> None:
    pipeline = reference_pipeline(audio=False)
    event = _run_expecting_failure(
        job_context, pipeline, request_for(output_language=Language.ENGLISH)
    )

    assert isinstance(event, JobFailed)
    assert event.category is ErrorCategory.INVALID_INPUT
    assert not job_context.output_path.exists()


def test_empty_transcription_is_reported_as_model_failure(
    job_context: JobContext,
) -> None:
    empty = Transcript(segments=(), language=Language.PORTUGUESE, model_name="small")
    pipeline = reference_pipeline(transcriber=FakeTranscriber(transcript=empty))
    event = _run_expecting_failure(
        job_context, pipeline, request_for(output_language=Language.PORTUGUESE)
    )

    assert isinstance(event, JobFailed)
    assert event.category is ErrorCategory.MODEL_FAILED
    assert not job_context.output_path.exists()


def test_alignment_without_aligned_words_blocks_publication(
    job_context: JobContext,
) -> None:
    transcript = reference_transcript()
    alignment = AlignmentResult(
        transcript=transcript,
        diagnostics=AlignmentDiagnostics(aligned_words=0),
    )
    pipeline = reference_pipeline(aligner=FakeAligner(alignment=alignment))
    event = _run_expecting_failure(
        job_context, pipeline, request_for(output_language=Language.PORTUGUESE)
    )

    assert isinstance(event, JobFailed)
    assert event.category is ErrorCategory.ALIGNMENT_INSUFFICIENT
    assert not job_context.output_path.exists()


def test_translation_returning_the_wrong_language_fails_explicitly(
    job_context: JobContext,
) -> None:
    translator = FakeTranslator(language=Language.PORTUGUESE)
    pipeline = reference_pipeline(translate=True, translator=translator)
    request = request_for(
        output_language=Language.ENGLISH,
        source_language=Language.PORTUGUESE,
        translate=True,
    )
    event = _run_expecting_failure(job_context, pipeline, request)

    assert isinstance(event, JobFailed)
    assert event.category is ErrorCategory.TRANSLATION_FAILED
    assert not job_context.output_path.exists()


def test_publication_failure_keeps_the_previous_srt_intact(
    job_context: JobContext,
) -> None:
    class FailingPublisher(FakePublisher):
        def publish(self, track, destination_path) -> str:
            raise PublicationError("Não foi possível gravar o arquivo de saída.")

    previous = "1\n00:00:00,000 --> 00:00:01,000\nlegenda anterior\n\n"
    job_context.output_path.parent.mkdir(parents=True, exist_ok=True)
    job_context.output_path.write_text(previous, encoding="utf-8")

    pipeline = reference_pipeline(publisher=FailingPublisher())
    event = _run_expecting_failure(
        job_context, pipeline, request_for(output_language=Language.PORTUGUESE)
    )

    assert isinstance(event, JobFailed)
    assert event.category is ErrorCategory.WRITE_FAILED
    assert job_context.output_path.read_text(encoding="utf-8") == previous


def test_cancellation_before_start_never_reaches_the_destination(
    job_context: JobContext,
) -> None:
    job_context.token.cancel("Cancelado antes de iniciar.")
    pipeline = reference_pipeline()
    events: list = []
    controller = JobController(pipeline, events.append, context=job_context)

    assert (
        controller.run(request_for(output_language=Language.PORTUGUESE), job_context)
        is None
    )

    assert isinstance(events[-1], JobCancelled)
    assert not job_context.output_path.exists()


def test_cancellation_between_stages_stops_before_publication(
    job_context: JobContext,
) -> None:
    class CancellingTranscriber(FakeTranscriber):
        def transcribe(self, audio, *, language=None, progress=None, token=None):
            if token is not None:
                token.cancel("Cancelado durante a transcrição.")
            return reference_transcript()

    pipeline = reference_pipeline(transcriber=CancellingTranscriber())
    event = _run_expecting_failure(
        job_context, pipeline, request_for(output_language=Language.PORTUGUESE)
    )

    assert isinstance(event, JobCancelled)
    assert not job_context.output_path.exists()
    assert not job_context.staged_output_path.exists()


def test_unexpected_error_is_reported_without_leaking_details(
    job_context: JobContext,
) -> None:
    class ExplodingTranscriber(FakeTranscriber):
        def transcribe(self, audio, *, language=None, progress=None, token=None):
            raise RuntimeError("falha interna simulada")

    pipeline = reference_pipeline(transcriber=ExplodingTranscriber())
    event = _run_expecting_failure(
        job_context, pipeline, request_for(output_language=Language.PORTUGUESE)
    )

    assert isinstance(event, JobFailed)
    assert event.category is ErrorCategory.UNEXPECTED
    assert "inesperado" in event.message.lower()
    assert "falha interna simulada" in (event.technical_detail or "")
    assert not job_context.output_path.exists()


def test_second_failed_job_does_not_touch_the_previous_published_file(
    job_context: JobContext,
) -> None:
    ok_events: list = []
    ok_controller = JobController(
        reference_pipeline(), ok_events.append, context=job_context
    )
    result = ok_controller.run(
        request_for(output_language=Language.PORTUGUESE), job_context
    )
    assert result is not None
    published = Path(result.output_path).read_text(encoding="utf-8")
    assert published

    second_context = JobContext(
        job_id="job-2",
        source_label="aula.mp4",
        work_dir=job_context.work_dir,
        cache_dir=job_context.cache_dir,
        output_path=job_context.output_path,
    )
    event = _run_expecting_failure(
        second_context,
        reference_pipeline(audio=False),
        request_for(output_language=Language.PORTUGUESE),
    )

    assert isinstance(event, JobFailed)
    assert job_context.output_path.read_text(encoding="utf-8") == published
