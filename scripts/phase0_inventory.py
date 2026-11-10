#!/usr/bin/env python3
"""Collect a reproducible, privacy-conscious environment inventory for Legendar.

This diagnostic is intentionally read-only: it does not install packages,
download models, inspect user media, or modify application files.
"""
from __future__ import annotations

import argparse
import ctypes
import importlib.metadata
import json
import os
import platform
import shutil
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

SCHEMA_VERSION = 1
PACKAGE_DISTRIBUTIONS = {
    "openai-whisper": "openai-whisper",
    "whisperx": "whisperx",
    "stable-ts": "stable-ts",
    "torch": "torch",
    "torchaudio": "torchaudio",
    "torchvision": "torchvision",
    "numpy": "numpy",
    "PySide6": "PySide6",
    "yt-dlp": "yt-dlp",
    "yt-dlp-ejs": "yt-dlp-ejs",
}


def _parse_linux_meminfo(content: str) -> dict[str, int | None]:
    """Return total and available memory in bytes from /proc/meminfo."""
    values: dict[str, int] = {}
    for line in content.splitlines():
        key, separator, raw_value = line.partition(":")
        if not separator:
            continue
        parts = raw_value.strip().split()
        if not parts:
            continue
        try:
            value = int(parts[0])
        except ValueError:
            continue
        unit = parts[1].lower() if len(parts) > 1 else ""
        values[key] = value * 1024 if unit == "kb" else value

    return {
        "total_bytes": values.get("MemTotal"),
        "available_bytes": values.get("MemAvailable", values.get("MemFree")),
    }


def _parse_os_release(content: str) -> dict[str, str | None]:
    """Parse non-sensitive identity fields from the Linux os-release format."""
    allowed = {"ID", "NAME", "VERSION_ID", "PRETTY_NAME"}
    result: dict[str, str | None] = {key.lower(): None for key in allowed}
    for line in content.splitlines():
        key, separator, raw_value = line.partition("=")
        if not separator or key not in allowed:
            continue
        try:
            parts = shlex.split(raw_value, comments=False, posix=True)
        except ValueError:
            continue
        if parts:
            result[key.lower()] = parts[0]
    return result


def _collect_linux_distribution(
    os_release_path: Path = Path("/etc/os-release"),
) -> dict[str, str | None] | None:
    """Return distribution identity without collecting machine-specific IDs."""
    if not os_release_path.is_file():
        return None
    try:
        return _parse_os_release(os_release_path.read_text(encoding="utf-8"))
    except OSError:
        return None


def _collect_linux_graphics_adapters(
    pci_devices_root: Path = Path("/sys/bus/pci/devices"),
) -> list[dict[str, str | None]]:
    """Enumerate PCI display controllers using Linux sysfs; no lspci required."""
    if not pci_devices_root.is_dir():
        return []

    vendor_names = {
        "0x1002": "AMD",
        "0x10de": "NVIDIA",
        "0x8086": "Intel",
    }
    adapters: list[dict[str, str | None]] = []
    for device_path in sorted(pci_devices_root.iterdir()):
        try:
            class_id = (device_path / "class").read_text(encoding="ascii").strip()
            if not class_id.lower().startswith("0x03"):
                continue
            vendor_id = (device_path / "vendor").read_text(
                encoding="ascii"
            ).strip().lower()
            device_id = (device_path / "device").read_text(
                encoding="ascii"
            ).strip().lower()
            driver_path = device_path / "driver"
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
                "class_id": class_id.lower(),
                "driver": driver,
            }
        )
    return adapters


def _collect_memory() -> dict[str, int | None]:
    """Collect physical-memory totals without adding third-party dependencies."""
    meminfo = Path("/proc/meminfo")
    if meminfo.is_file():
        try:
            return _parse_linux_meminfo(meminfo.read_text(encoding="utf-8"))
        except OSError:
            pass

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
        status.dwLength = ctypes.sizeof(MemoryStatusEx)
        try:
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return {
                    "total_bytes": int(status.ullTotalPhys),
                    "available_bytes": int(status.ullAvailPhys),
                }
        except (AttributeError, OSError):
            pass

    try:
        page_size = int(os.sysconf("SC_PAGE_SIZE"))
        total_pages = int(os.sysconf("SC_PHYS_PAGES"))
        available_pages = int(os.sysconf("SC_AVPHYS_PAGES"))
        return {
            "total_bytes": page_size * total_pages,
            "available_bytes": page_size * available_pages,
        }
    except (AttributeError, OSError, ValueError):
        return {"total_bytes": None, "available_bytes": None}


def _cpu_model() -> str | None:
    """Return a CPU model label, avoiding hostnames and hardware identifiers."""
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


def _run_command(command: Sequence[str], timeout: int = 8) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            list(command),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError:
        return {"available": False, "version": None, "error": "not_found"}
    except subprocess.TimeoutExpired:
        return {"available": False, "version": None, "error": "timeout"}
    except OSError as exc:
        return {
            "available": False,
            "version": None,
            "error": type(exc).__name__,
        }

    output = (completed.stdout or completed.stderr).strip()
    output_lines = [line.strip() for line in output.splitlines() if line.strip()]
    first_line = output_lines[0] if output_lines else None
    result = {
        "available": completed.returncode == 0,
        "version": first_line,
        "returncode": completed.returncode,
    }
    if len(output_lines) > 1:
        result["details"] = output_lines
    return result


