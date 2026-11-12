"""Política de recursos para o runtime local do Legendar.

A política decide quando manter modelos residentes e quantas threads CPU usar.
Ela não mede desempenho nem inventa capacidade: usa apenas o inventário do
sistema e configurações explícitas. O modo auto é conservador em máquinas
com pouca RAM.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum


class ResourceProfile(StrEnum):
    AUTO = "auto"
    LOW_MEMORY = "low-memory"
    BALANCED = "balanced"
    PERFORMANCE = "performance"


@dataclass(frozen=True, slots=True)
class ResourcePolicy:
    profile: ResourceProfile
    retain_models: bool
    cpu_threads: int
    cpu_interop_threads: int


def _physical_cpu_count() -> int | None:
    if os.name != "posix":
        return None
    try:
        import psutil
    except ImportError:
        return None
    count = psutil.cpu_count(logical=False)
    return int(count) if count else None


def _total_memory_bytes() -> int | None:
    if os.name == "posix":
        try:
            pages = os.sysconf("SC_PHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            return int(pages * page_size)
        except (OSError, ValueError):
            return None
    return None


def detect_resource_profile() -> ResourceProfile:
    """Resolve auto sem assumir hardware específico."""

    raw = os.environ.get("LEGENDAR_RESOURCE_PROFILE", "auto").strip().casefold()
    explicit = {
        item.value for item in ResourceProfile if item is not ResourceProfile.AUTO
    }
    if raw in explicit:
        return ResourceProfile(raw)
    memory = _total_memory_bytes()
    if memory is not None and memory < 16 * 1024**3:
        return ResourceProfile.LOW_MEMORY
    return ResourceProfile.BALANCED


def resolve_resource_policy() -> ResourcePolicy:
    profile = detect_resource_profile()
    logical = os.cpu_count() or 1
    physical = _physical_cpu_count() or max(1, logical // 2)

    if profile is ResourceProfile.LOW_MEMORY:
        threads = min(physical, 4)
        interop = 1
        retain = False
    elif profile is ResourceProfile.PERFORMANCE:
        threads = max(1, logical)
        interop = max(1, min(4, physical))
        retain = True
    else:
        threads = max(1, min(physical, 6))
        interop = max(1, min(2, physical))
        retain = True

    for name in ("LEGENDAR_CPU_THREADS", "LEGENDAR_CPU_INTEROP_THREADS"):
        raw = os.environ.get(name, "").strip()
        if not raw:
            continue
        try:
            value = int(raw)
        except ValueError as exc:
            raise ValueError(f"{name} deve ser inteiro positivo.") from exc
        if value < 1:
            raise ValueError(f"{name} deve ser inteiro positivo.")
        if name == "LEGENDAR_CPU_THREADS":
            threads = value
        else:
            interop = value

    return ResourcePolicy(
        profile=profile,
        retain_models=retain,
        cpu_threads=threads,
        cpu_interop_threads=interop,
    )


def configure_torch_threads(policy: ResourcePolicy) -> ResourcePolicy:
    """Configura threads antes da primeira inferência."""

    try:
        import torch
    except ImportError:
        return policy

    try:
        torch.set_num_threads(policy.cpu_threads)
    except RuntimeError:
        pass
    try:
        torch.set_num_interop_threads(policy.cpu_interop_threads)
    except RuntimeError:
        pass
    return policy
