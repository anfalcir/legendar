#!/usr/bin/env python3
"""Avalia forced alignment contra fronteiras de palavras anotadas manualmente.

Manifesto JSONL local:
{"sample_id":"pt-01","audio":"./pt-01.wav","language":"pt","timeline_offset_seconds":0.0,
 "segments":[{"text":"Uma frase.","window_start_seconds":0.0,"window_end_seconds":2.5,
 "words":[{"word":"Uma","start":0.12,"end":0.31},{"word":"frase.","start":0.40,"end":0.88}]}]}

Os tempos de referência são globais (linha do tempo da mídia original);
janelas são locais ao WAV normalizado. O relatório nunca inclui caminho,
áudio ou texto, apenas IDs e métricas agregadas.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import sys
import time
import wave
from collections import defaultdict
from importlib.metadata import version
from pathlib import Path
from statistics import median
from typing import Any

from legendar.domain.entities.media import AudioAsset
from legendar.domain.entities.transcript import Transcript, TranscriptSegment
from legendar.domain.value_objects.language import Language
from legendar.domain.value_objects.time import TimeRange
from legendar.infrastructure.alignment.whisperx import WhisperXAligner


def _finite_number(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} deve ser numérico.")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} deve ser finito.")
    return number


def _normalized_word(value: str) -> str:
    return " ".join(value.split()).casefold()


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    if not 0.0 <= percentile <= 100.0:
        raise ValueError("Percentil deve ficar entre 0 e 100.")
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile / 100.0 * len(ordered)))
    return ordered[rank - 1]


def _error_summary(
    start_errors: list[float], end_errors: list[float]
) -> dict[str, Any]:
    boundary_errors = [*start_errors, *end_errors]

    def milliseconds(value: float | None) -> float | None:
        return None if value is None else round(value * 1000.0, 3)

    median_start = median(start_errors) if start_errors else None
    p95_start = _percentile(start_errors, 95.0)
    median_end = median(end_errors) if end_errors else None
    p95_end = _percentile(end_errors, 95.0)
    median_boundary = median(boundary_errors) if boundary_errors else None
    p95_boundary = _percentile(boundary_errors, 95.0)

    return {
        "median_start_error_ms": milliseconds(median_start),
        "p95_start_error_ms": milliseconds(p95_start),
        "median_end_error_ms": milliseconds(median_end),
        "p95_end_error_ms": milliseconds(p95_end),
        "median_boundary_error_ms": milliseconds(median_boundary),
        "p95_boundary_error_ms": milliseconds(p95_boundary),
        "provisional_targets": {
            "median_at_or_below_150ms": (
                median_start is not None
                and median_end is not None
                and median_start <= 0.150
                and median_end <= 0.150
            ),
            "p95_at_or_below_350ms": (
                p95_start is not None
                and p95_end is not None
                and p95_start <= 0.350
                and p95_end <= 0.350
            ),
            "both_met": (
                median_start is not None
                and median_end is not None
                and p95_start is not None
                and p95_end is not None
                and median_start <= 0.150
                and median_end <= 0.150
                and p95_start <= 0.350
                and p95_end <= 0.350
            ),
        },
    }


def _read_manifest(manifest: Path) -> list[dict[str, Any]]:
    manifest = manifest.expanduser().resolve()
    if not manifest.is_file():
        raise FileNotFoundError(f"Manifesto não encontrado: {manifest}")

    samples: list[dict[str, Any]] = []
    with manifest.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Linha {line_number}: JSON inválido: {exc.msg}."
                ) from exc
            if not isinstance(row, dict):
                raise ValueError(f"Linha {line_number}: cada linha deve ser um objeto.")

            sample_id = row.get("sample_id")
            if not isinstance(sample_id, str) or not sample_id.strip():
                raise ValueError(f"Linha {line_number}: sample_id é obrigatório.")
            language = Language.parse(row.get("language"))
            if language is None:
                raise ValueError(
                    f"Linha {line_number}: idioma deve ser pt/pt-BR ou en/en-US."
                )

            audio_value = row.get("audio")
            if not isinstance(audio_value, str) or not audio_value.strip():
                raise ValueError(f"Linha {line_number}: áudio é obrigatório.")
            audio_path = Path(audio_value).expanduser()
            if not audio_path.is_absolute():
                audio_path = manifest.parent / audio_path
            audio_path = audio_path.resolve()
            if not audio_path.is_file():
                raise FileNotFoundError(
                    f"Linha {line_number}: arquivo de áudio não encontrado."
                )

            offset = _finite_number(
                row.get("timeline_offset_seconds", 0.0),
                label=f"Linha {line_number}: timeline_offset_seconds",
            )
            raw_segments = row.get("segments")
            if not isinstance(raw_segments, list) or not raw_segments:
                raise ValueError(
                    f"Linha {line_number}: segments deve conter pelo menos um item."
                )

            segments: list[dict[str, Any]] = []
            for segment_index, segment in enumerate(raw_segments):
                if not isinstance(segment, dict):
                    raise ValueError(
                        f"Linha {line_number}, segmento {segment_index}: objeto inválido."
                    )
                text = segment.get("text")
                if not isinstance(text, str) or not text.strip():
                    raise ValueError(
                        f"Linha {line_number}, segmento {segment_index}: texto obrigatório."
                    )
                window_start = _finite_number(
                    segment.get("window_start_seconds"),
                    label="window_start_seconds",
                )
                window_end = _finite_number(
                    segment.get("window_end_seconds"),
                    label="window_end_seconds",
                )
                window = TimeRange(window_start, window_end)
                expected_tokens = text.split()
                raw_words = segment.get("words")
                if not isinstance(raw_words, list) or len(raw_words) != len(
                    expected_tokens
                ):
                    raise ValueError(
                        f"Linha {line_number}, segmento {segment_index}: informe "
                        "uma palavra de referência para cada token separado por espaço."
                    )

                expected_words: list[dict[str, Any]] = []
                for word_index, (expected, raw_word) in enumerate(
                    zip(expected_tokens, raw_words, strict=True)
                ):
                    if not isinstance(raw_word, dict):
                        raise ValueError(
                            f"Linha {line_number}, segmento {segment_index}, "
                            f"palavra {word_index}: objeto inválido."
                        )
                    word = raw_word.get("word")
                    if not isinstance(word, str) or _normalized_word(
                        word
                    ) != _normalized_word(expected):
                        raise ValueError(
                            f"Linha {line_number}, segmento {segment_index}, "
                            f"palavra {word_index}: texto de referência não corresponde "
                            "ao token do segmento."
                        )
                    start = _finite_number(raw_word.get("start"), label="word.start")
                    end = _finite_number(raw_word.get("end"), label="word.end")
                    if start < 0 or end <= start:
                        raise ValueError(
                            f"Linha {line_number}, segmento {segment_index}, "
                            f"palavra {word_index}: intervalo inválido."
                        )
                    expected_words.append(
                        {"word": expected, "start": start, "end": end}
                    )
                segments.append(
                    {
                        "text": text,
                        "window": window,
                        "words": expected_words,
                    }
                )

            samples.append(
                {
                    "sample_id": sample_id.strip(),
                    "language": language,
                    "audio_path": audio_path,
                    "timeline_offset_seconds": offset,
                    "segments": segments,
                }
            )

    if not samples:
        raise ValueError("O manifesto não contém amostras.")
    return samples


def _audio_asset(sample: dict[str, Any]) -> AudioAsset:
    path: Path = sample["audio_path"]
    try:
        with wave.open(str(path), "rb") as source:
            channels = source.getnchannels()
            sample_rate = source.getframerate()
            sample_width = source.getsampwidth()
            compression = source.getcomptype()
            frames = source.getnframes()
    except (OSError, wave.Error) as exc:
        raise ValueError(
            f"Áudio inválido para a amostra {sample['sample_id']}."
        ) from exc

    if (
        channels != 1
        or sample_rate != 16_000
        or sample_width != 2
        or compression != "NONE"
        or frames < 1
    ):
        raise ValueError(
            f"A amostra {sample['sample_id']} precisa ser WAV PCM s16le mono/16 kHz."
        )
    return AudioAsset(
        path=str(path),
        sample_rate_hz=16_000,
        channels=1,
        sample_format="pcm_s16le",
        duration_seconds=frames / 16_000,
        timeline_start_seconds=sample["timeline_offset_seconds"],
        timeline_offset_source="annotated_manifest.timeline_offset_seconds",
    )


class _ProgressSink:
    def report(self, fraction: float, message: str = "") -> None:
        return None


def evaluate_manifest(
    manifest: Path,
    *,
    models_dir: Path = Path(".cache/phase5"),
    device: str = "auto",
) -> dict[str, Any]:
    samples = _read_manifest(manifest)
    aligner = WhisperXAligner(models_dir, device=device)
    started = time.perf_counter()

    results: list[dict[str, Any]] = []
    start_errors_by_language: dict[str, list[float]] = defaultdict(list)
    end_errors_by_language: dict[str, list[float]] = defaultdict(list)
    aggregate_by_language: dict[str, dict[str, int]] = {}

    for sample in samples:
        audio = _audio_asset(sample)
        timeline_start = audio.timeline_start_seconds
        timeline_end = timeline_start + audio.duration_seconds
        for segment in sample["segments"]:
            if segment["window"].end > audio.duration_seconds:
                raise ValueError(
                    f"Janela de busca fora da duração da amostra {sample['sample_id']}."
                )
            for reference_word in segment["words"]:
                if (
                    reference_word["start"] < timeline_start
                    or reference_word["end"] > timeline_end
                ):
                    raise ValueError(
                        f"Timestamp de referência fora da mídia em {sample['sample_id']}."
                    )
        transcript = Transcript(
            segments=tuple(
                TranscriptSegment(
                    text=segment["text"],
                    alignment_window=segment["window"],
                )
                for segment in sample["segments"]
            ),
            language=sample["language"],
            model_name="human-reference",
            model_revision=None,
        )
        alignment = aligner.align(audio, transcript, progress=_ProgressSink())

        sample_start_errors: list[float] = []
        sample_end_errors: list[float] = []
        matched = 0
        reference_words = 0
        invalid = 0
        for segment_index, expected_segment in enumerate(sample["segments"]):
            actual_segment = alignment.transcript.segments[segment_index]
            expected_words = expected_segment["words"]
            actual_words = actual_segment.words
            reference_words += len(expected_words)

            for word_index, expected in enumerate(expected_words):
                actual = (
                    actual_words[word_index] if word_index < len(actual_words) else None
                )
                if (
                    actual is None
                    or _normalized_word(actual.text)
                    != _normalized_word(expected["word"])
                    or actual.range is None
                ):
                    continue

                start_error = abs(actual.range.start - expected["start"])
                end_error = abs(actual.range.end - expected["end"])
                sample_start_errors.append(start_error)
                sample_end_errors.append(end_error)
                matched += 1

                global_start = sample["timeline_offset_seconds"]
                global_end = global_start + audio.duration_seconds
                if (
                    actual.range.start < global_start - 1e-6
                    or actual.range.end > global_end + 1e-6
                    or actual.range.end <= actual.range.start
                ):
                    invalid += 1

        language_code = sample["language"].value
        start_errors_by_language[language_code].extend(sample_start_errors)
        end_errors_by_language[language_code].extend(sample_end_errors)
        language_summary = aggregate_by_language.setdefault(
            language_code,
            {
                "samples": 0,
                "reference_words": 0,
                "matched_words": 0,
                "invalid_timestamps": 0,
            },
        )
        language_summary["samples"] += 1
        language_summary["reference_words"] += reference_words
        language_summary["matched_words"] += matched
        language_summary["invalid_timestamps"] += invalid

        results.append(
            {
                "sample_id": sample["sample_id"],
                "language": language_code,
                "reference_words": reference_words,
                "matched_words": matched,
                "unmatched_words": reference_words - matched,
                "coverage": round(matched / max(reference_words, 1), 6),
                "invalid_timestamps": invalid,
                "errors": _error_summary(sample_start_errors, sample_end_errors),
                "diagnostic_issues": list(alignment.diagnostics.issues),
            }
        )

    summary: dict[str, Any] = {}
    for language, counts in aggregate_by_language.items():
        starts = start_errors_by_language[language]
        ends = end_errors_by_language[language]
        reference_words = counts["reference_words"]
        summary[language] = {
            **counts,
            "coverage": round(counts["matched_words"] / max(reference_words, 1), 6),
            "errors": _error_summary(starts, ends),
        }

    total_samples = len(samples)
    total_reference_words = sum(
        value["reference_words"] for value in aggregate_by_language.values()
    )
    total_matched_words = sum(
        value["matched_words"] for value in aggregate_by_language.values()
    )
    all_starts = [
        value for errors in start_errors_by_language.values() for value in errors
    ]
    all_ends = [
        value for errors in end_errors_by_language.values() for value in errors
    ]

    return {
        "schema_version": 1,
        "status": "completed",
        "classification": "human_annotated_alignment_evaluation_not_automatic_acceptance",
        "acceptance_decision": "requires_human_review",
        "scope": (
            "WhisperX forced alignment against manually reviewed word boundaries. "
            "Reference word times are on the original media timeline; alignment windows "
            "are local to the normalized WAV."
        ),
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "torch": str(__import__("torch").__version__),
            "whisperx": version("whisperx"),
            "device": aligner.loaded_device or device,
            "logical_cpus": __import__("os").cpu_count(),
            "peak_rss_bytes": _peak_rss_bytes(),
            "wall_seconds": round(time.perf_counter() - started, 3),
        },
        "corpus": {
            "samples": total_samples,
            "languages": sorted(summary),
            "reference_words": total_reference_words,
            "matched_words": total_matched_words,
            "coverage": round(
                total_matched_words / max(total_reference_words, 1), 6
            ),
        },
        "overall_errors": _error_summary(all_starts, all_ends),
        "by_language": summary,
        "samples": results,
        "provisional_limits": {
            "median_boundary_error_ms": 150,
            "p95_boundary_error_ms": 350,
            "invalid_timestamp_count": 0,
            "unaligned_words_must_remain_visible": True,
            "note": (
                "Targets from the master plan are provisional. Report does not "
                "approve product acceptance automatically."
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--models-dir", type=Path, default=Path(".cache/phase5"))
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--output", type=Path, default=Path("phase5-annotated-alignment.json"))
    args = parser.parse_args()

    try:
        report = evaluate_manifest(
            args.manifest,
            models_dir=args.models_dir,
            device=args.device,
        )
    except Exception as exc:  # noqa: BLE001 - CLI precisa materializar falha no relatório
        failure = {
            "schema_version": 1,
            "status": "failed",
            "classification": "human_annotated_alignment_evaluation_not_automatic_acceptance",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(failure, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(failure, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def _peak_rss_bytes() -> int | None:
    try:
        import resource

        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except (ImportError, AttributeError, OSError):
        return None
    return int(peak * 1024 if sys.platform.startswith("linux") else peak)


if __name__ == "__main__":
    raise SystemExit(main())
