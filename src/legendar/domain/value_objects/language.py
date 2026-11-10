"""Idiomas suportados como origem ou destino, com normalização de rótulos."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from legendar.domain.errors.base import DomainError


class LanguageError(DomainError):
    """Idioma inválido ou não suportado pelo produto."""


_ALIASES = {
    "pt": "pt",
    "pt-br": "pt",
    "pt_br": "pt",
    "ptbr": "pt",
    "portuguese": "pt",
    "português": "pt",
    "portugues": "pt",
    "en": "en",
    "en-us": "en",
    "en_us": "en",
    "english": "en",
    "inglês": "en",
    "ingles": "en",
}


class Language(str, Enum):
    """Códigos ISO 639-1 usados internamente (Whisper usa ``pt``/``en``)."""

    PORTUGUESE = "pt"
    ENGLISH = "en"

    @property
    def label_pt(self) -> str:
        return {"pt": "Português (BR)", "en": "Inglês"}[self.value]

    @classmethod
    def parse(cls, value: str | Language | None) -> Language | None:
        """Normaliza um rótulo para ``Language``; ``None`` permanece ``None``.

        ``None``/vazio significa "detecção automática". Rótulos desconhecidos
        levantam ``LanguageError`` em vez de adivinhar silenciosamente.
        """
        if value is None:
            return None
        if isinstance(value, cls):
            return value
        normalized = str(value).strip().lower().replace(" ", "")
        if normalized in {"", "auto", "automatic", "detect"}:
            return None
        code = _ALIASES.get(normalized)
        if code is None:
            raise LanguageError(f"Idioma não suportado: {value!r}")
        return cls(code)


@dataclass(frozen=True, slots=True)
class OutputLanguage:
    """Idioma final suportado apenas EN ou PT-BR (sem autodetecção)."""

    value: Language

    def __post_init__(self) -> None:
        if not isinstance(self.value, Language):
            raise LanguageError("Idioma final deve ser uma instância de Language")

    def __str__(self) -> str:
        return self.value.value
