"""Serialização e validação do formato SRT.

O domínio não conhece SRT; este módulo concentra o formato. A validação faz
*round-trip*: serializa, re-parseia e compara tempos/texto, garantindo que o
arquivo publicado corresponde ao trilho em memória.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from legendar.domain.entities.subtitle import SubtitleTrack
from legendar.domain.errors.catalog import SrtValidationError
from legendar.domain.value_objects.time import TimeRange

_TS = re.compile(r"^(\d{2}):(\d{2}):(\d{2}),(\d{3})$")
_BLOCK = re.compile(
    r"(?P<index>\d+)\n(?P<start>\d{2}:\d{2}:\d{2},\d{3}) --> "
    r"(?P<end>\d{2}:\d{2}:\d{2},\d{3})\n(?P<text>.*?)(?:\n\n|\Z)",
    re.DOTALL,
)


def format_timestamp(seconds: float) -> str:
    """Formata segundos como ``HH:MM:SS,mmm``.

    O arredondamento é para baixo (truncamento) para nunca empurrar o início
    de uma cue sobre o fim da anterior.
    """
    if seconds < 0:
        raise SrtValidationError("Timestamp negativo não é válido em SRT.")
    total_ms = int(round(seconds * 1000))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def parse_timestamp(value: str) -> float:
    match = _TS.match(value.strip())
    if match is None:
        raise SrtValidationError(f"Timestamp SRT inválido: {value!r}")
    hours, minutes, secs, millis = (int(group) for group in match.groups())
    if minutes > 59 or secs > 59:
        raise SrtValidationError(f"Timestamp SRT fora de faixa: {value!r}")
    return hours * 3600 + minutes * 60 + secs + millis / 1000


@dataclass(frozen=True, slots=True)
class ParsedCue:
    index: int
    start: float
    end: float
    text: str

    @property
    def range(self) -> TimeRange:
        return TimeRange(self.start, self.end)


def format_srt(track: SubtitleTrack) -> str:
    """Serializa o trilho em SRT com ``\\n`` e linha final em branco."""
    if track.is_empty:
        raise SrtValidationError("Não é possível serializar um trilho vazio.")
    blocks: list[str] = []
    for cue in track.cues:
        text = cue.normalized_text
        if not text:
            raise SrtValidationError(f"Cue {cue.index} sem texto após normalização.")
        blocks.append(
            f"{cue.index}\n"
            f"{format_timestamp(cue.range.start)} --> {format_timestamp(cue.range.end)}\n"
            f"{text}\n"
        )
    return "\n".join(blocks)


def parse_srt(content: str) -> tuple[ParsedCue, ...]:
    """Lê SRT e devolve as cues; levanta ``SrtValidationError`` se malformado."""
    normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    if not normalized:
        raise SrtValidationError("Arquivo SRT vazio.")
    cues: list[ParsedCue] = []
    for match in _BLOCK.finditer(normalized + "\n\n"):
        cues.append(
            ParsedCue(
                index=int(match.group("index")),
                start=parse_timestamp(match.group("start")),
                end=parse_timestamp(match.group("end")),
                text=match.group("text").strip(),
            )
        )
    if not cues:
        raise SrtValidationError("Nenhuma cue SRT reconhecida.")
    return tuple(cues)


def validate_roundtrip(track: SubtitleTrack, content: str) -> None:
    """Garante que o SRT serializado reabre com os mesmos índices e tempos."""
    parsed = parse_srt(content)
    if len(parsed) != len(track.cues):
        raise SrtValidationError(
            f"SRT com {len(parsed)} cues, esperado {len(track.cues)}."
        )
    for expected, actual in zip(track.cues, parsed, strict=True):
        if expected.index != actual.index:
            raise SrtValidationError(
                f"Índice divergente no SRT: {actual.index} != {expected.index}."
            )
        if format_timestamp(actual.start) != format_timestamp(expected.range.start):
            raise SrtValidationError(f"Início divergente na cue {expected.index}.")
        if format_timestamp(actual.end) != format_timestamp(expected.range.end):
            raise SrtValidationError(f"Fim divergente na cue {expected.index}.")
        if expected.normalized_text != " ".join(actual.text.split()):
            raise SrtValidationError(f"Texto divergente na cue {expected.index}.")
