"""Serialização e validação do formato SRT.

O domínio não conhece SRT; este módulo concentra o formato. A validação faz
*round-trip*: serializa, re-parseia e compara tempos/texto, garantindo que o
arquivo publicado corresponde ao trilho em memória.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from legendar.domain.entities.subtitle import SubtitleCue, SubtitleTrack
from legendar.domain.errors.catalog import SrtValidationError
from legendar.domain.value_objects.language import Language
from legendar.domain.value_objects.text_layout import (
    DEFAULT_MAX_CHARS_PER_LINE,
    DEFAULT_MAX_LINES,
)
from legendar.domain.value_objects.time import TimeRange

_TS = re.compile(r"^(\d{2}):(\d{2}):(\d{2}),(\d{3})$")
_BLOCK = re.compile(
    r"(?P<index>\d+)\n(?P<start>\d{2}:\d{2}:\d{2},\d{3}) --> "
    r"(?P<end>\d{2}:\d{2}:\d{2},\d{3})\n(?P<text>.*?)(?:\n\n|\Z)",
    re.DOTALL,
)


def format_timestamp(seconds: float) -> str:
    """Formata segundos como ``HH:MM:SS,mmm``.

    O timestamp é arredondado ao milissegundo mais próximo; a validação do trilho
    garante que os intervalos quantizados continuem positivos e ordenados.
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


def format_srt(
    track: SubtitleTrack,
    *,
    max_chars_per_line: int = DEFAULT_MAX_CHARS_PER_LINE,
    max_lines: int = DEFAULT_MAX_LINES,
) -> str:
    """Serializa o trilho em SRT com ``\\n`` e linha final em branco.

    Cada cue é gravada em até ``max_lines`` linhas de ``max_chars_per_line``
    caracteres, sem descartar palavras.
    """
    if track.is_empty:
        raise SrtValidationError("Não é possível serializar um trilho vazio.")
    blocks: list[str] = []
    for cue in track.cues:
        text = cue.normalized_text
        if not text:
            raise SrtValidationError(f"Cue {cue.index} sem texto após normalização.")
        lines = cue.lines(
            max_chars_per_line=max_chars_per_line,
            max_lines=max_lines,
        )
        body = "\n".join(lines)
        blocks.append(
            f"{cue.index}\n"
            f"{format_timestamp(cue.range.start)} --> {format_timestamp(cue.range.end)}\n"
            f"{body}\n"
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


def read_srt_file(
    path: str | Path,
    *,
    language: Language,
) -> tuple[SubtitleTrack, str]:
    """Carrega um SRT de origem sem executar qualquer etapa de mídia.

    UTF-8/UTF-8-BOM é preferido. SRTs antigos em Windows-1252 também são
    aceitos; não há decode com substituição silenciosa. A numeração de entrada
    é normalizada para 1..N, enquanto ordem, texto e timestamps são preservados.
    """
    if not isinstance(language, Language):
        raise SrtValidationError("Informe o idioma conhecido do SRT de origem.")

    source = Path(path).expanduser()
    if not source.is_file():
        raise SrtValidationError(f"Arquivo SRT não encontrado: {source.name}.")
    try:
        raw = source.read_bytes()
    except OSError as exc:
        raise SrtValidationError(
            f"Não foi possível ler o arquivo SRT: {source.name}."
        ) from exc
    if not raw:
        raise SrtValidationError("Arquivo SRT vazio.")

    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            content = raw.decode("utf-16")
            encoding = "utf-16"
        except UnicodeDecodeError as exc:
            raise SrtValidationError("O SRT possui codificação UTF-16 inválida.") from exc
    else:
        try:
            content = raw.decode("utf-8-sig")
            encoding = "utf-8"
        except UnicodeDecodeError:
            try:
                content = raw.decode("cp1252")
                encoding = "cp1252"
            except UnicodeDecodeError as exc:
                raise SrtValidationError(
                    "A codificação do SRT não é UTF-8 nem Windows-1252."
                ) from exc

    parsed = parse_srt(content)
    cues = tuple(
        SubtitleCue(
            index=index,
            text=item.text,
            range=item.range,
            language=language,
        )
        for index, item in enumerate(parsed, start=1)
    )
    return SubtitleTrack(language=language, cues=cues), encoding


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
