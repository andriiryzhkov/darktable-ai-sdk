"""Tests for the .dtmodel package format."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from dt_ai_sdk import load_model_config, package_model


MODEL_YAML = """\
id: pkg-test
name: Package Test
description: Fixture used to exercise the .dtmodel packager
task: general
"""


@pytest.fixture
def prepared_output(tmp_path: Path):
    """Set up a model with a populated output/ directory ready to zip."""
    model_dir = tmp_path / "models" / "pkg-test"
    model_dir.mkdir(parents=True)
    (model_dir / "model.yaml").write_text(MODEL_YAML)

    output = tmp_path / "output" / "pkg-test"
    output.mkdir(parents=True)
    (output / "config.json").write_text('{"id":"pkg-test"}\n')
    (output / "model.onnx").write_bytes(b"onnx-bytes")
    (output / "sub").mkdir()
    (output / "sub" / "extra.bin").write_bytes(b"aux")

    return load_model_config(model_dir, tmp_path)


def test_package_creates_zip(prepared_output) -> None:
    archive = package_model(prepared_output)
    assert archive.exists()
    assert archive.name == "pkg-test.dtmodel"
    assert zipfile.is_zipfile(archive)


def test_package_contains_all_files_under_model_id_prefix(prepared_output) -> None:
    archive = package_model(prepared_output)
    with zipfile.ZipFile(archive) as zf:
        names = sorted(zf.namelist())
    assert names == [
        "pkg-test/config.json",
        "pkg-test/model.onnx",
        "pkg-test/sub/extra.bin",
    ]


def test_package_deterministic_ordering(prepared_output) -> None:
    """Same inputs → same file-entry order (sorted). Guards against future refactors
    breaking reproducibility of the output archive."""
    archive1 = package_model(prepared_output)
    with zipfile.ZipFile(archive1) as zf:
        names1 = zf.namelist()

    # rebuild
    archive1.unlink()
    archive2 = package_model(prepared_output)
    with zipfile.ZipFile(archive2) as zf:
        names2 = zf.namelist()

    assert names1 == names2


def test_package_missing_output_raises(tmp_path: Path) -> None:
    model_dir = tmp_path / "models" / "pkg-test"
    model_dir.mkdir(parents=True)
    (model_dir / "model.yaml").write_text(MODEL_YAML)
    cfg = load_model_config(model_dir, tmp_path)
    (tmp_path / "output").mkdir()

    with pytest.raises(FileNotFoundError):
        package_model(cfg)
