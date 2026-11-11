"""Quebra de texto de legenda em linhas legíveis, sem perder conteúdo.

A regra é pura, determinística e independente de formato: o SRT apenas a usa
para gravar no máximo duas linhas por cue. Nenhuma palavra é descartada. Quando
o texto excede a capacidade declarada, o excedente permanece na última linha —
o validador sinaliza o excesso, em vez de truncar texto silenciosamente.
"""

from __future__ import annotations

from legendar.domain.errors.catalog import InvalidInputError

#: Limite editorial padrão: duas linhas de 42 caracteres por cue.
DEFAULT_MAX_CHARS_PER_LINE = 42
DEFAULT_MAX_LINES = 2


def wrap_lines(
    text: str,
    *,
    max_chars_per_line: int = DEFAULT_MAX_CHARS_PER_LINE,
    max_lines: int = DEFAULT_MAX_LINES,
) -> tuple[str, ...]:
    """Divide ``text`` em até ``max_lines`` linhas equilibradas.

    A largura efetiva é a menor que ainda cabe em ``max_lines`` linhas, o que
    evita uma linha longa seguida de uma palavra órfã. Palavras nunca são
    cortadas: uma palavra maior que ``max_chars_per_line`` ocupa a linha sozinha.
    """
    if max_chars_per_line < 1:
        raise InvalidInputError("A largura de linha da legenda deve ser positiva.")
    if max_lines < 1:
        raise InvalidInputError("A legenda precisa de ao menos uma linha.")

    words = text.split()
    if not words:
        return ()

    greedy = _greedy_lines(words, max_chars_per_line)
    if len(greedy) > max_lines:
        merged = _merge_overflow(greedy, max_lines)
        return tuple(" ".join(line) for line in merged)

    width = _balanced_width(
        [len(word) for word in words], len(greedy), max_chars_per_line
    )
    lines = _greedy_lines(words, width)
    if len(lines) > len(greedy):
        # O balanceamento nunca deve aumentar a contagem de linhas; se aumentar,
        # o resultado guloso original continua sendo a resposta segura.
        lines = greedy
    return tuple(" ".join(line) for line in lines)


def _greedy_lines(words: list[str], width: int) -> list[list[str]]:
    lines: list[list[str]] = []
    current: list[str] = []
    length = 0
    for word in words:
        if not current:
            current = [word]
            length = len(word)
            continue
        if length + 1 + len(word) <= width:
            current.append(word)
            length += 1 + len(word)
            continue
        lines.append(current)
        current = [word]
        length = len(word)
    if current:
        lines.append(current)
    return lines


def _balanced_width(lengths: list[int], target_lines: int, upper: int) -> int:
    """Menor largura que ainda produz no máximo ``target_lines`` linhas."""
    lower = max(max(lengths), 1)
    high = max(upper, lower)
    best = high
    while lower <= high:
        middle = (lower + high) // 2
        if _line_count(lengths, middle) <= target_lines:
            best = middle
            high = middle - 1
        else:
            lower = middle + 1
    return best


def _line_count(lengths: list[int], width: int) -> int:
    count = 1
    length = 0
    for word_length in lengths:
        if length == 0:
            length = word_length
            continue
        if length + 1 + word_length <= width:
            length += 1 + word_length
            continue
        count += 1
        length = word_length
    return count


def _merge_overflow(lines: list[list[str]], max_lines: int) -> list[list[str]]:
    head = lines[: max_lines - 1]
    tail = [word for line in lines[max_lines - 1 :] for word in line]
    return [*head, tail]
