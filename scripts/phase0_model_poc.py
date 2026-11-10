#!/usr/bin/env python3
"""Small reproducible WhisperX smoke benchmark on public FLEURS audio.

This is a pipeline/compatibility probe, not a statistically valid product
acceptance benchmark. It records WER against public references, alignment
coverage, runtime, and process peak RSS. Audio is downloaded from a pinned
public dataset revision and is not uploaded with the JSON report.
"""
from __future__ import annotations

import argparse
import csv
import gc
import io
import json
import math
import os
import platform
import re
import resource
import sys
import tarfile
import time
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
import torch
import whisperx
from huggingface_hub import hf_hub_download
from jiwer import wer


DATASET = "google/fleurs"
DATASET_REVISION = "c176a772dc5e1ced954fdd22af1a3bf5be2cbe6e"
LANGUAGES = {
    "pt_br": {"whisper": "pt", "label": "Portuguese (Brazil)"},
    "en_us": {"whisper": "en", "label": "English (United States)"},
}


def _normalize_text(value: str) -> str:
    value = value.casefold()
    value = re.sub(r"[^\w\s']", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


def _load_reference_rows(
    config: str,
    cache_dir: Path,
    samples_per_language: int,
) -> list[dict[str, str]]:
    tsv_path = hf_hub_download(
        repo_id=DATASET,
        repo_type="dataset",
        filename=f"data/{config}/test.tsv",
        revision=DATASET_REVISION,
        cache_dir=str(cache_dir),
    )
    rows: list[dict[str, str]] = []
    seen_utterances: set[str] = set()
    with Path(tsv_path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\\t")
        # FLEURS TSVs are headerless. Stable columns begin with id, path,
        # raw_transcription, transcription, normalized_transcription.
        for values in reader:
            if len(values) < 3:
                continue
            utterance_id = str(values[0]).strip()
            filename = str(values[1]).strip()
            reference = str(values[2]).strip()
            if not utterance_id or not filename or not reference:
                continue
            if utterance_id in seen_utterances:
                continue
            seen_utterances.add(utterance_id)
            rows.append(
                {
                    "id": utterance_id,
                    "filename": Path(filename).name,
                    "reference": reference,
                }
            )
            if len(rows) >= samples_per_language:
                break

    if len(rows) < samples_per_language:
        raise RuntimeError(
            f"FLEURS {config} provided only {len(rows)} valid rows; "
            f"{samples_per_language} requested"
        )
    return rows

def _read_audio(audio_bytes: bytes) -> tuple[np.ndarray, int]:
    waveform, sample_rate = sf.read(io.BytesIO(audio_bytes), dtype="float32")
    waveform = np.asarray(waveform, dtype=np.float32)
    if waveform.ndim == 2:
        waveform = waveform.mean(axis=1, dtype=np.float32)
    if waveform.ndim != 1 or waveform.size == 0:
        raise RuntimeError("FLEURS audio must be a non-empty mono waveform")
    if int(sample_rate) != 16000:
        raise RuntimeError(f"Expected 16 kHz FLEURS audio, received {sample_rate} Hz")
    return waveform, int(sample_rate)


def _read_selected_audio(
    config: str,
    cache_dir: Path,
    rows: list[dict[str, str]],
) -> dict[str, bytes]:
    archive_path = hf_hub_download(
        repo_id=DATASET,
        repo_type="dataset",
        filename=f"data/{config}/audio/test.tar.gz",
        revision=DATASET_REVISION,
        cache_dir=str(cache_dir),
    )
    wanted = {row["filename"] for row in rows}
    found: dict[str, bytes] = {}
    with tarfile.open(archive_path, mode="r:gz") as archive:
        for member in archive:
            if not member.isfile() or Path(member.name).name not in wanted:
                continue
            filename = Path(member.name).name
            source = archive.extractfile(member)
            if source is None:
                continue
            found[filename] = source.read()
            if wanted.issubset(found):
                break

    missing = wanted.difference(found)
    if missing:
        raise RuntimeError(
            f"FLEURS archive {config} is missing expected audio files: {sorted(missing)}"
        )
    return found


def _peak_rss_bytes() -> int | None:
    try:
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except (AttributeError, OSError):
        return None
    # Linux reports KiB; macOS reports bytes. CI for this benchmark is Linux.
    return int(peak * 1024 if sys.platform.startswith("linux") else peak)


def run_benchmark(
    model_name: str = "tiny",
    samples_per_language: int = 2,
    cache_dir: Path | None = None,
) -> dict[str, Any]:
    if samples_per_language < 1 or samples_per_language > 10:
        raise ValueError("samples_per_language must be between 1 and 10")

    cache_dir = cache_dir or Path(".cache/phase0")
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = cache_dir.resolve()
    os.environ["HF_HOME"] = str(cache_dir)
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

    started = time.perf_counter()
    corpus: dict[str, tuple[list[dict[str, str]], dict[str, bytes]]] = {}
    for config in LANGUAGES:
        rows = _load_reference_rows(config, cache_dir, samples_per_language)
        audio = _read_selected_audio(config, cache_dir, rows)
        corpus[config] = (rows, audio)

    model = whisperx.load_model(
        model_name,
        device="cpu",
        compute_type="int8",
        language=None,
    )

    records: list[dict[str, Any]] = []
    for config, language_info in LANGUAGES.items():
        rows, audio_files = corpus[config]
        align_model, align_metadata = whisperx.load_align_model(
            language_code=language_info["whisper"],
            device="cpu",
        )

        for row in rows:
            waveform, sample_rate = _read_audio(audio_files[row["filename"]])
            duration = float(waveform.size / sample_rate)

            transcribe_started = time.perf_counter()
            recognized = model.transcribe(
                waveform,
                batch_size=1,
                language=language_info["whisper"],
            )
            transcribe_seconds = time.perf_counter() - transcribe_started

            recognized_text = " ".join(
                segment.get("text", "").strip()
                for segment in recognized.get("segments", [])
            ).strip()
            normalized_reference = _normalize_text(row["reference"])
            normalized_hypothesis = _normalize_text(recognized_text)
            error_rate = float(wer(normalized_reference, normalized_hypothesis))

            align_started = time.perf_counter()
            aligned = whisperx.align(
                recognized.get("segments", []),
                align_model,
                align_metadata,
                waveform,
                device="cpu",
                return_char_alignments=False,
            )
            align_seconds = time.perf_counter() - align_started

            words = [
                word
                for segment in aligned.get("segments", [])
                for word in segment.get("words", [])
            ]
            valid_timed_words = [
                word
                for word in words
                if isinstance(word.get("start"), (int, float))
                and isinstance(word.get("end"), (int, float))
                and math.isfinite(float(word["start"]))
                and math.isfinite(float(word["end"]))
                and 0 <= float(word["start"]) < float(word["end"]) <= duration + 0.25
            ]
            records.append(
                {
                    "dataset": DATASET,
                    "dataset_revision": DATASET_REVISION,
                    "config": config,
                    "language": language_info["whisper"],
                    "sample_id": row["id"],
                    "audio_duration_seconds": round(duration, 3),
                    "reference_word_count": len(normalized_reference.split()),
                    "hypothesis_word_count": len(normalized_hypothesis.split()),
                    "wer": round(error_rate, 6),
                    "transcription_seconds": round(transcribe_seconds, 3),
                    "alignment_seconds": round(align_seconds, 3),
                    "real_time_factor": round(
                        (transcribe_seconds + align_seconds) / max(duration, 0.001), 3
                    ),
                    "aligned_word_count": len(valid_timed_words),
                    "unaligned_or_invalid_word_count": max(0, len(words) - len(valid_timed_words)),
                }
            )

        del align_model, align_metadata
        gc.collect()

    del model
    gc.collect()

    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(record["config"], []).append(record)

    summary = {}
    for config, items in grouped.items():
        summary[config] = {
            "samples": len(items),
            "mean_wer": round(sum(item["wer"] for item in items) / len(items), 6),
            "mean_real_time_factor": round(
                sum(item["real_time_factor"] for item in items) / len(items), 3
            ),
            "aligned_word_count": sum(item["aligned_word_count"] for item in items),
            "unaligned_or_invalid_word_count": sum(
                item["unaligned_or_invalid_word_count"] for item in items
            ),
            "reference_word_count": sum(item["reference_word_count"] for item in items),
        }

    return {
        "schema_version": 1,
        "status": "completed",
        "classification": "smoke_benchmark_not_product_acceptance",
        "dataset": {
            "id": DATASET,
            "revision": DATASET_REVISION,
            "license": "CC-BY-4.0",
            "split": "test",
            "configurations": list(LANGUAGES),
            "samples_per_language": samples_per_language,
            "attribution": "Google FLEURS dataset, CC-BY-4.0",
        },
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "torch": str(torch.__version__),
            "whisperx": package_version("whisperx"),
            "model": model_name,
            "device": "cpu",
            "compute_type": "int8",
            "logical_cpus": os.cpu_count(),
            "peak_rss_bytes": _peak_rss_bytes(),
            "wall_seconds": round(time.perf_counter() - started, 3),
        },
        "summary": summary,
        "samples": records,
        "limitations": [
            "A small read-speech public corpus does not represent sermons, music, noise, or spontaneous speech.",
            "WER is lexical accuracy, not word-timestamp accuracy.",
            "WhisperX alignment coverage and timestamp bounds are smoke checks, not comparison to manually annotated word boundaries.",
            "The tiny model is a compatibility baseline, not necessarily the best production model.",
            "Performance on a GitHub runner does not predict performance on the target computer.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="tiny")
    parser.add_argument("--samples-per-language", type=int, default=2)
    parser.add_argument("--cache-dir", type=Path, default=Path(".cache/phase0"))
    parser.add_argument("--output", type=Path, default=Path("phase0-model-poc.json"))
    args = parser.parse_args()

    try:
        report = run_benchmark(
            model_name=args.model,
            samples_per_language=args.samples_per_language,
            cache_dir=args.cache_dir,
        )
    except Exception as exc:
        failure = {
            "schema_version": 1,
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "classification": "smoke_benchmark_not_product_acceptance",
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


if __name__ == "__main__":
    raise SystemExit(main())
