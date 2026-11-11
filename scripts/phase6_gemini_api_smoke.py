#!/usr/bin/env python3
"""Smoke opt-in da Gemini Developer API; nunca imprime conteúdo nem credenciais."""

from __future__ import annotations

import sys

from legendar.application.pipeline.translation import TranslationUnit
from legendar.domain.value_objects.language import Language
from legendar.infrastructure.translation.gemini import GeminiTranslator


class NullProgress:
    def report(self, _fraction: float, _message: str = "") -> None:
        pass


def main() -> int:
    translator = GeminiTranslator.from_environment()
    if not translator.is_configured:
        print("GEMINI_API_KEY ausente; smoke real não executado.", file=sys.stderr)
        return 2
    try:
        result = translator.translate(
            (
                TranslationUnit(index=1, text="The old city was quiet."),
                TranslationUnit(index=2, text="Then the bells began to ring."),
            ),
            source_language=Language.ENGLISH,
            target_language=Language.PORTUGUESE,
            progress=NullProgress(),
        )
    except Exception as exc:
        print(
            f"Gemini API smoke falhou: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 1
    if len(result.texts) != 2 or any(not text.strip() for text in result.texts):
        print("Gemini API smoke violou a correspondência 1:1.", file=sys.stderr)
        return 1
    counters = translator.performance_snapshot()["counters"]
    print(
        "Gemini API smoke aprovado: 2 cues, "
        f"modelo={translator.model}, métricas={counters}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
