"""Política de recursos para o runtime local do Legendar.

A topologia CPU é obtida do conjunto realmente disponível ao processo e, no
Linux, dos identificadores de pacote/núcleo expostos pelo sysfs. Quando a
topologia física não está disponível, o fallback é explícito e registrado:
não presumimos uma proporção SMT fixa de 2:1.
"""

from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class ResourceProfile(str, Enum):
    AUTO = "auto"
    LOW_MEMORY = "low-memory"
    BALANCED = "balanced"
    PERFORMANCE = "performance"


@dataclass(frozen=True, slots=True)
class CpuTopology:
    logical_count: int
    physical_count: int
    source: str


@dataclass(frozen=True, slots=True)
class ResourcePolicy:
    profile: ResourceProfile
    retain_models: bool
    cpu_threads: int
    cpu_interop_threads: int
    logical_cpu_count: int = 1
    physical_cpu_count: int = 1
    cpu_topology_source: str = "logical-count-fallback"


def _parse_cpu_list(value: str) -> set[int]:
    """Interpreta listas de CPUs Linux como 0-3,6; entrada inválida é rejeitada."""
    cpus: set[int] = set()
    for item in value.strip().split(","):
        item = item.strip()
        if not item:
            continue
        if "-" in item:
            first, separator, last = item.partition("-")
            if not separator or not first.isdigit() or not last.isdigit():
                raise ValueError("lista de CPUs inválida")
            start, end = int(first), int(last)
            if end < start:
                raise ValueError("intervalo de CPUs invertido")
            cpus.update(range(start, end + 1))
        else:
            if not item.isdigit():
                raise ValueError("lista de CPUs inválida")
            cpus.add(int(item))
    if not cpus:
        raise ValueError("lista de CPUs vazia")
    return cpus


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        return None


def _cgroup_cpu_quota(cgroup_root: Path) -> int | None:
    """Converte quota cgroup v2/v1 em um limite inteiro conservador de CPUs."""
    v2 = _read_text(cgroup_root / "cpu.max")
    if v2:
        parts = v2.split()
        if len(parts) >= 2 and parts[0] != "max":
            try:
                quota, period = int(parts[0]), int(parts[1])
            except ValueError:
                quota = period = 0
            if quota > 0 and period > 0:
                return max(1, quota // period)

    v1_roots = (
        cgroup_root / "cpu",
        cgroup_root / "cpu,cpuacct",
        cgroup_root,
    )
    for root in v1_roots:
        quota_text = _read_text(root / "cpu.cfs_quota_us")
        period_text = _read_text(root / "cpu.cfs_period_us")
        if quota_text is None or period_text is None:
            continue
        try:
            quota, period = int(quota_text), int(period_text)
        except ValueError:
            continue
        if quota > 0 and period > 0:
            return max(1, quota // period)
    return None


def _cpu_topology(
    *,
    sysfs_root: Path = Path("/sys/devices/system/cpu"),
    cgroup_root: Path = Path("/sys/fs/cgroup"),
    affinity: set[int] | None = None,
    logical_count: int | None = None,
) -> CpuTopology:
    """Retorna a topologia efetivamente disponível, sem inferir SMT 2:1."""
    detected_logical = os.cpu_count() if logical_count is None else logical_count
    source_parts: list[str] = []

    if affinity is None:
        get_affinity = getattr(os, "sched_getaffinity", None)
        if callable(get_affinity):
            try:
                allowed = set(get_affinity(0))
                source_parts.append("process-affinity")
            except OSError:
                allowed = set()
        else:
            allowed = set()
    else:
        allowed = set(affinity)
        source_parts.append("test-affinity")

    if not allowed and detected_logical:
        allowed = set(range(detected_logical))
        source_parts.append("os-cpu-count-fallback")

    cpuset_text = _read_text(cgroup_root / "cpuset.cpus.effective")
    if cpuset_text is None:
        cpuset_text = _read_text(cgroup_root / "cpuset" / "cpuset.cpus")
    if cpuset_text:
        try:
            cpuset = _parse_cpu_list(cpuset_text)
        except ValueError:
            cpuset = set()
        if cpuset:
            allowed = allowed.intersection(cpuset) if allowed else cpuset
            source_parts.append("cgroup-cpuset")

    quota = _cgroup_cpu_quota(cgroup_root)
    if quota is not None:
        source_parts.append("cgroup-quota")
    logical = len(allowed) if allowed else (detected_logical or 1)
    if quota is not None:
        logical = min(logical, quota)
    logical = max(1, logical)

    core_ids: set[tuple[str, str]] = set()
    topology_complete = bool(allowed)
    for cpu_id in sorted(allowed):
        topology_dir = sysfs_root / f"cpu{cpu_id}" / "topology"
        package_id = _read_text(topology_dir / "physical_package_id")
        core_id = _read_text(topology_dir / "core_id")
        if package_id is None or core_id is None:
            topology_complete = False
            break
        core_ids.add((package_id, core_id))

    if topology_complete and core_ids:
        physical = min(len(core_ids), logical)
        source_parts.insert(0, "linux-sysfs-package-core")
    else:
        physical = logical
        source_parts.insert(0, "logical-count-fallback")

    if not source_parts:
        source_parts.append("logical-count-fallback")
    return CpuTopology(
        logical_count=logical,
        physical_count=max(1, physical),
        source="+".join(dict.fromkeys(source_parts)),
    )


def _physical_cpu_count() -> int | None:
    topology = _cpu_topology()
    if topology.logical_count < 1:
        return None
    return topology.physical_count


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
    if memory is not None:
        if memory < 8 * 1024**3:
            return ResourceProfile.LOW_MEMORY
        if memory < 12 * 1024**3:
            return ResourceProfile.BALANCED
        return ResourceProfile.PERFORMANCE
    return ResourceProfile.BALANCED


def resolve_resource_policy() -> ResourcePolicy:
    profile = detect_resource_profile()
    topology = _cpu_topology()
    logical = topology.logical_count
    physical = topology.physical_count

    if profile is ResourceProfile.LOW_MEMORY:
        threads = max(1, min(physical, 4))
        interop = 1
        retain = False
    elif profile is ResourceProfile.PERFORMANCE:
        # Perfil agressivo para o hardware local: usa os núcleos físicos
        # disponíveis e até quatro threads de interop. A referência histórica
        # deste equipamento apresentou 4/4 como configuração quente mais rápida.
        threads = max(1, min(physical, 4))
        interop = max(1, min(4, physical))
        retain = True
    else:
        threads = max(1, min(physical, 4))
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
        logical_cpu_count=logical,
        physical_cpu_count=physical,
        cpu_topology_source=topology.source,
    )


def configure_torch_threads(policy: ResourcePolicy) -> ResourcePolicy:
    """Configura threads antes da primeira inferência."""
    try:
        import torch
    except ImportError:
        return policy

    with contextlib.suppress(RuntimeError):
        torch.set_num_threads(policy.cpu_threads)
    with contextlib.suppress(RuntimeError):
        torch.set_num_interop_threads(policy.cpu_interop_threads)
    return policy
