"""Round-trip tests for the model.yaml schema."""

from __future__ import annotations

from pathlib import Path

import pytest

from dt_ai_sdk import ModelConfig, ModelConfigError, load_model_config


MINIMAL_YAML = """\
id: sample-model
name: Sample Model
description: A tiny sample used for schema testing
task: general
"""


FULL_YAML = """\
id: sample-model
name: Sample Model
description: A tiny sample used for schema testing
task: mask
type: split
version: "2.1"
arch: sam2
tiling: true
dep_group: core

model_card:
  license: Apache-2.0
  paper: https://example.com/paper

attributes:
  input_size: 1024
  prev_mask_size: 256

cpu_only:
  - migraphx

coreml_format: mlprogram

repo:
  submodule: vendor/sample
  setup: pip install -e vendor/sample

checkpoints:
  - url: https://example.com/model.pt
    path: temp/sample-model/model.pt

convert:
  - script: scripts/export_encoder.py
    args:
      checkpoint: "{root}/temp/{model_dir}/model.pt"
      output_dir: "{output}"

demo:
  image_args:
    default:
      strength: "1.0"
"""


def _write_model(tmp_path: Path, content: str) -> tuple[Path, Path]:
    model_dir = tmp_path / "models" / "sample-model"
    model_dir.mkdir(parents=True)
    (model_dir / "model.yaml").write_text(content)
    return model_dir, tmp_path


def test_minimal_config(tmp_path: Path) -> None:
    model_dir, root = _write_model(tmp_path, MINIMAL_YAML)
    cfg = load_model_config(model_dir, root)

    assert cfg.id == "sample-model"
    assert cfg.name == "Sample Model"
    assert cfg.task == "general"
    # defaults
    assert cfg.type == "single"
    assert cfg.version == "1.0"
    assert cfg.arch == "generic"
    assert cfg.tiling is False
    assert cfg.dep_group == "core"
    assert cfg.checkpoints == []
    assert cfg.convert == []
    assert cfg.repo is None


def test_full_config(tmp_path: Path) -> None:
    model_dir, root = _write_model(tmp_path, FULL_YAML)
    cfg = load_model_config(model_dir, root)

    assert cfg.type == "split"
    assert cfg.version == "2.1"
    assert cfg.arch == "sam2"
    assert cfg.tiling is True
    assert cfg.attributes == {"input_size": 1024, "prev_mask_size": 256}
    assert cfg.cpu_only == ["migraphx"]
    assert cfg.coreml_format == "mlprogram"

    assert cfg.repo is not None
    assert cfg.repo.submodule == "vendor/sample"
    assert cfg.repo.setup == "pip install -e vendor/sample"

    assert len(cfg.checkpoints) == 1
    assert cfg.checkpoints[0].url == "https://example.com/model.pt"

    assert len(cfg.convert) == 1
    assert cfg.convert[0].script == "scripts/export_encoder.py"


def test_paths_derive_from_root(tmp_path: Path) -> None:
    model_dir, root = _write_model(tmp_path, MINIMAL_YAML)
    cfg = load_model_config(model_dir, root)

    assert cfg.output_dir == root / "output" / "sample-model"
    assert cfg.temp_dir == root / "temp" / "sample-model"
    assert cfg.model_dir == model_dir
    assert cfg.repo_dir is None


def test_repo_dir_when_repo_declared(tmp_path: Path) -> None:
    model_dir, root = _write_model(tmp_path, FULL_YAML)
    cfg = load_model_config(model_dir, root)
    assert cfg.repo_dir == root / "vendor" / "sample"


def test_resolve_template(tmp_path: Path) -> None:
    model_dir, root = _write_model(tmp_path, MINIMAL_YAML)
    cfg = load_model_config(model_dir, root)

    resolved = cfg.resolve_template("{root}/foo/{output}/bar")
    assert str(root) in resolved
    assert str(cfg.output_dir) in resolved
    assert resolved.startswith(f"{root}/foo/")
    assert resolved.endswith("/bar")


def test_skip_marker_detected(tmp_path: Path) -> None:
    model_dir, root = _write_model(tmp_path, MINIMAL_YAML)
    (model_dir / ".skip").touch()
    cfg = load_model_config(model_dir, root)
    assert cfg.skip is True


def test_missing_required_field_raises(tmp_path: Path) -> None:
    """The error must name the file and every missing field.

    A repo can hold dozens of models, so a bare KeyError leaves you
    grepping for which one is broken.
    """
    model_dir = tmp_path / "models" / "bad"
    model_dir.mkdir(parents=True)
    (model_dir / "model.yaml").write_text("name: only\n")
    with pytest.raises(ModelConfigError) as exc:
        load_model_config(model_dir, tmp_path)

    message = str(exc.value)
    assert "model.yaml" in message
    for field in ("id", "description", "task"):
        assert field in message


def test_invalid_yaml_names_the_file(tmp_path: Path) -> None:
    model_dir = tmp_path / "models" / "bad"
    model_dir.mkdir(parents=True)
    (model_dir / "model.yaml").write_text("id: a\n  bad indent: [\n")
    with pytest.raises(ModelConfigError) as exc:
        load_model_config(model_dir, tmp_path)
    assert "invalid YAML" in str(exc.value)


def test_empty_yaml_is_reported(tmp_path: Path) -> None:
    model_dir = tmp_path / "models" / "bad"
    model_dir.mkdir(parents=True)
    (model_dir / "model.yaml").write_text("")
    with pytest.raises(ModelConfigError) as exc:
        load_model_config(model_dir, tmp_path)
    assert "empty" in str(exc.value)


def test_missing_file_is_reported(tmp_path: Path) -> None:
    model_dir = tmp_path / "models" / "gone"
    model_dir.mkdir(parents=True)
    with pytest.raises(ModelConfigError) as exc:
        load_model_config(model_dir, tmp_path)
    assert "model.yaml" in str(exc.value)
