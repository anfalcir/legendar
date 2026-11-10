from __future__ import annotations

from pathlib import Path

import pytest

from legendar.infrastructure.speech.model_cache import ModelCache


def test_path_is_stable_and_inside_root(tmp_path: Path) -> None:
    cache = ModelCache(tmp_path)

    assert cache.path_for("tiny") == (tmp_path / "tiny").resolve()
    assert cache.path_for(" large-v3 ") == (tmp_path / "large-v3").resolve()


@pytest.mark.parametrize("name", ["", "  ", "../fora", "a/b", ".", ".."])
def test_rejects_unsafe_model_names(tmp_path: Path, name: str) -> None:
    with pytest.raises(ValueError):
        ModelCache(tmp_path).path_for(name)


def test_describe_reports_missing_model_without_creating_it(tmp_path: Path) -> None:
    cache = ModelCache(tmp_path)

    (model,) = cache.describe(("tiny",))

    assert model.exists is False
    assert model.size_bytes == 0
    assert not (tmp_path / "tiny").exists()


def test_describe_measures_existing_model_tree(tmp_path: Path) -> None:
    model_dir = tmp_path / "tiny"
    model_dir.mkdir()
    (model_dir / "model.bin").write_bytes(b"x" * 10)
    (model_dir / "config.json").write_bytes(b"y" * 5)

    (model,) = ModelCache(tmp_path).describe(("tiny",))

    assert model.exists is True
    assert model.size_bytes == 15


def test_describe_without_names_lists_current_directories(tmp_path: Path) -> None:
    (tmp_path / "tiny").mkdir()
    (tmp_path / "base").mkdir()
    (tmp_path / "arquivo.txt").write_text("ignorado", encoding="utf-8")

    names = [model.name for model in ModelCache(tmp_path).describe()]

    assert names == ["base", "tiny"]


def test_ensure_root_preserves_existing_content(tmp_path: Path) -> None:
    root = tmp_path / "cache"
    root.mkdir()
    (root / "tiny").mkdir()
    (root / "tiny" / "model.bin").write_bytes(b"dados")

    returned = ModelCache(root).ensure_root()

    assert returned == root
    assert (root / "tiny" / "model.bin").read_bytes() == b"dados"


def test_cache_has_no_delete_operation() -> None:
    """A política é explícita: o job nunca apaga o cache de modelos."""
    assert not hasattr(ModelCache, "clear")
    assert not hasattr(ModelCache, "remove")
    assert not hasattr(ModelCache, "delete")
