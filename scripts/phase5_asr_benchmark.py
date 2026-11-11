#!/usr/bin/env python3
"""Benchmark pareado OpenAI Whisper x faster-whisper em PT-BR e inglês.

Usa FLEURS (CC-BY-4.0) por padrão ou manifesto TSV local com referências
revisadas. O relatório contém somente IDs sintéticos, métricas e configuração;
nunca inclui áudio, transcrição de referência ou hipótese.
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import platform
import sys
import tempfile
import time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

try:
    from scripts.phase4_model_benchmark import (
        _load_fleurs_rows,
        _load_manifest_rows,
        _normalize_text,
        _peak_rss_bytes,
        _read_audio,
    )
except ModuleNotFoundError:
    from phase4_model_benchmark import (
        _load_fleurs_rows,
        _load_manifest_rows,
        _normalize_text,
        _peak_rss_bytes,
        _read_audio,
    )

BACKENDS = ("openai-whisper", "faster-whisper")
MODEL_PROFILES = ("tiny", "base", "small", "medium", "large", "turbo")


def _package_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "unknown"


def _audio_asset(sample: dict[str, Any], cache_dir: Path, soundfile, np):
    from legendar.domain.entities.media import AudioAsset

    waveform, duration = _read_audio(sample, soundfile, np)
    audio_path = cache_dir / f"{sample['sample_id']}.wav"
    soundfile.write(audio_path, waveform, 16_000, subtype="PCM_16")
    return (
        AudioAsset(
            path=str(audio_path),
            sample_rate_hz=16_000,
            channels=1,
            sample_format="pcm_s16le",
            duration_seconds=duration,
            timeline_start_seconds=0.0,
            timeline_offset_source="phase5_benchmark_audio_starts_at_zero",
        ),
        duration,
    )


def run_benchmark(
    *,
    backends: tuple[str, ...] = BACKENDS,
    models: tuple[str, ...] = ("base",),
    samples_per_language: int = 10,
    cache_dir: Path = Path(".cache/phase5"),
    device: str = "cpu",
    compute_type: str | None = None,
    cpu_threads: int = 4,
    beam_size: int = 5,
    manifest: Path | None = None,
) -> dict[str, Any]:
    if not backends or len(set(backends)) != len(backends):
        raise ValueError("Informe backends únicos.")
    unknown_backends = sorted(set(backends).difference(BACKENDS))
    if unknown_backends:
        raise ValueError(f"Backends não permitidos: {', '.join(unknown_backends)}.")
    if not models or len(set(models)) != len(models):
        raise ValueError("Informe modelos únicos.")
    unknown_models = sorted(set(models).difference(MODEL_PROFILES))
    if unknown_models:
        raise ValueError(f"Modelos não permitidos: {', '.join(unknown_models)}.")
    if not 1 <= samples_per_language <= 100:
        raise ValueError("samples_per_language deve ficar entre 1 e 100.")
    if device not in {"cpu", "cuda", "auto"}:
        raise ValueError("device deve ser cpu, cuda ou auto.")
    if not 1 <= cpu_threads <= 64:
        raise ValueError("cpu_threads deve ficar entre 1 e 64.")
    if not 1 <= beam_size <= 10:
        raise ValueError("beam_size deve ficar entre 1 e 10.")

    try:
        import numpy as np
        import soundfile as sf
        from jiwer import cer, wer
    except ImportError as exc:
        raise RuntimeError(
            "Benchmark exige runtime-cpu/runtime-cu128 e o grupo phase0."
        ) from exc

    cache_dir = cache_dir.expanduser().resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    started = time.perf_counter()
    samples = (
        _load_manifest_rows(manifest)
        if manifest is not None
        else _load_fleurs_rows(cache_dir / "dataset", samples_per_language)
    )

    from legendar.domain.value_objects.language import Language
    from legendar.infrastructure.transcription.faster_whisper import (
        FasterWhisperTranscriber,
    )
    from legendar.infrastructure.transcription.whisper import WhisperTranscriber

    reports: list[dict[str, Any]] = []
    summaries: dict[str, Any] = {}
    resolved_device: str | None = None

    with tempfile.TemporaryDirectory(prefix="legendar-phase5-", dir=cache_dir) as temp:
        audio_dir = Path(temp)
        prepared = [
            (sample, *_audio_asset(sample, audio_dir, sf, np)) for sample in samples
        ]

        for backend in backends:
            for model_name in models:
                if backend == "openai-whisper":
                    transcriber = WhisperTranscriber(
                        cache_dir / "models",
                        model_name=model_name,
                        device=device,
                    )
                else:
                    transcriber = FasterWhisperTranscriber(
                        cache_dir / "models",
                        model_name=model_name,
                        device=device,
                        compute_type=compute_type,
                        cpu_threads=cpu_threads,
                        beam_size=beam_size,
                        vad_filter=False,
                    )

                model_records: list[dict[str, Any]] = []
                backend_started = time.perf_counter()
                for sample, audio, duration in prepared:
                    inference_started = time.perf_counter()
                    transcript = transcriber.transcribe(
                        audio,
                        language=Language.parse(sample["language"]),
                        progress=_NullProgress(),
                    )
                    elapsed = time.perf_counter() - inference_started
                    reference = _normalize_text(sample["reference"])
                    hypothesis = _normalize_text(transcript.text)
                    if not hypothesis:
                        raise RuntimeError(
                            f"{backend}/{model_name} não gerou texto para "
                            f"{sample['sample_id']}."
                        )
                    record = {
                        "backend": backend,
                        "model": model_name,
                        "sample_id": sample["sample_id"],
                        "language": sample["language"],
                        "audio_duration_seconds": round(duration, 3),
                        "reference_word_count": len(reference.split()),
                        "hypothesis_word_count": len(hypothesis.split()),
                        "wer": round(float(wer(reference, hypothesis)), 6),
                        "cer": round(float(cer(reference, hypothesis)), 6),
                        "transcription_wall_seconds": round(elapsed, 3),
                        "real_time_factor": round(elapsed / max(duration, 0.001), 4),
                        "first_sample_includes_cold_model_load": len(model_records) == 0,
                    }
                    model_records.append(record)
                    reports.append(record)

                snapshot = transcriber.performance_snapshot()
                counters = snapshot.get("counters", {})
                configuration = snapshot.get("configuration", {})
                resolved_device = configuration.get("loaded_device") or device
                by_language: dict[str, list[dict[str, Any]]] = {}
                for item in model_records:
                    by_language.setdefault(item["language"], []).append(item)
                key = f"{backend}:{model_name}"
                summaries[key] = {
                    "samples": len(model_records),
                    "languages": {
                        language: {
                            "samples": len(items),
                            "mean_wer": round(
                                sum(item["wer"] for item in items) / len(items), 6
                            ),
                            "mean_cer": round(
                                sum(item["cer"] for item in items) / len(items), 6
                            ),
                            "mean_real_time_factor": round(
                                sum(item["real_time_factor"] for item in items)
                                / len(items),
                                4,
                            ),
                            "mean_transcription_wall_seconds": round(
                                sum(item["transcription_wall_seconds"] for item in items)
                                / len(items),
                                3,
                            ),
                        }
                        for language, items in sorted(by_language.items())
                    },
                    "cold_first_sample_wall_seconds": model_records[0][
                        "transcription_wall_seconds"
                    ],
                    "warm_mean_wall_seconds": (
                        round(
                            sum(item["transcription_wall_seconds"] for item in model_records[1:])
                            / len(model_records[1:]),
                            3,
                        )
                        if len(model_records) > 1
                        else None
                    ),
                    "model_load_seconds": round(
                        float(counters.get("model_load_seconds", 0.0)), 3
                    ),
                    "inference_seconds": round(
                        float(counters.get("inference_seconds", 0.0)), 3
                    ),
                    "configuration": configuration,
                    "backend_wall_seconds": round(
                        time.perf_counter() - backend_started, 3
                    ),
                }
                del transcriber
                gc.collect()

    comparison: dict[str, Any] = {}
    for model_name in models:
        baseline_key = f"openai-whisper:{model_name}"
        candidate_key = f"faster-whisper:{model_name}"
        if baseline_key not in summaries or candidate_key not in summaries:
            continue
        baseline_languages = summaries[baseline_key]["languages"]
        candidate_languages = summaries[candidate_key]["languages"]
        language_comparison: dict[str, Any] = {}
        for language in sorted(set(baseline_languages) & set(candidate_languages)):
            baseline = baseline_languages[language]
            candidate = candidate_languages[language]
            baseline_rtf = baseline["mean_real_time_factor"]
            candidate_rtf = candidate["mean_real_time_factor"]
            language_comparison[language] = {
                "baseline_mean_wer": baseline["mean_wer"],
                "candidate_mean_wer": candidate["mean_wer"],
                "wer_delta_absolute": round(
                    candidate["mean_wer"] - baseline["mean_wer"], 6
                ),
                "baseline_mean_cer": baseline["mean_cer"],
                "candidate_mean_cer": candidate["mean_cer"],
                "cer_delta_absolute": round(
                    candidate["mean_cer"] - baseline["mean_cer"], 6
                ),
                "baseline_mean_rtf": baseline_rtf,
                "candidate_mean_rtf": candidate_rtf,
                "speedup_percent": (
                    round((1.0 - candidate_rtf / baseline_rtf) * 100.0, 2)
                    if baseline_rtf > 0
                    else None
                ),
            }
        comparison[model_name] = language_comparison

    return {
        "schema_version": 1,
        "status": "completed",
        "classification": "asr_comparison_not_product_acceptance",
        "scope": (
            "Pareado OpenAI Whisper x faster-whisper; recognition only. "
            "Forced alignment is validated separately by phase5_alignment_smoke."
        ),
        "dataset": (
            {
                "id": "google/fleurs",
                "revision": "c176a772dc5e1ced954fdd22af1a3bf5be2cbe6e",
                "license": "CC-BY-4.0",
                "split": "test",
                "samples_per_language": samples_per_language,
            }
            if manifest is None
            else {
                "id": "local-manifest",
                "manifest_sample_count": len(samples),
                "audio_and_references_not_embedded": True,
            }
        ),
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "device_requested": device,
            "device_resolved": resolved_device,
            "logical_cpus": os.cpu_count(),
            "peak_rss_bytes": _peak_rss_bytes(),
            "openai_whisper": _package_version("openai-whisper"),
            "faster_whisper": _package_version("faster-whisper"),
            "ctranslate2": _package_version("ctranslate2"),
            "wall_seconds": round(time.perf_counter() - started, 3),
        },
        "backends": list(backends),
        "models": list(models),
        "summary": summaries,
        "comparison": comparison,
        "samples": reports,
        "limitations": [
            "FLEURS é fala lida; não representa sermões, fala espontânea, música, ruído ou sobreposição.",
            "WER/CER medem reconhecimento lexical, não qualidade de timestamps.",
            "Amostras pequenas no CI são smoke tests, não aceite estatístico do produto.",
            "Resultados de runners GitHub não predizem desempenho no computador de referência.",
            "O primeiro sample de cada backend/model inclui carga fria; os demais reutilizam o modelo.",
            "VAD permanece desabilitado para comparação justa; seu efeito exige experimento separado.",
        ],
    }


class _NullProgress:
    def report(self, fraction: float, message: str = "") -> None:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backends", default=",".join(BACKENDS))
    parser.add_argument("--models", default="base")
    parser.add_argument("--samples-per-language", type=int, default=10)
    parser.add_argument("--cache-dir", type=Path, default=Path(".cache/phase5"))
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="cpu")
    parser.add_argument("--compute-type")
    parser.add_argument("--cpu-threads", type=int, default=4)
    parser.add_argument("--beam-size", type=int, default=5)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output", type=Path, default=Path("phase5-asr-benchmark.json"))
    args = parser.parse_args()
    try:
        report = run_benchmark(
            backends=tuple(item.strip() for item in args.backends.split(",") if item.strip()),
            models=tuple(item.strip().lower() for item in args.models.split(",") if item.strip()),
            samples_per_language=args.samples_per_language,
            cache_dir=args.cache_dir,
            device=args.device,
            compute_type=args.compute_type,
            cpu_threads=args.cpu_threads,
            beam_size=args.beam_size,
            manifest=args.manifest,
        )
    except Exception as exc:  # noqa: BLE001 - CLI persiste falha de forma auditável
        failure = {
            "schema_version": 1,
            "status": "failed",
            "classification": "asr_comparison_not_product_acceptance",
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


if __name__ == "__main__":
    raise SystemExit(main())
