"""Integridade do corpus sintético congelado para a Fase 8.1."""

from __future__ import annotations

import json
from pathlib import Path

FIXTURE_DIR = (
    Path(__file__).resolve().parents[1] / "fixtures" / "phase_8_1"
)


def _load(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def test_gemini_synthetic_fixtures_cover_recovery_shapes() -> None:
    data = _load("gemini_responses.json")
    assert data["schema_version"] == 1
    assert data["provenance"] == "synthetic-only"

    cases = {case["id"]: case for case in data["cases"]}
    assert set(cases) == {
        "gemini_one_empty_item",
        "gemini_no_candidate",
        "gemini_truncated_output",
    }

    empty = cases["gemini_one_empty_item"]
    assert empty["expected_classification"] == "item_text_empty"
    response_text = empty["response"]["candidates"][0]["content"]["parts"][0]["text"]
    parsed = json.loads(response_text)
    assert [item["cue_id"] for item in parsed["translations"]] == [70, 71, 72]
    assert parsed["translations"][1]["text"].strip() == ""

    assert cases["gemini_no_candidate"]["response"]["candidates"] == []
    truncated = cases["gemini_truncated_output"]["response"]["candidates"][0]
    assert truncated["finishReason"] == "MAX_TOKENS"


def test_subtitle_synthetic_fixtures_cover_phase_8_1_findings() -> None:
    data = _load("subtitle_scenarios.json")
    assert data["schema_version"] == 1
    assert data["provenance"] == "synthetic-only"
    assert data["constraints"] == {"max_lines": 2, "max_characters_per_line": 42}

    cases = {case["id"]: case for case in data["cases"]}
    assert set(cases) == {
        "continuous_fragmented_phrase",
        "two_short_sentences",
        "legitimate_single_interjection",
        "long_display_text",
        "canonical_entities",
        "acknowledgement_not_refusal",
        "explicit_negation",
    }

    fragmented = cases["continuous_fragmented_phrase"]
    assert len(fragmented["words"]) >= 6
    assert all(
        word["start"] < word["end"]
        for word in fragmented["words"]
    )
    assert cases["two_short_sentences"]["words"][0]["text"].endswith(".")
    assert cases["legitimate_single_interjection"]["words"][0]["text"] == "Oh!"
    assert len(cases["long_display_text"]["text"]) > 84

    entities = cases["canonical_entities"]["protected_entities"]
    assert entities == ["Mira", "Northreach", "Silver Clans"]
    thank_you = cases["acknowledgement_not_refusal"]
    assert thank_you["illustrative_pt_br"] != thank_you["prohibited_semantic_shift"]


def test_human_reference_template_does_not_masquerade_as_reviewed_corpus() -> None:
    data = _load("human_reference.template.json")
    assert data["language"] == "pt-BR"
    assert data["reference_status"] == "pending-human-review"
    assert data["audio_sha256"] == ""
    assert data["reviewer"] == ""
