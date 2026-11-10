"""Testes do controlador: eventos, sequência, terminal único e cancelamento."""

from __future__ import annotations

import pytest
from tests.helpers.fakes import (
    FakeAligner,
    FakeAudioPreparer,
    FakeInspector,
    FakePublisher,
    FakeTranscriber,
)

from legendar.application.job.controller import JobController
from legendar.application.pipeline.serial_pipeline import (
    JobRequest,
    PipelinePorts,
    SerialPipeline,
)
from legendar.domain.entities.media import MediaKind, MediaSource
from legendar.domain.errors.base import ErrorCategory
from legendar.domain.errors.catalog import PublicationError
from legendar.domain.events.job_events import (
    JobCancelled,
    JobCompleted,
    JobEvent,
    JobFailed,
    JobStarted,
    ProgressReported,
    StateChanged,
)
from legendar.domain.state.machine import JobState
from legendar.domain.value_objects.language import Language


def _request() -> JobRequest:
    return JobRequest(
        source=MediaSource(kind=MediaKind.LOCAL_FILE, location="/tmp/aula.mp4"),
        output_language=Language.PORTUGUESE,
    )


def _build(events: list[JobEvent], **overrides) -> JobController:
    ports = {
        "inspector": FakeInspector(),
        "audio_preparer": FakeAudioPreparer(),
        "transcriber": FakeTranscriber(),
        "aligner": FakeAligner(),
        "publisher": FakePublisher(),
    }
    ports.update(overrides)
    return JobController(SerialPipeline(PipelinePorts(**ports)), events.append)


def test_happy_path_emits_started_states_and_completed(job_context):
    events: list[JobEvent] = []
    controller = _build(events)

    result = controller.run(_request(), job_context)

    assert result is not None
    assert isinstance(events[0], JobStarted)
    assert isinstance(events[-1], JobCompleted)
    assert controller.state is JobState.COMPLETED

    changed = [event for event in events if isinstance(event, StateChanged)]
    assert [event.current for event in changed] == [
        JobState.VALIDATING_INPUT,
        JobState.INSPECTING_MEDIA,
        JobState.PREPARING_AUDIO,
        JobState.TRANSCRIBING,
        JobState.ALIGNING,
        JobState.SEGMENTING,
        JobState.VALIDATING_SRT,
        JobState.PUBLISHING,
        JobState.COMPLETED,
    ]


def test_sequence_numbers_strictly_increase(job_context):
    events: list[JobEvent] = []
    _build(events).run(_request(), job_context)

    sequences = [event.sequence for event in events]
    assert sequences == sorted(sequences)
    assert len(set(sequences)) == len(sequences)


def test_only_one_terminal_event_is_emitted(job_context):
    events: list[JobEvent] = []
    controller = _build(events)
    controller.run(_request(), job_context)

    terminal = [
        event
        for event in events
        if isinstance(event, (JobCompleted, JobCancelled, JobFailed))
    ]
    assert len(terminal) == 1
    count_before_cancel = len(events)
    assert controller.cancel() is False
    assert len(events) == count_before_cancel


def test_controller_cannot_run_twice(job_context):
    controller = _build([])
    controller.run(_request(), job_context)
    with pytest.raises(RuntimeError):
        controller.run(_request(), job_context)


def test_domain_error_becomes_job_failed_with_category(job_context):
    class FailingPublisher(FakePublisher):
        def publish(self, track, destination_path):
            raise PublicationError("Falha de escrita.")

    events: list[JobEvent] = []
    controller = _build(events, publisher=FailingPublisher())

    assert controller.run(_request(), job_context) is None
    failure = events[-1]
    assert isinstance(failure, JobFailed)
    assert failure.category is ErrorCategory.WRITE_FAILED
    assert controller.state is JobState.FAILED


def test_unexpected_error_is_wrapped_without_leaking_traceback(job_context):
    class ExplodingAligner:
        def align(self, audio, transcript, *, progress=None):
            raise ValueError("boom")

    events: list[JobEvent] = []
    controller = _build(events, aligner=ExplodingAligner())

    assert controller.run(_request(), job_context) is None
    failure = events[-1]
    assert isinstance(failure, JobFailed)
    assert failure.category is ErrorCategory.UNEXPECTED
    assert "ValueError" in (failure.technical_detail or "")


def test_cancellation_goes_through_cancelling_and_emits_single_terminal(job_context):
    events: list[JobEvent] = []
    controller = _build(events, transcriber=FakeTranscriber(token=job_context.token))

    # Pedido de cancelamento aceito antes da primeira etapa pesada.
    assert job_context.token.cancel("usuário desistiu") is True
    assert controller.run(_request(), job_context) is None

    states = [event.current for event in events if isinstance(event, StateChanged)]
    assert JobState.CANCELLING in states
    assert states[-1] is JobState.CANCELLED
    assert isinstance(events[-1], JobCancelled)
    assert not any(isinstance(event, JobFailed) for event in events)


def test_progress_is_monotonic_and_deduplicated(job_context):
    events: list[JobEvent] = []
    controller = _build(events)
    controller.run(_request(), job_context)

    fractions = [
        event.fraction for event in events if isinstance(event, ProgressReported)
    ]
    assert fractions == sorted(fractions)
    assert all(0.0 <= fraction <= 1.0 for fraction in fractions)
    assert len(fractions) > 0



def test_cancel_is_rejected_once_non_cancellable_publication_begins(job_context):
    from threading import Event, Thread

    entered_publication = Event()
    release_publication = Event()
    events: list[JobEvent] = []
    outcomes = []

    class BlockingPublisher(FakePublisher):
        def publish(self, track, destination_path):
            entered_publication.set()
            assert release_publication.wait(timeout=5)
            return super().publish(track, destination_path)

    controller = _build(events, publisher=BlockingPublisher())

    worker = Thread(
        target=lambda: outcomes.append(controller.run(_request(), job_context))
    )
    worker.start()

    assert entered_publication.wait(timeout=5)
    assert controller.state is JobState.PUBLISHING
    assert controller.cancel() is False
    assert not job_context.token.is_cancelled

    release_publication.set()
    worker.join(timeout=5)

    assert not worker.is_alive()
    assert len(outcomes) == 1
    assert outcomes[0] is not None
    assert controller.state is JobState.COMPLETED


def test_cancel_without_active_job_returns_false():
    controller = _build([])
    assert controller.cancel() is False
