#!/usr/bin/env python3
"""Small reproducible WhisperX smoke benchmark on public FLEURS samples.

This is a pipeline/compatibility probe, not a statistically valid product
acceptance benchmark. It records WER against dataset references, alignment
coverage, runtime, and process peak RSS. No media or transcript is uploaded
except the JSON report produced locally by the caller.
"""
from __future__ import annotations

import argparse
import gc
import io
from importlib.metadata import version as package_version
import json
import math
import os
import platform
import re
import resource
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
import torch
import whisperx
from datasets import Audio, load_dataset
from jiwer import wer


DATASET = "google/fleurs"
LANGUAGES = {
    "pt_br": {"whisper": "pt", "label": "Portuguese (Brazil)"},
    "en_us": {"whisper": "en", "label": "English (United States)"},
}


def _normalize_text(value: str) -> str:
    value = value.casefold()
    value = re.sub(r"[^\w\s']", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


def _read_audio(audio_record: dict[str, Any]) -> tuple[np.ndarray, int]:
    raw = audio_record.get("bytes")
    path = audio_record.get("path")
    if raw:
        waveform, sample_rate = sf.read(io.BytesIO(raw), dtype="float32")
    elif path:
        waveform, sample_rate = sf.read(path, dtype="float32")
    else:
        raise RuntimeError("FLEURS example contains neither audio bytes nor a path")

    waveform = np.asarray(waveform, dtype=np.float32)
    if waveform.ndim == 2:
        waveform = waveform.mean(axis=1, dtype=np.float32)
    if waveform.ndim != 1 or waveform.size == 0:
        raise RuntimeError("Audio must be a non-empty mono waveform")
    if int(sample_rate) != 16000:
        raise RuntimeError(f"Expected 16 kHz FLEURS audio, received {sample_rate} Hz")
    return waveform, int(sample_rate)


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

    if cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)
        os.environ["HF_HOME"] = str(cache_dir.resolve())
        os.environ["HF_HUB_CACHE"] = str((cache_dir / "hub").resolve())
        os.environ["HF_DATASETS_CACHE"] = str((cache_dir / "datasets").resolve())

    started = time.perf_counter()
    records: list[dict[str, Any]] = []
    model = whisperx.load_model(
        model_name,
        device="cpu",
        compute_type="int8",
        language=None,
    )

    for config, language_info in LANGUAGES.items():
        dataset = load_dataset(
            DATASET,
            config,
            split=f"test[:{samples_per_language}]",
        )
        dataset = dataset.cast_column("audio", Audio(decode=False))

        align_model, align_metadata = whisperx.load_align_model(
            language_code=language_info["whisper"],
            device="cpu",
        )

        for index, example in enumerate(dataset):
            waveform, sample_rate = _read_audio(example["audio"])
            duration = float(waveform.size / sample_rate)
            reference = str(example.get("raw_transcription") or example["transcription"])

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
            normalized_reference = _normalize_text(reference)
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
                    "config": config,
                    "language": language_info["whisper"],
                    "sample_id": int(example.get("id", index)),
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

        del align_model, align_metadata, dataset
        gc.collect()

    del model
    gc.collect()

    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(record["config"], []).append(record)

    summary = {}
    for config, items in grouped.items():
        total_reference_words = sum(item["reference_word_count"] for item in items)
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
            "reference_word_count": total_reference_words,
        }

    return {
        "schema_version": 1,
        "status": "completed",
        "classification": "smoke_benchmark_not_product_acceptance",
        "dataset": {
            "id": DATASET,
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
