"""Teste de fronteira: o domínio não pode conhecer UI, infraestrutura ou modelos.

Lemos os módulos via AST (sem importar), para garantir que a regra vale mesmo
para arquivos que falhariam ao importar sem as dependências pesadas instaladas.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "legendar"

FORBIDDEN_ANYWHERE = {"PySide6", "PyQt5", "PyQt6", "qtpy"}
FORBIDDEN_IN_DOMAIN = {
    "legendar.infrastructure",
    "legendar.presentation",
    "legendar.application",
}
FORBIDDEN_IN_APPLICATION = {"legendar.infrastructure", "legendar.presentation"}
FORBIDDEN_DEPENDENCIES = {
    "whisperx",
    "torch",
    "torchaudio",
    "whisper",
    "ffmpeg",
    "yt_dlp",
}


def _modules(layer: str) -> list[Path]:
    return sorted((SRC / layer).rglob("*.py"))


def _imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.add(node.module.split(".")[0])
    return names


def _violations(layer: str, forbidden: set[str]) -> list[str]:
    errors: list[str] = []
    for path in _modules(layer):
        for name in sorted(_imported_names(path) & forbidden):
            errors.append(f"{path.relative_to(SRC)} importa {name}")
    return errors


def test_domain_is_free_of_ui_infrastructure_and_models():
    assert (
        _violations(
            "domain", FORBIDDEN_ANYWHERE | FORBIDDEN_IN_DOMAIN | FORBIDDEN_DEPENDENCIES
        )
        == []
    )


def test_application_only_depends_on_domain_and_ports():
    assert (
        _violations("application", FORBIDDEN_ANYWHERE | FORBIDDEN_IN_APPLICATION) == []
    )


def test_infrastructure_and_presentation_do_not_depend_on_bootstrap_or_each_other():
    assert (
        _violations("infrastructure", {"legendar.presentation", "legendar.bootstrap"})
        == []
    )
    assert (
        _violations(
            "presentation",
            {
                "legendar.infrastructure",
                "legendar.bootstrap",
                *FORBIDDEN_DEPENDENCIES,
            },
        )
        == []
    )


def test_domain_has_no_io_side_effects_at_import_time():
    """Nenhum módulo de domínio deve abrir arquivos, rede ou processos ao importar."""
    forbidden_calls = {"open", "system", "popen", "run", "urlopen", "socket", "connect"}
    offenders: list[str] = []
    for path in _modules("domain"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if name in forbidden_calls:
                offenders.append(
                    f"{path.relative_to(SRC)}:{node.lineno} chama {name}()"
                )
    assert offenders == []


def test_ports_are_protocols_and_cover_the_pipeline():
    from legendar.application.ports import protocols

    expected = {
        "MediaDownloader",
        "MediaInspector",
        "AudioPreparer",
        "Transcriber",
        "Aligner",
        "Translator",
        "SrtSourceReader",
        "SubtitlePublisher",
        "PerformanceReporter",
    }
    for name in expected:
        port = getattr(protocols, name)
        assert getattr(port, "_is_protocol", False), f"{name} não é Protocol"


def test_translator_port_is_per_cue_and_language_explicit():
    import inspect

    from legendar.application.ports import protocols

    signature = inspect.signature(protocols.Translator.translate)
    parameters = list(signature.parameters.values())

    assert parameters[1].name == "units"
    assert parameters[1].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    keyword_only = {
        parameter.name
        for parameter in parameters[2:]
        if parameter.kind is inspect.Parameter.KEYWORD_ONLY
    }
    assert keyword_only == {
        "source_language",
        "target_language",
        "progress",
        "token",
    }


def test_translation_adapter_is_the_only_module_that_knows_transformers():
    """Só a infraestrutura de tradução importa ``transformers``/``sentencepiece``."""
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        relative = path.relative_to(SRC)
        if relative.parts[0] == "infrastructure" and "translation" in relative.parts:
            continue
        names = _imported_names(path)
        for name in sorted(names & {"transformers", "sentencepiece"}):
            offenders.append(f"{relative} importa {name}")
    assert offenders == []
