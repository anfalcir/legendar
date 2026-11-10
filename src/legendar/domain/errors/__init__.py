from legendar.domain.errors.base import DomainError, ErrorCategory
from legendar.domain.errors.catalog import (
    AlignmentInsufficientError,
    DownloadError,
    InvalidInputError,
    InvalidTransitionError,
    JobCancelledError,
    MediaToolError,
    ModelError,
    PublicationError,
    SrtValidationError,
    TranslationError,
    UnsupportedLanguageError,
    UnsupportedMediaError,
)

__all__ = [
    "AlignmentInsufficientError",
    "DomainError",
    "DownloadError",
    "ErrorCategory",
    "InvalidInputError",
    "InvalidTransitionError",
    "JobCancelledError",
    "MediaToolError",
    "ModelError",
    "PublicationError",
    "SrtValidationError",
    "TranslationError",
    "UnsupportedLanguageError",
    "UnsupportedMediaError",
]
