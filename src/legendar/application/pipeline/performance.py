"""Medições de uma execução do pipeline, sem capturar conteúdo audiovisual."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any


ResourceSnapshot = Mapping[str, int | float | None]
ResourceProvider = Callable[[], ResourceSnapshot]


def snapshot_adapter_metrics(ports: object) -> dict[str, dict[str, Any]]:
    """Lê somente snapshots numéricos/configuração expostos pelos adaptadores."""
    components = {
        "transcription": getattr(ports, "transcriber", None),
        "alignment": getattr(ports, "aligner", None),
        "translation": getattr(ports, "translator", None),
    }
    result: dict[str, dict[str, Any]] = {}
    for name, component in components.items():
        snapshot = getattr(component, "performance_snapshot", None)
        if not callable(snapshot):
            continue
        try:
            value = snapshot()
        except Exception:
            continue
        if isinstance(value, Mapping):
            result[name] = dict(value)
    return result


def _safe_snapshot(provider: ResourceProvider | None) -> dict[str, Any] | None:
    if provider is None:
        return None
    try:
        return dict(provider())
    except Exception:
        return None


def _numeric_delta(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, float]:
    delta: dict[str, float] = {}
    for key, value in after.items():
        previous = before.get(key, 0)
        if (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and isinstance(previous, (int, float))
            and not isinstance(previous, bool)
        ):
            delta[key] = float(value) - float(previous)
    return delta


class PipelinePerformanceSession:
    """Acumula tempos por etapa e metadados sanitizados de uma única execução."""

    def __init__(
        self,
        job_id: str,
        *,
        resource_provider: ResourceProvider | None = None,
        adapter_metrics_before: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> None:
        self.job_id = job_id
        self._resource_provider = resource_provider
        self._started = time.perf_counter()
        self._process_started = time.process_time()
        self._stages: list[dict[str, Any]] = []
        self._counts: dict[str, int | float] = {}
        self._metadata: dict[str, Any] = {}
        self._adapter_metrics_before = {
            key: dict(value) for key, value in (adapter_metrics_before or {}).items()
        }

    @contextmanager
    def measure(self, name: str) -> Iterator[None]:
        """Mede tempo de parede, CPU do processo e recursos antes/depois."""
        wall_started = time.perf_counter()
        cpu_started = time.process_time()
        resources_before = _safe_snapshot(self._resource_provider)
        try:
            yield
        finally:
            resources_after = _safe_snapshot(self._resource_provider)
            self._stages.append(
                {
                    "name": name,
                    "wall_seconds": max(0.0, time.perf_counter() - wall_started),
                    "process_cpu_seconds": max(0.0, time.process_time() - cpu_started),
                    "resources_before": resources_before,
                    "resources_after": resources_after,
                }
            )

    def set_metadata(self, **values: Any) -> None:
        """Registra somente campos de configuração previamente selecionados."""
        self._metadata.update(values)

    def set_count(self, name: str, value: int | float) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return
        self._counts[name] = value

    def build_report(
        self,
        *,
        status: str,
        adapter_metrics_after: Mapping[str, Mapping[str, Any]] | None = None,
        error_type: str | None = None,
    ) -> dict[str, Any]:
        adapters_after = adapter_metrics_after or {}
        adapters: dict[str, Any] = {}
        for name in sorted(set(self._adapter_metrics_before) | set(adapters_after)):
            before = self._adapter_metrics_before.get(name, {})
            after = dict(adapters_after.get(name, {}))
            before_counters = before.get("counters", {})
            after_counters = after.get("counters", {})
            if not isinstance(before_counters, Mapping):
                before_counters = {}
            if not isinstance(after_counters, Mapping):
                after_counters = {}
            adapters[name] = {
                "configuration": after.get("configuration", {}),
                "loaded_before_job": bool(before.get("loaded", False)),
                "loaded_after_job": bool(after.get("loaded", False)),
                "counter_delta": _numeric_delta(before_counters, after_counters),
                "counters_after": dict(after_counters),
            }

        report: dict[str, Any] = {
            "schema_version": 1,
            "job_id": self.job_id,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "total_wall_seconds": max(0.0, time.perf_counter() - self._started),
            "total_process_cpu_seconds": max(
                0.0, time.process_time() - self._process_started
            ),
            "metadata": self._metadata,
            "counts": self._counts,
            "stages": self._stages,
            "adapters": adapters,
        }
        if error_type:
            report["error_type"] = error_type
        return report
