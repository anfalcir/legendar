"""Testes de contexto de job e cancelamento cooperativo thread-safe."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from legendar.application.job.context import CancellationTokenImpl
from legendar.domain.errors.catalog import JobCancelledError


def test_concurrent_cancel_requests_are_idempotent() -> None:
    token = CancellationTokenImpl()
    requests = 12
    barrier = Barrier(requests)

    def cancel(index: int) -> bool:
        barrier.wait(timeout=5)
        return token.cancel(f"solicitação-{index}")

    with ThreadPoolExecutor(max_workers=requests) as executor:
        results = list(executor.map(cancel, range(requests)))

    assert sum(results) == 1
    assert token.is_cancelled
    assert token.reason is not None
    assert token.reason.startswith("solicitação-")
    assert token.cancel("pedido posterior") is False

    with pytest.raises(JobCancelledError, match="solicitação-"):
        token.raise_if_cancelled()


def test_cancel_without_reason_uses_safe_default_message() -> None:
    token = CancellationTokenImpl()

    assert token.cancel() is True
    with pytest.raises(JobCancelledError, match="Trabalho cancelado pelo usuário"):
        token.raise_if_cancelled()
