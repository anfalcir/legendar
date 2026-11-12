#!/usr/bin/env python3
"""Avaliação determinística de legibilidade e integridade estrutural de SRT.

Uso:
    python scripts/phase8_srt_quality.py resultado.srt
    python scripts/phase8_srt_quality.py resultado.srt --json
    python scripts/phase8_srt_quality.py resultado.srt --compare baseline.srt

O script não corrige o SRT. Ele mede e retorna código diferente de zero quando
um gate estrutural configurável falha. A homologação audiovisual continua
exigindo inspeção humana no player e referência temporal independente.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
from dataclasses import dataclass
from pathlib import Path

TIMESTAMP_RE = re.compile(
    r"^(?P<start>\d{2}:\d{2}:\d{2},\d{3})\s+-->\s+"
    r"(?P<end>\d{2}:\d{2}:\d{2},\d{3})"
)
CONNECTORS = {
    "a", "ao", "aos", "as", "com", "da", "das", "de", "do", "dos", "e",
    "em", "na", "nas", "no", "nos", "ou", "para", "pela", "pelas", "pelo",
    "pelos", "por", "que", "se", "sem", "sob", "sobre", "the", "an", "and",
    "at", "by", "for", "from", "in", "into", "of", "on", "or", "to", "with",
)


@dataclass(frozen=True, slots=True)
class Cue:
    index: int
    start: float
    end: float
    text: str
    lines: tuple[str, ...]

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def chars_per_second(self) -> float:
        return len(self.text) / self.duration if self.duration > 0 else float("inf")


def _timestamp(value: str) -> float:
    hours, minutes, rest = value.split(":")
    seconds, millis = rest.split(",")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000


def parse_srt(path: Path) -> list[Cue]:
    content = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", content.strip())
    cues: list[Cue] = []
    for block in blocks:
        lines = [line.strip("\ufeff") for line in block.split("\n")]
        if len(lines) < 3:
            raise ValueError(f"Bloco SRT inválido em {path}: menos de 3 linhas.")
        try:
            index = int(lines[0])
        except ValueError as exc:
            raise ValueError(f"Índice SRT inválido: {lines[0]!r}") from exc
        match = TIMESTAMP_RE.match(lines[1])
        if not match:
            raise ValueError(f"Timestamp SRT inválido na cue {index}: {lines[1]!r}")
        start = _timestamp(match.group("start"))
        end = _timestamp(match.group("end"))
        if end <= start:
            raise ValueError(f"Cue {index} tem duração não positiva.")
        cue_lines = tuple(line.strip() for line in lines[2:] if line.strip())
        text = " ".join(cue_lines)
        if not text:
            raise ValueError(f"Cue {index} sem texto.")
        cues.append(Cue(index=index, start=start, end=end, text=text, lines=cue_lines))
    return cues


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    rank = max(1, int((percentile / 100.0) * len(ordered) + 0.999999))
    return ordered[min(rank, len(ordered)) - 1]


def analyze(cues: list[Cue]) -> dict[str, object]:
    durations = [cue.duration for cue in cues]
    cps = [cue.chars_per_second for cue in cues]
    short = [cue.index for cue in cues if cue.duration < 1.0]
    long = [cue.index for cue in cues if cue.duration > 7.0]
    wide = [cue.index for cue in cues if any(len(line) > 42 for line in cue.lines)]
    overflow = [cue.index for cue in cues if cue.chars_per_second > 17.0]
    overlaps: list[int] = []
    fragments: list[int] = []
    duplicates: list[int] = []
    for previous, current in zip(cues, cues[1:], strict=False):
        if current.start < previous.end:
            overlaps.append(current.index)
        if current.text.casefold() == previous.text.casefold() and current.start - previous.end <= 1.0:
            duplicates.append(current.index)
        previous_last = previous.text.split()[-1].casefold().strip(".,;:!?")
        current_first = current.text[:1]
        if previous_last in CONNECTORS and current_first.islower():
            fragments.append(current.index)

    gaps = [
        current.start - previous.end
        for previous, current in zip(cues, cues[1:], strict=False)
        if current.start >= previous.end
    ]
    return {
        "cue_count": len(cues),
        "duration_seconds": round(sum(durations), 3),
        "median_duration_seconds": round(statistics.median(durations), 3),
        "p95_cps": round(_percentile(cps, 95), 3),
        "max_cps": round(max(cps, default=0.0), 3),
        "short_cues": short,
        "long_cues": long,
        "wide_cues": wide,
        "reading_speed_cues": overflow,
        "overlap_cues": overlaps,
        "duplicate_cues": duplicates,
        "syntactic_fragment_cues": fragments,
        "p95_gap_seconds": round(_percentile(gaps, 95), 3),
        "first_start_seconds": cues[0].start if cues else None,
        "last_end_seconds": cues[-1].end if cues else None,
    }


def compare(candidate: dict[str, object], baseline: dict[str, object]) -> dict[str, object]:
    baseline_count = int(baseline["cue_count"])
    candidate_count = int(candidate["cue_count"])
    return {
        "cue_count_delta": candidate_count - baseline_count,
        "cue_count_ratio": (
            round(candidate_count / baseline_count, 4) if baseline_count else None
        ),
        "short_cues_delta": len(candidate["short_cues"]) - len(baseline["short_cues"]),
        "reading_speed_cues_delta": (
            len(candidate["reading_speed_cues"]) - len(baseline["reading_speed_cues"])
        ),
        "fragmentation_delta": (
            len(candidate["syntactic_fragment_cues"])
            - len(baseline["syntactic_fragment_cues"])
        ),
        "flicker_proxy_delta": (
            len(candidate["short_cues"]) - len(baseline["short_cues"])
        ),
    }


def _gate(metrics: dict[str, object]) -> list[str]:
    failures: list[str] = []
    if int(metrics["cue_count"]) == 0:
        failures.append("SRT vazio")
    if metrics["overlap_cues"]:
        failures.append(f"há {len(metrics['overlap_cues'])} sobreposição(ões)")
    if metrics["wide_cues"]:
        failures.append(f"há {len(metrics['wide_cues'])} cue(s) acima de 42 caracteres por linha")
    if metrics["reading_speed_cues"]:
        failures.append(f"há {len(metrics['reading_speed_cues'])} cue(s) acima de 17 CPS")
    if metrics["long_cues"]:
        failures.append(f"há {len(metrics['long_cues'])} cue(s) acima de 7 s")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("srt", type=Path)
    parser.add_argument("--compare", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    candidate = analyze(parse_srt(args.srt))
    payload: dict[str, object] = {"candidate": candidate}
    if args.compare is not None:
        baseline = analyze(parse_srt(args.compare))
        payload["baseline"] = baseline
        payload["comparison"] = compare(candidate, baseline)
    failures = _gate(candidate)
    payload["gate"] = {"status": "PASS" if not failures else "FAIL", "failures": failures}

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Cues: {candidate['cue_count']}")
        print(f"Duração coberta: {candidate['duration_seconds']} s")
        print(f"Duração mediana: {candidate['median_duration_seconds']} s")
        print(f"P95 CPS: {candidate['p95_cps']}")
        print(f"CPS máximo: {candidate['max_cps']}")
        print(
            "Curta/longa/rápida/larga/sobreposta/duplicada/fragmentada: "
            f"{len(candidate['short_cues'])}/"
            f"{len(candidate['long_cues'])}/"
            f"{len(candidate['reading_speed_cues'])}/"
            f"{len(candidate['wide_cues'])}/"
            f"{len(candidate['overlap_cues'])}/"
            f"{len(candidate['duplicate_cues'])}/"
            f"{len(candidate['syntactic_fragment_cues'])}"
        )
        print(f"Gate estrutural: {'PASS' if not failures else 'FAIL'}")
        for failure in failures:
            print(f"  - {failure}")
        if "comparison" in payload:
            print(f"Comparação: {json.dumps(payload['comparison'], ensure_ascii=False)}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
