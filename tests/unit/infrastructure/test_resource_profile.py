import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import legendar.infrastructure.resources.profile as resource_profile
from legendar.infrastructure.resources.profile import (
    ResourcePolicy,
    ResourceProfile,
    configure_torch_threads,
    resolve_resource_policy,
)


def test_low_memory_profile_limits_threads_and_eviction(monkeypatch) -> None:
    monkeypatch.setenv("LEGENDAR_RESOURCE_PROFILE", "low-memory")
    monkeypatch.delenv("LEGENDAR_CPU_THREADS", raising=False)
    monkeypatch.delenv("LEGENDAR_CPU_INTEROP_THREADS", raising=False)

    policy = resolve_resource_policy()

    assert policy.profile is ResourceProfile.LOW_MEMORY
    assert policy.retain_models is False
    assert 1 <= policy.cpu_threads <= 4
    assert policy.cpu_interop_threads == 1


def test_explicit_thread_overrides_are_independent(monkeypatch) -> None:
    monkeypatch.setenv("LEGENDAR_RESOURCE_PROFILE", "balanced")
    monkeypatch.setenv("LEGENDAR_CPU_THREADS", "3")
    monkeypatch.setenv("LEGENDAR_CPU_INTEROP_THREADS", "2")

    policy = resolve_resource_policy()

    assert policy.cpu_threads == 3
    assert policy.cpu_interop_threads == 2


def test_performance_profile_retains_models(monkeypatch) -> None:
    monkeypatch.setenv("LEGENDAR_RESOURCE_PROFILE", "performance")
    monkeypatch.delenv("LEGENDAR_CPU_THREADS", raising=False)
    monkeypatch.delenv("LEGENDAR_CPU_INTEROP_THREADS", raising=False)

    policy = resolve_resource_policy()

    assert policy.profile is ResourceProfile.PERFORMANCE
    assert policy.retain_models is True


