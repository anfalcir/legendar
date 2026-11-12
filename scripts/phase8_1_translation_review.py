#!/usr/bin/env python3
"""Gera uma planilha local para revisão humana do corpus PT-BR.

O pareamento entre SRTs é temporal, nunca por número/posição da cue. O SRT
fonte pode ser ASR automático: cada bloco exige conferência com o áudio antes
de avaliar o tradutor. O script não envia nem registra o conteúdo dos arquivos.
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path

try:
    from scripts.phase8_srt_quality import Cue, parse_srt
except ModuleNotFoundError:
    # Execução direta: o diretório scripts/ é sys.path[0].
    from phase8_srt_quality import Cue, parse_srt

_WORD_RE = re.compile(r"[\wÀ-ÿ'-]+", re.UNICODE)
_NEGATION_RE = re.compile(
    r"\b(no|not|never|none|neither|don't|doesn't|didn't|can't|cannot|won't|"
    r"isn't|aren't|wasn't|weren't|without)\b",
    re.IGNORECASE,
)
_GRATITUDE_RE = re.compile(r"\b(thank you|thanks|thankful|much obliged)\b", re.IGNORECASE)


def _format_time(seconds: float) -> str:
    millis = round(seconds * 1000)
    hours, remainder = divmod(millis, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _overlap(left: Cue, right: Cue) -> float:
    return max(0.0, min(left.end, right.end) - max(left.start, right.start))


def _format_cues(cues: list[Cue]) -> str:
    return "\n".join(
        f"[{_format_time(cue.start)}–{_format_time(cue.end)}] {cue.text}"
        for cue in cues
    )


def _risk_categories(cue: Cue) -> tuple[str, ...]:
    words = _WORD_RE.findall(cue.text)
    categories: list[str] = []
    if _GRATITUDE_RE.search(cue.text):
        categories.append("gratitude")
    if _NEGATION_RE.search(cue.text):
        categories.append("negation")
    if "?" in cue.text:
        categories.append("question")
    if len(words) <= 3:
        categories.append("short_cue")
    if any(
        token[:1].isupper() and token[1:].islower()
        for token in words[1:]
    ):
        categories.append("possible_proper_name")
    return tuple(categories)


def _select_anchors(source: list[Cue], translated: list[Cue], count: int) -> list[Cue]:
    candidates = [
        cue for cue in source if any(_overlap(cue, target) > 0 for target in translated)
    ]
    if not candidates or count <= 0:
        return []
    count = min(count, len(candidates))
    selected: list[Cue] = []
    selected_ids: set[int] = set()

    # Prioriza categorias de alto risco sem deixar a amostra concentrada no início.
    category_groups: dict[str, list[Cue]] = defaultdict(list)
    for cue in candidates:
        for category in _risk_categories(cue):
            category_groups[category].append(cue)
    for category in (
        "gratitude",
        "negation",
        "question",
        "possible_proper_name",
        "short_cue",
    ):
        group = category_groups.get(category, [])
        if not group or len(selected) >= count:
            continue
        midpoint = (len(group) - 1) / 2
        choice = group[round(midpoint)]
        if choice.index not in selected_ids:
            selected.append(choice)
            selected_ids.add(choice.index)

    # Completa a amostra distribuindo âncoras pelo eixo temporal.
    remaining = [cue for cue in candidates if cue.index not in selected_ids]
    slots = count - len(selected)
    if slots > 0 and remaining:
        if slots >= len(remaining):
            additions = remaining
        elif slots == 1:
            additions = [remaining[len(remaining) // 2]]
        else:
            positions = [
                round(i * (len(remaining) - 1) / (slots - 1))
                for i in range(slots)
            ]
            additions = [remaining[position] for position in positions]
        selected.extend(additions)

    return sorted(selected[:count], key=lambda cue: (cue.start, cue.index))


def build_review_rows(
    source: list[Cue],
    translated: list[Cue],
    *,
    samples: int = 30,
    context_cues: int = 2,
) -> list[dict[str, str]]:
    """Cria blocos com contexto, alinhados por sobreposição temporal."""
    if context_cues < 0:
        raise ValueError("context_cues não pode ser negativo.")
    if samples < 1:
        raise ValueError("samples deve ser maior que zero.")
    if not source or not translated:
        raise ValueError("Os dois SRTs precisam conter cues.")

    anchors = _select_anchors(source, translated, samples)
    rows: list[dict[str, str]] = []
    for number, anchor in enumerate(anchors, start=1):
        position = source.index(anchor)
        start_position = max(0, position - context_cues)
        end_position = min(len(source), position + context_cues + 1)
        source_window = source[start_position:end_position]
        window_start = source_window[0].start
        window_end = source_window[-1].end
        translated_window = [
            cue
            for cue in translated
            if cue.end > window_start and cue.start < window_end
        ]
        before = source_window[: position - start_position]
        after = source_window[position - start_position + 1 :]
        rows.append(
            {
                "sample_id": f"PTBR-{number:03d}",
                "risk_categories": ", ".join(_risk_categories(anchor)),
                "source_start": _format_time(anchor.start),
                "source_end": _format_time(anchor.end),
                "source_context_before": _format_cues(before),
                "source_en_asr": anchor.text,
                "source_context_after": _format_cues(after),
                "current_ptbr_contextual": _format_cues(translated_window),
                "source_asr_verified_by_audio": "",
                "reviewed_ptbr": "",
                "semantic_verdict": "",
                "protected_entities": "",
                "reviewer_notes": "",
            }
        )
    return rows


def write_review_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        raise ValueError("Nenhum bloco pareado disponível para revisão.")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_srt", type=Path, help="SRT fonte em inglês (ASR).")
    parser.add_argument("translated_srt", type=Path, help="SRT atual em PT-BR.")
    parser.add_argument("--output", type=Path, required=True, help="CSV local de revisão.")
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--context-cues", type=int, default=2)
    args = parser.parse_args(argv)

    rows = build_review_rows(
        parse_srt(args.source_srt),
        parse_srt(args.translated_srt),
        samples=args.samples,
        context_cues=args.context_cues,
    )
    write_review_csv(args.output, rows)
    print(
        f"Planilha de revisão criada: {args.output} "
        f"({len(rows)} blocos; conteúdo não foi enviado nem registrado em logs)."
    )
    print(
        "Antes de avaliar a tradução, confira cada linha fonte com o áudio; "
        "o SRT em inglês pode conter erros de ASR."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
