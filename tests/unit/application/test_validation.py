"""Testes da validação final: falhas estruturais vs. avisos de legibilidade."""

from __future__ import annotations

import pytest

from legendar.application.pipeline.segmentation import SegmentationPolicy
from legendar.application.pipeline.validation import (
    MEDIA_DURATION_TOLERANCE_SECONDS,
    validate_track,
)
from legendar.domain.entities.subtitle import SubtitleCue, SubtitleTrack
from legendar.domain.errors.catalog import SrtValidationError
from legendar.domain.value_objects.language import Language
from legendar.domain.value_objects.time import TimeRange


def _cue(index: int, text: str, start: float, end: float) -> SubtitleCue:
    return SubtitleCue(
        index=index,
        text=text,
        range=TimeRange(start, end),
        language=Language.PORTUGUESE,
    )


def _track(*cues: SubtitleCue) -> SubtitleTrack:
    return SubtitleTrack(language=Language.PORTUGUESE, cues=cues)


def test_clean_track_has_no_warnings() -> None:
    track = _track(_cue(1, "bom dia", 0.0, 2.0), _cue(2, "até logo", 2.5, 4.5))

    report = validate_track(track, media_duration=10.0)

    assert report.is_clean
    assert report.warnings == ()
    assert report.short_cues == report.long_cues == ()
    assert report.overflow_cues == report.wide_cues == ()


def test_empty_track_is_a_structural_failure() -> None:
    with pytest.raises(SrtValidationError, match="vazio"):
        validate_track(SubtitleTrack(language=Language.PORTUGUESE, cues=()))


def test_cue_finishing_after_the_media_is_a_structural_failure() -> None:
    track = _track(_cue(1, "bom dia", 0.0, 12.0))

    with pytest.raises(SrtValidationError, match="depois do fim da mídia"):
        validate_track(track, media_duration=10.0)


def test_end_within_tolerance_of_the_media_is_not_a_structural_failure() -> None:
    track = _track(_cue(1, "bom dia", 0.0, 10.0 + MEDIA_DURATION_TOLERANCE_SECONDS))

    report = validate_track(track, media_duration=10.0)

    # Passa na estrutura; o excesso de duração continua sendo avisado.
    assert report.long_cues == (1,)


def test_short_cue_is_warned_with_comma_decimals() -> None:
    track = _track(_cue(1, "oi", 0.0, 0.4))

    report = validate_track(track)

    assert report.short_cues == (1,)
    assert report.warnings[0] == ("1 legenda abaixo da duração mínima de 1,0 s: 1.")


def test_long_cue_is_warned() -> None:
    track = _track(_cue(1, "texto curto", 0.0, 9.0))

    report = validate_track(track)

    assert report.long_cues == (1,)
    assert any(
        "acima da duração máxima de 7,0 s" in warning for warning in report.warnings
    )


def test_cue_above_reading_speed_is_warned() -> None:
    text = " ".join(["palavra"] * 6)  # 41 caracteres em 1 s (> 17 cps)
    track = _track(_cue(1, text, 0.0, 1.0))

    report = validate_track(track)

    assert report.overflow_cues == (1,)
    assert any("velocidade de leitura" in warning for warning in report.warnings)


def test_cue_wider_than_two_lines_is_warned() -> None:
    text = " ".join(["palavra"] * 13)  # 103 caracteres > 84
    track = _track(_cue(1, text, 0.0, 8.0))

    report = validate_track(track, policy=SegmentationPolicy(max_cue_duration=10.0))

    assert report.wide_cues == (1,)
    assert any("84 caracteres por cue" in warning for warning in report.warnings)


def test_reports_are_capped_in_the_warning_text() -> None:
    cues = tuple(_cue(index, "oi", index - 1, index - 0.6) for index in range(1, 12))
    track = _track(*cues)

    report = validate_track(track)

    assert len(report.short_cues) == 11
    assert report.warnings[0].endswith("1, 2, 3, 4, 5, 6, 7, 8, ….")


def test_custom_policy_changes_the_thresholds() -> None:
    track = _track(_cue(1, "texto médio", 0.0, 3.0))
    policy = SegmentationPolicy(min_cue_duration=4.0, max_cue_duration=9.0)

    report = validate_track(track, policy=policy)

    assert report.short_cues == (1,)



def test_quality_report_is_structured_and_includes_cps_metrics() -> None:
    track = _track(_cue(1, "bom dia", 0.0, 2.0), _cue(2, "até logo", 2.5, 4.5))

    report = validate_track(track)

    assert report.status.value == "APPROVED"
    assert report.cue_count == 2
    assert report.max_cps == pytest.approx(4.0)
    assert report.p95_cps == pytest.approx(4.0)
    assert report.issues == ()


def test_editorial_risks_require_review_without_removing_content() -> None:
    repeated = "vamos seguir"
    track = _track(
        _cue(1, repeated, 0.0, 1.0),
        _cue(2, repeated, 1.2, 2.2),
    )

    report = validate_track(track)

    assert report.status.value == "REVIEW_REQUIRED"
    assert report.duplicate_cues == (2,)
    assert len(track.cues) == 2
    assert track.cues[0].text == track.cues[1].text


def test_suspicious_control_and_replacement_characters_are_reported() -> None:
    track = _track(_cue(1, "texto \ufffd inválido", 0.0, 2.0))

    report = validate_track(track)

    assert report.status.value == "REVIEW_REQUIRED"
    assert report.suspicious_cues == (1,)
    assert any(issue.code == "SUSPICIOUS_TEXT" for issue in report.issues)


def test_repeated_word_loop_is_reported_but_preserved() -> None:
    text = "não não não não pare"
    track = _track(_cue(1, text, 0.0, 3.0))

    report = validate_track(track)

    assert report.suspicious_cues == (1,)
    assert track.cues[0].text == text


def test_connector_at_cue_boundary_is_reported_as_fragment() -> None:
    track = _track(
        _cue(1, "ele caminhou para", 0.0, 2.0),
        _cue(2, "casa rapidamente", 2.2, 4.0),
    )

    report = validate_track(track)

    assert report.fragmented_cues == (2,)
    assert report.status.value == "REVIEW_REQUIRED"


def test_content_loss_blocks_publication_quality_gate() -> None:
    track = _track(_cue(1, "conteúdo preservado", 0.0, 2.0))

    report = validate_track(track, content_loss_count=1)

    assert report.status.value == "BLOCKED"
    assert report.is_blocked
    assert "1 segmento(s)" in report.summary


def test_translation_invariant_numbers_and_acronyms_are_checked() -> None:
    source = _track(_cue(1, "A NASA lançou 3 satélites", 0.0, 3.0))
    target = _track(_cue(1, "A agência lançou satélites", 0.0, 3.0))

    report = validate_track(target, source_track=source)

    assert report.status.value == "REVIEW_REQUIRED"
    issue = next(issue for issue in report.issues if issue.code == "TRANSLATION_INVARIANT")
    assert "número 3" in issue.message
    assert "sigla NASA" in issue.message
