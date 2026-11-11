#!/usr/bin/env python3
"""Resume relatórios locais da Fase 1 sem ler mídia, transcrições ou legendas."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

STAGES = (
    "media_acquisition",
    "media_inspection",
    "audio_preparation",
    "transcription",
    "alignment",
    "segmentation",
    "translation",
    "srt_validation",
    "srt_publication",
)


def _read_reports(directory: Path) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    if not directory.is_dir():
        return reports
    for path in sorted(directory.glob("job-*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(value, dict) and value.get("schema_version") == 1:
            reports.append(value)
    return reports


def _stage_times(report: dict[str, Any]) -> dict[str, float]:
    result: dict[str, float] = {}
    stages = report.get("stages", [])
    if not isinstance(stages, list):
        return result
    for item in stages:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        seconds = item.get("wall_seconds")
        if (
            isinstance(name, str)
            and isinstance(seconds, (int, float))
            and not isinstance(seconds, bool)
        ):
            result[name] = result.get(name, 0.0) + float(seconds)
    return result


def _adapter_load_seconds(report: dict[str, Any], name: str) -> float:
    adapters = report.get("adapters", {})
    adapter = adapters.get(name, {}) if isinstance(adapters, dict) else {}
    counters = adapter.get("counter_delta", {}) if isinstance(adapter, dict) else {}
    value = counters.get("model_load_seconds", 0.0) if isinstance(counters, dict) else 0.0
    return float(value) if isinstance(value, (int, float)) else 0.0


def _load_state(report: dict[str, Any], name: str) -> str:
    adapters = report.get("adapters", {})
    adapter = adapters.get(name, {}) if isinstance(adapters, dict) else {}
    if not isinstance(adapter, dict):
        return "n/a"
    counters = adapter.get("counter_delta", {})
    attempts = counters.get("model_load_attempts", 0) if isinstance(counters, dict) else 0
    if not attempts:
        return "unused"
    return "warm" if adapter.get("loaded_before_job") else "cold"


def _print_report(report: dict[str, Any]) -> None:
    metadata = report.get("metadata", {})
    metadata = metadata if isinstance(metadata, dict) else {}
    duration = metadata.get("audio_duration_seconds")
    total = report.get("total_wall_seconds")
    status = str(report.get("status", "unknown"))
    job_id = str(report.get("job_id", "unknown"))
    date = str(report.get("generated_at_utc", "unknown"))
    stages = _stage_times(report)
    rtf = float(total) / float(duration) if (
        isinstance(total, (int, float))
        and isinstance(duration, (int, float))
        and duration > 0
    ) else None
    duration_label = f"{float(duration) / 60:.2f} min" if isinstance(duration, (int, float)) else "n/a"
    total_label = f"{float(total) / 60:.2f} min" if isinstance(total, (int, float)) else "n/a"
    rtf_label = f"{rtf:.3f}" if rtf is not None else "n/a"
    print(f"\nJob {job_id} | {date} | {status}")
    print(f"Áudio: {duration_label} | Total: {total_label} | RTF: {rtf_label}")
    print(f"{'Etapa':24} {'Tempo (min)':>12} {'RTF etapa':>12}")
    for name in STAGES:
        seconds = stages.get(name)
        if seconds is None:
            continue
        stage_rtf = seconds / float(duration) if isinstance(duration, (int, float)) and duration > 0 else None
        stage_rtf_label = f"{stage_rtf:.3f}" if stage_rtf is not None else "n/a"
        print(f"{name:24} {seconds / 60:12.3f} {stage_rtf_label:>12}")
    print("Carga de modelos (inclui download inicial, se ocorreu no job):")
    for name in ("transcription", "alignment", "translation"):
        seconds = _adapter_load_seconds(report, name)
        print(
            f"  {name:16} {_load_state(report, name):6} "
            f"{seconds:.2f} s"
        )


def _print_medians(reports: list[dict[str, Any]]) -> None:
    completed = [report for report in reports if report.get("status") == "completed"]
    if not completed:
        return
    print(f"\nMedianas de {len(completed)} execução(ões) concluída(s)")
    metrics: dict[str, list[float]] = {"total": []}
    for report in completed:
        total = report.get("total_wall_seconds")
        if isinstance(total, (int, float)):
            metrics["total"].append(float(total))
        for name, seconds in _stage_times(report).items():
            metrics.setdefault(name, []).append(seconds)
    for name, values in metrics.items():
        if values:
            print(f"  {name:24} {statistics.median(values) / 60:.3f} min")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Resume relatórios JSON sanitizados da telemetria local do Legendar."
    )
    parser.add_argument(
        "--directory",
        type=Path,
        default=Path.home() / ".cache" / "legendar" / "logs" / "performance",
        help="Diretório dos relatórios (padrão: cache local do Legendar).",
    )
    parser.add_argument("--last", type=int, default=10, help="Quantidade máxima de jobs exibidos.")
    args = parser.parse_args(argv)
    if args.last < 1:
        parser.error("--last deve ser pelo menos 1.")
    reports = _read_reports(args.directory)
    if not reports:
        print(f"Nenhum relatório da Fase 1 encontrado em: {args.directory}")
        print("Execute um job pela aplicação instrumentada e rode este resumo novamente.")
        return 1
    selected = reports[-args.last :]
    print(f"Relatórios encontrados: {len(reports)} | Exibindo: {len(selected)}")
    for report in selected:
        _print_report(report)
    _print_medians(selected)
    print("\nThroughput de fala/alinhamento:")
    for report in selected:
        counts = report.get("counts", {})
        counts = counts if isinstance(counts, dict) else {}
        stages = _stage_times(report)
        recognized = counts.get("recognized_words")
        aligned = counts.get("aligned_words")
        transcribe_seconds = stages.get("transcription", 0.0)
        alignment_seconds = stages.get("alignment", 0.0)
        if recognized and transcribe_seconds > 0:
            print(
                f"  {report.get('job_id', 'unknown')}: "
                f"{float(recognized) / transcribe_seconds:.2f} palavras/s reconhecidas"
            )
        if aligned and alignment_seconds > 0:
            print(
                f"  {report.get('job_id', 'unknown')}: "
                f"{float(aligned) / alignment_seconds:.2f} palavras/s alinhadas"
            )
    print("\nThroughput de tradução (apenas quando medido):")
    for report in selected:
        adapters = report.get("adapters", {})
        translation = adapters.get("translation", {}) if isinstance(adapters, dict) else {}
        counters = translation.get("counter_delta", {}) if isinstance(translation, dict) else {}
        generated = counters.get("generated_tokens", 0) if isinstance(counters, dict) else 0
        generation_seconds = counters.get("generation_seconds", 0) if isinstance(counters, dict) else 0
        if generated and generation_seconds:
            print(
                f"  {report.get('job_id', 'unknown')}: "
                f"{float(generated) / float(generation_seconds):.2f} tokens/s gerados"
            )
    print("\nObservação: RTF = tempo da etapa/job dividido pela duração do áudio.")
    print("Execuções cold incluem a carga inicial (e eventual download) dos modelos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
