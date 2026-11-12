from __future__ import annotations

from pathlib import Path

import pytest
from scripts.phase8_srt_quality import (
    _percentile,
    analyze,
    compare,
    main,
    parse_srt,
)


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
    assert cues[0].lines == ("Bom dia", "para todos.")
    assert cues[0].start == pytest.approx(0.0)
    assert cues[0].end == pytest.approx(2.0)
    assert cues[0].duration == pytest.approx(2.0)


def test_analysis_detects_short_and_fast_cues(tmp_path: Path) -> None:
    path = tmp_path / "risks.srt"
    _write(
        path,
        "1\n00:00:00,000 --> 00:00:00,400\nIsso mesmo\n\n"
        "2\n00:00:00,400 --> 00:00:00,800\nSim, concordo\n\n"
        "3\n00:00:00,800 --> 00:00:01,200\nNão, obrigado\n",
    )

    metrics = analyze(parse_srt(path))

    assert metrics["cue_count"] == 3
    assert metrics["short_cues"] == [1, 2, 3]
    assert metrics["overlap_cues"] == []
    assert metrics["max_cps"] > 17.0
    assert metrics["reading_speed_cues"] == [1, 2, 3]


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


def test_analysis_detects_long_wide_and_duplicate_cues(tmp_path: Path) -> None:
    path = tmp_path / "layout.srt"
    long_line = (
        "Esta legenda contém uma linha propositalmente muito extensa para o teste."
    )
    _write(
        path,
        "1\n00:00:00,000 --> 00:00:08,000\n" + long_line + "\n\n"
        "2\n00:00:09,000 --> 00:00:10,000\nRepetida\n\n"
        "3\n00:00:10,500 --> 00:00:11,500\nRepetida\n",
    )

    metrics = analyze(parse_srt(path))

    assert metrics["long_cues"] == [1]
    assert metrics["wide_cues"] == [1]
    assert metrics["duplicate_cues"] == [3]
    assert metrics["p95_gap_seconds"] == pytest.approx(1.0)


def test_percentile_and_empty_analysis() -> None:
    assert _percentile([], 95) == 0.0
    assert _percentile([1.0, 2.0, 3.0, 4.0], 50) == 2.0
    metrics = analyze([])
    assert metrics["cue_count"] == 0
    assert metrics["first_start_seconds"] is None
    assert metrics["last_end_seconds"] is None


def test_compare_handles_empty_baseline() -> None:
    empty = analyze([])
    nonempty = analyze(parse_srt_from_text("1\n00:00:00,000 --> 00:00:02,000\nTexto\n"))
    result = compare(nonempty, empty)
    assert result["cue_count_delta"] == 1
    assert result["cue_count_ratio"] is None


def parse_srt_from_text(content: str):
    from tempfile import NamedTemporaryFile

    with NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".srt") as stream:
        stream.write(content)
        stream.flush()
        return parse_srt(Path(stream.name))


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("bloco inválido\n", "menos de 3 linhas"),
        ("x\n00:00:00,000 --> 00:00:01,000\ntexto\n", "Índice SRT inválido"),
        ("1\ntimestamp inválido\ntexto\n", "Timestamp SRT inválido"),
        ("1\n00:00:00,000 --> 00:00:01,000\n\n", "menos de 3 linhas"),
        ("1\n00:00:02,000 --> 00:00:01,000\ntexto\n", "duração não positiva"),
    ],
)
def test_parse_srt_rejects_malformed_blocks(
    tmp_path: Path, content: str, message: str
) -> None:
    path = tmp_path / "bad.srt"
    _write(path, content)
    with pytest.raises(ValueError, match=message):
        parse_srt(path)


def test_cli_text_and_comparison_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    candidate = tmp_path / "candidate.srt"
    baseline = tmp_path / "baseline.srt"
    valid = "1\n00:00:00,000 --> 00:00:02,000\nTexto curto\n"
    _write(candidate, valid)
    _write(baseline, valid)

    assert main([str(candidate), "--compare", str(baseline)]) == 0
    output = capsys.readouterr().out
    assert "Gate estrutural: PASS" in output
    assert "Comparação:" in output


def test_cli_json_and_gate_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    candidate = tmp_path / "candidate.srt"
    _write(
        candidate,
        "1\n00:00:00,000 --> 00:00:08,000\n"
        "Esta linha é excessivamente longa e também ficará acima do limite "
        "de leitura.\n",
    )

    assert main([str(candidate), "--json"]) == 1
    output = capsys.readouterr().out
    assert '"status": "FAIL"' in output
    assert '"wide_cues"' in output
