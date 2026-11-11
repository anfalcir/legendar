"""Gate editorial determinístico do trilho final antes da publicação.

Falhas estruturais ou perda de conteúdo bloqueiam a publicação. Riscos
editoriais preservam o SRT, mas classificam o resultado como revisão necessária.
Nenhuma regra remove, reescreve ou corrige texto automaticamente.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum

from legendar.application.pipeline.segmentation import SegmentationPolicy
from legendar.domain.entities.subtitle import SubtitleTrack
from legendar.domain.errors.catalog import SrtValidationError

MEDIA_DURATION_TOLERANCE_SECONDS = 0.5
_LIST_LIMIT = 8
_REPEATED_WORD_LIMIT = 4
_CONNECTORS = {
    "a",
    "ao",
    "aos",
    "as",
    "com",
    "da",
    "das",
    "de",
    "do",
    "dos",
    "e",
    "em",
    "na",
    "nas",
    "no",
    "nos",
    "ou",
    "para",
    "pela",
    "pelas",
    "pelo",
    "pelos",
    "por",
    "que",
    "se",
    "sem",
    "sob",
    "sobre",
    "the",
    "an",
    "and",
    "at",
    "by",
    "for",
    "from",
    "in",
    "into",
    "of",
    "on",
    "or",
    "to",
    "with",
}
_NUMBER_RE = re.compile(r"(?<!\w)\d+(?:[.,:/-]\d+)*(?!\w)")
_ACRONYM_RE = re.compile(r"\b[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,}\b")
_WORD_RE = re.compile(r"\b[^\W\d_][\w'’-]*\b", re.UNICODE)


class QualityStatus(str, Enum):
    APPROVED = "APPROVED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class QualityIssue:
    code: str
    severity: str
    message: str
    cue_indices: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class TrackValidationReport:
    """Diagnóstico estruturado e compatível com os avisos legados."""

    warnings: tuple[str, ...] = field(default_factory=tuple)
    short_cues: tuple[int, ...] = ()
    long_cues: tuple[int, ...] = ()
    overflow_cues: tuple[int, ...] = ()
    wide_cues: tuple[int, ...] = ()
    duplicate_cues: tuple[int, ...] = ()
    suspicious_cues: tuple[int, ...] = ()
    fragmented_cues: tuple[int, ...] = ()
    flicker_cues: tuple[int, ...] = ()
    issues: tuple[QualityIssue, ...] = ()
    status: QualityStatus = QualityStatus.APPROVED
    cue_count: int = 0
    max_cps: float = 0.0
    p95_cps: float = 0.0
    blocked_reasons: tuple[str, ...] = ()

    @property
    def is_clean(self) -> bool:
        return self.status is QualityStatus.APPROVED

    @property
    def review_required(self) -> bool:
        return self.status is QualityStatus.REVIEW_REQUIRED

    @property
    def is_blocked(self) -> bool:
        return self.status is QualityStatus.BLOCKED

    @property
    def review_cue_indices(self) -> tuple[int, ...]:
        return tuple(
            sorted({index for issue in self.issues for index in issue.cue_indices})
        )

    @property
    def approved_cue_count(self) -> int:
        return max(0, self.cue_count - len(self.review_cue_indices))

    @property
    def summary(self) -> str:
        if self.status is QualityStatus.APPROVED:
            return f"Qualidade editorial aprovada: {self.cue_count} cues."
        if self.status is QualityStatus.BLOCKED:
            return "Publicação bloqueada: " + "; ".join(self.blocked_reasons)
        details = " | ".join(issue.message for issue in self.issues[:3])
        suffix = " | ..." if len(self.issues) > 3 else ""
        return (
            f"Revisão editorial necessária: {self.approved_cue_count} cue(s) sem "
            f"alerta; {len(self.review_cue_indices)} cue(s) para revisar. "
            f"{details}{suffix}"
        )


def validate_track(
    track: SubtitleTrack,
    *,
    policy: SegmentationPolicy | None = None,
    media_duration: float | None = None,
    content_loss_count: int = 0,
    source_track: SubtitleTrack | None = None,
) -> TrackValidationReport:
    """Valida integridade, estrutura e riscos editoriais sem alterar o texto."""
    policy = policy or SegmentationPolicy()
    if track.is_empty:
        raise SrtValidationError("Trilho de legendas vazio.")
    if content_loss_count < 0:
        raise ValueError("content_loss_count não pode ser negativo.")

    short: list[int] = []
    long: list[int] = []
    overflow: list[int] = []
    wide: list[int] = []
    duplicates: list[int] = []
    suspicious: list[int] = []
    fragmented: list[int] = []
    cps_values: list[float] = []
    flicker = _find_flicker_cues(track)
    issues: list[QualityIssue] = []
    warnings: list[str] = []

    for position, cue in enumerate(track.cues):
        text = cue.normalized_text
        if not text:
            raise SrtValidationError(f"Cue {cue.index} sem texto.")
        if (
            media_duration is not None
            and cue.range.end > media_duration + MEDIA_DURATION_TOLERANCE_SECONDS
        ):
            raise SrtValidationError(
                f"Cue {cue.index} termina em {_seconds(cue.range.end)} s, depois do "
                f"fim da mídia ({_seconds(media_duration)} s)."
            )
        duration = cue.range.duration
        cps = len(text) / duration
        cps_values.append(cps)
        if duration < policy.min_cue_duration:
            short.append(cue.index)
        if duration > policy.max_cue_duration:
            long.append(cue.index)
        if duration < policy.reading_time(text):
            overflow.append(cue.index)
        if len(text) > policy.max_chars_per_cue:
            wide.append(cue.index)

        if _has_suspicious_text(text):
            suspicious.append(cue.index)
        if position:
            previous = track.cues[position - 1]
            if (
                text.casefold() == previous.normalized_text.casefold()
                and cue.range.start - previous.range.end <= 1.0
            ):
                duplicates.append(cue.index)
            first = text[:1]
            if (
                previous.normalized_text.split()[-1].casefold().strip(".,;:!?")
                in _CONNECTORS
                and first.islower()
            ):
                fragmented.append(cue.index)

    _append_issue(
        issues,
        warnings,
        "SHORT_CUE",
        short,
        f"Abaixo da duração mínima de {_seconds(policy.min_cue_duration)} s",
    )
    _append_issue(
        issues,
        warnings,
        "LONG_CUE",
        long,
        f"Acima da duração máxima de {_seconds(policy.max_cue_duration)} s",
    )
    _append_issue(
        issues,
        warnings,
        "READING_SPEED",
        overflow,
        f"Acima da velocidade de leitura de {policy.chars_per_second:g} CPS",
    )
    _append_issue(
        issues,
        warnings,
        "CUE_WIDTH",
        wide,
        f"Acima de {policy.max_chars_per_cue} caracteres por cue",
    )
    _append_issue(
        issues,
        warnings,
        "REPEATED_CUE",
        duplicates,
        "Texto idêntico em cues consecutivas próximas; confirmar repetição",
    )
    _append_issue(
        issues,
        warnings,
        "SUSPICIOUS_TEXT",
        suspicious,
        "Caracteres de controle, substituição ou repetição anômala",
    )
    _append_issue(
        issues,
        warnings,
        "SYNTACTIC_FRAGMENT",
        fragmented,
        "Cue anterior termina em conectivo/preposição; revisar a quebra",
    )
    _append_issue(
        issues,
        warnings,
        "FLICKER",
        flicker,
        "Sequência de cues muito curtas e rápidas; revisar possível flicker",
    )

    if source_track is not None:
        missing = _missing_invariants(source_track, track)
        if missing:
            indexes = tuple(cue.index for cue in track.cues)
            issues.append(
                QualityIssue(
                    "TRANSLATION_INVARIANT",
                    "warning",
                    "A tradução pode ter alterado números ou siglas: "
                    + ", ".join(missing),
                    indexes,
                )
            )
            warnings.append(
                "Possível alteração de números/siglas na tradução: "
                + ", ".join(missing[:_LIST_LIMIT])
                + "."
            )

    blocked_reasons = (
        (f"{content_loss_count} segmento(s) de origem sem conteúdo publicado",)
        if content_loss_count
        else ()
    )
    if blocked_reasons:
        issues.append(QualityIssue("CONTENT_LOSS", "critical", blocked_reasons[0], ()))
        warnings.append("Publicação bloqueada: " + blocked_reasons[0] + ".")

    status = (
        QualityStatus.BLOCKED
        if blocked_reasons
        else QualityStatus.REVIEW_REQUIRED
        if issues
        else QualityStatus.APPROVED
    )
    ordered_cps = sorted(cps_values)
    p95_index = max(0, (95 * len(ordered_cps) + 99) // 100 - 1)
    return TrackValidationReport(
        warnings=tuple(warnings),
        short_cues=tuple(short),
        long_cues=tuple(long),
        overflow_cues=tuple(overflow),
        wide_cues=tuple(wide),
        duplicate_cues=tuple(duplicates),
        suspicious_cues=tuple(suspicious),
        fragmented_cues=tuple(fragmented),
        flicker_cues=flicker,
        issues=tuple(issues),
        status=status,
        cue_count=len(track.cues),
        max_cps=max(cps_values, default=0.0),
        p95_cps=ordered_cps[p95_index] if ordered_cps else 0.0,
        blocked_reasons=blocked_reasons,
    )



def _find_flicker_cues(track: SubtitleTrack) -> tuple[int, ...]:
    """Marca sequências de três ou mais flashes curtos em intervalos próximos."""
    marked: list[int] = []
    run: list[int] = []
    previous_end: float | None = None
    for cue in track.cues:
        is_fast = cue.range.duration <= 0.6
        is_contiguous = (
            previous_end is None or cue.range.start - previous_end <= 0.15
        )
        if is_fast and is_contiguous:
            run.append(cue.index)
        else:
            if len(run) >= 3:
                marked.extend(run)
            run = [cue.index] if is_fast else []
        previous_end = cue.range.end
    if len(run) >= 3:
        marked.extend(run)
    return tuple(marked)


def _append_issue(
    issues: list[QualityIssue],
    warnings: list[str],
    code: str,
    indexes: list[int],
    description: str,
) -> None:
    if not indexes:
        return
    issues.append(QualityIssue(
        code, "warning", f"{description}: {_cue_list(indexes)}", tuple(indexes)
    ))
    warnings.append(
        f"{len(indexes)} {_noun(len(indexes))} "
        f"{description[0].lower() + description[1:]}: {_cue_list(indexes)}."
    )


def _has_suspicious_text(text: str) -> bool:
    if "\ufffd" in text:
        return True
    for char in text:
        category = unicodedata.category(char)
        if category in {"Cc", "Cs"}:
            return True
        if char in {"\u202a", "\u202b", "\u202d", "\u202e", "\u2066", "\u2067", "\u2068", "\u2069"}:
            return True
    words = [word.casefold() for word in _WORD_RE.findall(text)]
    run = 1
    for previous, current in zip(words, words[1:], strict=False):
        run = run + 1 if current == previous else 1
        if run >= _REPEATED_WORD_LIMIT:
            return True
    return False


def _missing_invariants(source: SubtitleTrack, target: SubtitleTrack) -> list[str]:
    source_text = " ".join(cue.normalized_text for cue in source.cues)
    target_text = " ".join(cue.normalized_text for cue in target.cues)
    missing_numbers = sorted(
        set(_NUMBER_RE.findall(source_text)) - set(_NUMBER_RE.findall(target_text))
    )
    missing_acronyms = sorted(
        set(_ACRONYM_RE.findall(source_text)) - set(_ACRONYM_RE.findall(target_text))
    )
    return [
        *(f"número {item}" for item in missing_numbers),
        *(f"sigla {item}" for item in missing_acronyms),
    ]


def _cue_list(indexes: list[int]) -> str:
    shown = ", ".join(str(index) for index in indexes[:_LIST_LIMIT])
    if len(indexes) > _LIST_LIMIT:
        shown += ", …"
    return shown


def _seconds(value: float) -> str:
    return f"{value:.1f}".replace(".", ",")


def _noun(count: int) -> str:
    return "legenda" if count == 1 else "legendas"
