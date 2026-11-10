"""Legendar — pipeline de transcrição, alinhamento e legendas SRT.

O pacote é organizado em camadas cujo acoplamento depende de uma única direção:

- ``domain``: regras puras e invariantes, sem Qt, FFmpeg, rede ou I/O.
- ``application``: orquestração do job, portas e pipeline, dependendo só do domínio.
- ``infrastructure``: adaptadores concretos (mídia, modelos, filesystem, settings).
- ``presentation``: GUI PySide6 e view model sem dependência de infraestrutura.
- ``bootstrap``: composição explícita das dependências.

Não há superfície pública adicional; o código interno deve ser importado por módulo.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
