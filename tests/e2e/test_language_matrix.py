"""Matriz end-to-end dos quatro pares de idioma do produto.

Cada caso executa controlador, pipeline, segmentação, tradução opcional,
validação e publicação SRT reais, com as portas externas substituídas.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from legendar.application.job.context import JobContext
from legendar.application.job.controller import JobController
from legendar.domain.events.job_events import JobCompleted, JobFailed
from legendar.domain.value_objects.language import Language
from legendar.infrastructure.filesystem.srt import parse_srt
from tests.e2e.support import (
    SENTENCES,
    reference_pipeline,
    request_for,
)
from tests.helpers.fakes import FakeTranslator

pytestmark = pytest.mark.e2e

CASES = (
    pytest.param(Language.PORTUGUESE, Language.PORTUGUESE, False, id="pt-pt"),
    pytest.param(Language.PORTUGUESE, Language.ENGLISH, True, id="pt-en"),
    pytest.param(Language.ENGLISH, Language.PORTUGUESE, True, id="en-pt"),
    pytest.param(Language.ENGLISH, Language.ENGLISH, False, id="en-en"),
)


def _run(context: JobContext, request, source: Language) -> list:
    events: list = []
    translator = FakeTranslator()
    pipeline = reference_pipeline(
        translate=request.translate, language=source, translator=translator
    )
    controller = JobController(pipeline, events.append, context=context)
    result = controller.run(request, context)
    return events, result, translator


@pytest.mark.parametrize(("source", "target", "translate"), CASES)
def test_language_matrix_publishes_a_valid_srt(
    job_context: JobContext, source: Language, target: Language, translate: bool
) -> None:
    request = request_for(
        output_language=target, source_language=source, translate=translate
    )
    events, result, translator = _run(job_context, request, source)

    assert result is not None
    assert isinstance(events[-1], JobCompleted)
    assert result.source_language is source
    assert result.final_language is target
    assert bool(translator.calls) is translate

    destination = Path(result.output_path)
    assert destination.is_file()
    assert destination == job_context.output_path
    assert not job_context.staged_output_path.exists()

    content = destination.read_text(encoding="utf-8")
    cues = parse_srt(content)
    assert len(cues) == len(result.track.cues) >= 2
    assert [cue.index for cue in cues] == list(range(1, len(cues) + 1))

    previous_end = 0.0
    for cue in cues:
        assert cue.start >= previous_end
        assert cue.end > cue.start
        assert cue.end <= 60.5
        assert cue.text.strip()
        lines = cue.text.split("\n")
        assert 1 <= len(lines) <= 2
        if not translate:
            # Sem tradução, o layout respeita duas linhas de 42 caracteres.
            assert all(len(line) <= 42 for line in lines)
        previous_end = cue.end


def test_untranslated_job_preserves_every_original_word(
    job_context: JobContext,
) -> None:
    request = request_for(output_language=Language.PORTUGUESE)
    events, result, translator = _run(job_context, request, Language.PORTUGUESE)

    assert isinstance(events[-1], JobCompleted)
    assert translator.calls == []
    published = " ".join(Path(result.output_path).read_text(encoding="utf-8").split())
    for sentence in SENTENCES:
        for token in sentence.split():
            assert token in published


def test_translated_job_keeps_one_text_per_cue_and_the_original_times(
    job_context: JobContext,
) -> None:
    request = request_for(
        output_language=Language.ENGLISH,
        source_language=Language.PORTUGUESE,
        translate=True,
    )
    events, result, translator = _run(job_context, request, Language.PORTUGUESE)

    assert isinstance(events[-1], JobCompleted)
    source_language, target_language = translator.calls[0][1], translator.calls[0][2]
    assert source_language is Language.PORTUGUESE
    assert target_language is Language.ENGLISH
    assert [cue.range for cue in result.track.cues] == [
        cue.range for cue in result.segmentation.track.cues
    ]
    published = " ".join(Path(result.output_path).read_text(encoding="utf-8").split())
    assert "[en]" in published


def test_language_matrix_is_reported_on_failure_without_publishing(
    job_context: JobContext,
) -> None:
    request = request_for(
        output_language=Language.PORTUGUESE,
        source_language=Language.ENGLISH,
        translate=False,
    )
    events, result, _translator = _run(job_context, request, Language.ENGLISH)

    assert result is None
    assert isinstance(events[-1], JobFailed)
    assert not job_context.output_path.exists()
