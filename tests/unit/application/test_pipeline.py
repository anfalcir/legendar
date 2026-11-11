"""Testes do pipeline serial: ordem das etapas, falhas e ponto de não retorno."""

from __future__ import annotations

import pytest
from tests.helpers.fakes import (
    FakeAligner,
    FakeAudioPreparer,
    FakeDownloader,
    FakeInspector,
    FakePublisher,
    FakeTranscriber,
    FakeTranslator,
    make_media_info,
    make_transcript,
)

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
from legendar.domain.errors.catalog import (
    InvalidInputError,
    JobCancelledError,
    PublicationError,
    TranslationError,
    UnsupportedLanguageError,
)
from legendar.domain.state.machine import JobState
from legendar.domain.value_objects.language import Language
from legendar.domain.value_objects.time import TimeRange


def _pipeline(**overrides) -> tuple[SerialPipeline, dict]:
    ports = {
        "inspector": FakeInspector(),
        "audio_preparer": FakeAudioPreparer(),
        "transcriber": FakeTranscriber(),
        "aligner": FakeAligner(),
        "publisher": FakePublisher(),
    }
    ports.update(overrides)
    return SerialPipeline(PipelinePorts(**ports)), ports


def _request(**overrides) -> JobRequest:
    params = {
        "source": MediaSource(kind=MediaKind.LOCAL_FILE, location="/tmp/aula.mp4"),
        "output_language": Language.PORTUGUESE,
    }
    params.update(overrides)
    return JobRequest(**params)


def test_happy_path_publishes_and_reports_states(job_context):
    pipeline, ports = _pipeline()
    seen: list[JobState] = []
    result = pipeline.execute(_request(), job_context, on_state=seen.append)

    assert result.output_path == str(job_context.output_path)
    assert result.final_language is Language.PORTUGUESE
    assert len(ports["publisher"].calls) == 1
    assert seen == [
        JobState.INSPECTING_MEDIA,
        JobState.PREPARING_AUDIO,
        JobState.TRANSCRIBING,
        JobState.ALIGNING,
        JobState.SEGMENTING,
        JobState.VALIDATING_SRT,
        JobState.PUBLISHING,
    ]


def test_youtube_source_is_downloaded_before_local_inspection(job_context, tmp_path):
    downloaded = str(tmp_path / "workspace" / "legendar-youtube-id.webm")
    downloader = FakeDownloader(path=downloaded)
    inspector = FakeInspector()
    preparer = FakeAudioPreparer()
    pipeline, ports = _pipeline(
        downloader=downloader,
        inspector=inspector,
        audio_preparer=preparer,
    )
    request = _request(
        source=MediaSource(
            kind=MediaKind.YOUTUBE,
            location="https://youtu.be/video123",
        )
    )

    result = pipeline.execute(request, job_context)

    assert result.output_path == str(job_context.output_path)
    assert downloader.calls[0][0] == request.source
    assert inspector.calls[0].kind is MediaKind.LOCAL_FILE
    assert inspector.calls[0].location == downloaded
    assert preparer.calls[0][0] == downloaded


def test_explicit_audio_stream_index_is_forwarded_to_preparer(job_context):
    from dataclasses import replace

    info = make_media_info()
    second_stream = type(info.audio_streams[0])(
        index=4,
        codec="opus",
        channels=2,
        sample_rate_hz=48_000,
    )
    multi_stream_info = replace(
        info,
        audio_streams=(info.audio_streams[0], second_stream),
    )
    preparer = FakeAudioPreparer()
    pipeline, _ = _pipeline(
        inspector=FakeInspector(info=multi_stream_info),
        audio_preparer=preparer,
    )

    pipeline.execute(_request(stream_index=4), job_context)

    assert preparer.calls[0][1].index == 4


def test_translation_preserves_cue_timings(job_context):
    pipeline, _ = _pipeline(translator=FakeTranslator(language=Language.ENGLISH))
    request = _request(
        source_language=Language.PORTUGUESE,
        output_language=Language.ENGLISH,
        translate=True,
    )
    result = pipeline.execute(request, job_context)

    original = result.segmentation.track.cues
    translated = result.track.cues
    assert [cue.range for cue in translated] == [cue.range for cue in original]
    assert all(cue.language is Language.ENGLISH for cue in translated)
    assert all(cue.text.startswith("[en]") for cue in translated)


