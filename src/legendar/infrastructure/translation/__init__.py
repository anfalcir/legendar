"""Adaptadores de tradução automática."""

from legendar.infrastructure.translation.gemini import GeminiTranslator
from legendar.infrastructure.translation.translategemma import (
    TranslateGemmaTranslator,
)

__all__ = ["GeminiTranslator", "TranslateGemmaTranslator"]