def _find_executable(name: str, project_root: Path) -> str | None:
    found = shutil.which(name)
    if found:
        return found

    suffix = ".exe" if os.name == "nt" else ""
    bundled = project_root / "ffmpeg" / "bin" / f"{name}{suffix}"
    return str(bundled) if bundled.is_file() else None


def _probe_executable(name: str, project_root: Path) -> dict[str, Any]:
    executable = _find_executable(name, project_root)
    if not executable:
        return {"available": False, "version": None, "error": "not_found"}
    return _run_command([executable, "-version"])


def _probe_path_executable(name: str) -> dict[str, Any]:
    """Probe an optional runtime executable available on PATH."""
    executable = shutil.which(name)
    if not executable:
        return {"available": False, "version": None, "error": "not_found"}
    return _run_command([executable, "--version"])


def _package_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for label, distribution in PACKAGE_DISTRIBUTIONS.items():
        try:
            versions[label] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            versions[label] = None
    return versions


def _probe_torch_runtime() -> dict[str, Any]:
    """Import PyTorch only when explicitly requested by the user."""
    try:
        import torch  # type: ignore[import-not-found]

        cuda_available = bool(torch.cuda.is_available())
        devices = []
        if cuda_available:
            for index in range(torch.cuda.device_count()):
                devices.append(
                    {
                        "index": index,
                        "name": torch.cuda.get_device_name(index),
                        "total_memory_bytes": int(
                            torch.cuda.get_device_properties(index).total_memory
                        ),
                    }
                )
        return {
            "imported": True,
            "version": str(torch.__version__),
            "cuda_available": cuda_available,
            "cuda_runtime_version": getattr(torch.version, "cuda", None),
            "hip_runtime_version": getattr(torch.version, "hip", None),
            "cudnn_version": torch.backends.cudnn.version(),
            "devices": devices,
        }
    except Exception as exc:  # diagnostic must report, not hide, import failures
        return {
            "imported": False,
            "error_type": type(exc).__name__,
        }


def collect_inventory(project_root: Path, probe_torch: bool = False) -> dict[str, Any]:
    memory = _collect_memory()
    disk = shutil.disk_usage(project_root)
    nvidia_smi = shutil.which("nvidia-smi")
    gpu_probe = (
        _run_command(
            [
                nvidia_smi,
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader",
            ]
        )
        if nvidia_smi
        else {"available": False, "version": None, "error": "not_found"}
    )
    if "version" in gpu_probe and gpu_probe["version"]:
        gpu_probe["devices"] = gpu_probe.pop("details", [gpu_probe["version"]])
        gpu_probe.pop("version", None)
    gpu_probe.pop("returncode", None)

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "runtime": {
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "executable_name": Path(sys.executable).name,
        },
        "system": {
            "os": platform.system(),
            "release": platform.release(),
            "distribution": (
                _collect_linux_distribution() if sys.platform.startswith("linux") else None
            ),
            "architecture": platform.machine(),
            "cpu_model": _cpu_model(),
            "logical_cpu_count": os.cpu_count(),
            "graphics_adapters": (
                _collect_linux_graphics_adapters()
                if sys.platform.startswith("linux")
                else []
            ),
            "memory_total_bytes": memory["total_bytes"],
            "memory_available_bytes": memory["available_bytes"],
            "disk_total_bytes": disk.total,
            "disk_free_bytes": disk.free,
        },
        "media_tools": {
            "ffmpeg": _probe_executable("ffmpeg", project_root),
            "ffprobe": _probe_executable("ffprobe", project_root),
            "deno": _probe_path_executable("deno"),
            "node": _probe_path_executable("node"),
        },
        "nvidia_gpu_probe": gpu_probe,
        "packages": _package_versions(),
        "torch_runtime": (
            _probe_torch_runtime() if probe_torch else {"status": "not_probed"}
        ),
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Coleta versões e características do ambiente para a Fase 0 do "
            "Legendar. Não instala dependências nem baixa modelos."
        )
    )
    parser.add_argument(
        "--probe-torch",
        action="store_true",
        help="Importa PyTorch para consultar CUDA e dispositivos disponíveis.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Grava o relatório JSON neste caminho; por padrão, imprime no terminal.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Permite substituir o arquivo indicado por --output.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    project_root = Path(__file__).resolve().parents[1]
    report = json.dumps(
        collect_inventory(project_root, probe_torch=args.probe_torch),
        ensure_ascii=False,
        indent=2,
    )

    if args.output:
        if args.output.exists() and not args.force:
            print(
                f"Erro: {args.output} já existe. Use --force para substituí-lo.",
                file=sys.stderr,
            )
            return 2
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(report + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"Erro ao gravar relatório: {exc}", file=sys.stderr)
            return 2
        print(f"Relatório salvo em: {args.output}")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
