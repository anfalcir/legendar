#!/usr/bin/env python3
"""Gera manifesto TSV local para benchmark pareado de tradução a partir de SRT.

O arquivo de saída contém texto-fonte e referência humana vazia. Não versionar
o manifesto: ele pode conter conteúdo protegido da mídia.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
import sys
from pathlib import Path

TIMESTAMP = re.compile(
    r"^(?P<h>\d{2,}):(?P<m>[0-5]\d):(?P<s>[0-5]\d),(?P<ms>\d{3})$"
)
TIME_LINE = re.compile(
    r"^(\d{2,}:[0-5]\d:[0-5]\d,\d{3})\s+-->\s+"
    r"(\d{2,}:[0-5]\d:[0-5]\d,\d{3})(?:\s+.*)?$"
)


def _milliseconds(value: str) -> int:
    match = TIMESTAMP.fullmatch(value)
    if match is None:
        raise ValueError(f"timestamp inválido: {value!r}")
    hours, minutes, seconds, millis = (int(part) for part in match.groups())
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + millis


def parse_srt(content: str) -> list[tuple[int, str]]:
    """Lê cues SRT sem alterar o texto nem descartar cues multilinha."""
    normalized = (
        content.lstrip("\ufeff")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )
    blocks = re.split(r"\n[ \t]*\n", normalized.strip())
    cues: list[tuple[int, str]] = []
    seen: set[int] = set()

    for block_number, block in enumerate(blocks, start=1):
        lines = block.split("\n")
        if len(lines) < 3 or not lines[0].strip().isdigit():
            raise ValueError(f"bloco SRT {block_number}: estrutura de cue inválida")
        cue_id = int(lines[0].strip())
        if cue_id < 1 or cue_id in seen:
            raise ValueError(f"bloco SRT {block_number}: ID duplicado ou inválido")
        seen.add(cue_id)

        time_match = TIME_LINE.fullmatch(lines[1].strip())
        if time_match is None:
            raise ValueError(f"cue {cue_id}: linha de timestamps inválida")
        start, end = time_match.groups()
        if _milliseconds(end) <= _milliseconds(start):
            raise ValueError(f"cue {cue_id}: fim deve ser posterior ao início")

        text = "\n".join(lines[2:]).strip()
        if not text:
            raise ValueError(f"cue {cue_id}: texto vazio")
        cues.append((cue_id, text))

    if not cues:
        raise ValueError("SRT sem cues")
    actual_ids = [cue_id for cue_id, _ in cues]
    expected_ids = list(range(1, len(cues) + 1))
    if actual_ids != expected_ids:
        raise ValueError("IDs devem estar em ordem sequencial começando em 1")
    return cues


def write_manifest(source: Path, output: Path) -> tuple[int, str]:
    raw = source.read_bytes()
    content = raw.decode("utf-8-sig")
    cues = parse_srt(content)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        writer.writerow(("cue_id", "source_text", "reference_text"))
        for cue_id, text in cues:
            writer.writerow((cue_id, text, ""))
    return len(cues), hashlib.sha256(raw).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, required=True, help="SRT original em inglês"
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="TSV local de benchmark"
    )
    args = parser.parse_args()
    try:
        count, digest = write_manifest(args.source, args.output)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"Manifesto não gerado: {exc}", file=sys.stderr)
        return 1
    print(f"Manifesto local gerado: {count} cues; SHA-256 do SRT: {digest}")
    print("reference_text foi deixado vazio; nenhuma referência humana foi criada.")
    print("Não versione nem compartilhe o TSV: ele contém texto-fonte da mídia.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