def test_translation_without_configured_translator_fails(job_context):
    pipeline, _ = _pipeline(translator=None)
    request = _request(
        source_language=Language.PORTUGUESE,
        output_language=Language.ENGLISH,
        translate=True,
    )
    with pytest.raises(UnsupportedLanguageError):
        pipeline.execute(request, job_context)


def _two_segment_transcript() -> Transcript:
    first = make_transcript().segments[0]
    second = TranscriptSegment(
        text="segunda parte",
        range=TimeRange(4.0, 5.0),
        words=(
            TranscriptWord("segunda", TimeRange(4.0, 4.4)),
            TranscriptWord("parte", TimeRange(4.5, 5.0)),
        ),
    )
    return Transcript(
        segments=(first, second),
        language=Language.PORTUGUESE,
        model_name="tiny",
    )


def test_translation_must_keep_one_unit_per_cue(job_context):
    transcriber = FakeTranscriber(transcript=_two_segment_transcript())
    pipeline, _ = _pipeline(
        transcriber=transcriber,
        translator=FakeTranslator(language=Language.ENGLISH, keep_shape=False),
    )
    request = _request(
        source_language=Language.PORTUGUESE,
        output_language=Language.ENGLISH,
        translate=True,
    )
    with pytest.raises(TranslationError):
        pipeline.execute(request, job_context)


def test_output_language_differing_from_source_requires_translation(job_context):
    # O fake transcreve em inglês; pedir PT sem tradução é incoerente.
    pipeline, _ = _pipeline(transcriber=FakeTranscriber(transcript=make_transcript()))
    request = _request(output_language=Language.PORTUGUESE, translate=False)
    with pytest.raises(UnsupportedLanguageError):
        pipeline.execute(request, job_context)


def test_detected_language_mismatch_becomes_warning(job_context):
    pipeline, _ = _pipeline(
        transcriber=FakeTranscriber(transcript=make_transcript()),
        translator=FakeTranslator(language=Language.ENGLISH),
    )
    request = _request(
        source_language=Language.PORTUGUESE,
        output_language=Language.ENGLISH,
        translate=True,
    )
    result = pipeline.execute(request, job_context)

    assert any("idioma detectado" in warning for warning in result.warnings)


def test_media_without_audio_is_rejected(job_context):
    pipeline, _ = _pipeline(inspector=FakeInspector(info=make_media_info(audio=False)))
    with pytest.raises(InvalidInputError):
        pipeline.execute(_request(), job_context)


def test_processing_port_can_cancel_job_before_publication(job_context):
    class CancellingTranscriber(FakeTranscriber):
        def transcribe(self, audio, *, language=None, progress=None, token=None):
            assert token is job_context.token
            token.cancel("cancelado durante transcrição")
            token.raise_if_cancelled()

    pipeline, ports = _pipeline(transcriber=CancellingTranscriber())

    with pytest.raises(JobCancelledError, match="cancelado durante transcrição"):
        pipeline.execute(_request(), job_context)
    assert ports["publisher"].calls == []


def test_publishing_is_not_interruptible(job_context):
    class CancellingPublisher(FakePublisher):
        def publish(self, track, destination_path):
            job_context.token.cancel("tarde demais")
            return super().publish(track, destination_path)

    publisher = CancellingPublisher()
    pipeline, _ = _pipeline(publisher=publisher)
    result = pipeline.execute(_request(), job_context)

    assert result.output_path == str(job_context.output_path)
    assert len(publisher.calls) == 1


def test_publish_failure_propagates_as_domain_error(job_context):
    class FailingPublisher(FakePublisher):
        def publish(self, track, destination_path):
            raise PublicationError("Não foi possível gravar o SRT.")

    pipeline, _ = _pipeline(publisher=FailingPublisher())
    with pytest.raises(PublicationError):
        pipeline.execute(_request(), job_context)



def test_alignment_diagnostics_are_propagated_as_pipeline_warnings(job_context):
    transcript = make_transcript(language=Language.PORTUGUESE)
    alignment = AlignmentResult(
        transcript=transcript,
        diagnostics=AlignmentDiagnostics(
            aligned_words=len(transcript.segments[0].words),
            issues=("overlap",),
        ),
        model_name="whisperx-test",
    )
    pipeline, _ = _pipeline(aligner=FakeAligner(alignment=alignment))

    result = pipeline.execute(_request(), job_context)

    assert "Anomalias no alinhamento: overlap." in result.warnings
