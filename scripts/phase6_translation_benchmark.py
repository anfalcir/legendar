#!/usr/bin/env python3
"""Benchmark pareado de tradução NLLB/Gemini sem persistir textos traduzidos.

Manifesto TSV:
cue_id<TAB>source_text<TAB>reference_text
A referência humana é opcional; sem ela, WER/CER permanecem null.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

from legendar.application.pipeline.translation import TranslationUnit
from legendar.domain.value_objects.language import Language
from legendar.infrastructure.translation.gemini import GeminiTranslator
from legendar.infrastructure.translation.nllb import NllbTranslator


class NullProgress:
    def report(self, _fraction: float, _message: str = "") -> None:
        pass


def load_manifest(path: Path) -> tuple[tuple[TranslationUnit, ...], tuple[str, ...] | None]:
    """Carrega cues e referências humanas, sem normalizar ou reordenar IDs."""
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        required = {"cue_id", "source_text"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError("Manifesto precisa de cue_id e source_text.")
        units: list[TranslationUnit] = []
        references: list[str] = []
        reference_state: list[bool] = []
        seen: set[int] = set()
        for row_number, row in enumerate(reader, start=2):
            try:
                cue_id = int(row["cue_id"])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"cue_id inválido na linha {row_number}.") from exc
            if cue_id < 1 or cue_id in seen:
                raise ValueError(f"cue_id duplicado ou inválido na linha {row_number}.")
            seen.add(cue_id)
            source_text = (row.get("source_text") or "").strip()
            if not source_text:
                raise ValueError(f"source_text vazio na linha {row_number}.")
            units.append(TranslationUnit(index=cue_id, text=source_text))
            reference = (row.get("reference_text") or "").strip()
            references.append(reference)
            reference_state.append(bool(reference))
    if not units:
        raise ValueError("Manifesto sem cues.")
    if any(reference_state) and not all(reference_state):
        raise ValueError("Preencha reference_text em todas as linhas ou deixe todas vazias.")
    return tuple(units), tuple(references) if all(reference_state) else None


def _translator(backend: str, models_dir: Path) -> Any:
    if backend == "nllb":
        return NllbTranslator.from_environment(models_dir)
    if backend == "gemini":
        return GeminiTranslator.from_environment(models_dir)
    raise ValueError(f"Backend desconhecido: {backend}")


def _score(references: tuple[str, ...] | None, hypotheses: tuple[str, ...]) -> tuple[float | None, float | None]:
    if references is None:
        return None, None
    try:
        from jiwer import cer, wer
    except ImportError as exc:
        raise RuntimeError(
            "Instale o grupo phase0 para calcular WER/CER (dependência jiwer)."
        ) from exc
    return float(wer(list(references), list(hypotheses))), float(
        cer(list(references), list(hypotheses))
    )


def run_benchmark(
    *,
    units: tuple[TranslationUnit, ...],
    references: tuple[str, ...] | None,
    source_language: Language,
    target_language: Language,
    backends: tuple[str, ...],
    models_dir: Path,
    repeats: int,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for backend in backends:
        translator = _translator(backend, models_dir)
        run_seconds: list[float] = []
        last_wer: float | None = None
        last_cer: float | None = None
        for _ in range(repeats):
            started = time.perf_counter()
            result = translator.translate(
                units,
                source_language=source_language,
                target_language=target_language,
                progress=NullProgress(),
            )
            elapsed = time.perf_counter() - started
            if len(result.texts) != len(units):
                raise RuntimeError(f"{backend} violou a correspondência 1:1.")
            run_seconds.append(elapsed)
            last_wer, last_cer = _score(references, result.texts)
        snapshot = translator.performance_snapshot()
        config = snapshot.get("configuration", {})
        results.append(
            {
                "backend": backend,
                "model": config.get("model"),
                "batch_size": config.get("batch_size"),
                "units": len(units),
                "repeats": repeats,
                "run_seconds": run_seconds,
                "median_seconds": statistics.median(run_seconds),
                "units_per_second": len(units) / statistics.median(run_seconds),
                "wer": last_wer,
                "cer": last_cer,
                "performance": snapshot,
            }
        )
    return {
        "schema_version": 1,
        "source_language": source_language.value,
        "target_language": target_language.value,
        "units": len(units),
        "human_references_available": references is not None,
        "results": results,
        "privacy": {
            "contains_source_text": False,
            "contains_translations": False,
            "contains_human_references": False,
            "contains_api_keys": False,
        },
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-language", choices=("pt", "en"), required=True)
    parser.add_argument("--target-language", choices=("pt", "en"), required=True)
    parser.add_argument("--backends", default="nllb,gemini")
    parser.add_argument("--models-dir", type=Path, default=Path.home() / ".cache/legendar/models")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.repeats < 1 or args.repeats > 10:
        print("--repeats deve estar entre 1 e 10.", file=sys.stderr)
        return 2
    try:
        units, references = load_manifest(args.manifest)
        backends = tuple(dict.fromkeys(part.strip() for part in args.backends.split(",") if part.strip()))
        if not backends or any(name not in {"nllb", "gemini"} for name in backends):
            raise ValueError("Use backends nllb,gemini.")
        result = run_benchmark(
            units=units,
            references=references,
            source_language=Language(args.source_language),
            target_language=Language(args.target_language),
            backends=backends,
            models_dir=args.models_dir,
            repeats=args.repeats,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception as exc:
        print(f"Benchmark de tradução não concluído: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(
        f"Benchmark concluído: {result['units']} cues, "
        f"{len(result['results'])} backend(s). Relatório sanitizado: {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
