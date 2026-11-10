#!/usr/bin/env python3
"""Validate critical invariants of Legendar's universal uv lockfile."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


def validate(project_path: Path, lock_path: Path) -> list[str]:
    import tomllib

    with project_path.open("rb") as handle:
        project = tomllib.load(handle)
    with lock_path.open("rb") as handle:
        lock = tomllib.load(handle)

    failures: list[str] = []
    project_config = project.get("project", {})
    extras = project_config.get("optional-dependencies", {})
    packages: list[dict[str, Any]] = lock.get("package", [])

    if str(lock.get("requires-python", "")).replace(" ", "") != str(project_config.get("requires-python", "")).replace(" ", ""):
        failures.append("uv.lock requires-python does not match pyproject.toml")

    whisperx = [item for item in packages if item.get("name") == "whisperx"]
    whisperx_versions = sorted({item.get("version") for item in whisperx})
    if whisperx_versions != ["3.8.6"]:
        failures.append(
            "WhisperX lock must contain exactly stable 3.8.6; "
            f"found {whisperx_versions!r}"
        )

    yt_dlp_ejs = [item for item in packages if item.get("name") == "yt-dlp-ejs"]
    if not yt_dlp_ejs:
        failures.append("yt-dlp-ejs is missing from the resolved lock")

    if any(item.get("name") == "datasets" for item in packages):
        failures.append(
            "datasets must not be in the lock: its Hugging Face Hub constraint "
            "conflicts with WhisperX 3.8.6"
        )

    expected_torch_sources = {
        "2.8.0+cpu": "https://download.pytorch.org/whl/cpu",
        "2.8.0+cu128": "https://download.pytorch.org/whl/cu128",
    }
    torch_packages = [item for item in packages if item.get("name") == "torch"]
    locked_sources = {
        item.get("version"): item.get("source", {}).get("registry")
        for item in torch_packages
    }
    for version, expected_source in expected_torch_sources.items():
        if locked_sources.get(version) != expected_source:
            failures.append(
                f"Torch {version} must resolve from {expected_source}; "
                f"found {locked_sources.get(version)!r}"
            )

    for profile in ("runtime-cpu", "runtime-cu128"):
        requirements = extras.get(profile, [])
        if not any(str(item).lower().startswith("whisperx") for item in requirements):
            failures.append(f"{profile} does not declare WhisperX directly")
    if "runtime-cpu" not in extras or "runtime-cu128" not in extras:
        failures.append("Both runtime-cpu and runtime-cu128 extras must exist")

    conflicts = lock.get("conflicts", [])
    conflict_names = {
        entry.get("extra")
        for group in conflicts
        for entry in group
        if entry.get("package") == project_config.get("name")
    }
    if not {"runtime-cpu", "runtime-cu128"}.issubset(conflict_names):
        failures.append("uv.lock does not declare CPU and CUDA runtime profiles as conflicting")

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path("pyproject.toml"))
    parser.add_argument("--lock", type=Path, default=Path("uv.lock"))
    args = parser.parse_args()

    failures = validate(args.project, args.lock)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    print("PASS: lockfile profile, source, and stable-version invariants")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
