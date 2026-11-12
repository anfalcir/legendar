"""Testes do pipeline serial: ordem das etapas, falhas e ponto de não retorno."""

from __future__ import annotations

import threading

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
    AlignmentInsufficientError,
    InvalidInputError,
    JobCancelledError,
    PublicationError,
    SrtValidationError,
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
    assert result.quality_report is not None
    assert result.quality_report.status.value == "REVIEW_REQUIRED"
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
    pipeline, _ = _pipeline(
        transcriber=FakeTranscriber(
            transcript=make_transcript(language=Language.PORTUGUESE)
        ),
        translator=FakeTranslator(),
    )
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
    assert result.final_language is Language.ENGLISH


def test_translation_reports_the_translating_state(job_context):
    pipeline, _ = _pipeline(
        transcriber=FakeTranscriber(
            transcript=make_transcript(language=Language.PORTUGUESE)
        ),
        translator=FakeTranslator(),
    )
    seen: list[JobState] = []
    pipeline.execute(
        _request(
            source_language=Language.PORTUGUESE,
            output_language=Language.ENGLISH,
            translate=True,
        ),
        job_context,
        on_state=seen.append,
    )

    assert seen.index(JobState.SEGMENTING) < seen.index(JobState.TRANSLATING)
    assert seen.index(JobState.TRANSLATING) < seen.index(JobState.VALIDATING_SRT)


def test_translation_receives_one_unit_per_cue_and_the_detected_language(
    job_context,
):
    translator = FakeTranslator()
    pipeline, _ = _pipeline(
        transcriber=FakeTranscriber(
            transcript=make_transcript(language=Language.PORTUGUESE)
        ),
        translator=translator,
    )
    result = pipeline.execute(
        _request(
            source_language=Language.PORTUGUESE,
            output_language=Language.ENGLISH,
            translate=True,
        ),
        job_context,
    )

    units, source_language, target_language = translator.calls[0]
    assert [unit.index for unit in units] == [
        cue.index for cue in result.segmentation.track.cues
    ]
    assert [unit.text for unit in units] == [
        cue.normalized_text for cue in result.segmentation.track.cues
    ]
    assert source_language is Language.PORTUGUESE
    assert target_language is Language.ENGLISH


def test_translator_returning_another_language_is_rejected(job_context):
    pipeline, _ = _pipeline(
        transcriber=FakeTranscriber(
            transcript=make_transcript(language=Language.PORTUGUESE)
        ),
        translator=FakeTranslator(language=Language.PORTUGUESE),
    )

    with pytest.raises(TranslationError, match="idioma diferente"):
        pipeline.execute(
            _request(
                source_language=Language.PORTUGUESE,
                output_language=Language.ENGLISH,
                translate=True,
            ),
            job_context,
        )


def test_translation_in_the_final_language_is_reported_as_error(job_context):
    pipeline, _ = _pipeline(
        transcriber=FakeTranscriber(transcript=make_transcript()),
        translator=FakeTranslator(),
    )

    with pytest.raises(TranslationError, match="já está no idioma final"):
        pipeline.execute(
            _request(
                source_language=Language.PORTUGUESE,
                output_language=Language.ENGLISH,
                translate=True,
            ),
            job_context,
        )


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
        translator=FakeTranslator(keep_shape=False),
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
    # O usuário declara PT-BR, mas o áudio está em inglês: publica-se em inglês
    # (sem tradução) e o desvio é reportado como aviso.
    pipeline, _ = _pipeline(transcriber=FakeTranscriber(transcript=make_transcript()))
    request = _request(
        source_language=Language.PORTUGUESE,
        output_language=Language.ENGLISH,
    )
    result = pipeline.execute(request, job_context)

    assert any("idioma detectado" in warning for warning in result.warnings)
    assert result.final_language is Language.ENGLISH


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


def test_unmatched_alignment_words_block_publication(job_context):
    transcript = make_transcript(language=Language.PORTUGUESE)
    alignment = AlignmentResult(
        transcript=transcript,
        diagnostics=AlignmentDiagnostics(
            aligned_words=1,
            unmatched_words=(TranscriptWord("mundo"),),
            issues=("unmatched_word",),
        ),
        model_name="whisperx-test",
    )
    pipeline, ports = _pipeline(aligner=FakeAligner(alignment=alignment))

    with pytest.raises(
        AlignmentInsufficientError, match="evidência temporal confiável"
    ):
        pipeline.execute(_request(), job_context)

    assert ports["publisher"].calls == []


def test_alignment_diagnostics_are_propagated_as_pipeline_warnings(
    job_context,
):
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


