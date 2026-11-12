from legendar.infrastructure.resources.profile import (
    ResourceProfile,
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
