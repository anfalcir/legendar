from __future__ import annotations

import csv

import pytest
from scripts.phase6_build_manifest import parse_srt, write_manifest


def test_parse_srt_preserves_multiline_text_and_order() -> None:
    source = (
        "1\n00:00:01,000 --> 00:00:02,000\nFirst line\nSecond line\n\n"
        "2\n00:00:03,000 --> 00:00:04,000\nNext cue\n"
    )
    assert parse_srt(source) == [(1, "First line\nSecond line"), (2, "Next cue")]


@pytest.mark.parametrize(
    "source",
    [
        "1\n00:00:02,000 --> 00:00:01,000\nInvalid duration",
        "1\n00:00:01,000 --> 00:00:02,000\nText\n\n1\n00:00:03,000 --> 00:00:04,000\nDuplicate",
        "2\n00:00:01,000 --> 00:00:02,000\nStarts at two",
        "1\n00:00:01,000 --> 00:00:02,000\n   ",
    ],
)
def test_parse_srt_rejects_invalid_cues(source: str) -> None:
    with pytest.raises(ValueError):
        parse_srt(source)


def test_write_manifest_leaves_human_reference_empty(tmp_path) -> None:
    source = tmp_path / "source.srt"
    output = tmp_path / "corpus.tsv"
    source.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nHello\n", encoding="utf-8"
    )
    count, digest = write_manifest(source, output)
    with output.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    assert count == 1
    assert len(digest) == 64
    assert rows == [{"cue_id": "1", "source_text": "Hello", "reference_text": ""}]
