"""Tests for repo-wide model discovery."""

from __future__ import annotations

from pathlib import Path

from dt_ai_sdk import discover_models


MODEL_YAML = """\
id: {id}
name: {id}
description: fixture
task: general
"""


def _make(root: Path, mid: str) -> None:
    d = root / "models" / mid
    d.mkdir(parents=True)
    (d / "model.yaml").write_text(MODEL_YAML.format(id=mid))


def test_discover_finds_all_models(tmp_path: Path) -> None:
    _make(tmp_path, "alpha")
    _make(tmp_path, "beta")
    _make(tmp_path, "gamma")

    configs = discover_models(tmp_path)
    assert [c.id for c in configs] == ["alpha", "beta", "gamma"]


def test_discover_skips_dirs_without_yaml(tmp_path: Path) -> None:
    _make(tmp_path, "alpha")
    (tmp_path / "models" / "not-a-model").mkdir()

    configs = discover_models(tmp_path)
    assert [c.id for c in configs] == ["alpha"]


def test_discover_skips_files_in_models_dir(tmp_path: Path) -> None:
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "README.md").write_text("hello")
    _make(tmp_path, "alpha")

    configs = discover_models(tmp_path)
    assert [c.id for c in configs] == ["alpha"]
