"""Persistência local de métricas de desempenho sem conteúdo de mídia ou texto."""

from __future__ import annotations

import ctypes
import importlib.metadata
import json
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Mapping

from legendar.infrastructure.filesystem.paths import ensure_private_directory

LOGGER = logging.getLogger(__name__)

_PACKAGE_NAMES = (
    "openai-whisper",
    "whisperx",
    "transformers",
    "torch",
    "torchaudio",
    "ctranslate2",
    "numpy",
)


def _linux_memory() -> dict[str, int | None]:
    values: dict[str, int] = {}
    try:
        lines = Path("/proc/meminfo").read_text(encoding="ascii").splitlines()
    except OSError:
        return {"total_bytes": None, "available_bytes": None}
    for line in lines:
        key, separator, raw = line.partition(":")
        if not separator:
            continue
        parts = raw.split()
        if not parts:
            continue
        try:
            value = int(parts[0])
        except ValueError:
            continue
        values[key] = value * 1024 if len(parts) > 1 and parts[1].lower() == "kb" else value
    return {
        "total_bytes": values.get("MemTotal"),
        "available_bytes": values.get("MemAvailable", values.get("MemFree")),
    }


def _system_memory() -> dict[str, int | None]:
    if sys.platform.startswith("linux"):
        return _linux_memory()
    if os.name == "nt":
        class MemoryStatusEx(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatusEx()
        status.dwLength = ctypes.sizeof(status)
        try:
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return {
                    "total_bytes": int(status.ullTotalPhys),
                    "available_bytes": int(status.ullAvailPhys),
                }
        except (AttributeError, OSError):
            pass
    return {"total_bytes": None, "available_bytes": None}


def _process_rss_bytes() -> int | None:
    if sys.platform.startswith("linux"):
        try:
            resident_pages = int(Path("/proc/self/statm").read_text().split()[1])
            return resident_pages * int(os.sysconf("SC_PAGE_SIZE"))
        except (OSError, ValueError, IndexError):
            return None
    if os.name == "nt":
        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        try:
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            ok = ctypes.windll.psapi.GetProcessMemoryInfo(
                handle, ctypes.byref(counters), counters.cb
            )
            if ok:
                return int(counters.WorkingSetSize)
        except (AttributeError, OSError):
            pass
    return None


def _process_peak_rss_bytes() -> int | None:
    try:
        import resource
    except ImportError:
        return None
    try:
        value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    except (AttributeError, OSError, ValueError):
        return None
    # Linux reports KiB; macOS reports bytes.
    return value * 1024 if sys.platform.startswith("linux") else value


def _cpu_model() -> str | None:
    if sys.platform.startswith("linux"):
        try:
            for line in Path("/proc/cpuinfo").read_text(
                encoding="utf-8", errors="replace"
            ).splitlines():
                key, separator, value = line.partition(":")
                if separator and key.strip().lower() in {"model name", "hardware"}:
                    return value.strip() or None
        except OSError:
            pass
    return platform.processor() or None


def _physical_cpu_count() -> int | None:
    if not sys.platform.startswith("linux"):
        return None
    pairs: set[tuple[str, str]] = set()
    physical_id: str | None = None
    core_id: str | None = None
    try:
        lines = Path("/proc/cpuinfo").read_text(
            encoding="ascii", errors="replace"
        ).splitlines()
    except OSError:
        return None
    for line in (*lines, ""):
        key, separator, value = line.partition(":")
        if not separator:
            if physical_id is not None and core_id is not None:
                pairs.add((physical_id, core_id))
            physical_id = None
            core_id = None
            continue
        if key.strip() == "physical id":
            physical_id = value.strip()
        elif key.strip() == "core id":
            core_id = value.strip()
    return len(pairs) or None


def _tool_version(name: str) -> str | None:
    binary = shutil.which(name)
    if not binary:
        return None
    try:
        result = subprocess.run(
            [binary, "-version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    lines = (result.stdout or result.stderr).splitlines()
    return lines[0].strip()[:240] if lines else None


def _package_versions() -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for package in _PACKAGE_NAMES:
        try:
            result[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            result[package] = None
    return result


def _nvidia_devices() -> list[str]:
    binary = shutil.which("nvidia-smi")
    if not binary:
        return []
    try:
        result = subprocess.run(
            [
                binary,
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [line.strip()[:240] for line in result.stdout.splitlines() if line.strip()]


def _graphics_adapters() -> list[dict[str, str | None]]:
    if not sys.platform.startswith("linux"):
        return []
    devices = Path("/sys/bus/pci/devices")
    vendor_names = {"0x1002": "AMD", "0x10de": "NVIDIA", "0x8086": "Intel"}
    adapters: list[dict[str, str | None]] = []
    if not devices.is_dir():
        return adapters
    for device in sorted(devices.iterdir()):
        try:
            class_id = (device / "class").read_text(encoding="ascii").strip()
            if not class_id.lower().startswith("0x03"):
                continue
            vendor_id = (device / "vendor").read_text(encoding="ascii").strip().lower()
            device_id = (device / "device").read_text(encoding="ascii").strip().lower()
            driver_path = device / "driver"
            driver = (
                driver_path.resolve(strict=True).name
                if driver_path.is_symlink()
                else None
            )
        except (OSError, RuntimeError):
            continue
        adapters.append(
            {
                "vendor": vendor_names.get(vendor_id, "Unknown"),
                "vendor_id": vendor_id,
                "device_id": device_id,
                "driver": driver,
            }
        )
    return adapters


def collect_performance_environment() -> dict[str, Any]:
    """Inventário sanitizado: sem hostname, usuário, caminhos ou variáveis de ambiente."""
    memory = _system_memory()
    return {
        "python_version": platform.python_version(),
        "os": platform.system(),
        "os_release": platform.release(),
        "architecture": platform.machine(),
        "cpu_model": _cpu_model(),
        "physical_cpu_count": _physical_cpu_count(),
        "logical_cpu_count": os.cpu_count(),
        "memory_total_bytes": memory["total_bytes"],
        "graphics_adapters": _graphics_adapters(),
        "nvidia_devices": _nvidia_devices(),
        "packages": _package_versions(),
        "media_tools": {
            "ffmpeg": _tool_version("ffmpeg"),
            "ffprobe": _tool_version("ffprobe"),
        },
    }


class JsonPerformanceReporter:
    """Grava um JSON privado por job no subdiretório performance dos logs."""

    def __init__(self, logs_dir: Path) -> None:
        self.output_dir = Path(logs_dir).expanduser() / "performance"
        ensure_private_directory(self.output_dir)

    def capture_resources(self) -> dict[str, int | None]:
        memory = _system_memory()
        return {
            "process_rss_bytes": _process_rss_bytes(),
            "process_peak_rss_bytes": _process_peak_rss_bytes(),
            "system_memory_available_bytes": memory["available_bytes"],
            "system_memory_total_bytes": memory["total_bytes"],
        }

    def write_report(self, report: Mapping[str, Any]) -> Path:
        job_id = str(report.get("job_id", "job"))
        safe_id = re.sub(r"[^A-Za-z0-9._-]+", "_", job_id).strip("._") or "job"
        destination = self.output_dir / f"job-{safe_id}.json"
        temporary = destination.with_name(
            f".{destination.name}.{uuid.uuid4().hex}.partial"
        )
        payload = dict(report)
        payload["environment"] = collect_performance_environment()
        try:
            with temporary.open("x", encoding="utf-8") as handle:
                os.chmod(temporary, 0o600)
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
            os.chmod(destination, 0o600)
        except OSError:
            temporary.unlink(missing_ok=True)
            raise
        LOGGER.info("Relatório de desempenho sanitizado salvo em %s", destination)
        return destination
