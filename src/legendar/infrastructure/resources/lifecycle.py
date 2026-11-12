"""Liberação segura de memória de modelos locais."""

from __future__ import annotations

import gc
from typing import Any


def release_model_resources(model: Any) -> None:
    """Libera referências de modelo e caches de backend sem tocar no cache em disco."""

    del model
    gc.collect()
    try:
        import torch
    except ImportError:
        return
    try:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except (AttributeError, RuntimeError):
        pass
    try:
        mps = getattr(torch, "mps", None)
        empty_cache = getattr(mps, "empty_cache", None)
        if callable(empty_cache):
            empty_cache()
    except (AttributeError, RuntimeError):
        pass
