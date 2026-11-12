from __future__ import annotations

from pathlib import Path

import pytest

from scripts.phase8_srt_quality import analyze, parse_srt


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def test_parse_srt_preserves_multiline_text_and_timing(tmp_path: Path) -> None:
    path = tmp_path / "sample.srt"
    _write(
        path,
        "1\n00:00:00,000 --> 00:00:02,000\nBom dia\npara todos.\n\n"
        "2\n00:00:02,500 --> 00:00:04,000\nAté logo!\n",
    )

    cues = parse_srt(path)

    assert len(cues) == 2
    assert cues[0].text == "Bom dia para todos."
    assert cues[0].start == pytest.approx(0.0)
    assert cues[0].end == pytest.approx(2.0)


def test_analysis_detects_readability_risks_without_modifying_text(tmp_path: Path) -> None:
    path = tmp_path / "risks.srt"
    _write(
        path,
        "1\n00:00:00,000 --> 00:00:00,400\nOi\n\n"
        "2\n00:00:00,400 --> 00:00:00,800\nSim\n\n"
        "3\n00:00:00,800 --> 00:00:01,200\nNão\n",
    )

    metrics = analyze(parse_srt(path))

    assert metrics["cue_count"] == 3
    assert metrics["short_cues"] == [1, 2, 3]
    assert metrics["overlap_cues"] == []
    assert metrics["max_cps"] > 17.0


def test_analysis_detects_overlap_and_syntactic_fragment(tmp_path: Path) -> None:
    path = tmp_path / "fragment.srt"
    _write(
        path,
        "1\n00:00:00,000 --> 00:00:02,000\nEle caminhou para\n\n"
        "2\n00:00:01,500 --> 00:00:03,500\ncasa rapidamente\n",
    )

    metrics = analyze(parse_srt(path))

    assert metrics["overlap_cues"] == [2]
    assert metrics["syntactic_fragment_cues"] == [2]


def test_analysis_rejects_non_positive_duration(tmp_path: Path) -> None:
    path = tmp_path / "bad.srt"
    _write(path, "1\n00:00:02,000 --> 00:00:01,000\ntexto\n")

    with pytest.raises(ValueError, match="duração não positiva"):
        parse_srt(path)
