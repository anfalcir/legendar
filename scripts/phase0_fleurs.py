"""Helpers for reading the pinned, headerless Google FLEURS TSV schema."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import TextIO


def parse_reference_rows(
    handle: TextIO,
    samples_per_language: int,
) -> list[dict[str, str]]:
    """Parse FLEURS test.tsv rows: id, path, raw_transcription, ..."""
    if samples_per_language < 1:
        raise ValueError("samples_per_language must be positive")

    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    reader = csv.reader(handle, delimiter="\t")
    for values in reader:
        if len(values) < 3:
            continue
        utterance_id = str(values[0]).strip()
        filename = str(values[1]).strip()
        reference = str(values[2]).strip()
        if not utterance_id or not filename or not reference:
            continue
        if utterance_id in seen:
            continue
        seen.add(utterance_id)
        rows.append({
            "id": utterance_id,
            "filename": Path(filename).name,
            "reference": reference,
        })
        if len(rows) >= samples_per_language:
            break
    return rows
