from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

from scripts.phase8_1_translation_review import (
    build_review_rows,
    main,
    write_review_csv,
)
from scripts.phase8_srt_quality import Cue


def _cue(index: int, start: float, end: float, text: str) -> Cue:
    return Cue(
        index=index,
        start=start,
        end=end,
        text=text,
        lines=(text,),
    )


def _corpus() -> tuple[list[Cue], list[Cue]]:
    source = [
        _cue(10, 0.0, 1.0, "Thank you."),
        _cue(20, 1.0, 2.0, "No, I won't."),
        _cue(30, 2.0, 3.0, "Welcome to Northreach."),
        _cue(40, 3.0, 4.0, "Are you coming?"),
        _cue(50, 4.0, 5.0, "A short line."),
    ]
    # Os IDs e os limites das cues de destino são diferentes de propósito.
    translated = [
        _cue(1, 0.0, 2.0, "Obrigado. Não vou."),
        _cue(2, 2.0, 5.0, "Bem-vindo a Northreach. Você vem? Uma frase curta."),
    ]
    return source, translated


def test_review_rows_pair_by_time_and_include_surrounding_context() -> None:
    source, translated = _corpus()

    rows = build_review_rows(source, translated, samples=5, context_cues=1)

    assert len(rows) == 5
    first = rows[0]
    assert first["source_en_asr"] == "Thank you."
    assert "Obrigado." in first["current_ptbr_contextual"]
    assert "No, I won't." in first["source_context_after"]
    assert first["reviewed_ptbr"] == ""
    assert first["source_asr_verified_by_audio"] == ""


def test_review_sample_is_deterministic_and_covers_high_risk_categories() -> None:
    source, translated = _corpus()

    first = build_review_rows(source, translated, samples=5)
    second = build_review_rows(source, translated, samples=5)

    assert first == second
    categories = {
        category for row in first for category in row["risk_categories"].split(", ")
    }
    assert {"gratitude", "negation", "question", "possible_proper_name"} <= categories


def test_review_sample_respects_requested_size_and_context_limit() -> None:
    source, translated = _corpus()

    rows = build_review_rows(source, translated, samples=2, context_cues=0)

    assert len(rows) == 2
    assert all(row["source_context_before"] == "" for row in rows)
    assert all(row["source_context_after"] == "" for row in rows)


def test_review_rejects_invalid_inputs() -> None:
    source, translated = _corpus()

    try:
        build_review_rows(source, translated, context_cues=-1)
    except ValueError as error:
        assert "context_cues" in str(error)
    else:
        raise AssertionError("context_cues negativo deveria falhar")

    try:
        build_review_rows([], translated)
    except ValueError as error:
        assert "dois SRTs" in str(error)
    else:
        raise AssertionError("corpus vazio deveria falhar")


def test_csv_is_excel_friendly_and_keeps_review_fields_empty(tmp_path: Path) -> None:
    source, translated = _corpus()
    rows = build_review_rows(source, translated, samples=2)
    output = tmp_path / "review" / "ptbr.csv"

    write_review_csv(output, rows)

    raw = output.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    with output.open(encoding="utf-8-sig", newline="") as stream:
        parsed = list(csv.DictReader(stream, delimiter=";"))
    assert len(parsed) == 2
    assert parsed[0]["reviewed_ptbr"] == ""
    assert parsed[0]["semantic_verdict"] == ""


def test_cli_creates_review_csv_from_srt_files(tmp_path: Path, capsys) -> None:
    source = tmp_path / "source.srt"
    translated = tmp_path / "translated.srt"
    output = tmp_path / "review.csv"
    source.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nThank you.\n\n"
        "2\n00:00:01,000 --> 00:00:02,000\nAre you coming?\n",
        encoding="utf-8",
    )
    translated.write_text(
        "1\n00:00:00,000 --> 00:00:02,000\nObrigado. Você vem?\n",
        encoding="utf-8",
    )

    assert (
        main(
            [
                str(source),
                str(translated),
                "--output",
                str(output),
                "--samples",
                "2",
            ]
        )
        == 0
    )
    assert output.exists()
    assert "confira cada linha fonte com o áudio" in capsys.readouterr().out


def test_direct_script_execution_resolves_local_quality_parser(tmp_path: Path) -> None:
    source = tmp_path / "source.srt"
    translated = tmp_path / "translated.srt"
    output = tmp_path / "review.csv"
    source.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nThank you.\n",
        encoding="utf-8",
    )
    translated.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nObrigado.\n",
        encoding="utf-8",
    )
    repository_root = Path(__file__).resolve().parents[2]

    result = subprocess.run(
        [
            sys.executable,
            "scripts/phase8_1_translation_review.py",
            str(source),
            str(translated),
            "--output",
            str(output),
            "--samples",
            "1",
        ],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert output.exists()
