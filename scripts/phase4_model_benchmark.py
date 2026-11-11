#!/usr/bin/env python3
"""Benchmark reproduzível do reconhecimento OpenAI Whisper em PT-BR e inglês.

Por padrão usa FLEURS (fala lida, CC-BY-4.0). Também aceita um manifesto TSV local
para avaliação com amostras autorizadas e referências revisadas. Áudios e textos
não são incluídos no relatório: somente métricas agregadas e IDs sintéticos.
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
import sys
import tarfile
import time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

DATASET = "google/fleurs"
DATASET_REVISION = "c176a772dc5e1ced954fdd22af1a3bf5be2cbe6e"
LANGUAGES = {
    "pt_br": {"whisper": "pt", "label": "Português (Brasil)"},
    "en_us": {"whisper": "en", "label": "Inglês (EUA)"},
}
MODEL_PROFILES = ("tiny", "base", "small", "medium", "large", "turbo")


def _normalize_text(value: str) -> str:
    value = value.casefold()
    value = re.sub(r"[^\w\s']", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


def _parse_language(value: str) -> str:
    normalized = (value or "").strip().casefold().replace("_", "-")
    aliases = {
        "pt": "pt",
        "pt-br": "pt",
        "portuguese": "pt",
        "português": "pt",
        "portugues": "pt",
        "en": "en",
        "en-us": "en",
        "english": "en",
        "inglês": "en",
        "ingles": "en",
    }
    try:
        return aliases[normalized]
    except KeyError as exc:
        raise ValueError(
            f"Idioma {value!r} não suportado; use PT-BR/pt ou EN/en."
        ) from exc


def _load_manifest_rows(manifest: Path) -> list[dict[str, str]]:
    """Lê TSV local com colunas language, audio e reference, sem copiar conteúdo."""
    manifest = manifest.expanduser().resolve()
    if not manifest.is_file():
        raise FileNotFoundError(f"Manifesto não encontrado: {manifest}")

    samples: list[dict[str, str]] = []
    with manifest.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        required = {"language", "audio", "reference"}
        if not reader.fieldnames or not required.issubset(
            {name.strip().casefold() for name in reader.fieldnames}
        ):
            raise ValueError(
                "O manifesto TSV exige cabeçalho com language, audio e reference."
            )
        for row_number, row in enumerate(reader, start=2):
            normalized = {
                (key or "").strip().casefold(): (value or "").strip()
                for key, value in row.items()
            }
            language = _parse_language(normalized.get("language", ""))
            audio_value = normalized.get("audio", "")
            reference = normalized.get("reference", "")
            if not audio_value or not reference:
                raise ValueError(
                    f"Linha {row_number}: áudio e transcrição de referência são obrigatórios."
                )
            audio_path = Path(audio_value).expanduser()
            if not audio_path.is_absolute():
                audio_path = manifest.parent / audio_path
            audio_path = audio_path.resolve()
            if not audio_path.is_file():
                raise FileNotFoundError(
                    f"Linha {row_number}: áudio não encontrado: {audio_path}"
                )
            samples.append(
                {
                    "sample_id": f"local-{len(samples) + 1:04d}",
                    "language": language,
                    "reference": reference,
                    "audio_path": str(audio_path),
                }
            )
    if not samples:
        raise ValueError("O manifesto não contém amostras.")
    return samples


def _load_fleurs_rows(
    cache_dir: Path,
    samples_per_language: int,
) -> list[dict[str, Any]]:
    try:
        from huggingface_hub import hf_hub_download
        from scripts.phase0_fleurs import parse_reference_rows
    except ImportError:
        # Execução direta de scripts/: o diretório do script já está em sys.path.
        from huggingface_hub import hf_hub_download
        from phase0_fleurs import parse_reference_rows

    samples: list[dict[str, Any]] = []
    for config, language_info in LANGUAGES.items():
        rows_path = hf_hub_download(
            repo_id=DATASET,
            repo_type="dataset",
            filename=f"data/{config}/test.tsv",
            revision=DATASET_REVISION,
            cache_dir=str(cache_dir),
        )
        with Path(rows_path).open("r", encoding="utf-8", newline="") as handle:
            rows = parse_reference_rows(handle, samples_per_language)
        if len(rows) < samples_per_language:
            raise RuntimeError(
                f"FLEURS {config}: {len(rows)} amostras válidas; "
                f"{samples_per_language} solicitadas."
            )

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
                source = archive.extractfile(member)
                if source is None:
                    continue
                found[Path(member.name).name] = source.read()
                if wanted.issubset(found):
                    break
        missing = wanted.difference(found)
        if missing:
            raise RuntimeError(
                f"Áudios FLEURS ausentes em {config}: {sorted(missing)}"
            )
        for row in rows:
            samples.append(
                {
                    "sample_id": f"{config}-{row['id']}",
                    "language": language_info["whisper"],
                    "reference": row["reference"],
                    "audio_bytes": found[row["filename"]],
                }
            )
    return samples


def _read_audio(sample: dict[str, Any], soundfile, np):
    source = (
        io.BytesIO(sample["audio_bytes"])
        if "audio_bytes" in sample
        else sample["audio_path"]
    )
    waveform, sample_rate = soundfile.read(source, dtype="float32")
    waveform = np.asarray(waveform, dtype=np.float32)
    if waveform.ndim == 2:
        waveform = waveform.mean(axis=1, dtype=np.float32)
    if waveform.ndim != 1 or waveform.size == 0:
        raise RuntimeError(f"Áudio inválido na amostra {sample['sample_id']}.")
    if int(sample_rate) != 16_000:
        raise RuntimeError(
            f"Amostra {sample['sample_id']}: esperado 16 kHz, recebido {sample_rate} Hz."
        )
    if not np.isfinite(waveform).all():
        raise RuntimeError(f"Áudio contém amostras não finitas: {sample['sample_id']}.")
    return waveform, float(waveform.size / sample_rate)


def _resolve_device(torch, requested: str) -> str:
    if requested == "auto":
        if torch.cuda.is_available():
            return "cuda"
        mps = getattr(getattr(torch.backends, "mps", None), "is_available", None)
        return "mps" if callable(mps) and mps() else "cpu"
    if requested == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA foi solicitada, mas não está disponível.")
    if requested == "mps":
        mps = getattr(getattr(torch.backends, "mps", None), "is_available", None)
        if not callable(mps) or not mps():
            raise RuntimeError("MPS foi solicitado, mas não está disponível.")
    return requested


def _peak_rss_bytes() -> int | None:
    try:
        import resource
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except (ImportError, AttributeError, OSError):
        return None
    return int(peak * 1024 if sys.platform.startswith("linux") else peak)


def run_benchmark(
    *,
    models: tuple[str, ...] = ("tiny", "base", "small"),
    samples_per_language: int = 10,
    cache_dir: Path = Path(".cache/phase4"),
    device: str = "auto",
    manifest: Path | None = None,
) -> dict[str, Any]:
    if not 1 <= samples_per_language <= 100:
        raise ValueError("samples_per_language deve estar entre 1 e 100.")
    if not models or len(set(models)) != len(models):
        raise ValueError("Informe modelos únicos.")
    unknown = sorted(set(models).difference(MODEL_PROFILES))
    if unknown:
        raise ValueError(f"Modelos Whisper não permitidos: {', '.join(unknown)}.")

    try:
        import numpy as np
        import soundfile as sf
        import torch
        import whisper
        from jiwer import cer, wer
    except ImportError as exc:
        raise RuntimeError(
            "Benchmark exige o perfil runtime-cpu/runtime-cu128 e o grupo phase0."
        ) from exc

    cache_dir = cache_dir.expanduser().resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    model_dir = cache_dir / "models"
    model_dir.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

    started = time.perf_counter()
    samples = (
        _load_manifest_rows(manifest)
        if manifest is not None
        else _load_fleurs_rows(cache_dir / "dataset", samples_per_language)
    )
    resolved_device = _resolve_device(torch, device)
    reports: list[dict[str, Any]] = []
    summaries: dict[str, dict[str, Any]] = {}

    for model_name in models:
        if model_name not in whisper.available_models():
            raise ValueError(
                f"O runtime instalado não disponibiliza o modelo {model_name!r}."
            )
        model_started = time.perf_counter()
        model = whisper.load_model(
            model_name,
            device=resolved_device,
            download_root=str(model_dir),
        )
        model_results: list[dict[str, Any]] = []
        for index, sample in enumerate(samples, start=1):
            waveform, duration = _read_audio(sample, sf, np)
            transcribe_started = time.perf_counter()
            result = model.transcribe(
                waveform,
                task="transcribe",
                language=sample["language"],
                fp16=resolved_device != "cpu",
                verbose=None,
                word_timestamps=False,
            )
            elapsed = time.perf_counter() - transcribe_started
            hypothesis = str(result.get("text", "")).strip()
            reference = _normalize_text(sample["reference"])
            normalized_hypothesis = _normalize_text(hypothesis)
            if not normalized_hypothesis:
                raise RuntimeError(
                    f"Modelo {model_name} não gerou texto para {sample['sample_id']}."
                )
            record = {
                "model": model_name,
                "sample_id": sample["sample_id"],
                "language": sample["language"],
                "audio_duration_seconds": round(duration, 3),
                "reference_word_count": len(reference.split()),
                "hypothesis_word_count": len(normalized_hypothesis.split()),
                "wer": round(float(wer(reference, normalized_hypothesis)), 6),
                "cer": round(float(cer(reference, normalized_hypothesis)), 6),
                "transcription_seconds": round(elapsed, 3),
                "real_time_factor": round(elapsed / max(duration, 0.001), 3),
            }
            model_results.append(record)
            reports.append(record)

        by_language: dict[str, list[dict[str, Any]]] = {}
        for item in model_results:
            by_language.setdefault(item["language"], []).append(item)
        summaries[model_name] = {
            "samples": len(model_results),
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
                        sum(item["real_time_factor"] for item in items) / len(items), 3
                    ),
                    "mean_transcription_seconds": round(
                        sum(item["transcription_seconds"] for item in items)
                        / len(items),
                        3,
                    ),
                }
                for language, items in sorted(by_language.items())
            },
            "model_load_and_preparation_seconds": round(
                max(
                    0.0,
                    time.perf_counter()
                    - model_started
                    - sum(item["transcription_seconds"] for item in model_results),
                ),
                3,
            ),
        }
        del model
        gc.collect()
        if resolved_device == "cuda":
            torch.cuda.empty_cache()

    try:
        whisper_version = version("openai-whisper")
    except PackageNotFoundError:
        whisper_version = "unknown"

    return {
        "schema_version": 1,
        "status": "completed",
        "classification": "recognition_benchmark_not_product_acceptance",
        "scope": "Whisper transcription only; no forced alignment or timestamp scoring.",
        "dataset": (
            {
                "id": DATASET,
                "revision": DATASET_REVISION,
                "license": "CC-BY-4.0",
                "split": "test",
                "configurations": list(LANGUAGES),
                "samples_per_language": samples_per_language,
                "attribution": "Google FLEURS dataset, CC-BY-4.0",
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
            "torch": str(torch.__version__),
            "openai_whisper": whisper_version,
            "device": resolved_device,
            "logical_cpus": os.cpu_count(),
            "peak_rss_bytes": _peak_rss_bytes(),
            "wall_seconds": round(time.perf_counter() - started, 3),
        },
        "models": list(models),
        "summary": summaries,
        "samples": reports,
        "limitations": [
            "FLEURS is read speech and does not represent sermons, spontaneous speech, music, noise, or overlap.",
            "WER/CER evaluate lexical recognition only; they do not measure word timestamp accuracy.",
            "Two samples per language are a CI smoke test, not a statistical product acceptance corpus.",
            "GitHub runner performance does not predict performance on the target computer.",
            "A local manifest report contains metrics and synthetic sample IDs only, never audio or transcript text.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", default="tiny,base,small")
    parser.add_argument("--samples-per-language", type=int, default=10)
    parser.add_argument("--cache-dir", type=Path, default=Path(".cache/phase4"))
    parser.add_argument("--device", choices=("auto", "cpu", "cuda", "mps"), default="auto")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output", type=Path, default=Path("phase4-model-benchmark.json"))
    args = parser.parse_args()
    try:
        models = tuple(item.strip().lower() for item in args.models.split(",") if item.strip())
        report = run_benchmark(
            models=models,
            samples_per_language=args.samples_per_language,
            cache_dir=args.cache_dir,
            device=args.device,
            manifest=args.manifest,
        )
    except Exception as exc:  # noqa: BLE001 - CLI precisa materializar falha em relatório
        failure = {
            "schema_version": 1,
            "status": "failed",
            "classification": "recognition_benchmark_not_product_acceptance",
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
