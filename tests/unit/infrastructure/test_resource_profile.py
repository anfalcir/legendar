import sys
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


def test_physical_cpu_count_handles_unavailable_count(monkeypatch) -> None:
    monkeypatch.setattr(resource_profile.os, "cpu_count", lambda: None)

    assert resource_profile._physical_cpu_count() is None


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
