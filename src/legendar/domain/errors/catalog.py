"""Erros de domínio especializados, um por categoria do plano mestre."""

from __future__ import annotations

from legendar.domain.errors.base import DomainError, ErrorCategory


class InvalidInputError(DomainError):
    category = ErrorCategory.INVALID_INPUT


class UnsupportedMediaError(DomainError):
    category = ErrorCategory.UNSUPPORTED_MEDIA


class DownloadError(DomainError):
    category = ErrorCategory.DOWNLOAD_FAILED


class MediaToolError(DomainError):
    """Falha de FFmpeg/ffprobe (ferramenta ausente, código de saída != 0)."""

    category = ErrorCategory.FFMPEG_FAILED


class ModelError(DomainError):
    category = ErrorCategory.MODEL_FAILED


class UnsupportedLanguageError(DomainError):
    category = ErrorCategory.UNSUPPORTED_LANGUAGE


class AlignmentInsufficientError(DomainError):
    category = ErrorCategory.ALIGNMENT_INSUFFICIENT


class TranslationError(DomainError):
    category = ErrorCategory.TRANSLATION_FAILED


class SrtValidationError(DomainError):
    category = ErrorCategory.SRT_VALIDATION_FAILED


class PublicationError(DomainError):
    category = ErrorCategory.WRITE_FAILED


class JobCancelledError(DomainError):
    category = ErrorCategory.CANCELLED

    def __init__(self, message: str = "Trabalho cancelado pelo usuário.") -> None:
        super().__init__(message)


class InvalidTransitionError(DomainError):
    """Transição de estado inválida na máquina de estados do job."""

    category = ErrorCategory.UNEXPECTED