def test_cpu_topology_falls_back_without_assuming_smt_ratio(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(resource_profile.os, "cpu_count", lambda: 4)
    monkeypatch.setattr(
        resource_profile.os, "sched_getaffinity", lambda _pid: set(), raising=False
    )
    monkeypatch.setattr(resource_profile, "_cgroup_cpu_quota", lambda _root: None)
    monkeypatch.setattr(resource_profile, "_read_text", lambda _path: None)

    topology = resource_profile._cpu_topology(
        sysfs_root=tmp_path / "missing-sysfs",
        cgroup_root=tmp_path / "missing-cgroup",
    )

    assert topology.logical_count == 4
    assert topology.physical_count == 4
    assert "logical-count-fallback" in topology.source


def _write_fake_cpu_topology(root: Path, *, logical: int, physical: int) -> None:
    for cpu in range(logical):
        topology = root / f"cpu{cpu}" / "topology"
        topology.mkdir(parents=True)
        (topology / "physical_package_id").write_text("0", encoding="ascii")
        (topology / "core_id").write_text(str(cpu % physical), encoding="ascii")


def test_detects_four_physical_and_four_logical_cpus(tmp_path: Path) -> None:
    sysfs = tmp_path / "sys"
    _write_fake_cpu_topology(sysfs, logical=4, physical=4)

    topology = resource_profile._cpu_topology(
        sysfs_root=sysfs,
        cgroup_root=tmp_path / "missing-cgroup",
        affinity={0, 1, 2, 3},
        logical_count=4,
    )

    assert topology.logical_count == 4
    assert topology.physical_count == 4
    assert "linux-sysfs-package-core" in topology.source


def test_detects_four_physical_and_eight_logical_cpus(tmp_path: Path) -> None:
    sysfs = tmp_path / "sys"
    _write_fake_cpu_topology(sysfs, logical=8, physical=4)

    topology = resource_profile._cpu_topology(
        sysfs_root=sysfs,
        cgroup_root=tmp_path / "missing-cgroup",
        affinity=set(range(8)),
        logical_count=8,
    )

    assert topology.logical_count == 8
    assert topology.physical_count == 4


def test_cpu_topology_respects_process_affinity(tmp_path: Path) -> None:
    sysfs = tmp_path / "sys"
    _write_fake_cpu_topology(sysfs, logical=8, physical=4)

    topology = resource_profile._cpu_topology(
        sysfs_root=sysfs,
        cgroup_root=tmp_path / "missing-cgroup",
        affinity={0, 4},
        logical_count=8,
    )

    assert topology.logical_count == 2
    assert topology.physical_count == 1


def test_cpu_topology_respects_cgroup_v2_cpu_quota(tmp_path: Path) -> None:
    sysfs = tmp_path / "sys"
    cgroup = tmp_path / "cgroup"
    _write_fake_cpu_topology(sysfs, logical=8, physical=4)
    cgroup.mkdir()
    (cgroup / "cpu.max").write_text("200000 100000", encoding="ascii")

    topology = resource_profile._cpu_topology(
        sysfs_root=sysfs,
        cgroup_root=cgroup,
        affinity=set(range(8)),
        logical_count=8,
    )

    assert topology.logical_count == 2
    assert topology.physical_count == 2
    assert "cgroup-quota" in topology.source


def test_cpu_topology_respects_cgroup_cpuset(tmp_path: Path) -> None:
    sysfs = tmp_path / "sys"
    cgroup = tmp_path / "cgroup"
    _write_fake_cpu_topology(sysfs, logical=8, physical=4)
    cgroup.mkdir()
    (cgroup / "cpuset.cpus.effective").write_text("0-3", encoding="ascii")

    topology = resource_profile._cpu_topology(
        sysfs_root=sysfs,
        cgroup_root=cgroup,
        affinity=set(range(8)),
        logical_count=8,
    )

    assert topology.logical_count == 4
    assert topology.physical_count == 4
    assert "cgroup-cpuset" in topology.source


def test_low_memory_policy_uses_four_physical_cores_on_four_logical_cpu_host(
    monkeypatch,
) -> None:
    monkeypatch.setenv("LEGENDAR_RESOURCE_PROFILE", "low-memory")
    monkeypatch.delenv("LEGENDAR_CPU_THREADS", raising=False)
    monkeypatch.delenv("LEGENDAR_CPU_INTEROP_THREADS", raising=False)
    monkeypatch.setattr(
        resource_profile,
        "_cpu_topology",
        lambda: resource_profile.CpuTopology(
            logical_count=4,
            physical_count=4,
            source="linux-sysfs-package-core+process-affinity",
        ),
    )

    policy = resolve_resource_policy()

    assert policy.cpu_threads == 4
    assert policy.cpu_interop_threads == 1
    assert policy.logical_cpu_count == 4
    assert policy.physical_cpu_count == 4
    assert "linux-sysfs-package-core" in policy.cpu_topology_source


def test_total_memory_uses_posix_sysconf(monkeypatch) -> None:
    monkeypatch.setattr(resource_profile.os, "name", "posix")
    values = {"SC_PHYS_PAGES": 4096, "SC_PAGE_SIZE": 4096}
    monkeypatch.setattr(
        resource_profile.os, "sysconf", lambda key: values[key], raising=False
    )

    assert resource_profile._total_memory_bytes() == 4096 * 4096


def test_total_memory_falls_back_when_sysconf_fails(monkeypatch) -> None:
    monkeypatch.setattr(resource_profile.os, "name", "posix")

    def unavailable(_key: str) -> int:
        raise OSError("sysconf unavailable")

    monkeypatch.setattr(resource_profile.os, "sysconf", unavailable, raising=False)

    assert resource_profile._total_memory_bytes() is None


def test_non_posix_memory_detection_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(resource_profile.os, "name", "nt")

    assert resource_profile._total_memory_bytes() is None


def test_auto_profile_uses_balanced_for_sufficient_memory(monkeypatch) -> None:
    monkeypatch.setenv("LEGENDAR_RESOURCE_PROFILE", "auto")
    monkeypatch.setattr(resource_profile, "_total_memory_bytes", lambda: 16 * 1024**3)

    assert resource_profile.detect_resource_profile() is ResourceProfile.BALANCED


@pytest.mark.parametrize("value", ["not-an-integer", "0"])
def test_thread_overrides_reject_invalid_values(monkeypatch, value: str) -> None:
    monkeypatch.setenv("LEGENDAR_RESOURCE_PROFILE", "balanced")
    monkeypatch.setenv("LEGENDAR_CPU_THREADS", value)

    with pytest.raises(ValueError, match="deve ser inteiro positivo"):
        resolve_resource_policy()


def test_configure_torch_threads_applies_policy(monkeypatch) -> None:
    calls: list[tuple[str, int]] = []
    fake_torch = SimpleNamespace(
        set_num_threads=lambda value: calls.append(("threads", value)),
        set_num_interop_threads=lambda value: calls.append(("interop", value)),
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    policy = ResourcePolicy(ResourceProfile.BALANCED, True, 3, 2)

    assert configure_torch_threads(policy) is policy
    assert calls == [("threads", 3), ("interop", 2)]


def test_configure_torch_threads_ignores_runtime_lock(monkeypatch) -> None:
    def locked(_value: int) -> None:
        raise RuntimeError("torch threads already initialized")

    monkeypatch.setitem(
        sys.modules,
        "torch",
        SimpleNamespace(
            set_num_threads=locked,
            set_num_interop_threads=locked,
        ),
    )
    policy = ResourcePolicy(ResourceProfile.BALANCED, True, 3, 2)

    assert configure_torch_threads(policy) is policy


def test_configure_torch_threads_is_optional_without_torch(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "torch", None)
    policy = ResourcePolicy(ResourceProfile.BALANCED, True, 3, 2)

    assert configure_torch_threads(policy) is policy