class PerformanceReporterFake:
    def __init__(self) -> None:
        self.reports: list[dict] = []

    def capture_resources(self) -> dict[str, int]:
        return {"process_rss_bytes": 1024, "system_memory_available_bytes": 4096}

    def write_report(self, report) -> None:
        self.reports.append(dict(report))


def test_pipeline_records_sanitized_stage_timings_and_counts(job_context):
    ports = {
        "inspector": FakeInspector(),
        "audio_preparer": FakeAudioPreparer(),
        "transcriber": FakeTranscriber(),
        "aligner": FakeAligner(),
        "publisher": FakePublisher(),
    }
    reporter = PerformanceReporterFake()
    pipeline = SerialPipeline(
        PipelinePorts(**ports),
        performance_reporter=reporter,
    )

    result = pipeline.execute(_request(), job_context)

    assert result.output_path == str(job_context.output_path)
    assert len(reporter.reports) == 1
    report = reporter.reports[0]
    assert report["status"] == "completed"
    assert report["metadata"]["media_duration_seconds"] == 12.0
    assert report["metadata"]["audio_duration_seconds"] == 12.0
    assert [stage["name"] for stage in report["stages"]] == [
        "media_acquisition",
        "media_inspection",
        "audio_preparation",
        "transcription",
        "alignment",
        "segmentation",
        "srt_validation",
        "srt_publication",
    ]
    assert report["counts"]["recognized_words"] == 2
    assert report["counts"]["aligned_words"] == 2
    assert report["counts"]["subtitle_cues"] >= 1
    assert all(stage["wall_seconds"] >= 0 for stage in report["stages"])
    serialized = __import__("json").dumps(report)
    assert "/tmp/aula.mp4" not in serialized
    assert "hello world" not in serialized


def test_pipeline_reports_failure_without_exception_message(job_context):
    reporter = PerformanceReporterFake()
    pipeline = SerialPipeline(
        PipelinePorts(
            inspector=FakeInspector(info=make_media_info(audio=False)),
            audio_preparer=FakeAudioPreparer(),
            transcriber=FakeTranscriber(),
            aligner=FakeAligner(),
            publisher=FakePublisher(),
        ),
        performance_reporter=reporter,
    )

    with pytest.raises(InvalidInputError):
        pipeline.execute(_request(), job_context)

    assert len(reporter.reports) == 1
    report = reporter.reports[0]
    assert report["status"] == "failed"
    assert report["error_type"] == "InvalidInputError"
    assert "exception_message" not in report


def test_pipeline_blocks_publication_when_segmentation_drops_source_content(
    job_context,
):
    base = make_transcript(language=Language.PORTUGUESE)
    dropped = TranscriptSegment(text="fala sem tempo", range=None, words=())
    transcript = Transcript(
        segments=(*base.segments, dropped),
        language=base.language,
        model_name=base.model_name,
    )
    alignment = AlignmentResult(
        transcript=transcript,
        diagnostics=AlignmentDiagnostics(aligned_words=2),
    )
    publisher = FakePublisher()
    pipeline, _ = _pipeline(
        aligner=FakeAligner(alignment=alignment), publisher=publisher
    )

    with pytest.raises(SrtValidationError, match="Publicação bloqueada"):
        pipeline.execute(_request(), job_context)

    assert publisher.calls == []

class ReleasableAdapter:
    """Decorador de porta que simula modelo residente e lifecycle observável."""

    def __init__(
        self,
        delegate,
        *,
        loaded: bool = False,
        fail_release: bool = False,
    ) -> None:
        self.delegate = delegate
        self.loaded = loaded
        self.fail_release = fail_release
        self.release_calls = 0

    @property
    def is_loaded(self) -> bool:
        return self.loaded

    def transcribe(self, *args, **kwargs):
        self.loaded = True
        return self.delegate.transcribe(*args, **kwargs)

    def align(self, *args, **kwargs):
        self.loaded = True
        return self.delegate.align(*args, **kwargs)

    def translate(self, *args, **kwargs):
        self.loaded = True
        return self.delegate.translate(*args, **kwargs)

    def release_resources(self) -> None:
        self.release_calls += 1
        if self.fail_release:
            raise RuntimeError("falha sintética ao liberar modelo")
        self.loaded = False

    def performance_snapshot(self) -> dict:
        return {"loaded": self.loaded, "configuration": {}, "counters": {}}


def _releasable_pipeline(
    *,
    reporter=None,
    transcriber=None,
    aligner=None,
    translator=None,
) -> tuple[SerialPipeline, dict]:
    ports = {
        "inspector": FakeInspector(),
        "audio_preparer": FakeAudioPreparer(),
        "transcriber": transcriber or ReleasableAdapter(FakeTranscriber()),
        "aligner": aligner or ReleasableAdapter(FakeAligner()),
        "publisher": FakePublisher(),
        "translator": translator,
    }
    return (
        SerialPipeline(
            PipelinePorts(**ports),
            performance_reporter=reporter,
        ),
        ports,
    )


