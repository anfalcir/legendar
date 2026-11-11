#!/usr/bin/env python3
"""Smoke real do pipeline de reconhecimento + forced alignment WhisperX.

Usa FLEURS (fala lida, CC-BY-4.0) em PT-BR e EN. A saída mede cobertura
estrutural e WER lexical, mas não erro temporal contra anotação humana.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import platform
import sys
import tarfile
import tempfile
import time
import wave
from importlib.metadata import version
from pathlib import Path
from typing import Any

from huggingface_hub import hf_hub_download
from jiwer import wer

from legendar.domain.entities.media import AudioAsset
from legendar.domain.value_objects.language import Language
from legendar.infrastructure.alignment.whisperx import WhisperXAligner
from legendar.infrastructure.transcription.faster_whisper import (
    FasterWhisperTranscriber,
)
from legendar.infrastructure.transcription.whisper import WhisperTranscriber

DATASET = "google/fleurs"
DATASET_REVISION = "c176a772dc5e1ced954fdd22af1a3bf5be2cbe6e"
LANGUAGES = {
    "pt_br": {"language": Language.PORTUGUESE, "label": "pt"},
    "en_us": {"language": Language.ENGLISH, "label": "en"},
}


class NullProgress:
    def report(self, fraction: float, message: str = "") -> None:
        return None


def _normalize_text(value: str) -> str:
    import re

    value = value.casefold()
    value = re.sub(r"[^\w\s']", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


def _load_samples(
    cache_dir: Path,
    samples_per_language: int,
) -> list[dict[str, Any]]:
    try:
        from scripts.phase0_fleurs import parse_reference_rows
    except ModuleNotFoundError:
        from phase0_fleurs import parse_reference_rows

    samples: list[dict[str, Any]] = []
    for config, settings in LANGUAGES.items():
        tsv_path = hf_hub_download(
            repo_id=DATASET,
            repo_type="dataset",
            filename=f"data/{config}/test.tsv",
            revision=DATASET_REVISION,
            cache_dir=str(cache_dir),
        )
        with Path(tsv_path).open("r", encoding="utf-8", newline="") as handle:
            rows = parse_reference_rows(handle, samples_per_language)
        if len(rows) < samples_per_language:
            raise RuntimeError(
                f"FLEURS {config}: apenas {len(rows)} amostras; "
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
                if source is not None:
                    found[Path(member.name).name] = source.read()
                if wanted.issubset(found):
                    break
        missing = wanted.difference(found)
        if missing:
            raise RuntimeError(f"Áudios ausentes no FLEURS {config}: {sorted(missing)}")

        for row in rows:
            samples.append(
                {
                    "sample_id": f"{config}-{row['id']}",
                    "language": settings["language"],
                    "language_code": settings["label"],
                    "reference": row["reference"],
                    "audio_bytes": found[row["filename"]],
                }
            )
    return samples


def _write_audio(audio_bytes: bytes, destination: Path) -> AudioAsset:
    """Decode FLEURS WAV (PCM or IEEE float) and normalize to product PCM s16le."""
    import numpy as np
    import soundfile as sf

    try:
        waveform, sample_rate = sf.read(
            io.BytesIO(audio_bytes),
            dtype="float32",
            always_2d=True,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        raise RuntimeError("Não foi possível decodificar a amostra FLEURS.") from exc

    if sample_rate != 16_000:
        raise RuntimeError(
            f"Esperado áudio FLEURS em 16 kHz; recebido {sample_rate} Hz."
        )
    if waveform.ndim != 2 or waveform.shape[0] < 1 or waveform.shape[1] < 1:
        raise RuntimeError("A amostra FLEURS não contém frames/canais válidos.")
    if not np.isfinite(waveform).all():
        raise RuntimeError("A amostra FLEURS contém valores não finitos.")

    # O contrato da Fase 3 é mono. Downmix determinístico antes de quantizar.
    mono = waveform.mean(axis=1, dtype=np.float32)
    clipped = np.clip(mono, -1.0, 32767.0 / 32768.0)
    pcm = np.rint(clipped * 32768.0).astype("<i2")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(destination), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(16_000)
        target.writeframes(pcm.tobytes())

    return AudioAsset(
        path=str(destination),
        sample_rate_hz=16_000,
        channels=1,
        sample_format="pcm_s16le",
        duration_seconds=pcm.size / 16_000,
        timeline_start_seconds=0.0,
        timeline_offset_source="fleurs_reference_wave_starts_at_zero",
    )


def _peak_rss_bytes() -> int | None:
    try:
        import resource

        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except (ImportError, AttributeError, OSError):
        return None
    return int(peak * 1024 if sys.platform.startswith("linux") else peak)


def run_smoke(
    *,
    model: str = "tiny",
    samples_per_language: int = 1,
    cache_dir: Path = Path(".cache/phase5"),
    device: str = "cpu",
    backend: str = "openai-whisper",
) -> dict[str, Any]:
    if not 1 <= samples_per_language <= 10:
        raise ValueError("samples_per_language deve ficar entre 1 e 10.")
    if device not in {"cpu", "cuda", "auto"}:
        raise ValueError("device deve ser cpu, cuda ou auto.")
    if backend not in {"openai-whisper", "faster-whisper"}:
        raise ValueError("backend deve ser openai-whisper ou faster-whisper.")

    cache_dir = cache_dir.expanduser().resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

    started = time.perf_counter()
    samples = _load_samples(cache_dir / "dataset", samples_per_language)
    transcriber_class = (
        FasterWhisperTranscriber if backend == "faster-whisper" else WhisperTranscriber
    )
    transcriber = transcriber_class(
        cache_dir,
        model_name=model,
        device=device,
    )
    aligner = WhisperXAligner(cache_dir, device=device)
    records: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(
        prefix="legendar-phase5-", dir=cache_dir
    ) as temporary:
        temporary_dir = Path(temporary)
        for sample in samples:
            audio = _write_audio(
                sample["audio_bytes"],
                temporary_dir / f"{sample['sample_id']}.wav",
            )

            transcription_started = time.perf_counter()
            transcript = transcriber.transcribe(
                audio,
                language=sample["language"],
                progress=NullProgress(),
            )
            transcription_seconds = time.perf_counter() - transcription_started

            alignment_started = time.perf_counter()
            alignment = aligner.align(
                audio,
                transcript,
                progress=NullProgress(),
            )
            alignment_seconds = time.perf_counter() - alignment_started

            reference = _normalize_text(sample["reference"])
            hypothesis = _normalize_text(transcript.text)
            if not hypothesis:
                raise RuntimeError(
                    f"{backend} não reconheceu fala em {sample['sample_id']}."
                )

            total_words = len(transcript.text.split())
            aligned_words = alignment.diagnostics.aligned_words
            unmatched_words = len(alignment.diagnostics.unmatched_words)
            valid_bounds = 0
            for segment in alignment.transcript.segments:
                for word in segment.words:
                    if word.range is None:
                        continue
                    if (
                        0.0
                        <= word.range.start
                        < word.range.end
                        <= audio.duration_seconds + 1e-6
                    ):
                        valid_bounds += 1

            if aligned_words == 0 or valid_bounds == 0:
                raise RuntimeError(
                    f"WhisperX não alinhou nenhuma palavra válida em "
                    f"{sample['sample_id']}."
                )

            total_seconds = transcription_seconds + alignment_seconds
            records.append(
                {
                    "sample_id": sample["sample_id"],
                    "language": sample["language_code"],
                    "audio_duration_seconds": round(audio.duration_seconds, 3),
                    "reference_word_count": len(reference.split()),
                    "recognized_word_count": total_words,
                    "wer": round(float(wer(reference, hypothesis)), 6),
                    "transcription_seconds": round(transcription_seconds, 3),
                    "alignment_seconds": round(alignment_seconds, 3),
                    "real_time_factor": round(
                        total_seconds / max(audio.duration_seconds, 0.001), 3
                    ),
                    "aligned_words": aligned_words,
                    "unmatched_words": unmatched_words,
                    "alignment_coverage": round(aligned_words / max(total_words, 1), 6),
                    "valid_timestamps": valid_bounds,
                    "diagnostic_issues": list(alignment.diagnostics.issues),
                }
            )

    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(record["language"], []).append(record)

    summary = {}
    for language, rows in grouped.items():
        total = sum(row["recognized_word_count"] for row in rows)
        aligned = sum(row["aligned_words"] for row in rows)
        summary[language] = {
            "samples": len(rows),
            "mean_wer": round(sum(row["wer"] for row in rows) / len(rows), 6),
            "alignment_coverage": round(aligned / max(total, 1), 6),
            "aligned_words": aligned,
            "unmatched_words": sum(row["unmatched_words"] for row in rows),
            "valid_timestamps": sum(row["valid_timestamps"] for row in rows),
        }

    return {
        "schema_version": 1,
        "status": "completed",
        "classification": "alignment_integration_smoke_not_product_acceptance",
        "scope": (
            "Local Whisper transcription plus WhisperX forced alignment; "
            "FLEURS has lexical references but no human word-boundary annotations."
        ),
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
            "torch": str(__import__("torch").__version__),
            "asr_backend": backend,
            "openai_whisper": version("openai-whisper"),
            "faster_whisper": version("faster-whisper"),
            "whisperx": version("whisperx"),
            "asr_model": model,
            "alignment_device": aligner.loaded_device or device,
            "logical_cpus": os.cpu_count(),
            "peak_rss_bytes": _peak_rss_bytes(),
            "wall_seconds": round(time.perf_counter() - started, 3),
        },
        "summary": summary,
        "samples": records,
        "limitations": [
            "FLEURS is read speech and does not represent sermons, spontaneous speech, music, noise, or overlap.",
            "WER measures lexical recognition, not timestamp accuracy.",
            "Alignment coverage and bounds are structural smoke checks, not error against human word-boundary annotations.",
            "GitHub runner performance does not predict performance on the target computer.",
            "Product acceptance requires a local, authorized corpus with human-annotated word boundaries.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="tiny")
    parser.add_argument("--samples-per-language", type=int, default=1)
    parser.add_argument("--cache-dir", type=Path, default=Path(".cache/phase5"))
    parser.add_argument("--device", choices=("cpu", "cuda", "auto"), default="cpu")
    parser.add_argument(
        "--backend",
        choices=("openai-whisper", "faster-whisper"),
        default="openai-whisper",
    )
    parser.add_argument(
        "--output", type=Path, default=Path("phase5-alignment-smoke.json")
    )
    args = parser.parse_args()

    try:
        report = run_smoke(
            model=args.model,
            samples_per_language=args.samples_per_language,
            cache_dir=args.cache_dir,
            device=args.device,
            backend=args.backend,
        )
    except Exception as exc:  # noqa: BLE001 - CLI precisa materializar falha no artefato
        failure = {
            "schema_version": 1,
            "status": "failed",
            "classification": "alignment_integration_smoke_not_product_acceptance",
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
