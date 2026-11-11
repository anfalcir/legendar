"""Verifica links relativos da documentação em Markdown.

Uso:
    python scripts/check_doc_links.py [raiz]

O verificador ignora links externos (http/https/mailto), âncoras puras e
arquivos dentro de diretórios ignorados (ambiente virtual, caches e binários).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

#: Diretórios que nunca fazem parte da documentação versionada.
IGNORED_DIRECTORIES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".cache",
    ".pytest_cache",
    ".ruff_cache",
    "ffmpeg",
    "node_modules",
}

#: Links Markdown com destino entre parênteses.
_LINK = re.compile(r"\[[^\]]*\]\((?P<target>[^)\s]+)(?:\s+\"[^\"]*\")?\)")


def markdown_files(root: Path) -> list[Path]:
    """Lista os arquivos Markdown versionados sob ``root``."""
    files: list[Path] = []
    for path in sorted(root.rglob("*.md")):
        parts = set(path.relative_to(root).parts)
        if parts & IGNORED_DIRECTORIES:
            continue
        files.append(path)
    return files


def check_file(path: Path, root: Path) -> list[str]:
    """Devolve os problemas encontrados em um arquivo Markdown."""
    problems: list[str] = []
    text = path.read_text(encoding="utf-8")
    for match in _LINK.finditer(text):
        target = match.group("target").strip()
        if not target or target.startswith(("#", "http://", "https://", "mailto:")):
            continue
        relative = target.split("#", 1)[0]
        if not relative:
            continue
        candidate = (path.parent / relative).resolve()
        if not candidate.exists():
            source = path.relative_to(root)
            problems.append(f"{source}: link quebrado -> {target}")
    return problems


def check_repository(root: Path) -> list[str]:
    """Verifica todos os arquivos Markdown do repositório."""
    problems: list[str] = []
    for path in markdown_files(root):
        problems.extend(check_file(path, root))
    return problems


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    root = Path(arguments[0]).expanduser().resolve() if arguments else Path.cwd()
    problems = check_repository(root)
    if problems:
        print("Links quebrados encontrados:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    files = markdown_files(root)
    print(
        f"Documentação verificada: {len(files)} arquivos Markdown sem links quebrados."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