def test_low_memory_releases_each_model_after_its_stage_and_reports_state(
    job_context, monkeypatch
) -> None:
    monkeypatch.setenv("LEGENDAR_RESOURCE_PROFILE", "low-memory")
    monkeypatch.delenv("LEGENDAR_CPU_THREADS", raising=False)
    monkeypatch.delenv("LEGENDAR_CPU_INTEROP_THREADS", raising=False)
    transcriber = ReleasableAdapter(FakeTranscriber())
    aligner = ReleasableAdapter(FakeAligner())
    translator = ReleasableAdapter(FakeTranslator())
    reporter = PerformanceReporterFake()
    pipeline, _ = _releasable_pipeline(
        reporter=reporter,
        transcriber=transcriber,
        aligner=aligner,
        translator=translator,
    )

    pipeline.execute(
        _request(
            source_language=Language.PORTUGUESE,
            output_language=Language.ENGLISH,
            translate=True,
        ),
        job_context,
    )

    assert [item.release_calls for item in (transcriber, aligner, translator)] == [
        1,
        1,
        1,
    ]
    assert all(
        item.is_loaded is False for item in (transcriber, aligner, translator)
    )
    report = reporter.reports[0]
    assert report["metadata"]["transcription_loaded_after_stage"] is False
    assert report["metadata"]["alignment_loaded_after_stage"] is False
    assert report["metadata"]["translation_loaded_after_stage"] is False
    assert report["counts"]["transcription_resource_release_attempted"] == 1
    assert report["counts"]["alignment_resource_release_attempted"] == 1
    assert report["counts"]["translation_resource_release_attempted"] == 1
    assert all(
        report["adapters"][name]["loaded_after_job"] is False
        for name in ("transcription", "alignment", "translation")
    )


def test_low_memory_releases_transcriber_after_cancellation(
    job_context, monkeypatch
) -> None:
    monkeypatch.setenv("LEGENDAR_RESOURCE_PROFILE", "low-memory")

    class CancellingTranscriber(FakeTranscriber):
        def transcribe(self, audio, *, language=None, progress=None, token=None):
            token.cancel("cancelamento no estágio de transcrição")
            token.raise_if_cancelled()

    transcriber = ReleasableAdapter(CancellingTranscriber())
    reporter = PerformanceReporterFake()
    pipeline, _ = _releasable_pipeline(
        reporter=reporter,
        transcriber=transcriber,
    )

    with pytest.raises(JobCancelledError, match="cancelamento no estágio"):
        pipeline.execute(_request(), job_context)

    assert transcriber.release_calls == 1
    assert transcriber.is_loaded is False
    assert reporter.reports[0]["status"] == "cancelled"
    assert reporter.reports[0]["metadata"]["transcription_loaded_after_stage"] is False


def test_balanced_profile_retains_models_after_job(job_context, monkeypatch) -> None:
    monkeypatch.setenv("LEGENDAR_RESOURCE_PROFILE", "balanced")
    transcriber = ReleasableAdapter(FakeTranscriber())
    aligner = ReleasableAdapter(FakeAligner())
    translator = ReleasableAdapter(FakeTranslator())
    reporter = PerformanceReporterFake()
    pipeline, _ = _releasable_pipeline(
        reporter=reporter,
        transcriber=transcriber,
        aligner=aligner,
        translator=translator,
    )

    pipeline.execute(
        _request(
            source_language=Language.PORTUGUESE,
            output_language=Language.ENGLISH,
            translate=True,
        ),
        job_context,
    )

    assert [item.release_calls for item in (transcriber, aligner, translator)] == [
        0,
        0,
        0,
    ]
    report = reporter.reports[0]
    assert all(
        report["adapters"][name]["loaded_after_job"] is True
        for name in ("transcription", "alignment", "translation")
    )


def test_low_memory_cleanup_runs_on_failure_even_before_model_stages(
    job_context, monkeypatch
) -> None:
    monkeypatch.setenv("LEGENDAR_RESOURCE_PROFILE", "low-memory")
    transcriber = ReleasableAdapter(FakeTranscriber(), loaded=True)
    aligner = ReleasableAdapter(FakeAligner(), loaded=True)
    translator = ReleasableAdapter(FakeTranslator(), loaded=True)
    reporter = PerformanceReporterFake()
    pipeline = SerialPipeline(
        PipelinePorts(
            inspector=FakeInspector(info=make_media_info(audio=False)),
            audio_preparer=FakeAudioPreparer(),
            transcriber=transcriber,
            aligner=aligner,
            publisher=FakePublisher(),
            translator=translator,
        ),
        performance_reporter=reporter,
    )

    with pytest.raises(InvalidInputError):
        pipeline.execute(_request(), job_context)

    assert [item.release_calls for item in (transcriber, aligner, translator)] == [
        1,
        1,
        1,
    ]
    assert all(
        item.is_loaded is False for item in (transcriber, aligner, translator)
    )
    assert reporter.reports[0]["status"] == "failed"


