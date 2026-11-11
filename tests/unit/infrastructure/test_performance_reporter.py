from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

from legendar.infrastructure.diagnostics import performance as module
from legendar.infrastructure.diagnostics.performance import JsonPerformanceReporter


def test_reporter_writes_private_json_without_media_content(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        module,
        "collect_performance_environment",
        lambda: {"os": "TestOS", "cpu_model": "Test CPU"},
    )
    reporter = JsonPerformanceReporter(tmp_path / "logs")
    report = {
        "schema_version": 1,
        "job_id": "job-123",
        "status": "completed",
        "total_wall_seconds": 12.0,
        "metadata": {"audio_duration_seconds": 60.0},
        "counts": {"recognized_words": 10},
        "stages": [],
        "adapters": {},
    }

    path = reporter.write_report(report)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert path.parent == tmp_path / "logs" / "performance"
    assert payload["environment"]["cpu_model"] == "Test CPU"
    assert payload["metadata"]["audio_duration_seconds"] == 60.0
    assert "audio" not in payload
    assert "transcript" not in payload
    assert "subtitle" not in payload
    assert "source_path" not in payload
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert not list(path.parent.glob("*.partial"))


def test_reporter_uses_safe_filename_for_job_identifier(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(module, "collect_performance_environment", lambda: {})
    reporter = JsonPerformanceReporter(tmp_path / "logs")

    path = reporter.write_report({"job_id": "../../unsafe", "schema_version": 1})

    assert path.name == "job-unsafe.json"
    assert path.parent == tmp_path / "logs" / "performance"


def test_linux_inventory_parsers_cover_cpu_memory_and_graphics(
    tmp_path: Path,
) -> None:
    meminfo = tmp_path / "meminfo"
    meminfo.write_text(
        "MemTotal: 16384 kB\nMemAvailable: 8192 kB\nMemFree: invalid\n",
        encoding="ascii",
    )
    cpuinfo = tmp_path / "cpuinfo"
    cpuinfo.write_text(
        "processor : 0\nmodel name : Test CPU\nphysical id : 0\ncore id : 0\n\n"
        "processor : 1\nmodel name : Second CPU\nphysical id : 0\ncore id : 1\n\n",
        encoding="ascii",
    )

    memory = module._linux_memory(meminfo)
    assert memory == {
        "total_bytes": 16 * 1024 * 1024,
        "available_bytes": 8 * 1024 * 1024,
    }
    if sys.platform.startswith("linux"):
        assert module._system_memory()["total_bytes"] is not None
    assert module._cpu_model(cpuinfo) == "Test CPU"
    assert module._physical_cpu_count(cpuinfo) == 2

    devices = tmp_path / "pci"
    graphics = devices / "0000:00:01.0"
    graphics.mkdir(parents=True)
    (graphics / "class").write_text("0x030000\n", encoding="ascii")
    (graphics / "vendor").write_text("0x1002\n", encoding="ascii")
    (graphics / "device").write_text("0x1636\n", encoding="ascii")
    driver = tmp_path / "amdgpu"
    driver.mkdir()
    (graphics / "driver").symlink_to(driver, target_is_directory=True)

    non_graphics = devices / "0000:00:02.0"
    non_graphics.mkdir()
    (non_graphics / "class").write_text("0x020000\n", encoding="ascii")
    (non_graphics / "vendor").write_text("0x8086\n", encoding="ascii")
    (non_graphics / "device").write_text("0x1234\n", encoding="ascii")

    adapters = module._graphics_adapters(devices)
    assert adapters == [
        {
            "vendor": "AMD",
            "vendor_id": "0x1002",
            "device_id": "0x1636",
            "driver": "amdgpu",
        }
    ]


def test_runtime_inventory_handles_tools_packages_gpu_and_threads(monkeypatch) -> None:
    monkeypatch.setattr(module.shutil, "which", lambda name: f"/fake/{name}")

    def fake_run(command, **_kwargs):
        if command[0].endswith("ffmpeg"):
            return SimpleNamespace(stdout="ffmpeg version test\n", stderr="")
        if command[0].endswith("nvidia-smi"):
            if "--query-gpu=name,memory.total,driver_version" in command:
                return SimpleNamespace(
                    stdout="NVIDIA Test, 8192 MiB, 555.1\n", stderr=""
                )
            return SimpleNamespace(stdout="123, 45\n", stderr="")
        raise AssertionError(command)

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    assert module._tool_version("ffmpeg") == "ffmpeg version test"
    assert module._nvidia_devices() == ["NVIDIA Test, 8192 MiB, 555.1"]
    assert module._gpu_runtime_resources() == {
        "gpu0_memory_used_mib": 123,
        "gpu0_utilization_percent": 45,
    }

    def fake_version(name: str) -> str:
        if name == "torch":
            return "2.8.0"
        raise module.importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(module.importlib.metadata, "version", fake_version)
    packages = module._package_versions()
    assert packages["torch"] == "2.8.0"
    assert packages["whisperx"] is None

    assert module.collect_torch_thread_settings() == {}
    fake_torch = SimpleNamespace(
        get_num_threads=lambda: 6,
        get_num_interop_threads=lambda: (_ for _ in ()).throw(RuntimeError("busy")),
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    assert module.collect_torch_thread_settings() == {"pytorch_num_threads": 6}


def test_environment_snapshot_and_resource_capture_are_composed(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        module, "_system_memory", lambda: {"total_bytes": 1000, "available_bytes": 500}
    )
    monkeypatch.setattr(module, "_cpu_model", lambda: "Test CPU")
    monkeypatch.setattr(module, "_physical_cpu_count", lambda: 4)
    monkeypatch.setattr(module, "_graphics_adapters", lambda: [{"vendor": "AMD"}])
    monkeypatch.setattr(module, "_nvidia_devices", lambda: [])
    monkeypatch.setattr(module, "_package_versions", lambda: {"torch": "test"})
    monkeypatch.setattr(module, "_tool_version", lambda name: f"{name} version test")
    environment = module.collect_performance_environment()
    assert environment["cpu_model"] == "Test CPU"
    assert environment["physical_cpu_count"] == 4
    assert environment["memory_total_bytes"] == 1000
    assert environment["graphics_adapters"] == [{"vendor": "AMD"}]
    assert environment["media_tools"]["ffmpeg"] == "ffmpeg version test"

    monkeypatch.setattr(module, "_process_rss_bytes", lambda: 10)
    monkeypatch.setattr(module, "_process_peak_rss_bytes", lambda: 20)
    monkeypatch.setattr(
        module,
        "_gpu_runtime_resources",
        lambda: {"gpu0_memory_used_mib": 30},
    )
    reporter = JsonPerformanceReporter(tmp_path / "logs")
    assert reporter.capture_resources() == {
        "process_rss_bytes": 10,
        "process_peak_rss_bytes": 20,
        "system_memory_available_bytes": 500,
        "system_memory_total_bytes": 1000,
        "gpu0_memory_used_mib": 30,
    }


def test_runtime_probe_failures_are_non_fatal(monkeypatch) -> None:
    monkeypatch.setattr(module.shutil, "which", lambda _name: None)
    assert module._tool_version("missing") is None
    assert module._nvidia_devices() == []
    assert module._gpu_runtime_resources() == {}

    monkeypatch.setattr(module.shutil, "which", lambda _name: "/fake/tool")
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("probe failed")),
    )
    assert module._tool_version("ffmpeg") is None
    assert module._nvidia_devices() == []
    assert module._gpu_runtime_resources() == {}


def test_linux_process_memory_probes_return_byte_counts() -> None:
    if not sys.platform.startswith("linux"):
        return
    assert (module._process_rss_bytes() or 0) > 0
    assert (module._process_peak_rss_bytes() or 0) > 0
