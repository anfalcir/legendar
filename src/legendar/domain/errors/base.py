"""Hierarquia de erros do domínio.

Cada erro carrega uma ``category`` estável (ver ``ErrorCategory``) para que a
camada de apresentação possa traduzir falhas em mensagens claras sem depender
de strings técnicas do adaptador. A ``stage`` é preenchida pela orquestração
quando o erro cruza uma etapa do pipeline.
"""

from __future__ import annotations

from enum import Enum


class ErrorCategory(str, Enum):
    """Categorias mínimas descritas no plano mestre (seção 8.3)."""

    INVALID_INPUT = "invalid_input"
    UNSUPPORTED_MEDIA = "unsupported_media"
    DOWNLOAD_FAILED = "download_failed"
    FFMPEG_FAILED = "ffmpeg_failed"
    MODEL_FAILED = "model_failed"
    UNSUPPORTED_LANGUAGE = "unsupported_language"
    ALIGNMENT_INSUFFICIENT = "alignment_insufficient"
    TRANSLATION_FAILED = "translation_failed"
    SRT_VALIDATION_FAILED = "srt_validation_failed"
    WRITE_FAILED = "write_failed"
    CANCELLED = "cancelled"
    UNEXPECTED = "unexpected"


class DomainError(Exception):
    """Erro de domínio com categoria estável e mensagem em português.

    Subclasses sobrescrevem ``category``. ``technical_detail`` permanece opcional
    e nunca deve conter segredos ou caminhos sensíveis em logs de alto nível.
    """

    category: ErrorCategory = ErrorCategory.UNEXPECTED

    def __init__(
        self,
        message: str,
        *,
        technical_detail: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.technical_detail = technical_detail

    def with_detail(self, technical_detail: str) -> DomainError:
        """Retorna uma nova instância equivalente com detalhe técnico."""
        return type(self)(self.message, technical_detail=technical_detail)

    def __str__(self) -> str:
        return self.message