def test_resource_release_failure_does_not_mask_success(
    job_context, monkeypatch
) -> None:
    monkeypatch.setenv("LEGENDAR_RESOURCE_PROFILE", "low-memory")
    transcriber = ReleasableAdapter(FakeTranscriber(), fail_release=True)
    reporter = PerformanceReporterFake()
    pipeline, _ = _releasable_pipeline(
        reporter=reporter,
        transcriber=transcriber,
    )

    result = pipeline.execute(_request(), job_context)

    assert result.output_path == str(job_context.output_path)
    assert reporter.reports[0]["status"] == "completed"
    assert reporter.reports[0]["counts"]["transcription_resource_release_failures"] == 1
    assert reporter.reports[0]["adapters"]["transcription"]["loaded_after_job"] is True


def test_resource_release_failure_does_not_mask_original_error(
    job_context, monkeypatch
) -> None:
    from legendar.domain.errors.catalog import ModelError

    monkeypatch.setenv("LEGENDAR_RESOURCE_PROFILE", "low-memory")

    class FailingTranscriber:
        is_loaded = True

        def transcribe(self, *_args, **_kwargs):
            raise ModelError("erro original da transcrição")

        def release_resources(self):
            raise RuntimeError("erro secundário de liberação")

        def performance_snapshot(self):
            return {"loaded": self.is_loaded, "configuration": {}, "counters": {}}

    reporter = PerformanceReporterFake()
    pipeline, _ = _releasable_pipeline(
        reporter=reporter,
        transcriber=FailingTranscriber(),
    )

    with pytest.raises(ModelError, match="erro original"):
        pipeline.execute(_request(), job_context)

    assert reporter.reports[0]["error_type"] == "ModelError"
    assert reporter.reports[0]["counts"]["transcription_resource_release_failures"] == 1


def test_separate_pipeline_instances_do_not_release_a_shared_active_model(
    job_context, monkeypatch
) -> None:
    monkeypatch.setenv("LEGENDAR_RESOURCE_PROFILE", "low-memory")
    entered_first = threading.Event()
    allow_first_to_finish = threading.Event()
    second_started = threading.Event()
    entered_second = threading.Event()

    class BlockingTranscriber(ReleasableAdapter):
        def __init__(self):
            super().__init__(FakeTranscriber())
            self._lock = threading.Lock()
            self._active = 0
            self.max_active = 0
            self.calls = 0

        def transcribe(self, *args, **kwargs):
            with self._lock:
                self._active += 1
                self.max_active = max(self.max_active, self._active)
                self.calls += 1
                current_call = self.calls
            if current_call == 1:
                entered_first.set()
                assert allow_first_to_finish.wait(timeout=5)
            else:
                entered_second.set()
            try:
                return super().transcribe(*args, **kwargs)
            finally:
                with self._lock:
                    self._active -= 1

        def release_resources(self):
            with self._lock:
                assert self._active == 0
            super().release_resources()

    transcriber = BlockingTranscriber()
    shared_ports = {
        "inspector": FakeInspector(),
        "audio_preparer": FakeAudioPreparer(),
        "transcriber": transcriber,
        "aligner": ReleasableAdapter(FakeAligner()),
        "publisher": FakePublisher(),
    }
    first_pipeline = SerialPipeline(PipelinePorts(**shared_ports))
    second_pipeline = SerialPipeline(PipelinePorts(**shared_ports))
    errors: list[BaseException] = []

    def run_first() -> None:
        try:
            first_pipeline.execute(_request(), job_context)
        except BaseException as exc:  # noqa: BLE001 - capturar falha da thread do teste
            errors.append(exc)

    def run_second() -> None:
        second_started.set()
        try:
            second_pipeline.execute(_request(), job_context)
        except BaseException as exc:  # noqa: BLE001 - capturar falha da thread do teste
            errors.append(exc)

    first = threading.Thread(target=run_first)
    second = threading.Thread(target=run_second)
    first.start()
    assert entered_first.wait(timeout=5)
    second.start()
    assert second_started.wait(timeout=5)
    assert not entered_second.wait(timeout=0.1)
    allow_first_to_finish.set()
    first.join(timeout=5)
    second.join(timeout=5)

    assert not first.is_alive()
    assert not second.is_alive()
    assert errors == []
    assert entered_second.is_set()
    assert transcriber.max_active == 1
    assert transcriber.release_calls == 2


